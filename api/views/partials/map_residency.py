"""Map residency partial for htmx — real-time zone entry/exit display."""
from django.template.loader import render_to_string
from django.db.models import Q
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import DeviceSession, ShiftAssignment, Organization


@api_view(['GET'])
@login_required
def map_residency_partial(request):
    """Return HTML fragment showing current map residency events for dispatch map."""
    user = request.user

    qs = ShiftAssignment.objects.filter(is_active=True, is_completed=False)
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        dispatcher = getattr(user, 'dispatcher_profile', None)
        if dispatcher and dispatcher.organization:
            org = dispatcher.organization
            qs = qs.filter(
                Q(route__organization=org) |
                Q(guard_supervisor__organization=org) |
                Q(dispatcher=user)
            ).distinct()
        else:
            return HttpResponse('')

    events = []
    for assignment in qs.select_related('route', 'device', 'guard_supervisor'):
        session = DeviceSession.objects.filter(device=assignment.device, is_active=True).order_by('-entered_at').first()
        if not assignment.route:
            continue
        cps = list(assignment.route.checkpoints.all().order_by('order'))
        if not cps:
            continue
        if not assignment.device.last_latitude or not assignment.device.last_longitude:
            continue

        from api.services.gps import _haversine
        device_lat = assignment.device.last_latitude
        device_lng = assignment.device.last_longitude

        for cp in cps:
            if not cp.lat or not cp.lng:
                continue
            dist = _haversine(device_lat, device_lng, cp.lat, cp.lng)
            radius = cp.radius if cp.radius and cp.radius > 0 else 5
            if dist <= radius:
                events.append({
                    'device_id': assignment.device.device_id,
                    'device_label': assignment.device.device_name or assignment.device.device_id,
                    'checkpoint_id': cp.id,
                    'checkpoint_name': cp.name,
                    'confidence': max(0.0, 1.0 - (dist / radius)) if radius > 0 else 1.0,
                    'state': session.state if session else 'on_route',
                    'assignment_id': assignment.id,
                })

    return HttpResponse(render_to_string('partials/dispatch/map_residency.html', {
        'events': events,
    }, request=request))
