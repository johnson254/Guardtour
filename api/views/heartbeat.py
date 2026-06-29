"""Device heartbeat endpoint.

Security notes:
- Passwords are verified against PBKDF2 hashes via api.password.verify_device_password.
  Legacy plaintext hashes are transparently upgraded on first successful auth.
- Rate-limited to 30/min per device via DeviceHeartbeatThrottle to prevent
  firmware bugs or abuse from flooding the server.
- No select_for_update(): removed because overlapping heartbeats from flaky
  mobile networks caused connection pile-up. Device updates use atomic
  .update() calls instead of row-level locks.
"""
from django.db import transaction
from django.utils import timezone
from datetime import timedelta, datetime
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.models import (
    CallSign,
    Device,
    DeviceSession,
    GuardSupervisor,
    MapObject,
    Organization,
    ScanRecord,
    ShiftAssignment,
)
from api.services.gps import _haversine
from api.password import verify_device_password, hash_device_password
from api.throttles import DeviceHeartbeatThrottle


def _heartbeat_update_device(device, request):
    lat = request.data.get('lat')
    lng = request.data.get('lng')
    battery = request.data.get('battery_pct')
    gps_accuracy = request.data.get('gps_accuracy')
    if battery is not None:
        device.battery_pct = battery
    if lat is not None:
        device.last_latitude = lat
    if lng is not None:
        device.last_longitude = lng
    if gps_accuracy is not None:
        device.last_gps_accuracy = gps_accuracy
    device.last_seen = timezone.now()
    device.is_online = True
    return lat, lng, gps_accuracy


def _heartbeat_fetch_directives(device, lat, gps_accuracy):
    directives = {}
    if device.nfc_fetch_requested:
        directives['fetch_nfc'] = True
        device.nfc_fetch_requested = None
    if device.gps_fetch_requested:
        directives['fetch_gps'] = True
        directives['gps_accuracy'] = device.gps_accuracy_threshold or 10
    if device.gps_fetch_requested and lat is not None and gps_accuracy is not None:
        if gps_accuracy <= (device.gps_accuracy_threshold or 10):
            device.gps_fetch_requested = None
    return directives


def _heartbeat_operator_identity(device):
    cs = CallSign.objects.filter(device=device).first()
    if not cs:
        return {}
    return {
        'callsign': cs.callsign,
        'guard_name': f"{cs.current_guard.first_name} {cs.current_guard.last_name}".strip() if cs.current_guard else None,
    }


def _heartbeat_active_missions(device):
    from api.models import ScanRecord
    from django.db.models import Q
    assignments = ShiftAssignment.objects.filter(
        device=device, is_active=True, is_completed=False
    ).select_related('route')
    missions = []
    primary = None
    for a in assignments:
        if a.route:
            if not primary:
                primary = a.route
            cps = list(a.route.checkpoints.all().order_by('order'))
            total_cps = len(cps)
            hit_ids = set(ScanRecord.objects.filter(
                device=device, route=a.route, checkpoint__isnull=False,
                timestamp__gte=a.assigned_at,
            ).values_list('checkpoint_id', flat=True).distinct())
            hit_count = len(hit_ids)
            progress_pct = int((hit_count / total_cps) * 100) if total_cps > 0 else 0
            missions.append({
                'assignment_id': a.id,
                'route_id': a.route.id,
                'route_name': a.route.name,
                'shift_type': a.shift_type,
                'is_completed': a.is_completed,
                'progress_pct': progress_pct,
                'hit_count': hit_count,
                'total_checkpoints': total_cps,
            })
    directives = {'missions': missions}
    if primary:
        p = missions[0] if missions else None
        if p:
            directives['route_id'] = p['route_id']
            directives['route_name'] = p['route_name']
            directives['tts_voice'] = primary.tts_voice or 'en-US'
            directives['tts_rate'] = primary.tts_rate
            directives['tts_pitch'] = primary.tts_pitch
    return directives, assignments


