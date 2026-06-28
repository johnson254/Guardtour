from django.utils import timezone
from django.db.models import F as models_F
from datetime import timedelta
from rest_framework import serializers

from api.services.gps import _haversine, correct_gps_trail
from api.services.drift import validate_timestamp_drift, validate_sequence_id
from api.services.dwell import check_dwell_time
from api.services.scoring import verify_zone_scan, calculate_scan_validity
from api.services.anomalies import _sensor_confirms_presence, _sensor_mismatch


def authenticate_device(device_id, password):
    from api.models import Device
    if not device_id or not password:
        raise serializers.ValidationError({"detail": "Device authentication failed."})
    device = Device.objects.filter(device_id=device_id).first()
    if not device or device.password != password:
        raise serializers.ValidationError({"detail": "Device authentication failed."})
    if not device.is_active:
        raise serializers.ValidationError({"detail": "Device is decommissioned. Contact dispatcher."})
    return device


def check_cooldown(device, nfc_value, now):
    from api.models import ScanRecord
    cooldown = now - timedelta(seconds=30)
    if nfc_value:
        duplicate = ScanRecord.objects.filter(
            device=device,
            nfc_value=nfc_value,
            timestamp__gte=cooldown
        ).exists()
        if duplicate:
            raise serializers.ValidationError({"detail": "Cooldown active. Please wait 30s between scans."})
    else:
        duplicate = ScanRecord.objects.filter(
            device=device,
            timestamp__gte=cooldown
        ).exists()
        if duplicate:
            raise serializers.ValidationError({"detail": "Cooldown active. Please wait 30s between scans."})


def parse_nfc_payload(raw):
    if not raw or not isinstance(raw, dict):
        return 'tag', None, None

    ndef_records = raw.get('ndef_records') or []

    for rec in ndef_records:
        payload_json = rec.get('payload_json')
        if isinstance(payload_json, dict) and payload_json.get('type') == 'peer_handshake':
            peer_device_id = payload_json.get('device_id')
            nonce = payload_json.get('nonce')
            if peer_device_id and nonce:
                return 'peer', peer_device_id, {
                    'peer_device_id': peer_device_id,
                    'nonce': nonce,
                    'timestamp': payload_json.get('timestamp'),
                    'own_uid': raw.get('uid'),
                }

    for rec in ndef_records:
        payload_text = rec.get('payload_text')
        if payload_text:
            return 'tag', payload_text.strip(), None

    uid = raw.get('uid')
    if uid:
        return 'tag', uid.replace(':', '').lower(), None

    return 'tag', None, None


def validate_peer_exchange(device, peer_data):
    from api.models import Device, ScanRecord
    if not peer_data:
        raise serializers.ValidationError({"detail": "Peer exchange missing handshake data."})

    peer_device_id = peer_data.get('peer_device_id')
    nonce = peer_data.get('nonce')
    peer_ts = peer_data.get('timestamp')

    if not peer_device_id or not nonce:
        raise serializers.ValidationError({"detail": "Peer exchange incomplete."})

    peer_device = Device.objects.filter(device_id=peer_device_id).first()
    if not peer_device:
        raise serializers.ValidationError({"detail": f"Peer device {peer_device_id} not found."})

    if peer_ts:
        window_start = timezone.datetime.fromtimestamp(peer_ts / 1000, tz=timezone.get_current_timezone()) - timedelta(seconds=30)
        window_end = window_start + timedelta(seconds=60)
        reciprocal = ScanRecord.objects.filter(
            device=peer_device,
            nfc_value=device.device_id,
            scan_type='peer',
            timestamp__gte=window_start,
            timestamp__lte=window_end
        ).exists()
        if not reciprocal:
            raise serializers.ValidationError({"detail": "No reciprocal peer scan found within the time window."})

    return peer_device


def resolve_asset(nfc_value, scan_type='tag', organization=None):
    from api.models import Checkpoint, PatrolRoute
    from django.db.models import Q
    checkpoint = None
    route = None
    if not nfc_value:
        return checkpoint, route
    if scan_type == 'peer':
        return None, None
    qs = Checkpoint.objects.filter(nfc_tag=nfc_value)
    if organization:
        qs = qs.filter(
            Q(organization=organization) | Q(route__organization=organization) | Q(organization__isnull=True, route__isnull=True)
        ).distinct()
    checkpoint = qs.order_by('id').first()
    if checkpoint:
        route = checkpoint.route
    return checkpoint, route


def resolve_assignment(device, route_id, route):
    from api.models import ShiftAssignment
    if not device:
        return None
    assignments = ShiftAssignment.objects.filter(device=device, is_active=True)
    if route_id:
        return assignments.filter(route_id=route_id).first()
    if route:
        assignment = assignments.filter(route=route).first()
        if assignment:
            return assignment
    return assignments.order_by('-assigned_at').first()


