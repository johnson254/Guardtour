from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
import api.scan_guards_views as scan_guards_views
from .views import OrganizationViewSet, AdminViewSet, DispatcherViewSet, GuardSupervisorViewSet, CallSignViewSet, DeviceViewSet, PatrolRouteViewSet, CheckpointViewSet, ScanRecordViewSet, ShiftAssignmentViewSet, MapObjectViewSet, IncidentReportViewSet, OperatorAlertViewSet

router = DefaultRouter()
router.register('organizations', OrganizationViewSet, basename='organization')
router.register('admins', AdminViewSet, basename='admin')
router.register('dispatchers', DispatcherViewSet, basename='dispatcher')
router.register('guards', GuardSupervisorViewSet, basename='guardsupervisor')
router.register('callsigns', CallSignViewSet, basename='callsign')
router.register('devices', DeviceViewSet, basename='device')
router.register('routes', PatrolRouteViewSet, basename='patrolroute')
router.register('checkpoints', CheckpointViewSet, basename='checkpoint')
router.register('scans', ScanRecordViewSet, basename='scanrecord')
router.register('shifts', ShiftAssignmentViewSet, basename='shiftassignment')
router.register('map-objects', MapObjectViewSet, basename='mapobject')
router.register('incidents', IncidentReportViewSet, basename='incidentreport')
router.register('alerts', OperatorAlertViewSet, basename='operatoralert')

_api_v1_patterns = [
    path('auth/', include([
        path('register/', views.register, name='register'),
        path('login/', views.login, name='login'),
    ])),
    path('devices/', include([
        path('register/', views.register_device, name='register-device'),
        path('scans/', views.device_recent_scans, name='device-scans'),
        path('mission/', views.my_mission, name='my-mission'),
    ])),
    path('sync/', include([
        path('gps-batch/', views.gps_batch_sync, name='gps-batch'),
        path('scan-batch/', views.scan_batch_sync, name='scan-batch'),
        path('scan/', views.ScanRecordViewSet.as_view({'create': 'create'}), name='scan-create'),
    ])),
    path('missions/', include([
        path('<int:assignment_id>/status/', views.mission_status, name='mission-status'),
        path('<int:assignment_id>/gap-analysis/', views.route_gap_analysis_view, name='route-gap-analysis'),
        path('<int:pk>/end/', views.end_shift, name='end-shift'),
        path('transfer/', views.transfer_shift, name='transfer-shift'),
    ])),
    path('checkpoints/', include([
        path('schedule/', views.schedule_checkpoints, name='schedule-checkpoints'),
        path('bulk-schedule/', views.bulk_schedule_checkpoints, name='bulk-schedule-checkpoints'),
    ])),
    path('routes/', include([
        path('<int:route_id>/scheduled-checkpoints/', views.scheduled_checkpoints, name='scheduled-checkpoints'),
        path('<int:route_id>/peer-audit/', views.peer_audit_report, name='peer-audit'),
    ])),
    path('audit/', include([
        path('create-shift/', views.create_audit_shift, name='create-audit-shift'),
    ])),
    path('reports/', include([
        path('admin-stats/', views.admin_stats, name='admin-stats'),
        path('org-stats/', views.organization_stats, name='org-stats'),
    ])),
    path('', include(router.urls)),
]