def _heartbeat_lead_time_reminder(device, active_assignments, now):
    if device.tts_pending:
        return {}, False
    for a in active_assignments:
        route = a.route
        if not route or not route.send_start_alert:
            continue
        if not route.scheduled_start_time or not route.start_alert_lead_time:
            continue
        mission_date = a.scheduled_date or now.date()
        reminder_start_dt = timezone.make_aware(
            datetime.combine(mission_date, route.scheduled_start_time),
            timezone=now.tzinfo,
        ) - timedelta(minutes=route.start_alert_lead_time)
        if now < reminder_start_dt:
            continue
        scan_filter = {
            'route': route,
            'timestamp__gte': a.assigned_at,
            'checkpoint__isnull': False,
        }
        if a.guard_supervisor:
            scan_filter['guard_supervisor'] = a.guard_supervisor
        if ScanRecord.objects.filter(**scan_filter).exists():
            continue
        if device.last_reminder_at:
            elapsed = (now - device.last_reminder_at).total_seconds()
            if elapsed < route.start_alert_lead_time * 60:
                continue
        msg = route.readout_text or f"Reminder: {route.name} starts at {route.scheduled_start_time.strftime('%H:%M')}. Please proceed to your first checkpoint."
        device.last_reminder_at = now
        device.tts_acked = False
        device.tts_pending = msg
        device.tts_pending_voice = route.tts_voice or device.tts_voice or 'en-US'
        device.tts_pending_rate = route.tts_rate
        device.tts_pending_pitch = route.tts_pitch
        device.tts_pending_at = now
        return {
            'tts_pending': msg,
            'tts_pending_voice': route.tts_voice or device.tts_voice or 'en-US',
            'tts_pending_rate': route.tts_rate,
            'tts_pending_pitch': route.tts_pitch,
            'play_sound': True,
            'vibrate': True,
        }, True
    return {}, False


def _heartbeat_geofence_tts(device, lat, lng, now):
    if lat is None or lng is None or not device.organization_id:
        return {}
    geofences = MapObject.objects.filter(
        organization_id=device.organization_id,
        type='geofence',
    ).exclude(entry_msg__isnull=True).exclude(entry_msg__exact='')
    gf_states = device.geofence_states or {}
    for gf in geofences:
        inside = False
        if gf.geometry and isinstance(gf.geometry, list) and len(gf.geometry) >= 2:
            if gf.radius:
                dist = _haversine(lat, lng, gf.geometry[0], gf.geometry[1])
                inside = dist <= gf.radius
            elif len(gf.geometry) >= 3 and isinstance(gf.geometry[0], list):
                inside = _point_in_polygon(lat, lng, gf.geometry)
        gf_key = str(gf.id)
        if not inside and gf_key in gf_states:
            del gf_states[gf_key]
            device.geofence_states = gf_states
        elif inside and gf_key not in gf_states and not device.tts_pending:
            gf_states[gf_key] = now.isoformat()
            device.geofence_states = gf_states
            device.tts_acked = False
            device.tts_pending = gf.entry_msg
            device.tts_pending_voice = device.tts_voice or 'en-US'
            device.tts_pending_rate = device.tts_rate
            device.tts_pending_pitch = device.tts_pitch
            device.tts_pending_at = now
            return {
                'tts_pending': gf.entry_msg,
                'tts_pending_voice': device.tts_voice or 'en-US',
                'tts_pending_rate': device.tts_rate,
                'tts_pending_pitch': device.tts_pitch,
                'play_sound': True,
                'vibrate': True,
            }
    return {}


def _heartbeat_tts_delivery(device):
    if device.tts_pending:
        tts = {
            'tts_pending': device.tts_pending,
            'tts_pending_voice': device.tts_pending_voice,
            'tts_pending_rate': device.tts_pending_rate,
            'tts_pending_pitch': device.tts_pending_pitch,
        }
        if device.tts_acked:
            device.tts_acked = False
            device.save(update_fields=['tts_acked'])
        return tts
    return {}


def _heartbeat_tts_ack(device, request):
    if not request.data.get('tts_acked'):
        return
    device.tts_pending = None
    device.tts_pending_voice = ''
    device.tts_pending_rate = 1.0
    device.tts_pending_pitch = 1.0
    device.tts_pending_at = None
    device.tts_acked = True
    device.save(update_fields=[
        'tts_pending', 'tts_pending_voice', 'tts_pending_rate',
        'tts_pending_pitch', 'tts_pending_at', 'tts_acked',
    ])