def is_on_time(checkpoint, now):
    if not checkpoint or not checkpoint.planned_time:
        return True
    planned_dt = timezone.make_aware(
        timezone.datetime.combine(now.date(), checkpoint.planned_time),
        timezone=now.tzinfo
    )
    tol = checkpoint.time_tolerance
    return (planned_dt - timedelta(minutes=tol) <= now <= planned_dt + timedelta(minutes=tol))


def check_sequence(route, checkpoint, assignment, now):
    from api.models import ScanRecord
    if not route or not checkpoint or not assignment:
        return False
    if not route.enforce_order:
        return False
    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return False

    try:
        current_idx = next(i for i, cp in enumerate(cps) if cp.id == checkpoint.id)
    except StopIteration:
        return False

    scan_filter = {
        'route': route,
        'timestamp__gte': assignment.assigned_at,
        'checkpoint__isnull': False,
    }
    if assignment.guard_supervisor:
        scan_filter['guard_supervisor'] = assignment.guard_supervisor
    else:
        scan_filter['device'] = assignment.device

    hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())

    if not hit_ids:
        return current_idx != 0

    last_idx = -1
    for i, cp in enumerate(cps):
        if cp.id in hit_ids:
            last_idx = max(last_idx, i)

    expected_idx = last_idx + 1
    return current_idx != expected_idx


def trigger_emergency(assignment, checkpoint, device, now):
    from api.models import OperatorAlert
    route = assignment.route
    org = (route.organization if route else None) or device.organization

    assignment.status = 'emergency_active'
    assignment.save(update_fields=['status'])

    OperatorAlert.objects.create(
        organization=org,
        operator=assignment.guard_supervisor,
        title=f"EMERGENCY: {checkpoint.name}",
        message=f"Emergency checkpoint {checkpoint.name} triggered on route {route.name if route else 'Unknown'}",
        priority='urgent',
        play_sound=True,
        vibrate=True,
    )


def route_gap_analysis(route, assignment):
    from api.models import ScanRecord
    if not route or not assignment:
        return []

    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return []

    scan_filter = {
        'route': route,
        'timestamp__gte': assignment.assigned_at,
        'checkpoint__isnull': False,
    }
    if assignment.guard_supervisor:
        scan_filter['guard_supervisor'] = assignment.guard_supervisor
    else:
        scan_filter['device'] = assignment.device

    hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())

    missed = []
    for cp in cps:
        if cp.id not in hit_ids:
            missed.append({
                'id': cp.id,
                'name': cp.name,
                'order': cp.order,
                'checkpoint_type': cp.checkpoint_type,
            })
    return missed


def get_mission_status(assignment):
    from django.utils import timezone as dj_timezone
    from api.models import ScanRecord
    now = dj_timezone.now()
    route = assignment.route
    if not route:
        return None

    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return None

    if assignment.guard_supervisor:
        hit_ids = set(ScanRecord.objects.filter(
            guard_supervisor=assignment.guard_supervisor,
            route=route,
            timestamp__gte=assignment.assigned_at,
            checkpoint__isnull=False,
        ).values_list('checkpoint_id', flat=True).distinct())
    else:
        hit_ids = set(ScanRecord.objects.filter(
            route=route,
            timestamp__gte=assignment.assigned_at,
            checkpoint__isnull=False,
        ).values_list('checkpoint_id', flat=True).distinct())

    next_cp = None
    for cp in cps:
        if cp.id not in hit_ids:
            next_cp = cp
            break

    if not next_cp:
        return {'completed': True, 'hit_count': len(hit_ids), 'total': len(cps)}

    last_hit = None
    if assignment.guard_supervisor:
        last_hit = ScanRecord.objects.filter(
            guard_supervisor=assignment.guard_supervisor,
            route=route, checkpoint=next_cp,
            timestamp__gte=assignment.assigned_at,
        ).order_by('-timestamp').values_list('timestamp', flat=True).first()

    time_remaining_seconds = None
    is_window_missed = False
    if next_cp.planned_time and assignment.scheduled_date:
        planned_dt = dj_timezone.make_aware(
            dj_timezone.datetime.combine(assignment.scheduled_date, next_cp.planned_time),
            timezone=now.tzinfo,
        )
        time_remaining_seconds = int((planned_dt - now).total_seconds())
        deadline = planned_dt + timedelta(minutes=int(next_cp.time_tolerance or 15) + int(next_cp.dwell_time or 0))
        is_window_missed = now > deadline

    dwell_remaining_seconds = None
    is_present = False
    if last_hit and (next_cp.dwell_time or 0) > 0:
        end = last_hit + timedelta(minutes=next_cp.dwell_time)
        dwell_remaining_seconds = max(0, int((end - now).total_seconds()))
        is_present = now <= end

    return {
        'completed': False,
        'hit_count': len(hit_ids),
        'total': len(cps),
        'next_checkpoint': {
            'id': next_cp.id,
            'name': next_cp.name,
            'checkpoint_type': next_cp.checkpoint_type.upper() if next_cp.checkpoint_type else 'POI',
            'planned_time': next_cp.planned_time.strftime('%H:%M:%S') if next_cp.planned_time else None,
            'time_remaining_seconds': time_remaining_seconds,
            'is_window_missed': is_window_missed,
            'dwell_time_minutes': next_cp.dwell_time or 0,
            'dwell_remaining_seconds': dwell_remaining_seconds,
            'is_present': is_present,
            'lat': next_cp.lat,
            'lng': next_cp.lng,
            'radius': next_cp.radius,
        }
    }


