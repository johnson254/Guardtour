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


@api_view(['GET'])
@login_required
def dispatch_stats_partial(request):
    """Return HTML fragment of mission stats for htmx polling."""
    from django.utils import timezone as dj_timezone
    user = request.user
    assignments = _resolve_assignment_queryset(user).select_related('route')

    active_qs = assignments.filter(is_active=True, is_completed=False)
    completed_qs = assignments.filter(is_completed=True)
    pending_qs = assignments.filter(is_active=False, is_completed=False)

    active_count = sum(1 for a in active_qs if a.route_id)
    pending_count = sum(1 for a in pending_qs if a.route_id)
    completed_count = completed_qs.count()

    on_duty_guards = set()
    for a in active_qs:
        if a.route_id and a.guard_supervisor_id:
            on_duty_guards.add(a.guard_supervisor_id)

    daily_count = _resolve_route_queryset(user).filter(is_daily=True).exclude(status='archived').count()

    return HttpResponse(render_to_string('partials/dispatch/stats.html', {
        'active_count': active_count,
        'on_duty_count': len(on_duty_guards),
        'pending_count': pending_count,
        'daily_count': daily_count,
    }, request=request))


@api_view(['GET'])
@login_required
def deployment_live_partial(request):
    """Return HTML fragment of live deployment checkpoint data for htmx polling."""
    from django.utils import timezone as dj_timezone
    from api.models import ScanRecord, Checkpoint
    from django.db.models import Q

    user = request.user
    assignments = _resolve_assignment_queryset(user).filter(
        is_active=True, is_completed=False
    ).select_related('route', 'guard_supervisor', 'device')

    now = dj_timezone.now()
    live_data = {}

    for a in assignments:
        route = a.route
        if not route:
            continue
        cps = list(route.checkpoints.filter(
            Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=now.date())
        ).order_by('scheduled_date', 'order'))

        scan_filter = {'route': route, 'timestamp__gte': a.assigned_at, 'checkpoint__isnull': False}
        if a.guard_supervisor:
            scan_filter['guard_supervisor'] = a.guard_supervisor
        else:
            scan_filter['device'] = a.device

        hit_ids = set(ScanRecord.objects.filter(**scan_filter).values_list('checkpoint_id', flat=True).distinct())
        has_missed = False
        next_cp = None
        for cp in cps:
            if cp.id not in hit_ids:
                next_cp = cp
                missed = False
                if cp.planned_time and cp.scheduled_date:
                    planned_dt = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(cp.scheduled_date, cp.planned_time),
                        timezone=now.tzinfo,
                    )
                    deadline = planned_dt + dj_timezone.timedelta(minutes=cp.time_tolerance + cp.dwell_time)
                    missed = now > deadline
                    if missed:
                        has_missed = True
                elif cp.planned_time:
                    planned_dt = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(now.date(), cp.planned_time),
                        timezone=now.tzinfo,
                    )
                    deadline = planned_dt + dj_timezone.timedelta(minutes=cp.time_tolerance + cp.dwell_time)
                    missed = now > deadline
                    if missed:
                        has_missed = True
                break

        progress_pct = int((len(hit_ids) / len(cps)) * 100) if cps else 0
        live_data[a.id] = {
            'has_missed_checkpoints': has_missed,
            'hit_count': len(hit_ids),
            'total': len(cps),
            'progress_pct': progress_pct,
            'next_cp_name': next_cp.name if next_cp else None,
            'next_cp_time': next_cp.planned_time.strftime('%H:%M') if next_cp and next_cp.planned_time else None,
        }

    return HttpResponse(render_to_string('partials/dispatch/live_data.html', {
        'live_data': live_data,
    }, request=request))
