"""Route partials for htmx — route list and editor panel."""
from django.db.models import Q
from django.template.loader import render_to_string
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import PatrolRoute, Organization


def _resolve_route_queryset(user):
    """Return the queryset of PatrolRoute objects visible to this user."""
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return PatrolRoute.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        org = user.dispatcher_profile.organization
        return PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True))
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        org = user.guardsupervisor.organization
        return PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True))
    return PatrolRoute.objects.none()


@api_view(['GET'])
@login_required
def routes_list_partial(request):
    """Return HTML fragment of route card list for htmx."""
    user = request.user
    routes = _resolve_route_queryset(user).order_by('-id')

    q = request.GET.get('q', '').lower()
    if q:
        routes = [r for r in routes if q in (r.name or '').lower()]

    return HttpResponse(render_to_string('partials/routes/list.html', {
        'routes': routes,
    }, request=request))


@api_view(['GET'])
@login_required
def route_editor_partial(request, pk):
    """Return HTML fragment of route editor pre-filled for editing."""
    try:
        route = PatrolRoute.objects.get(pk=pk)
    except PatrolRoute.DoesNotExist:
        return HttpResponse('<p style="color:var(--danger)">Route not found</p>')

    return HttpResponse(render_to_string('partials/routes/editor.html', {
        'route': route,
    }, request=request))