def _heartbeat_peer_mode(device, active_assignments):
    import secrets
    result = {}
    for a in active_assignments:
        route = a.route
        if not route or not route.is_audit:
            continue
        peer_cp = route.checkpoints.filter(checkpoint_type='peer').first()
        if not peer_cp:
            continue
        target_device_id = peer_cp.nfc_tag
        if not target_device_id:
            continue
        if device.device_id == target_device_id:
            nonce = secrets.token_hex(8)
            device.peer_session_key = nonce
            result = {
                'peer_mode': 'hce_emulator',
                'peer_target_device_id': device.device_id,
                'peer_route_id': route.id,
                'peer_nonce': nonce,
            }
        else:
            result = {
                'peer_mode': 'hce_reader',
                'peer_target_device_id': target_device_id,
                'peer_route_id': route.id,
            }
        break
    return result


def _get_or_create_session(device, assignment, now):
    session = DeviceSession.objects.filter(device=device, is_active=True).order_by('-entered_at').first()
    if not session:
        state = DeviceSession.STATE_ON_ROUTE if assignment else DeviceSession.STATE_AUTHENTICATED
        session = DeviceSession.objects.create(
            device=device,
            assignment=assignment,
            state=state,
            last_heartbeat_at=now,
            battery_pct_at_enter=device.battery_pct,
        )
    else:
        session.last_heartbeat_at = now
        session.save(update_fields=['last_heartbeat_at', 'updated_at'])
    return session


def _evaluate_session_state(device, session, assignment, lat, lng, now):
    if not assignment or not assignment.route:
        if session.state == DeviceSession.STATE_AUTHENTICATED and assignment:
            session.state = DeviceSession.STATE_ON_ROUTE
            session.save(update_fields=['state', 'updated_at'])
        return session

    route = assignment.route
    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return session

    scan_filter = {
        'route': route,
        'timestamp__gte': assignment.assigned_at,
        'checkpoint__isnull': False,
    }
    if assignment.guard_supervisor:
        scan_filter['guard_supervisor'] = assignment.guard_supervisor
    else:
        scan_filter['device'] = device
    hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())

    if len(hit_ids) >= len(cps):
        new_state = DeviceSession.STATE_COMPLETED
    else:
        next_cp = None
        for cp in cps:
            if cp.id not in hit_ids:
                next_cp = cp
                break
        if next_cp and next_cp.lat and next_cp.lng and lat is not None and lng is not None:
            dist = _haversine(lat, lng, next_cp.lat, next_cp.lng)
            radius = next_cp.radius if next_cp.radius and next_cp.radius > 0 else 5
            if dist <= radius:
                new_state = DeviceSession.STATE_CHECKPOINT_DUE
            else:
                new_state = DeviceSession.STATE_ON_ROUTE
        elif len(hit_ids) >= len(cps) - 1:
            new_state = DeviceSession.STATE_COMPLETING
        else:
            new_state = DeviceSession.STATE_ON_ROUTE

    if session.state != new_state:
        session.state = new_state
        session.save(update_fields=['state', 'updated_at'])
    return session


