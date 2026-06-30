from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


@login_required
def dashboard_page(request):
    from api.views.reports import organization_stats
    stats_response = organization_stats(request)
    context = stats_response.data if hasattr(stats_response, 'data') else {}

    # Add dashboard-specific data
    user = request.user
    from api.models import GuardSupervisor, ShiftAssignment, IncidentReport, Device

    if user.is_superuser or hasattr(user, 'admin_profile'):
        guards = GuardSupervisor.objects.all()
        active_assignments = ShiftAssignment.objects.filter(is_active=True)
        incidents = IncidentReport.objects.filter(is_resolved=False)
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        guards = GuardSupervisor.objects.filter(organization=org) if org else GuardSupervisor.objects.none()
        active_assignments = ShiftAssignment.objects.filter(
            guard_supervisor__organization=org, is_active=True
        ) if org else ShiftAssignment.objects.none()
        incidents = IncidentReport.objects.filter(organization=org, is_resolved=False) if org else IncidentReport.objects.none()
    else:
        guards = GuardSupervisor.objects.none()
        active_assignments = ShiftAssignment.objects.none()
        incidents = IncidentReport.objects.none()

    context['on_duty_guards'] = guards.filter(is_on_shift=True).select_related('organization')[:12]
    context['active_deployments'] = active_assignments.select_related('route', 'guard_supervisor', 'device')[:10]
    context['unresolved_incidents_count'] = incidents.count()

    return render(request, 'dashboard.html', context)


@login_required
def map_view_page(request):
    return render(request, 'map_view.html')


@login_required
def routes_page(request):
    return render(request, 'routes.html')


@login_required
def mission_builder_page(request):
    """Redirect to routes page (Mission Builder is now integrated into routes)."""
    from django.http import HttpResponseRedirect
    resp = HttpResponseRedirect('/routes/')
    # If htmx request, use HX-Redirect for SPA navigation
    if request.headers.get('HX-Request'):
        resp = HttpResponseRedirect('/routes/')
        resp['HX-Redirect'] = '/routes/'
    return resp


@login_required
def peer_rules_page(request):
    return render(request, 'peer_rules.html')


@login_required
def dispatch_page(request):
    return render(request, 'dispatch.html')


@login_required
def incidents_page(request):
    return render(request, 'incidents.html')


@login_required
def guards_page(request):
    return render(request, 'guards.html')


@login_required
def manage_page(request):
    return render(request, 'manage.html')


@login_required
def reports_page(request):
    return render(request, 'reports.html')


@login_required
def admin_panel_page(request):
    return render(request, 'admin_panel.html')


def login_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'login.html')


def register_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'register.html')