def transfer_shift(assignment, new_guard, new_device=None, requested_by=None):
    from django.utils import timezone as dj_timezone
    now = dj_timezone.now()

    old_guard = assignment.guard_supervisor
    route = assignment.route
    shift_type = assignment.shift_type
    scheduled_date = assignment.scheduled_date

    assignment.is_active = False
    assignment.is_completed = False
    assignment.status = 'handover'
    assignment.ended_at = now
    assignment.save(update_fields=['is_active', 'status', 'ended_at'])

    if old_guard:
        has_other = ShiftAssignment.objects.filter(
            guard_supervisor=old_guard, is_active=True
        ).exclude(pk=assignment.pk).exists()
        if not has_other:
            old_guard.is_on_shift = False
            old_guard.save(update_fields=['is_on_shift'])

    device = new_device or assignment.device

    new_assignment = ShiftAssignment.objects.create(
        dispatcher=requested_by or assignment.dispatcher,
        guard_supervisor=new_guard,
        device=device,
        route=route,
        scheduled_date=scheduled_date,
        scheduled_start=assignment.scheduled_start,
        scheduled_end=assignment.scheduled_end,
        shift_type=shift_type,
        is_active=True,
        is_completed=False,
        status='active',
    )

    if new_guard:
        new_guard.is_on_shift = True
        new_guard.last_shift_change = now
        new_guard.save(update_fields=['is_on_shift', 'last_shift_change'])

    return new_assignment


