"""Manage page partials for htmx — device list and checkpoint registry."""
from django.db.models import Q
from django.template.loader import render_to_string
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import Device, MapObject, Organization


def _resolve_org(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return None
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        return user.dispatcher_profile.organization
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return user.guardsupervisor.organization
    return None


def _resolve_devices(user):
    org = _resolve_org(user)
    if org is None:
        return Device.objects.all()
    return Device.objects.filter(organization=org)


def _resolve_checkpoints(user):
    org = _resolve_org(user)
    qs = MapObject.objects.filter(
        Q(type__in=['nfc', 'gps', 'geo', 'peer', 'poi', 'geofence']) |
        Q(checkpoint_type__in=['nfc', 'gps', 'geo', 'peer'])
    )
    if org:
        qs = qs.filter(organization=org)
    return qs


@api_view(['GET'])
@login_required
def devices_list_partial(request):
    """Return HTML fragment of device cards for htmx."""
    devices = _resolve_devices(request.user).order_by('-is_online', 'device_name')
    q = request.GET.get('q', '').lower()
    status_filter = request.GET.get('status', 'all')
    if q:
        devices = [d for d in devices if q in (d.device_name or '').lower() or q in (d.device_id or '').lower() or q in (d.assigned_callsign or '').lower()]
    if status_filter == 'online':
        devices = [d for d in devices if d.is_online]
    return HttpResponse(render_to_string('partials/manage/devices.html', {
        'devices': devices,
    }, request=request))


@api_view(['GET'])
@login_required
def checkpoints_list_partial(request):
    """Return HTML fragment of checkpoint registry for htmx."""
    checkpoints = _resolve_checkpoints(request.user).order_by('-id')[:50]
    return HttpResponse(render_to_string('partials/manage/checkpoints.html', {
        'checkpoints': checkpoints,
    }, request=request))


@api_view(['GET'])
@login_required
def staff_panel_partial(request):
    """Return Staff & Duty panel content for htmx."""
    return HttpResponse(render_to_string('partials/manage/staff_panel.html', {}, request=request))


@api_view(['GET'])
@login_required
def fleet_panel_partial(request):
    """Return Fleet & Asset Registry panel content for htmx."""
    return HttpResponse(render_to_string('partials/manage/fleet_panel.html', {}, request=request))


@api_view(['GET'])
@login_required
def audit_panel_partial(request):
    """Return Routes & Audit panel content for htmx."""
    return HttpResponse(render_to_string('partials/manage/audit_panel.html', {}, request=request))
