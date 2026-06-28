from django.utils import timezone
from datetime import timedelta
from api.services.gps import _haversine
from api.services.dwell import _walk_dwell_trail
from api.services.anomalies import _sensor_confirms_presence, _sensor_mismatch, _detect_anomalies

PRECISION_MULTIPLIER = {'strict': 0.5, 'normal': 1.0, 'loose': 2.0}


def publish_map_residency(device, checkpoint, confidence):
    """Publish a map residency event that the HTMX partial consumes.

    This function creates a residency event record that can be polled by
    the dispatch map partial to show real-time zone entry/exit.

    Args:
        device: Device instance that entered the zone
        checkpoint: Checkpoint instance that was entered
        confidence: float 0-1 confidence score of the zone entry

    Returns:
        dict with event data for the HTMX partial
    """
    from api.models import DeviceSession

    event = {
        'device_id': device.device_id,
        'device_label': device.device_name or device.device_id,
        'checkpoint_id': checkpoint.id,
        'checkpoint_name': checkpoint.name,
        'confidence': confidence,
        'state': 'on_route',
        'entered_at': timezone.now().isoformat(),
    }

    # Get current session state if available
    session = DeviceSession.objects.filter(device=device, is_active=True).order_by('-entered_at').first()
    if session:
        event['state'] = session.state
        event['entered_at'] = session.last_heartbeat_at.isoformat() if session.last_heartbeat_at else event['entered_at']

    return event


def _compute_effective_radius(checkpoint, sensor_context=None):
    base_radius = checkpoint.radius if checkpoint.radius and checkpoint.radius > 0 else 5
    mult = PRECISION_MULTIPLIER.get(checkpoint.precision_level or 'normal', 1.0)
    effective = max(base_radius * mult, 0.1)
    if sensor_context and _sensor_confirms_presence(sensor_context):
        effective = max(effective, 15.0)
    return effective


def _tolerance_window(checkpoint, now):
    if not checkpoint or not checkpoint.planned_time:
        return None, None
    planned_time = checkpoint.planned_time
    if isinstance(planned_time, str):
        from datetime import datetime as dt
        try:
            planned_time = dt.strptime(planned_time, '%H:%M:%S').time()
        except ValueError:
            try:
                planned_time = dt.strptime(planned_time, '%H:%M').time()
            except ValueError:
                return None, None
    planned_dt = timezone.make_aware(
        timezone.datetime.combine(now.date(), planned_time),
        timezone=now.tzinfo,
    )
    tol = checkpoint.time_tolerance or 15
    dwell_extra = checkpoint.dwell_time or 0
    window_start = planned_dt - timedelta(minutes=tol)
    window_end = planned_dt + timedelta(minutes=tol + dwell_extra)
    return window_start, window_end


def device_has_clean_progression_record(assignment, device, now):
    from api.models import ScanRecord
    if not assignment or not device:
        return True
    recent_scans = ScanRecord.objects.filter(
        device=device,
        route=assignment.route,
        timestamp__gte=assignment.assigned_at,
    ).order_by('-timestamp')[:10]
    total = recent_scans.count()
    if total == 0:
        return True
    on_time_count = sum(1 for s in recent_scans if s.is_on_time)
    if on_time_count / total < 0.8:
        return False
    scored = [s for s in recent_scans if s.validity_score is not None]
    if scored:
        avg_score = sum(s.validity_score for s in scored) / len(scored)
        if avg_score < 0.6:
            return False
    dwell_scored = [s for s in scored if s.dwell_valid]
    if dwell_scored:
        avg_dwell = sum(s.validity_score for s in dwell_scored) / len(dwell_scored)
        if avg_dwell < 0.7:
            return False
    return True