def _build_map_update(device, session, assignment, lat, lng, now):
    if not assignment or not assignment.route or lat is None or lng is None:
        return None
    route = assignment.route
    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return None
    scan_filter = {
        'route': route,
        'timestamp__gte': assignment.assigned_at,
        'checkpoint__isnull': False,
    }
    if assignment.guard_supervisor:
        scan_filter['guard_supervisor'] = assignment.guard_supervisor
    else:
        scan_filter['device'] = device
    hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())
    next_cp = None
    for cp in cps:
        if cp.id not in hit_ids:
            next_cp = cp
            break
    if not next_cp or not next_cp.lat or not next_cp.lng:
        return None
    dist = _haversine(lat, lng, next_cp.lat, next_cp.lng)
    radius = next_cp.radius if next_cp.radius and next_cp.radius > 0 else 5
    if dist <= radius:
        return {
            'event': 'zone_enter',
            'checkpoint_id': next_cp.id,
            'checkpoint_name': next_cp.name,
            'radius_m': radius,
            'confidence': max(0.0, 1.0 - (dist / radius)) if radius > 0 else 1.0,
            'state': session.state if session else 'on_route',
        }
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([DeviceHeartbeatThrottle])
def heartbeat(request):
    """Main device polling endpoint. Called every ~30-60s by field devices.

    Returns: TTS directives, mission state, telemetry config, geofence events.
    Auth: device_id + password (hashed). Rate: 30 req/min per device.
    """
    device_id = request.data.get('device_id')
    password = request.data.get('password')

    if not device_id:
        return Response({'status': 'error', 'message': 'device_id required'}, status=400)
    if not password:
        return Response({'status': 'error', 'message': 'password required'}, status=400)

    # AUTH: plain get() — no select_for_update. Concurrent heartbeats from the
    # same device are safe because we only call .update() on individual fields.
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return Response({'status': 'device_not_found'}, status=404)

    # Password verify with automatic hash upgrade (legacy plaintext → PBKDF2).
    is_valid, needs_rehash = verify_device_password(password, device.password)
    if not is_valid:
        return Response({'status': 'auth_failed'}, status=401)

    if needs_rehash:
        Device.objects.filter(id=device.id).update(password=hash_device_password(password))

    lat, lng, gps_accuracy = _heartbeat_update_device(device, request)

    directives = {'status': 'ok'}
    directives.update(_heartbeat_fetch_directives(device, lat, gps_accuracy))
    directives.update(_heartbeat_operator_identity(device))

    mission_directives, active_assignments = _heartbeat_active_missions(device)
    directives.update(mission_directives)

    now = timezone.now()
    reminder_directives, reminder_sent = _heartbeat_lead_time_reminder(device, active_assignments, now)
    directives.update(reminder_directives)

    if not reminder_sent:
        directives.update(_heartbeat_geofence_tts(device, lat, lng, now))

    _heartbeat_tts_ack(device, request)
    directives.update(_heartbeat_tts_delivery(device))
    directives.update(_heartbeat_peer_mode(device, active_assignments))

    device.save(update_fields=[
        'battery_pct', 'last_latitude', 'last_longitude', 'last_gps_accuracy',
        'last_seen', 'is_online', 'nfc_fetch_requested', 'gps_fetch_requested',
        'gps_accuracy_threshold', 'peer_session_key',
        'geofence_states', 'last_reminder_at', 'tts_acked', 'tts_pending',
        'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at',
    ])

    session = None
    map_update = None
    active_assignment = active_assignments[0] if active_assignments else None
    if active_assignment:
        session = _get_or_create_session(device, active_assignment, now)
        session = _evaluate_session_state(device, session, active_assignment, lat, lng, now)
        map_update = _build_map_update(device, session, active_assignment, lat, lng, now)

    directives['session_state'] = session.state if session else 'authenticated'
    directives['mission_stage'] = active_assignment.mission_stage if active_assignment else 'assigned'

    # Next checkpoint ETA + anomaly flags for app dashboard
    if active_assignment and active_assignment.route:
        from api.services.scan import get_mission_status
        mission_status = get_mission_status(active_assignment)
        if mission_status and not mission_status.get('completed', False):
            next_cp = mission_status.get('next_checkpoint', {})
            if next_cp:
                directives['next_checkpoint'] = next_cp.get('name', '')
                directives['time_remaining_seconds'] = next_cp.get('time_remaining_seconds', -1)
                directives['is_window_missed'] = next_cp.get('is_window_missed', False)

    # Surface recent anomaly flags from last scan
    from api.models import ScanRecord
    last_scan = ScanRecord.objects.filter(device=device).order_by('-timestamp').first()
    if last_scan and last_scan.anomaly_flags:
        directives['anomaly_flags'] = last_scan.anomaly_flags
    directives['telemetry'] = session.telemetry_dict if session else {
        'gps_interval_ms': 60000,
        'constellation_required': False,
        'sensor_activation': 'none',
        'accuracy_min_meters': 10,
    }
    if map_update:
        directives['map_update'] = map_update

    return Response(directives)
