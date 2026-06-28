import json
import math
from django.db.models import F as models_F, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from .models import Device, Checkpoint, MapObject, ScanRecord, ShiftAssignment, GuardSupervisor


def authenticate_device(device_id, password):
    if not device_id or not password:
        raise serializers.ValidationError({"detail": "Device authentication failed."})
    device = Device.objects.filter(device_id=device_id).first()
    if not device or device.password != password:
        raise serializers.ValidationError({"detail": "Device authentication failed."})
    if not device.is_active:
        raise serializers.ValidationError({"detail": "Device is decommissioned. Contact dispatcher."})
    return device


def check_cooldown(device, nfc_value, now):
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


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── NFC Payload Parsing ──────────────────────────────────────

def parse_nfc_payload(raw):
    """Return (scan_type, extracted_id, peer_data) from raw NFC payload.

    scan_type: 'tag' | 'peer'
    extracted_id: the identifier to use as nfc_value
    peer_data: dict for peer exchanges, None for tag scans
    """
    if not raw or not isinstance(raw, dict):
        return 'tag', None, None

    ndef_records = raw.get('ndef_records') or []

    # Check for peer handshake NDEF record
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

    # Falls back to tag: extract from NDEF text or UID
    for rec in ndef_records:
        payload_text = rec.get('payload_text')
        if payload_text:
            return 'tag', payload_text.strip(), None

    uid = raw.get('uid')
    if uid:
        return 'tag', uid.replace(':', '').lower(), None

    return 'tag', None, None


def validate_peer_exchange(device, peer_data):
    """Validate a peer handshake exists reciprocally.

    Checks that the peer device (identified by peer_data['peer_device_id'])
    exists, is online or recently seen, and that a reciprocal scan record
    (this device scanning that one) exists within a small time window.
    """
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

    # Check for reciprocal scan within 30-second window
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


# ── Validity Scoring ─────────────────────────────────────────

def calculate_scan_validity(device, checkpoint, scan_lat, scan_lng, now, prev_scans=None):
    """Return (score, reason) tuple: 0.0-1.0 probability + human-readable explanation."""
    score = 0.0
    reasons = []

    # 1. GPS proximity to checkpoint (0-0.6) with context-aware radius
    if scan_lat and scan_lng and checkpoint and checkpoint.lat and checkpoint.lng:
        dist = _haversine(scan_lat, scan_lng, checkpoint.lat, checkpoint.lng)
        precision_mult = {'strict': 0.5, 'normal': 1.0, 'loose': 2.0}.get(checkpoint.precision_level or 'normal', 1.0)
        radius = (checkpoint.radius or 50) * precision_mult
        if dist <= radius:
            score += 0.6
            reasons.append(f"Within {dist:.0f}m of checkpoint (precision={checkpoint.precision_level or 'normal'}, radius={radius:.0f}m)")
        elif dist <= radius * 3:
            score += 0.3
            reasons.append(f"Near checkpoint ({dist:.0f}m, radius={radius:.0f}m)")
        else:
            reasons.append(f"Far from checkpoint ({dist:.0f}m, radius={radius:.0f}m)")

    # 2. Device GPS history consistency (0-0.15)
    if device.last_latitude and scan_lat and scan_lng:
        device_dist = _haversine(scan_lat, scan_lng, device.last_latitude, device.last_longitude)
        if device_dist < 200:
            score += 0.15
            reasons.append("Device GPS consistent")
        else:
            reasons.append("Device GPS differs from scan location")

    # 3. Movement plausibility from previous scan (0-0.25)
    if prev_scans and scan_lat and scan_lng:
        last = prev_scans[0]
        if last.lat and last.lng:
            gap_dist = _haversine(last.lat, last.lng, scan_lat, scan_lng)
            gap_minutes = max((now - last.timestamp).total_seconds() / 60, 0.1)
            speed = gap_dist / gap_minutes
            if speed < 500:
                score += 0.25
                reasons.append(f"Movement plausible ({speed:.0f} m/min)")
            else:
                reasons.append(f"Movement implausible ({speed:.0f} m/min)")

    # 4. Battery / online mitigators (-0.1 to +0.0)
    if device.battery_pct is not None and device.battery_pct <= 15:
        score -= 0.1
        reasons.append(f"Low battery ({device.battery_pct}%)")

    score = max(0.0, min(1.0, score))
    return round(score, 2), "; ".join(reasons)


# ── Asset & Assignment Resolution ────────────────────────────

def resolve_asset(nfc_value, scan_type='tag', organization=None):
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


