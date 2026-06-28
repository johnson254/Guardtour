"""Report partials for htmx — scans table and filter dropdowns."""
from django.db.models import Q
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import ScanRecord, GuardSupervisor, PatrolRoute, Organization


def _resolve_guard_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return GuardSupervisor.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if org:
            return GuardSupervisor.objects.filter(organization=org)
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return GuardSupervisor.objects.filter(organization=user.guardsupervisor.organization)
    return GuardSupervisor.objects.none()


def _resolve_route_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return PatrolRoute.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        return PatrolRoute.objects.filter(organization=user.dispatcher_profile.organization)
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return PatrolRoute.objects.filter(organization=user.guardsupervisor.organization)
    return PatrolRoute.objects.none()


@login_required
def scans_table_partial(request):
    """Return HTML fragment of filtered scans table + stats for htmx."""
    user = request.user
    queryset = ScanRecord.objects.none()
    if user.is_superuser or hasattr(user, 'admin_profile'):
        queryset = ScanRecord.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if org:
            queryset = ScanRecord.objects.filter(
                Q(guard_supervisor__organization=org) |
                Q(device__organization=org) |
                Q(route__organization=org)
            ).distinct()

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    guard_id = request.GET.get('guard_id')
    route_id = request.GET.get('route_id')
    is_on_time = request.GET.get('is_on_time')

    if start_date: queryset = queryset.filter(timestamp__date__gte=start_date)
    if end_date: queryset = queryset.filter(timestamp__date__lte=end_date)
    if guard_id: queryset = queryset.filter(guard_supervisor_id=guard_id)
    if route_id: queryset = queryset.filter(route_id=route_id)
    if is_on_time:
        queryset = queryset.filter(is_on_time=is_on_time.lower() == 'true')

    scans = list(queryset.order_by('-timestamp'))

    total = len(scans)
    on_time_count = sum(1 for s in scans if s.is_on_time)
    late_count = total - on_time_count
    on_time_pct = round((on_time_count / total) * 100) if total > 0 else 0

    guard_stats = {}
    for s in scans:
        name = s.guard_supervisor.username if s.guard_supervisor else 'Unknown'
        if name not in guard_stats:
            guard_stats[name] = {'total': 0, 'onTime': 0}
        guard_stats[name]['total'] += 1
        if s.is_on_time:
            guard_stats[name]['onTime'] += 1

    gs_cards = ''.join(
        f'<div class="card" style="padding:10px;">'
        f'<div>{name}</div>'
        f'<div style="font-size:0.9em;">{st["onTime"]}/{st["total"]} '
        f'({round((st["onTime"]/st["total"])*100) if st["total"] > 0 else 0}%)</div>'
        f'</div>'
        for name, st in guard_stats.items()
    )

    stats_html = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-bottom:15px;">'
        f'<div class="card" style="padding:15px;">'
        f'<h4>Scan Summary</h4>'
        f'<p>Total Scans: <strong>{total}</strong></p>'
        f'<p>On Time: <strong>{on_time_count}</strong> ({on_time_pct}%)</p>'
        f'<p>Late: <strong>{late_count}</strong></p>'
        f'</div>'
        f'<div class="card" style="padding:15px;">'
        f'<h4>Performance Trend</h4>'
        f'<p>On-Time Rate: <strong>{on_time_pct}%</strong></p>'
        f'<p>{"Excellent" if on_time_pct >= 90 else "Good" if on_time_pct >= 75 else "Needs Improvement"}</p>'
        f'</div>'
        f'</div>'
        f'<h4>Guard Performance</h4>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:10px;">{gs_cards}</div>'
    )

    if scans:
        rows = ''.join(
            f'<tr>'
            f'<td>{s.timestamp.isoformat() if s.timestamp else ""}</td>'
            f'<td>{s.guard_supervisor.username if s.guard_supervisor else "Unknown"}</td>'
            f'<td>{s.checkpoint_name or "N/A"}</td>'
            f'<td>{s.route.name if s.route else "N/A"}</td>'
            f'<td>{s.nfc_value or "N/A"}</td>'
            f'<td><span style="padding:2px 6px;border-radius:3px;font-size:0.85em;'
            f'background:{"#4caf50" if s.is_on_time else "#f44336"};color:white;">'
            f'{"On time" if s.is_on_time else "Late"}</span></td>'
            f'<td>{"(" + str(round(s.lat, 4)) + ", " + str(round(s.lng, 4)) + ")" if s.lat and s.lng else "N/A"}</td>'
            f'</tr>'
            for s in scans
        )
    else:
        rows = '<tr><td colspan="7" style="text-align:center;padding:30px;">No scan records match the selected filters</td></tr>'

    table_html = (
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;min-width:800px;">'
        '<thead><tr><th>Timestamp</th><th>Guard</th><th>Checkpoint</th><th>Route</th>'
        '<th>NFC Value</th><th>Status</th><th>Location</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
        '</div>'
    )

    return HttpResponse(f'{stats_html}{table_html}')


@api_view(['GET'])
@login_required
def reports_guards_options_partial(request):
    """Return HTML fragment of guard <option> elements for reports filter."""
    guards_qs = _resolve_guard_queryset(request.user)
    options = ''.join(
        f'<option value="{g.id}">{(g.first_name or "") + " " + (g.last_name or "")}</option>'.replace('  ', ' ').strip()
        for g in guards_qs.order_by('last_name', 'first_name')
    )
    return HttpResponse(f'<option value="">All Personnel</option>{options}')


@api_view(['GET'])
@login_required
def reports_routes_options_partial(request):
    """Return HTML fragment of route <option> elements for reports filter."""
    routes_qs = _resolve_route_queryset(request.user)
    options = ''.join(
        f'<option value="{r.id}">{r.name}</option>'
        for r in routes_qs.order_by('name')
    )
    return HttpResponse(f'<option value="">All Routes</option>{options}')