def process_scan(device_id, password, route_id, nfc_value, peer_key, now, raw_nfc=None, scan_lat=None, scan_lng=None, client_timestamp=None, sequence_id=None, sensor_context=None):
    from api.models import Device, ScanRecord, ShiftAssignment, GuardSupervisor, DeviceSession, MissionStateLog

    device = authenticate_device(device_id, password)

    server_now = now
    time_drift, is_suspicious = validate_timestamp_drift(client_timestamp, server_now)

    sequence_valid = validate_sequence_id(device, sequence_id)

    scan_type = 'tag'
    peer_data = None
    extracted_id = nfc_value
    if raw_nfc:
        scan_type, extracted_id, peer_data = parse_nfc_payload(raw_nfc)

    effective_id = extracted_id or nfc_value

    check_cooldown(device, effective_id, now)

    assignment = resolve_assignment(device, route_id, None)
    checkpoint = None
    route = None

    if scan_type == 'peer':
        if assignment and assignment.route:
            route = assignment.route
            checkpoint = route.checkpoints.filter(checkpoint_type='peer').first()
        if peer_data:
            validate_peer_exchange(device, peer_data)
    else:
        if assignment and assignment.route:
            route = assignment.route
            checkpoint = route.checkpoints.filter(nfc_tag=effective_id).first()
        if not checkpoint:
            checkpoint, route = resolve_asset(effective_id, 'tag', organization=device.organization)
            if route:
                assignment = resolve_assignment(device, route_id, route)

    guard_sup = None
    if assignment:
        guard_sup = assignment.guard_supervisor
        if guard_sup:
            GuardSupervisor.objects.filter(id=guard_sup.id).update(
                last_scan=now,
                nfc_tags_scanned=models_F('nfc_tags_scanned') + 1
            )

    out_of_sequence = False
    if checkpoint and route and not route.is_emergency:
        out_of_sequence = check_sequence(route, checkpoint, assignment, now)

    emergency_triggered = False
    if checkpoint and route and route.is_emergency and assignment:
        trigger_emergency(assignment, checkpoint, device, now)
        emergency_triggered = True
        out_of_sequence = False

    insufficient_dwell, dwell_seconds = check_dwell_time(checkpoint, assignment, now)

    prev_scans = list(ScanRecord.objects.filter(device=device).order_by('-timestamp')[:1])

    is_last_checkpoint = False
    mission_completed = False
    if assignment and route and checkpoint:
        cps = list(route.checkpoints.all().order_by('order'))
        if cps and cps[-1].id == checkpoint.id:
            is_last_checkpoint = True
    zone_result = verify_zone_scan(
        device=device,
        checkpoint=checkpoint,
        scan_lat=scan_lat,
        scan_lng=scan_lng,
        now=now,
        assignment=assignment,
        sensor_context=sensor_context,
        is_last_checkpoint=is_last_checkpoint,
        mission_completed=mission_completed,
    )

    val_score = zone_result['validity_score']
    val_reason = zone_result['verification_notes'] or 'zone_verification'

    if assignment and route and not emergency_triggered:
        cps = list(route.checkpoints.all().order_by('order'))
        if cps:
            scan_filter = {
                'route': route,
                'timestamp__gte': assignment.assigned_at,
                'checkpoint__isnull': False,
            }
            if assignment.guard_supervisor:
                scan_filter['guard_supervisor'] = assignment.guard_supervisor
            else:
                scan_filter['device'] = assignment.device
            hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())
            if checkpoint:
                hit_ids.add(checkpoint.id)
            if len(hit_ids) >= len(cps):
                assignment.is_completed = True
                assignment.is_active = False
                assignment.status = 'completed'
                assignment.mission_stage = 'completed'
                assignment.ended_at = now
                assignment.save(update_fields=['is_completed', 'is_active', 'status', 'mission_stage', 'ended_at'])
                mission_completed = True
                MissionStateLog.objects.create(
                    assignment=assignment,
                    from_stage='active',
                    to_stage='completed',
                    reason='all_checkpoints_scanned',
                    device=device,
                )

    if assignment and not emergency_triggered:
        if assignment.mission_stage == 'assigned':
            assignment.mission_stage = 'deployed'
            assignment.save(update_fields=['mission_stage'])
            MissionStateLog.objects.create(
                assignment=assignment,
                from_stage='assigned',
                to_stage='deployed',
                reason='first_heartbeat_after_assignment',
                device=device,
            )
        elif assignment.mission_stage == 'deployed' and not zone_result['dropped']:
            assignment.mission_stage = 'active'
            assignment.save(update_fields=['mission_stage'])
            MissionStateLog.objects.create(
                assignment=assignment,
                from_stage='deployed',
                to_stage='active',
                reason='first_successful_scan',
                device=device,
            )

    tts_message = None
    tts_voice = device.tts_voice or 'en-US'
    tts_rate = device.tts_rate
    tts_pitch = device.tts_pitch
    if checkpoint and checkpoint.next_announcement_text:
        tts_message = checkpoint.next_announcement_text
        if route:
            tts_voice = route.tts_voice or tts_voice
            tts_rate = route.tts_rate
            tts_pitch = route.tts_pitch
    elif route and route.readout_text and route.send_announcement:
        tts_message = route.readout_text
        tts_voice = route.tts_voice or tts_voice
        tts_rate = route.tts_rate
        tts_pitch = route.tts_pitch

    response = dict(
        guard_supervisor=guard_sup,
        device=device,
        checkpoint=checkpoint,
        route=route or (assignment.route if assignment else None),
        is_on_time=is_on_time(checkpoint, now),
        out_of_sequence=out_of_sequence,
        insufficient_dwell_time=insufficient_dwell,
        dwell_seconds=dwell_seconds,
        client_timestamp=client_timestamp,
        server_received_timestamp=server_now,
        time_drift_seconds=time_drift,
        time_drift_suspicious=is_suspicious,
        sequence_id=sequence_id,
        checkpoint_name=checkpoint.name if checkpoint else f"Unknown Tag: {nfc_value}",
        nfc_value=effective_id,
        raw_nfc=raw_nfc,
        scan_type=scan_type,
        validity_score=val_score,
        validity_reason=val_reason,
        verification_notes=zone_result['verification_notes'],
        dwell_valid=zone_result['dwell_valid'],
        anomaly_flags=zone_result['anomaly_flags'],
        sensor_aided=zone_result['sensor_aided'],
        sensor_context=sensor_context,
        _map_update=zone_result['map_update'],
        _tts_message=tts_message,
        _tts_voice=tts_voice,
        _tts_rate=tts_rate,
        _tts_pitch=tts_pitch,
        _play_sound=True,
        _vibrate=True,
    )
    if zone_result['dropped']:
        response['_dropped'] = True
    return response