urlpatterns = [
    # v1 API (stable, versioned contract for external clients)
    path('v1/', include((_api_v1_patterns, 'v1'))),

    # Legacy unversioned API (used by internal frontend/htmx partials)
    path('', include(router.urls)),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('register-device/', views.register_device, name='register_device'),
    path('heartbeat/', views.heartbeat, name='heartbeat'),
    path('admin-stats/', views.admin_stats, name='admin_stats'),
    path('org-stats/', views.organization_stats, name='org_stats'),
    path('alerts-partial/', views.alerts_partial, name='alerts_partial'),
    path('scans-table-partial/', views.scans_table_partial, name='scans_table_partial'),
    path('admin-stats-partial/', views.admin_stats_partial, name='admin_stats_partial'),
    path('org-stats-partial/', views.org_stats_partial, name='org_stats_partial'),
    path('incidents-partial/', views.incidents_partial, name='incidents_partial'),
    path('reports-guards-options-partial/', views.reports_guards_options_partial, name='reports_guards_options_partial'),
    path('reports-routes-options-partial/', views.reports_routes_options_partial, name='reports_routes_options_partial'),
    path('incidents-guards-options-partial/', views.incidents_guards_options_partial, name='incidents_guards_options_partial'),
    path('profiles/', views.profile_list, name='profile_list'),
    path('profiles/<int:pk>/', views.profile_detail, name='profile_detail'),
    path('guards-partial/', views.guards_partial, name='guards_partial'),
    path('guard-form-partial/<str:pk>/', views.guard_form_partial, name='guard_form_partial'),
    path('routes-list-partial/', views.routes_list_partial, name='routes_list_partial'),
    path('route-editor-partial/<int:pk>/', views.route_editor_partial, name='route_editor_partial'),
    path('blueprints-partial/', views.blueprints_partial, name='blueprints_partial'),
    path('missions-partial/', views.missions_partial, name='missions_partial'),
    path('devices-partial/', views.devices_list_partial, name='devices_list_partial'),
    path('checkpoints-partial/', views.checkpoints_list_partial, name='checkpoints_list_partial'),
    path('staff-panel-partial/', views.staff_panel_partial, name='staff_panel_partial'),
    path('fleet-panel-partial/', views.fleet_panel_partial, name='fleet_panel_partial'),
    path('audit-panel-partial/', views.audit_panel_partial, name='audit_panel_partial'),
    path('end-shift/<int:pk>/', views.end_shift, name='end_shift'),

    # Scan-only guard/supervisor creation (no Django auth user)
    path('scan-guards/', scan_guards_views.create_scan_guard, name='create_scan_guard'),

    # Provision device hardware_id -> guard callsign and create active assignment
    path('provision-device/', views.provision_device, name='provision_device'),

    # Blueprint-aware shift availability + unified assignment
    path('blueprint-shift-availability/', views.blueprint_shift_availability, name='blueprint_shift_availability'),
    path('assign-guard-to-blueprint-shift/', views.assign_guard_to_blueprint_shift, name='assign_guard_to_blueprint_shift'),

    # Live checkpoint tracking for dispatch console
    path('deployment-checkpoint-live/', views.deployment_checkpoint_live, name='deployment_checkpoint_live'),

    # Mission staging: single assignment status (used by app + frontend)
    path('mission-status/<int:assignment_id>/', views.mission_status, name='mission_status'),
    # Device self-service: get current mission by device auth (no assignment_id needed)
    path('my-mission/', views.my_mission, name='my_mission'),

    # Shift handover: transfer a partially completed route to another guard
    path('transfer-shift/', views.transfer_shift, name='transfer_shift'),

    # Route gap analysis: identify missed checkpoints for an assignment
    path('route-gap-analysis/<int:assignment_id>/', views.route_gap_analysis_view, name='route_gap_analysis'),

    # Resend TTS announcement for a deployment
    path('resend-tts/', views.resend_tts, name='resend_tts'),
    path('map-residency/', views.map_residency_events, name='map_residency_events'),

    # Offline sync: batch GPS + scan upload
    path('gps-batch/', views.gps_batch_sync, name='gps_batch_sync'),
    path('scan-batch/', views.scan_batch_sync, name='scan_batch_sync'),

    # Device trail retrieval
    path('device-trails/<str:device_id>/', views.device_trails, name='device_trails'),

    # Next operator ID for a given organization (ORG-SEQ)
    path('operator-id-next/', views.operator_id_next, name='operator_id_next'),

    # Device-authenticated recent scans (for Android app dashboard)
    path('device-scans/', views.device_recent_scans, name='device_recent_scans'),

    # Scheduled checkpoints (future days per hour)
    path('checkpoints/schedule/', views.schedule_checkpoints, name='schedule_checkpoints'),
    path('checkpoints/bulk-schedule/', views.bulk_schedule_checkpoints, name='bulk_schedule_checkpoints'),
    path('routes/<int:route_id>/scheduled-checkpoints/', views.scheduled_checkpoints, name='scheduled_checkpoints'),

    # Peer audit report (for audit routes)
    path('routes/<int:route_id>/peer-audit/', views.peer_audit_report, name='peer_audit_report'),

    # Seed attendance data for testing
    path('seed-attendance/', views.seed_attendance, name='seed_attendance'),
]

