from django.utils import timezone
from datetime import timedelta
from api.services.gps import _haversine


def _walk_dwell_trail(device, assignment, checkpoint, effective_radius, window_start, window_end, now):
    from api.models import DeviceTrail
    trail_qs = DeviceTrail.objects.filter(
        device=device,
        recorded_at__gte=window_start,
        recorded_at__lte=now,
    ).order_by('recorded_at')
    if assignment:
        trail_qs = trail_qs.filter(assignment=assignment)
    points = list(trail_qs.values('lat', 'lng', 'accuracy', 'recorded_at'))
    if not points:
        return 0, [], None
    continuous = 0
    best = 0
    prev_inside = False
    prev_ts = None
    hdop_values = []
    for p in points:
        dist = _haversine(p['lat'], p['lng'], checkpoint.lat, checkpoint.lng)
        if dist is None:
            continue
        inside = dist <= effective_radius
        ts = p['recorded_at']
        if inside:
            if prev_inside and prev_ts:
                delta = (ts - prev_ts).total_seconds()
                continuous += delta
            else:
                continuous = 0
            if continuous > best:
                best = continuous
        else:
            continuous = 0
        prev_inside = inside
        prev_ts = ts
        if p.get('accuracy') is not None:
            hdop_values.append(p['accuracy'])
    return best, points, hdop_values


def check_dwell_time(checkpoint, assignment, now):
    from api.models import ScanRecord
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