# Peer verification is handled by validate_peer_exchange (reciprocal key exchange within 30s)


def is_on_time(checkpoint, now):
    if not checkpoint or not checkpoint.planned_time:
        return True
    planned_dt = timezone.make_aware(
        timezone.datetime.combine(now.date(), checkpoint.planned_time),
        timezone=now.tzinfo
    )
    tol = checkpoint.time_tolerance
    return (planned_dt - timedelta(minutes=tol) <= now <= planned_dt + timedelta(minutes=tol))


# ── Mission Staging ─────────────────────────────────────────

def get_mission_status(assignment):
    """Return next checkpoint, time remaining, dwell state, missed windows for a single assignment."""
    from django.utils import timezone as dj_timezone
    now = dj_timezone.now()
    route = assignment.route
    if not route:
        return None

    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return None

    # Completed checkpoint IDs
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

    # Next checkpoint (first in order not hit)
    next_cp = None
    for cp in cps:
        if cp.id not in hit_ids:
            next_cp = cp
            break

    if not next_cp:
        return {'completed': True, 'hit_count': len(hit_ids), 'total': len(cps)}

    # Last hit time for dwell
    last_hit = None
    if assignment.guard_supervisor:
        last_hit = ScanRecord.objects.filter(
            guard_supervisor=assignment.guard_supervisor,
            route=route, checkpoint=next_cp,
            timestamp__gte=assignment.assigned_at,
        ).order_by('-timestamp').values_list('timestamp', flat=True).first()

    # Time remaining for planned checkpoint
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

    # Dwell
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


# ── Sequence Validation ─────────────────────────────────────

def check_sequence(route, checkpoint, assignment, now):
    """Check if checkpoint was scanned in the correct order.

    Returns True if out_of_sequence, False if in sequence or order not enforced.
    """
    if not route or not checkpoint or not assignment:
        return False
    if not route.enforce_order:
        return False
    cps = list(route.checkpoints.all().order_by('order'))
    if not cps:
        return False

    # Find the index of the scanned checkpoint in the route's sequence
    try:
        current_idx = next(i for i, cp in enumerate(cps) if cp.id == checkpoint.id)
    except StopIteration:
        return False

    # Get all previously scanned checkpoints in this assignment
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

    # If no previous scans, the first checkpoint in order (index 0) is expected
    if not hit_ids:
        return current_idx != 0

    # Find the last scanned checkpoint by max list index
    last_idx = -1
    for i, cp in enumerate(cps):
        if cp.id in hit_ids:
            last_idx = max(last_idx, i)

    # Expected next index is last_idx + 1
    expected_idx = last_idx + 1
    return current_idx != expected_idx


def check_dwell_time(checkpoint, assignment, now):
    """Check if sufficient dwell time was spent at checkpoint.

    Returns (insufficient_dwell_time, dwell_seconds) tuple.
    """
    if not checkpoint or not checkpoint.dwell_time or not assignment:
        return False, None

    scan_filter = {
        'checkpoint': checkpoint,
        'route': assignment.route,
        'timestamp__gte': assignment.assigned_at,
    }
    if assignment.guard_supervisor:
        scan_filter['guard_supervisor'] = assignment.guard_supervisor
    else:
        scan_filter['device'] = assignment.device

    last_scan_on_cp = ScanRecord.objects.filter(**scan_filter).order_by('-timestamp').first()
    if not last_scan_on_cp:
        return False, None

    dwell_seconds = int((now - last_scan_on_cp.timestamp).total_seconds())
    required_seconds = checkpoint.dwell_time * 60
    insufficient = dwell_seconds < required_seconds
    return insufficient, dwell_seconds


def trigger_emergency(assignment, checkpoint, device, now):
    """Trigger emergency protocol for emergency checkpoints."""
    from .models import OperatorAlert

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
    """Identify missed checkpoints for a route assignment.

    Returns list of checkpoint dicts that were skipped.
    """
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


