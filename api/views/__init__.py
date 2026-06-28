"""
API views package.
DRF ViewSets and function-based JSON API views are in views/core.py.
htmx HTML partial views are in views/partials/.
"""
# Re-export everything from core module for backward compatibility
from api.views.core import (
    # ViewSets
    OrganizationViewSet, AdminViewSet, DispatcherViewSet,
    GuardSupervisorViewSet, CallSignViewSet, DeviceViewSet,
    PatrolRouteViewSet, CheckpointViewSet, ScanRecordViewSet,
    ShiftAssignmentViewSet, MapObjectViewSet, IncidentReportViewSet,
    OperatorAlertViewSet,
    # Auth views
    register, login, login_page, register_page,
    # Device views
    register_device, provision_device, heartbeat,
    # Profile views
    profile_list, profile_detail,
    # Shift views
    end_shift, assign_guard_to_blueprint_shift, blueprint_shift_availability,
    # Misc API
    admin_stats, organization_stats, operator_id_next, generate_operator_id,
    deployment_checkpoint_live, resend_tts, mission_status, transfer_shift,
    route_gap_analysis_view, gps_batch_sync, scan_batch_sync,
    device_trails, device_recent_scans, seed_attendance,
     # Page renders
     dashboard_page, map_view_page, routes_page, dispatch_page,
     incidents_page, guards_page, manage_page, reports_page, admin_panel_page,
     logout_view, custom_404, custom_500,
    # Helpers
    _deactivate_assignments, _resolve_guard_queryset, _profile_create_or_update,
)

# Re-export partials for backward compatibility
from api.views.partials.guards import guards_partial, guard_form_partial
from api.views.partials.reports import scans_table_partial, reports_guards_options_partial, reports_routes_options_partial
from api.views.partials.admin import admin_stats_partial
from api.views.partials.incidents import incidents_partial, incidents_guards_options_partial
from api.views.partials.options import alerts_partial
from api.views.partials.routes import routes_list_partial, route_editor_partial
from api.views.partials.dispatch import blueprints_partial, missions_partial
from api.views.partials.manage import devices_list_partial, checkpoints_list_partial, staff_panel_partial, fleet_panel_partial, audit_panel_partial
