"""Incident partials for htmx — analytics dashboard."""
import json
from django.db.models import Q
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone

from api.models import ScanRecord, GuardSupervisor, Organization, OperatorAlert


@api_view(['GET'])
@login_required
def incidents_partial(request):
    """Return HTML fragment of incidents/analytics stats + table + chart data for htmx."""
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
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        org = user.guardsupervisor.organization
        queryset = ScanRecord.objects.filter(
            Q(guard_supervisor__organization=org) |
            Q(device__organization=org) |
            Q(route__organization=org)
        ).distinct()

    date_str = request.GET.get('date')
    guard_id = request.GET.get('guard_id')

    if date_str:
        queryset = queryset.filter(timestamp__date=date_str)

    scans = list(queryset.order_by('-timestamp'))
    today_scans = [s for s in scans if s.timestamp and s.timestamp.date() == timezone.now().date()]

    if guard_id:
        scans = [s for s in scans if s.guard_supervisor_id == int(guard_id)]

    total = len(scans)
    on_time_count = sum(1 for s in scans if s.is_on_time)
    late_count = total - on_time_count
    on_time_pct = round((on_time_count / total) * 100) if total > 0 else 100

    day_scans = [s for s in scans if s.guard_supervisor and s.guard_supervisor.shift == 'Day']
    night_scans = [s for s in scans if s.guard_supervisor and s.guard_supervisor.shift == 'Night']
    day_hits = len(day_scans)
    night_hits = len(night_scans)

    alerts = OperatorAlert.objects.none()
    if user.is_superuser or hasattr(user, 'admin_profile'):
        alerts = OperatorAlert.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        alerts = OperatorAlert.objects.filter(organization=user.dispatcher_profile.organization)
    unresolved = alerts.filter(is_read=False).count()

    hourly = [0] * 24
    for s in today_scans:
        if s.timestamp:
            hourly[s.timestamp.hour] += 1

    day_on = sum(1 for s in day_scans if s.is_on_time)
    day_late = day_hits - day_on
    night_on = sum(1 for s in night_scans if s.is_on_time)
    night_late = night_hits - night_on

    chart_data_json = json.dumps({
        'shiftPerf': {
            'Day': {'onTime': day_on, 'late': day_late},
            'Night': {'onTime': night_on, 'late': night_late}
        },
        'hourlyDensity': hourly,
        'compliance': on_time_pct,
        'totalScans': total,
        'dayHits': day_hits,
        'nightHits': night_hits,
        'criticalAlerts': unresolved
    })

    stats_html = (
        f'<div class="small-stat">'
        f'<span class="label-mini">Avg Compliance</span>'
        f'<div style="font-size:1.5rem;font-weight:800;color:var(--accent-green);">{on_time_pct}%</div>'
        f'<div class="trend-badge trend-neutral">Analyzing...</div>'
        f'</div>'
        f'<div class="small-stat">'
        f'<span class="label-mini">Day Shift Hits</span>'
        f'<div style="font-size:1.5rem;font-weight:800;color:white;">{day_hits}</div>'
        f'<div class="trend-badge trend-neutral">--</div>'
        f'</div>'
        f'<div class="small-stat">'
        f'<span class="label-mini">Night Shift Hits</span>'
        f'<div style="font-size:1.5rem;font-weight:800;color:white;">{night_hits}</div>'
        f'<div class="trend-badge trend-neutral">--</div>'
        f'</div>'
        f'<div class="small-stat">'
        f'<span class="label-mini">Critical Alerts</span>'
        f'<div style="font-size:1.5rem;font-weight:800;color:var(--primary);">{unresolved}</div>'
        f'<div class="trend-badge" style="background:rgba(255,255,255,0.05);color:var(--text-muted);">Stable</div>'
        f'</div>'
    )

    if scans:
        rows = ''.join(
            f'<tr>'
            f'<td style="font-weight:700;color:white;">{s.guard_supervisor.username if s.guard_supervisor else "Unknown"}</td>'
            f'<td><span class="deployment-tag">{s.guard_supervisor.shift if s.guard_supervisor else "N/A"}</span></td>'
            f'<td style="color:var(--primary-light);">{s.checkpoint_name or "N/A"}</td>'
            f'<td><span class="status-led {"active" if s.is_on_time else "inactive"}"></span>{"Verified" if s.is_on_time else "Violation"}</td>'
            f'<td style="font-size:0.75rem;color:var(--text-muted);">{(s.timestamp.strftime("%H:%M:%S") if s.timestamp else "")}</td>'
            f'</tr>'
            for s in scans[:10]
        )
    else:
        rows = '<tr><td colspan="5" style="text-align:center;padding:30px;color:var(--text-muted);">No scan records match the selected filters</td></tr>'

    table_html = (
        f'<table style="width:100%;border-spacing:0;">'
        f'<thead><tr><th>Operator</th><th>Shift</th><th>Checkpoint</th><th>Verification</th><th>Timestamp</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'<div id="chart-data-src" data-chart=\'{chart_data_json}\'></div>'
    )

    return HttpResponse(f'<div class="metric-row" id="incidents-stats">{stats_html}</div>'
                       f'<div class="table-scroll" id="incidents-table">{table_html}</div>')


def _resolve_guard_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return GuardSupervisor.objects.all()
    elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
        return GuardSupervisor.objects.filter(organization=user.dispatcher_profile.organization)
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return GuardSupervisor.objects.filter(organization=user.guardsupervisor.organization)
    return GuardSupervisor.objects.none()


@api_view(['GET'])
@login_required
def incidents_guards_options_partial(request):
    """Return HTML fragment of guard <option> elements for incidents filter."""
    guards_qs = _resolve_guard_queryset(request.user)
    options = ''.join(
        f'<option value="{g.id}">{(g.first_name or "") + " " + (g.last_name or "")} ({g.callsign or "??"})</option>'
        for g in guards_qs.order_by('last_name', 'first_name')
    )
    return HttpResponse(f'<option value="">— Global Shift Performance —</option>{options}')
