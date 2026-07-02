"""Manage page partials for htmx — panel stats, device list, checkpoint registry."""
from django.db.models import Q, Count
from django.template.loader import render_to_string
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import Device, MapObject, Organization
from api.models.personnel import GuardSupervisor
from api.models.dispatch import ShiftAssignment
from api.models.patrol import PatrolRoute


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
    qs = MapObject.objects.filter(type__in=['poi', 'geofence'])
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


@api_view(['GET'])
@login_required
def staff_panel_stats_partial(request):
    """Return personnel stats bar for htmx."""
    org = _resolve_org(request.user)
    qs = GuardSupervisor.objects.all()
    if org:
        qs = qs.filter(organization=org)
    total = qs.count()
    guards = qs.filter(role='guard').count()
    supers = qs.filter(role='supervisor').count()
    day = qs.filter(shift='Day').count()
    night = qs.filter(shift='Night').count()
    return HttpResponse(render_to_string('partials/manage/staff_panel_stats.html', {
        'total': total, 'guards': guards, 'supers': supers,
        'day': day, 'night': night,
        'tc_staff': total,
    }, request=request))


@api_view(['GET'])
@login_required
def fleet_panel_stats_partial(request):
    """Return fleet device stats bar for htmx."""
    org = _resolve_org(request.user)
    qs = Device.objects.all()
    if org:
        qs = qs.filter(organization=org)
    total = qs.count()
    online = qs.filter(is_online=True).count()
    on_mission = qs.filter(current_assignments__is_active=True).distinct().count()
    tts_pending = qs.filter(tts_pending__isnull=False, tts_acked=False).count()
    nfc_pending = qs.filter(nfc_fetch_requested__isnull=False).count()
    offline = total - online

    asset_count = MapObject.objects.filter(
        type__in=['poi', 'geofence']
    ).count()
    tc_fleet = total + asset_count
    return HttpResponse(render_to_string('partials/manage/fleet_panel_stats.html', {
        'total': total, 'online': online, 'on_mission': on_mission,
        'tts_pending': tts_pending, 'nfc_pending': nfc_pending,
        'offline': offline, 'tc_fleet': tc_fleet,
        'device_count': total,
    }, request=request))


@api_view(['GET'])
@login_required
def audit_panel_stats_partial(request):
    """Return route/audit stats bar for htmx."""
    org = _resolve_org(request.user)
    routes_qs = PatrolRoute.objects.all()
    shifts_qs = ShiftAssignment.objects.all()
    if org:
        routes_qs = routes_qs.filter(organization=org)
        shifts_qs = shifts_qs.filter(guard_supervisor__organization=org)
    total_routes = routes_qs.count()
    with_cps = routes_qs.annotate(cp_count=Count('checkpoints')).filter(cp_count__gt=0).count()
    active_shifts = shifts_qs.filter(is_active=True, is_completed=False).count()
    completed_shifts = shifts_qs.filter(is_completed=True).count()
    return HttpResponse(render_to_string('partials/manage/audit_panel_stats.html', {
        'total_routes': total_routes, 'active_shifts': active_shifts,
        'completed_shifts': completed_shifts, 'with_cps': with_cps,
        'tc_audit': total_routes,
    }, request=request))
