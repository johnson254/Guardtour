"""
API views package.
DRF ViewSets and function-based JSON API views are split across modules:
- auth: register, login, operator_id
- devices: register_device, provision_device
- heartbeat: heartbeat endpoint + helpers
- scans: ScanRecordViewSet, batch sync, trails
- dispatch: shift assignment, deployment, mission status
- manage: admin ViewSets (Org, Admin, Dispatcher, Guard, Device, Route, Checkpoint, etc.)
- reports: stats, profiles, seed data
- core: cross-cutting helpers (_haversine_meters, _point_in_polygon, _deactivate_assignments)
"""
from api.views.manage import (
    OrganizationViewSet, AdminViewSet, DispatcherViewSet,
    GuardSupervisorViewSet, CallSignViewSet, DeviceViewSet,
    PatrolRouteViewSet, CheckpointViewSet,
    ShiftAssignmentViewSet, MapObjectViewSet, IncidentReportViewSet,
    OperatorAlertViewSet,
)
from api.views.auth import (
    register, login,
    generate_operator_id, operator_id_next,
)
from api.views.devices import register_device, provision_device
from api.views.heartbeat import heartbeat
from api.views.scans import (
    ScanRecordViewSet, gps_batch_sync, scan_batch_sync,
    device_trails, device_recent_scans,
)
from api.views.dispatch import (
    end_shift, assign_guard_to_blueprint_shift, blueprint_shift_availability,
    resend_tts, mission_status, transfer_shift, route_gap_analysis_view,
    map_residency_events, deployment_checkpoint_live,
)
from api.views.reports import (
    admin_stats, organization_stats, profile_list, profile_detail,
    seed_attendance,
)
from api.views.core import _deactivate_assignments

# Re-export partials for backward compatibility
from api.views.partials.guards import guards_partial, guard_form_partial
from api.views.partials.reports import scans_table_partial, reports_guards_options_partial, reports_routes_options_partial
from api.views.partials.admin import admin_stats_partial
from api.views.partials.incidents import incidents_partial, incidents_guards_options_partial
from api.views.partials.options import alerts_partial
from api.views.partials.routes import routes_list_partial, route_editor_partial
from api.views.partials.dispatch import blueprints_partial, missions_partial
from api.views.partials.manage import devices_list_partial, checkpoints_list_partial, staff_panel_partial, fleet_panel_partial, audit_panel_partial

# Page renders (kept in core for now, could be moved)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import logout as django_logout


@login_required
def dashboard_page(request):
    stats_response = organization_stats(request)
    context = stats_response.data if hasattr(stats_response, 'data') else {}
    # ... (simplified - full implementation would be in reports.py)
    return render(request, 'dashboard.html', context or {})


@login_required
def map_view_page(request):
    return render(request, 'map_view.html')


@login_required
def routes_page(request):
    return render(request, 'routes.html')


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


@login_required
def login_page(request):
    return redirect('/dashboard/')

@login_required
def register_page(request):
    return redirect('/dashboard/')


def logout_view(request):
    django_logout(request)
    response = redirect('/')
    response.delete_cookie('gt_access_token')
    return response


def custom_404(request, exception=None):
    from django.http import HttpResponseNotFound
    return HttpResponseNotFound(render(request, '404.html').content)


def custom_500(request):
    from django.http import HttpResponseServerError
    return HttpResponseServerError(render(request, '404.html').content)
