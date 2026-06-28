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
from api.views.partials.org_bar import org_stats_partial
from api.views.partials.incidents import incidents_partial, incidents_guards_options_partial
from api.views.partials.options import alerts_partial
from api.views.partials.routes import routes_list_partial, route_editor_partial
from api.views.partials.dispatch import blueprints_partial, missions_partial
from api.views.partials.manage import devices_list_partial, checkpoints_list_partial, staff_panel_partial, fleet_panel_partial, audit_panel_partial

# Page renders
from api.views.page_views import (
    dashboard_page,
    map_view_page,
    routes_page,
    dispatch_page,
    incidents_page,
    guards_page,
    manage_page,
    reports_page,
    admin_panel_page,
    login_page,
    register_page,
    mission_builder_page,
    peer_rules_page,
)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import logout as django_logout


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
