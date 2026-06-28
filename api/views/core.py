import math


def _haversine_meters(lat1, lng1, lat2, lng2):
    """Distance in meters between two lat/lng points."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_in_polygon(lat, lng, polygon):
    """Ray-casting point-in-polygon. polygon = list of [lat, lng] points."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _deactivate_assignments(queryset):
    """Bulk-deactivate ShiftAssignments and properly reset guard is_on_shift.

    Uses .update() for efficiency then manually fixes guard shift status
    since post_save signal does NOT fire on QuerySet.update().
    """
    from django.utils import timezone
    from api.models import GuardSupervisor, ShiftAssignment

    now = timezone.now()
    guard_ids = set(
        queryset.exclude(guard_supervisor=None)
        .values_list('guard_supervisor_id', flat=True)
    )
    queryset.update(is_active=False, ended_at=now)
    if guard_ids:
        active_guard_ids = set(
            ShiftAssignment.objects.filter(
                guard_supervisor_id__in=guard_ids, is_active=True
            ).values_list('guard_supervisor_id', flat=True)
        )
        inactive_guard_ids = guard_ids - active_guard_ids
        if inactive_guard_ids:
            GuardSupervisor.objects.filter(
                id__in=inactive_guard_ids, is_on_shift=True
            ).update(is_on_shift=False)
