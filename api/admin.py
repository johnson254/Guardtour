from django.contrib import admin
from .models import (
    Organization, Admin, Dispatcher, GuardSupervisor, Device, 
    PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, 
    OperatorAlert, IncidentReport, DeviceProvisioning
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_email', 'created_at')
    search_fields = ('name', 'contact_email')

@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    filter_horizontal = ('organizations',)

@admin.register(Dispatcher)
class DispatcherAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'created_at')
    list_filter = ('organization',)
    search_fields = ('user__username',)

@admin.register(GuardSupervisor)
class GuardSupervisorAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'organization', 'role', 'shift', 'is_on_shift', 'nfc_tags_scanned')
    list_filter = ('role', 'shift', 'is_on_shift', 'organization')
    search_fields = ('first_name', 'last_name', 'callsign')

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'callsign', 'organization', 'is_online', 'registered_at')
    list_filter = ('is_online', 'organization')
    search_fields = ('device_id', 'device_name', 'callsign')

@admin.register(PatrolRoute)
class PatrolRouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'enforce_order', 'enforce_time', 'is_geofence', 'scheduled_start_time')
    list_filter = ('organization', 'enforce_order', 'enforce_time', 'is_geofence')
    search_fields = ('name', 'description')

@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'route', 'nfc_tag', 'order')
    list_filter = ('route__organization',)
    search_fields = ('name', 'nfc_tag')

@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = ('guard_supervisor', 'device', 'checkpoint_name', 'route', 'is_on_time', 'timestamp')
    list_filter = ('is_on_time', 'timestamp')
    search_fields = ('checkpoint_name', 'nfc_value')

@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('guard_supervisor', 'device', 'dispatcher', 'shift_type', 'is_active', 'assigned_at')
    list_filter = ('shift_type', 'is_active', 'guard_supervisor__organization')
    search_fields = ('guard_supervisor__first_name', 'guard_supervisor__last_name')

@admin.register(OperatorAlert)
class OperatorAlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'operator', 'priority', 'is_read', 'created_at')
    list_filter = ('priority', 'is_read', 'organization')
    search_fields = ('title', 'operator__first_name', 'operator__last_name')

@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'guard_supervisor', 'is_resolved', 'timestamp')
    list_filter = ('category', 'is_resolved', 'organization')
    search_fields = ('title', 'guard_supervisor__first_name', 'guard_supervisor__last_name')


@admin.register(DeviceProvisioning)
class DeviceProvisioningAdmin(admin.ModelAdmin):
    list_display = ('device', 'guard', 'callsign_snapshot', 'organization', 'created_at')
    list_filter = ('organization', 'created_at')
    search_fields = ('callsign_snapshot', 'device__device_id', 'guard__callsign')
