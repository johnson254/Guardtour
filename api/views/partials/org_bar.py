"""Org stats partial for htmx — top bar stats strip."""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse

from api.models import Device, GuardSupervisor, PatrolRoute, ShiftAssignment


@login_required
def org_stats_partial(request):
    """Return HTML fragment for the org bar stats strip."""
    user = request.user

    if user.is_superuser or hasattr(user, 'admin_profile'):
        total_guards = GuardSupervisor.objects.count()
        total_devices = Device.objects.count()
        total_routes = PatrolRoute.objects.count()
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if not org:
            total_guards = total_devices = total_routes = 0
        else:
            total_guards = GuardSupervisor.objects.filter(organization=org).count()
            total_devices = Device.objects.filter(organization=org).count()
            total_routes = PatrolRoute.objects.filter(Q(organization=org) | Q(organization=None)).count()
    elif hasattr(user, 'guardsupervisor'):
        org = user.guardsupervisor.organization
        if not org:
            total_guards = total_devices = total_routes = 0
        else:
            total_guards = GuardSupervisor.objects.filter(organization=org).count()
            total_devices = Device.objects.filter(organization=org).count()
            total_routes = PatrolRoute.objects.filter(Q(organization=org) | Q(organization=None)).count()
    else:
        total_guards = total_devices = total_routes = 0

    html = (
        f'<span class="org-stat"><i class="fas fa-users"></i> {total_guards} Guards</span>'
        f'<span class="org-stat"><i class="fas fa-microchip"></i> {total_devices} Devices</span>'
        f'<span class="org-stat"><i class="fas fa-route"></i> {total_routes} Routes</span>'
    )
    return HttpResponse(html)