def transfer_shift(assignment, new_guard, new_device=None, requested_by=None):
    """Transfer a partially completed route from one guard to another.

    Closes the current ShiftAssignment and creates a new one starting
    from the last successfully scanned checkpoint.
    """
    from django.utils import timezone as dj_timezone
    now = dj_timezone.now()

    old_guard = assignment.guard_supervisor
    route = assignment.route
    shift_type = assignment.shift_type
    scheduled_date = assignment.scheduled_date

    # Mark old assignment as handed over
    assignment.is_active = False
    assignment.is_completed = False
    assignment.status = 'handover'
    assignment.ended_at = now
    assignment.save(update_fields=['is_active', 'status', 'ended_at'])

    # Update old guard's shift status if no other active assignments
    if old_guard:
        has_other = ShiftAssignment.objects.filter(
            guard_supervisor=old_guard, is_active=True
        ).exclude(pk=assignment.pk).exists()
        if not has_other:
            old_guard.is_on_shift = False
            old_guard.save(update_fields=['is_on_shift'])

    # Determine which device to use
    device = new_device or assignment.device

    # Create new assignment
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

    # Update new guard's shift status
    if new_guard:
        new_guard.is_on_shift = True
        new_guard.last_shift_change = now
        new_guard.save(update_fields=['is_on_shift', 'last_shift_change'])

    return new_assignment


# ── Time Drift Validation ───────────────────────────────────

MAX_TIMESTAMP_DRIFT_SECONDS = 300  # 5 minutes

def validate_timestamp_drift(client_ts, server_now):
    """Validate client timestamp against server clock.

    Returns (drift_seconds, is_suspicious).
    Positive drift = client timestamp is behind server (backdating).
    """
    if not client_ts:
        return None, False
    drift = int((server_now - client_ts).total_seconds())
    suspicious = abs(drift) > MAX_TIMESTAMP_DRIFT_SECONDS
    return drift, suspicious


# ── Offline Sequence Validation ─────────────────────────────

def validate_sequence_id(device, sequence_id):
    """Validate and update the device's monotonic sequence counter.

    Returns True if the sequence is valid (monotonically increasing).
    """
    if sequence_id is None:
        return True
    if sequence_id <= device.last_sequence_id:
        return False
    Device.objects.filter(id=device.id, last_sequence_id__lt=sequence_id).update(
        last_sequence_id=sequence_id
    )
    return True


# ── Scan Pipeline ────────────────────────────────────────────

def process_scan(device_id, password, route_id, nfc_value, peer_key, now, raw_nfc=None, scan_lat=None, scan_lng=None, client_timestamp=None, sequence_id=None):
    device = authenticate_device(device_id, password)

    # ── Time Drift Check ──
    server_now = now
    time_drift, is_suspicious = validate_timestamp_drift(client_timestamp, server_now)

    # ── Offline Sequence Check ──
    sequence_valid = validate_sequence_id(device, sequence_id)

    # Parse raw NFC if provided — overrides nfc_value
    scan_type = 'tag'
    peer_data = None
    extracted_id = nfc_value
    if raw_nfc:
        scan_type, extracted_id, peer_data = parse_nfc_payload(raw_nfc)

    # Resolve the effective identifier
    effective_id = extracted_id or nfc_value

    check_cooldown(device, effective_id, now)

    # Resolve assignment first so we can scope checkpoint lookup by route.
    # This ensures duplicate nfc_tags across different routes resolve to
    # the correct checkpoint for THIS device's active mission.
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

    # ── Sequence Validation ──
    out_of_sequence = False
    if checkpoint and route and not route.is_emergency:
        out_of_sequence = check_sequence(route, checkpoint, assignment, now)

    # ── Emergency Trigger ──
    emergency_triggered = False
    if checkpoint and route and route.is_emergency and assignment:
        trigger_emergency(assignment, checkpoint, device, now)
        emergency_triggered = True
        out_of_sequence = False

    # ── Dwell Time Enforcement ──
    insufficient_dwell, dwell_seconds = check_dwell_time(checkpoint, assignment, now)

    # Previous scans for validity
    prev_scans = list(ScanRecord.objects.filter(device=device).order_by('-timestamp')[:1])

    # Calculate validity
    val_score, val_reason = calculate_scan_validity(device, checkpoint, scan_lat, scan_lng, now, prev_scans)

    # ── Mark assignment completed if all checkpoints hit ──
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
                assignment.ended_at = now
                assignment.save(update_fields=['is_completed', 'is_active', 'status', 'ended_at'])

    # Build TTS / confirmation directives for the device
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

    return dict(
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
        sequence_id=sequence_id,
        checkpoint_name=checkpoint.name if checkpoint else f"Unknown Tag: {nfc_value}",
        nfc_value=effective_id,
        raw_nfc=raw_nfc,
        scan_type=scan_type,
        validity_score=val_score,
        validity_reason=val_reason,
        # Response-only fields (not model fields — popped before serializer.save)
        _tts_message=tts_message,
        _tts_voice=tts_voice,
        _tts_rate=tts_rate,
        _tts_pitch=tts_pitch,
        _play_sound=True,
        _vibrate=True,
    )


# ── GPS Correction ──────────────────────────────

