"""Dispatch partials for htmx — blueprint library and mission grid."""
from django.db.models import Q
from django.template.loader import render_to_string
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import PatrolRoute, ShiftAssignment, Organization


def _resolve_route_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return PatrolRoute.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        org = user.dispatcher_profile.organization
        return PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True))
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        org = user.guardsupervisor.organization
        return PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True))
    return PatrolRoute.objects.none()


def _resolve_assignment_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return ShiftAssignment.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        org = user.dispatcher_profile.organization
        return ShiftAssignment.objects.filter(
            Q(route__organization=org) |
            Q(guard_supervisor__organization=org) |
            Q(dispatcher=user)
        ).distinct()
    return ShiftAssignment.objects.none()


@api_view(['GET'])
@login_required
def blueprints_partial(request):
    """Return HTML fragment of blueprint card grid for htmx."""
    user = request.user
    routes = _resolve_route_queryset(user).order_by('-id')

    q = request.GET.get('q', '').lower()
    if q:
        routes = [r for r in routes if q in (r.name or '').lower()]

    return HttpResponse(render_to_string('partials/dispatch/blueprints.html', {
        'routes': routes,
    }, request=request))


@api_view(['GET'])
@login_required
def missions_partial(request):
    """Return HTML fragment of mission grid grouped by route for htmx."""
    tab = request.GET.get('tab', 'active')
    user = request.user
    assignments = _resolve_assignment_queryset(user).select_related('route', 'guard_supervisor', 'device')

    # Filter by tab
    if tab == 'active':
        assignments = assignments.filter(is_active=True, is_completed=False)
    elif tab == 'upcoming':
        assignments = assignments.filter(is_active=False, is_completed=False)
    elif tab == 'done':
        assignments = assignments.filter(is_completed=True)
    elif tab == 'missed':
        assignments = assignments.filter(is_active=True, is_completed=False)
    # 'all' = no additional filter

    # Group by route
    groups = {}
    for a in assignments:
        route_id = a.route_id or 0
        route_name = a.route.name if a.route else 'Unassigned'
        if route_id not in groups:
            groups[route_id] = {'name': route_name, 'assignments': []}
        groups[route_id]['assignments'].append(a)

    return HttpResponse(render_to_string('partials/dispatch/missions.html', {
        'groups': groups.values(),
        'tab': tab,
    }, request=request))