def verify_zone_scan(device, checkpoint, scan_lat, scan_lng, now, assignment=None, sensor_context=None, is_last_checkpoint=False, mission_completed=False):
    result = {
        'validity_score': 0.0,
        'verification_notes': '',
        'dwell_valid': False,
        'dwell_seconds': None,
        'anomaly_flags': [],
        'sensor_aided': False,
        'dropped': False,
        'map_update': None,
    }
    if not checkpoint:
        return result

    window_start, window_end = _tolerance_window(checkpoint, now)
    if window_start and window_end:
        if now < window_start or now > window_end:
            result['validity_score'] = 0.0
            result['verification_notes'] = 'out_of_tolerance_window'
            if window_end and now > window_end and is_last_checkpoint and not mission_completed:
                result['verification_notes'] += ' mission_stall_penalty'
            result['dropped'] = True
            return result

    effective_radius = _compute_effective_radius(checkpoint, sensor_context)
    dist = _haversine(scan_lat, scan_lng, checkpoint.lat, checkpoint.lng)
    if dist is None:
        if checkpoint.checkpoint_type == 'nfc' and checkpoint.nfc_tag:
            radius_score = 1.0
            result['verification_notes'] += ' nfc_only_no_gps'
        else:
            result['verification_notes'] += ' no_gps'
            result['dropped'] = True
            return result
    elif dist <= effective_radius:
        radius_score = 1.0
    elif dist <= effective_radius * 3:
        radius_score = 0.5
    else:
        radius_score = 0.0
        result['verification_notes'] += ' outside_radius'

    continuous_presence = 0
    trail_points = []
    dwell_valid = False
    anomaly_flags = []
    if window_start and window_end:
        continuous_presence, trail_points, _ = _walk_dwell_trail(
            device, assignment, checkpoint, effective_radius, window_start, window_end, now
        )
    dwell_required = (checkpoint.dwell_time or 0) * 60
    if dwell_required > 0:
        if continuous_presence >= dwell_required:
            dwell_valid = True
            result['dwell_seconds'] = int(continuous_presence)
        else:
            dwell_valid = False
            result['dwell_seconds'] = int(continuous_presence) if continuous_presence > 0 else 0
    else:
        dwell_valid = True
    result['dwell_valid'] = dwell_valid

    if trail_points:
        anomaly_flags = _detect_anomalies(trail_points, checkpoint, continuous_presence)
    result['anomaly_flags'] = anomaly_flags

    sensor_aided = False
    if sensor_context:
        if _sensor_confirms_presence(sensor_context):
            sensor_aided = True
            result['sensor_aided'] = True
            result['verification_notes'] += ' sensor_confirmed_presence'
        elif _sensor_mismatch(sensor_context):
            anomaly_flags.append('sensor_mismatch')
            result['anomaly_flags'] = anomaly_flags
            result['verification_notes'] += ' sensor_mismatch'

    nfc_factor = 1.0 if checkpoint.nfc_tag else 0.0
    radius_factor = radius_score
    dwell_factor = 1.0 if dwell_valid else (0.5 if continuous_presence > 0 else 0.0)
    anomaly_factor = 1.0 if not anomaly_flags else 0.0
    sensor_factor = 1.0 if sensor_aided else 0.0
    drift_factor = 1.0

    validity = (
        nfc_factor * 0.25 +
        radius_factor * 0.20 +
        dwell_factor * 0.25 +
        anomaly_factor * 0.15 +
        sensor_factor * 0.10 +
        drift_factor * 0.05
    )
    validity = min(1.0, max(0.0, validity))

    if sensor_aided and validity < 0.75:
        validity = 0.75

    if anomaly_flags:
        validity *= 0.6
    if not dwell_valid and dwell_required > 0:
        validity *= 0.5
    if sensor_context and _sensor_mismatch(sensor_context):
        validity *= 0.5

    if not device_has_clean_progression_record(assignment, device, now):
        validity *= 0.7
        result['verification_notes'] += ' degraded_by_history'

    result['validity_score'] = round(min(1.0, max(0.0, validity)), 2)

    if dist is not None and dist <= effective_radius:
        result['map_update'] = {
            'event': 'zone_enter',
            'checkpoint_id': checkpoint.id,
            'radius_m': effective_radius,
            'confidence': result['validity_score'],
        }

    return result


def calculate_scan_validity(device, checkpoint, scan_lat, scan_lng, now, prev_scans=None):
    from api.services.gps import _haversine
    score = 0.0
    reasons = []

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

    if device.last_latitude and scan_lat and scan_lng:
        device_dist = _haversine(scan_lat, scan_lng, device.last_latitude, device.last_longitude)
        if device_dist < 200:
            score += 0.15
            reasons.append("Device GPS consistent")
        else:
            reasons.append("Device GPS differs from scan location")

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

    if device.battery_pct is not None and device.battery_pct <= 15:
        score -= 0.1
        reasons.append(f"Low battery ({device.battery_pct}%)")

    score = max(0.0, min(1.0, score))
    return round(score, 2), "; ".join(reasons)