def _spherical_interpolate(lat1, lng1, lat2, lng2, ratio):
    """Spherically interpolate between two lat/lng points.

    Uses 3D cartesian conversion for proper great-circle interpolation
    rather than naive linear interpolation which breaks down over large distances.
    """
    lat1_r, lng1_r = math.radians(lat1), math.radians(lng1)
    lat2_r, lng2_r = math.radians(lat2), math.radians(lng2)

    x1 = math.cos(lat1_r) * math.cos(lng1_r)
    y1 = math.cos(lat1_r) * math.sin(lng1_r)
    z1 = math.sin(lat1_r)

    x2 = math.cos(lat2_r) * math.cos(lng2_r)
    y2 = math.cos(lat2_r) * math.sin(lng2_r)
    z2 = math.sin(lat2_r)

    x = x1 + (x2 - x1) * ratio
    y = y1 + (y2 - y1) * ratio
    z = z1 + (z2 - z1) * ratio

    mag = math.sqrt(x * x + y * y + z * z)
    if mag == 0:
        return lat1, lng1
    x, y, z = x / mag, y / mag, z / mag

    interp_lat = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    interp_lng = math.degrees(math.atan2(y, x))
    return interp_lat, interp_lng


MAX_INTERPOLATION_GAP_SECONDS = 600  # 10 minutes

def correct_gps_trail(points, max_speed_ms=30.0, window_size=3):
    """Smooth a trail of GPS points with accuracy-weighted averaging and outlier rejection.

    Uses spherical interpolation for outlier correction to avoid
    geographic distortion from naive linear interpolation.

    If the time gap between consecutive points exceeds MAX_INTERPOLATION_GAP_SECONDS,
    a gap marker (gap: True) is inserted instead of interpolating, preventing
    fake "constant speed" trails across long offline periods.

    Args:
        points: list of dicts with lat, lng, accuracy, recorded_at
        max_speed_ms: max plausible speed (m/s) between consecutive points
        window_size: sliding window for weighted average (odd number)

    Returns:
        list of dicts with same keys + corrected flag, plus gap markers
    """
    if len(points) < 2:
        return [dict(p, corrected=False) for p in points]

    n = len(points)

    # Pass 1: reject speed outliers (teleportation) using spherical interpolation
    # and insert gap markers for long time gaps
    cleaned = [dict(points[0], corrected=False)]
    for i in range(1, n):
        prev = cleaned[-1]
        p = points[i]
        dt = abs((p['recorded_at'] - prev['recorded_at']).total_seconds())

        # Insert gap marker if time gap exceeds threshold
        if dt > MAX_INTERPOLATION_GAP_SECONDS:
            cleaned.append({'gap': True, 'recorded_at': prev['recorded_at'] + timedelta(seconds=MAX_INTERPOLATION_GAP_SECONDS)})
            cleaned.append(dict(p, corrected=False))
            continue

        d = _haversine(prev['lat'], prev['lng'], p['lat'], p['lng'])
        speed = d / dt if dt > 0 else 0
        if speed > max_speed_ms:
            ratio = min(1.0, max_speed_ms / speed) if speed > 0 else 1.0
            interp_lat, interp_lng = _spherical_interpolate(
                prev['lat'], prev['lng'], p['lat'], p['lng'], ratio
            )
            cleaned.append(dict(p, lat=interp_lat, lng=interp_lng, corrected=True))
        else:
            cleaned.append(dict(p, corrected=False))

    # Pass 2: accuracy-weighted moving average (skip gap markers)
    result = []
    half = window_size // 2
    for i in range(len(cleaned)):
        p = cleaned[i]
        if p.get('gap'):
            result.append(p)
            continue
        acc = p.get('accuracy') or 50.0
        start = max(0, i - half)
        end = min(len(cleaned), i + half + 1)
        wsum = 0.0
        lat_w = 0.0
        lng_w = 0.0
        for j in range(start, end):
            q = cleaned[j]
            if q.get('gap'):
                continue
            qacc = q.get('accuracy') or 50.0
            w = 1.0 / (qacc + 1.0)
            wsum += w
            lat_w += q['lat'] * w
            lng_w += q['lng'] * w
        smoothed_lat = lat_w / wsum if wsum > 0 else p['lat']
        smoothed_lng = lng_w / wsum if wsum > 0 else p['lng']
        is_corrected = p.get('corrected', False) or (abs(smoothed_lat - p['lat']) > 0.0001)
        result.append(dict(p, lat=smoothed_lat, lng=smoothed_lng, corrected=is_corrected))

    return result
