"""Route partials for htmx — route list, editor panel, wizard steps, checkpoint rows, deploy preview."""
import calendar as cal_mod
from datetime import datetime

from django.db.models import Q
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import PatrolRoute, Organization, GuardSupervisor, MapObject, Checkpoint
from api.org_permissions import get_user_organization_or_none


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


def _resolve_guard_queryset(user):
    """Return guards visible to this user's org."""
    org = get_user_organization_or_none(user)
    if not org:
        return GuardSupervisor.objects.none()
    return GuardSupervisor.objects.filter(organization=org).order_by('callsign')


def _resolve_mapobject_queryset(user):
    """Return map objects visible to this user's org."""
    org = get_user_organization_or_none(user)
    if not org:
        return MapObject.objects.none()
    return MapObject.objects.filter(organization=org).order_by('name')


@api_view(['GET'])
@login_required
def routes_wizard_partial(request):
    """Return a wizard step HTML fragment."""
    step = request.GET.get('step', '1')
    strategy = request.GET.get('strategy', '')
    org = get_user_organization_or_none(request.user)

    ctx = {
        'step': step,
        'strategy': strategy,
        'guards': _resolve_guard_queryset(request.user),
    }

    template_map = {
        '1': 'partials/routes/wizard/step-1.html',
        '2': 'partials/routes/wizard/step-2.html',
        'quick': 'partials/routes/wizard/step-quick.html',
        'audit': 'partials/routes/wizard/step-audit.html',
        'quickdeploy': 'partials/routes/wizard/step-quickdeploy.html',
        'editconfirm': 'partials/routes/wizard/step-editconfirm.html',
    }

    template_name = template_map.get(step, template_map['1'])
    return HttpResponse(render_to_string(template_name, ctx, request=request))


@api_view(['GET'])
@login_required
def routes_checkpoint_form_partial(request):
    """Return a single checkpoint row HTML fragment."""
    cp_type = request.GET.get('type', 'nfc')
    order = int(request.GET.get('order', 0))

    ctx = {
        'type': cp_type,
        'order': order,
        'idx': order,
        'map_objects': _resolve_mapobject_queryset(request.user),
        'guards': _resolve_guard_queryset(request.user),
    }

    return HttpResponse(render_to_string('partials/routes/checkpoint-row.html', ctx, request=request))


@api_view(['GET'])
@login_required
def routes_deploy_preview_partial(request, pk):
    """Return deploy preview panel HTML for a saved route."""
    org = get_user_organization_or_none(request.user)
    route = get_object_or_404(PatrolRoute, pk=pk, organization=org)
    checkpoints = route.checkpoints.order_by('order')

    return HttpResponse(render_to_string('partials/routes/deploy-preview.html', {
        'route': route,
        'checkpoints': checkpoints,
    }, request=request))
