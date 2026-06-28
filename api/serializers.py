import re
from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from .models import Organization, Admin, Dispatcher, GuardSupervisor, Device, PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, MapObject, IncidentReport, OperatorAlert, DeviceProvisioning, CallSign

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'contact_email', 'phone', 'address', 'default_time_tolerance', 'is_active', 'shift_mode', 'created_at']

class AdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Admin
        fields = '__all__'

class DispatcherSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    organization_name = serializers.SerializerMethodField()
    email = serializers.EmailField(write_only=True, required=False)
    username = serializers.CharField(write_only=True, required=False)
    
    def get_organization_name(self, obj):
        if obj.organization:
            return obj.organization.name
        return None
    
    def create(self, validated_data):
        validated_data.pop('user', None)
        organization = validated_data.pop('organization', None) # Pop organization here
        email = validated_data.pop('email', None)
        username = validated_data.pop('username', None)
        
        if username:
            user = User.objects.create_user(
                username=username,
                email=email or '',
                password=User.objects.make_random_password() # Assign a random password, user can change later
            )
        else:
            user = validated_data.get('user')
            if not user:
                raise serializers.ValidationError("User is required")
        
        dispatcher = Dispatcher.objects.create(user=user, organization=organization, **validated_data)
        return dispatcher
    
    class Meta:
        model = Dispatcher
        fields = ['id', 'user', 'organization', 'organization_name', 'username', 'email', 
                  'can_manage_routes', 'can_manage_guards', 'can_view_reports', 'can_manage_devices', 
                  'created_at']

class GuardSupervisorSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def validate_callsign(self, value):
        if value:
            # Enforce ORG-SEQ format: ^[A-Z]{2,4}-\d{2,}$
            if not re.match(r'^[A-Z]{2,4}-\d{2,}$', value):
                raise serializers.ValidationError("Operator ID must be ORG-NN format (e.g. TCN-01)")
        return value

    class Meta:
        model = GuardSupervisor
        fields = [
            'id',
            'first_name',
            'last_name',
            'callsign',
            'organization',
            'organization_name',
            'role',
            'shift',
            'is_on_shift',
            'nfc_tags_scanned',
            'last_scan',
            'created_at',
        ]


class DeviceSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    assigned_callsign = serializers.SerializerMethodField()
    assigned_guard_id = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    tts_pending = serializers.ReadOnlyField()

    class Meta:
        model = Device
        fields = '__all__'
        read_only_fields = ['tts_pending', 'tts_pending_at', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'last_sequence_id']

    def get_device_name(self, obj):
        return obj.device_name or obj.device_id or 'Device'

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def get_assigned_callsign(self, obj):
        """Return the callsign shown in the Manage → Devices UI.

        Priority:
        1) Latest active shift assignment for this device
        2) Latest provisioning binding (callsign_snapshot)
        """
        try:
            if hasattr(obj, 'active_callsign') and obj.active_callsign is not None:
                return obj.active_callsign.callsign
        except Exception:
            pass
        return obj.callsign
    
    def get_assigned_guard_id(self, obj):
        try:
            if hasattr(obj, 'active_callsign') and obj.active_callsign and obj.active_callsign.current_guard:
                return obj.active_callsign.current_guard.id
        except Exception:
            pass
        return None

class CallSignSerializer(serializers.ModelSerializer):
    device_name = serializers.SerializerMethodField()
    device_id_code = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    guard_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    active_mission = serializers.SerializerMethodField()

    def get_device_name(self, obj):
        if obj.device:
            return obj.device.device_id or obj.device.device_name
        return None

    def get_device_id_code(self, obj):
        if obj.device:
            return obj.device.device_id
        return None

    def get_last_seen(self, obj):
        if obj.device:
            return obj.device.last_seen
        return None

    def get_is_online(self, obj):
        if obj.device:
            return obj.device.is_online
        return False

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def get_guard_name(self, obj):
        if obj.current_guard:
            name = f"{obj.current_guard.first_name} {obj.current_guard.last_name}".strip()
            return name if name else obj.current_guard.callsign or "Unnamed"
        return 'Unassigned'

    def get_active_mission(self, obj):
        if obj.current_guard:
            # Fetch the most recent active shift that has an assigned route
            active = ShiftAssignment.objects.filter(
                guard_supervisor=obj.current_guard,
                is_active=True
            ).exclude(route=None).order_by('-assigned_at').first()
            return active.route.name if active and active.route else 'Standby / Free Patrol'
        return '—'

    class Meta:
        model = CallSign
        fields = '__all__'

class CheckpointSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    asset_class = serializers.CharField(default='checkpoint', read_only=True)
    type = serializers.CharField(default='poi', read_only=True)
    geometry = serializers.SerializerMethodField()
    route = serializers.PrimaryKeyRelatedField(
        queryset=PatrolRoute.objects.all(), required=False, allow_null=True
    )

    def get_organization_name(self, obj):
        if obj.organization:
            return obj.organization.name
        if obj.route and obj.route.organization:
            return obj.route.organization.name
        return None

    def get_geometry(self, obj):
        if obj.lat is not None and obj.lng is not None:
            return [obj.lat, obj.lng]
        return None

    class Meta:
        model = Checkpoint
        fields = [
            'id', 'name', 'nfc_tag', 'lat', 'lng', 'order', 'planned_time', 
            'time_tolerance', 'dwell_time', 'radius', 'precision_level', 'route', 'organization',
            'checkpoint_type', 'organization_name', 'asset_class', 'type', 'geometry',
            'next_announcement_text'
        ]
        read_only_fields = ['organization']

    def validate(self, data):
        cp_type = data.get('checkpoint_type')
        if cp_type == 'nfc' and not data.get('nfc_tag'):
            raise serializers.ValidationError({'nfc_tag': 'NFC tag required for NFC checkpoints.'})
        if cp_type == 'gps' and (data.get('lat') is None or data.get('lng') is None):
            raise serializers.ValidationError({'lat': 'GPS coordinates required for GPS checkpoints.'})
        if cp_type == 'nfc':
            data['lat'] = None
            data['lng'] = None
        if cp_type == 'gps':
            data['nfc_tag'] = None
        if cp_type == 'peer':
            data['nfc_tag'] = None
            data['lat'] = None
            data['lng'] = None
        if cp_type == 'geo':
            data['nfc_tag'] = None

        # Prevent duplicate planned_time within same route
        planned_time = data.get('planned_time')
        route = data.get('route') or (self.instance.route_id if self.instance else None)
        if planned_time and route:
            dupes = Checkpoint.objects.filter(route=route, planned_time=planned_time)
            if self.instance and self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                raise serializers.ValidationError({'planned_time': f'Another checkpoint in this route already has planned time {planned_time}.'})

        return data

class PatrolRouteSerializer(serializers.ModelSerializer):
    checkpoints = CheckpointSerializer(many=True, required=False)
    organization_name = serializers.SerializerMethodField()
    checkpoint_count = serializers.SerializerMethodField()
    device_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    logic_type = serializers.CharField(required=False)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, allow_null=True)

    def get_checkpoint_count(self, obj):
        try:
            return obj.checkpoints.count()
        except Exception:
            return 0

    def get_device_count(self, obj):
        try:
            return obj.assigned_devices.count()
        except Exception:
            return 0

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        obj = instance
        # Map model flags back to UI logic string
        try:
            if getattr(obj, 'is_audit', False): ret['logic_type'] = "Audit"
            elif getattr(obj, 'is_emergency', False): ret['logic_type'] = "Emergency"
            
            elif getattr(obj, 'enforce_order', False) and getattr(obj, 'enforce_time', False):
                ret['logic_type'] = "Scheduled"
            elif getattr(obj, 'enforce_order', False) and not getattr(obj, 'enforce_time', False):
                ret['logic_type'] = "Sequential"
            elif not getattr(obj, 'enforce_order', False) and not getattr(obj, 'enforce_time', False):
                ret['logic_type'] = "Flexible"
            else:
                ret['logic_type'] = "Custom"
        except Exception:
            ret['logic_type'] = "Flexible"
        return ret

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    class Meta:
        model = PatrolRoute
        fields = [
            'id', 'name', 'description', 'status', 'frequency', 'scheduled_date', 'enforce_order', 'enforce_time',
            'is_geofence', 'is_emergency', 'is_audit', 'is_daily', 'scheduled_start_time', 'send_start_alert',
            'send_announcement', 'start_alert_lead_time', 'readout_text', 'tts_voice', 'tts_rate', 'tts_pitch', 'assigned_guards', 'assigned_devices',
            'checkpoints', 'organization', 'organization_name', 'checkpoint_count', 'device_count', 'logic_type', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['created_by']

    def _map_logic_to_flags(self, attrs):
        """Translate UI logic_type string into model boolean enforcement flags."""
        lt = attrs.pop('logic_type', None)
        if lt:
            if lt == "Flexible":
                attrs['enforce_order'] = False
                attrs['enforce_time'] = False
                attrs['is_audit'] = False
            elif lt == "Sequential":
                attrs['enforce_order'] = True
                attrs['enforce_time'] = False
                attrs['is_audit'] = False
            elif lt == "Scheduled":
                attrs['enforce_order'] = True
                attrs['enforce_time'] = True
                attrs['is_audit'] = False
            elif lt == "Audit":
                attrs['enforce_order'] = True
                attrs['enforce_time'] = True
                attrs['is_audit'] = True
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        checkpoints_data = validated_data.pop('checkpoints', [])
        assigned_guards_data = validated_data.pop('assigned_guards', [])
        assigned_devices_data = validated_data.pop('assigned_devices', [])
        validated_data = self._map_logic_to_flags(validated_data)
        route = PatrolRoute.objects.create(**validated_data)
        route.assigned_guards.set(assigned_guards_data)
        route.assigned_devices.set(assigned_devices_data)
        for checkpoint_data in checkpoints_data:
            Checkpoint.objects.create(route=route, organization=route.organization, **checkpoint_data)
        return route

    @transaction.atomic
    def update(self, instance, validated_data):
        checkpoints_data = validated_data.pop('checkpoints', None)
        assigned_guards_data = validated_data.pop('assigned_guards', None)
        assigned_devices_data = validated_data.pop('assigned_devices', None)
        validated_data = self._map_logic_to_flags(validated_data)
        
        # Update basic PatrolRoute fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if assigned_guards_data is not None:
            instance.assigned_guards.set(assigned_guards_data)

        if assigned_devices_data is not None:
            instance.assigned_devices.set(assigned_devices_data)

        if checkpoints_data is not None:
            existing = {cp.id: cp for cp in instance.checkpoints.all()}
            seen_ids = set()
            for checkpoint_data in checkpoints_data:
                cp_id = checkpoint_data.pop('id', None)
                if cp_id and cp_id in existing:
                    cp = existing[cp_id]
                    for attr, value in checkpoint_data.items():
                        setattr(cp, attr, value)
                    cp.save()
                    seen_ids.add(cp_id)
                else:
                    Checkpoint.objects.create(route=instance, organization=instance.organization, **checkpoint_data)
            for cp_id, cp in existing.items():
                if cp_id not in seen_ids:
                    cp.delete()
        
        return instance

class ScanRecordSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    guard_callsign = serializers.SerializerMethodField()
    guard_shift = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    device_id_code = serializers.SerializerMethodField()
    route_name = serializers.SerializerMethodField()
    route_id = serializers.SerializerMethodField()

    def get_user_name(self, obj):
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return 'Unknown'

    def get_guard_callsign(self, obj):
        return obj.guard_supervisor.callsign if obj.guard_supervisor else None

    def get_guard_shift(self, obj):
        return obj.guard_supervisor.shift if obj.guard_supervisor else None

    def get_device_name(self, obj):
        return (obj.device.device_id or obj.device.device_name) if obj.device else 'External/Virtual'

    def get_device_id_code(self, obj):
        return obj.device.device_id if obj.device else None

    def get_route_name(self, obj):
        return obj.route.name if obj.route else 'Unassigned/Free Patrol'

    def get_route_id(self, obj):
        return obj.route.id if obj.route else None

    class Meta:
        model = ScanRecord
        fields = ['id', 'timestamp', 'client_timestamp', 'server_received_timestamp', 'sequence_id', 'time_drift_seconds',
                  'guard_supervisor', 'user_name', 'guard_callsign',
                  'guard_shift', 'device', 'device_name', 'device_id_code', 'route', 'route_name', 'route_id',
                  'checkpoint', 'checkpoint_name', 'nfc_value', 'is_on_time', 'lat', 'lng',
                  'raw_nfc', 'scan_type', 'validity_score', 'validity_reason',
                  'out_of_sequence', 'insufficient_dwell_time', 'dwell_seconds']

class ShiftAssignmentSerializer(serializers.ModelSerializer):
    # Ensure dispatcher comes from request.user (set in ShiftAssignmentViewSet.perform_create)
    dispatcher = serializers.PrimaryKeyRelatedField(read_only=True)
    dispatcher_name = serializers.SerializerMethodField()

    guard_supervisor_name = serializers.SerializerMethodField()
    guard_supervisor_id = serializers.SerializerMethodField()
    guard_callsign = serializers.SerializerMethodField()

    device_name = serializers.SerializerMethodField()
    device_id_code = serializers.SerializerMethodField()

    route_name = serializers.SerializerMethodField()
    route_id = serializers.SerializerMethodField()

    total_checkpoints = serializers.IntegerField(read_only=True)
    completed_checkpoints = serializers.IntegerField(read_only=True)

    def get_dispatcher_name(self, obj):
        return obj.dispatcher.username if obj.dispatcher else None

    def get_guard_supervisor_name(self, obj):
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return 'Device Only'

    def get_guard_supervisor_id(self, obj):
        return obj.guard_supervisor.id if obj.guard_supervisor else None

    def get_guard_callsign(self, obj):
        return obj.guard_supervisor.callsign if obj.guard_supervisor else None

    def get_device_name(self, obj):
        return (obj.device.device_id or obj.device.device_name) if obj.device else None

    def get_device_id_code(self, obj):
        return obj.device.device_id if obj.device else None

    def get_route_name(self, obj):
        return obj.route.name if obj.route else None

    def get_route_id(self, obj):
        return obj.route.id if obj.route else None

    def validate(self, data):
        guard = data.get('guard_supervisor') or (self.instance.guard_supervisor if self.instance else None)
        s_start = data.get('scheduled_start') or (self.instance.scheduled_start if self.instance else None)
        s_end = data.get('scheduled_end') or (self.instance.scheduled_end if self.instance else None)
        if guard and s_start and s_end:
            qs = ShiftAssignment.objects.filter(
                guard_supervisor=guard,
                is_active=True,
                scheduled_start__lt=s_end,
                scheduled_end__gt=s_start,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    f"Guard already has an active shift overlapping with {s_start} - {s_end}"
                )
        return data

    class Meta:
        model = ShiftAssignment
        fields = [
            'id', 'dispatcher', 'dispatcher_name', 'guard_supervisor', 'guard_supervisor_id', 
            'guard_supervisor_name', 'guard_callsign', 'device', 'device_name', 'device_id_code', 
            'route', 'route_id', 'route_name', 'scheduled_date', 'scheduled_start', 'scheduled_end',
            'shift_type', 'is_active', 'is_completed', 'status', 'assigned_at', 'ended_at', 
            'total_checkpoints', 'completed_checkpoints'
        ]
        read_only_fields = ['dispatcher', 'assigned_at']


class GeometryField(serializers.Field):
    """Accepts [lat, lng] arrays and returns [lat, lng] — writable, unlike SerializerMethodField."""

    def to_representation(self, value):
        if not value:
            return None
        if isinstance(value, dict):
            coords = value.get('coordinates')
            if coords and isinstance(coords, list) and len(coords) >= 2:
                return [coords[1], coords[0]]
        if isinstance(value, list) and len(value) >= 2:
            return value
        return None

    def to_internal_value(self, data):
        if data is None:
            return None
        if isinstance(data, list) and len(data) >= 2:
            return data
        raise serializers.ValidationError("Geometry must be a [lat, lng] array or null")


class MapObjectSerializer(serializers.ModelSerializer):
    personnel_details = GuardSupervisorSerializer(source='assigned_personnel', many=True, read_only=True)
    asset_class = serializers.CharField(default='intelligence', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    entry_msg = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    exit_msg = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    geo_shape = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    geometry = GeometryField(allow_null=True, required=False)

    class Meta:
        model = MapObject
        fields = [
            'id', 'organization', 'name', 'type', 'geometry', 'radius', 
            'assigned_personnel', 'personnel_details', 'asset_class', 'created_at',
            'entry_msg', 'exit_msg', 'geo_shape', 'intrusion_alarm', 'fetch_location_on_scan',
            'planned_duration_minutes'
        ]

    def validate(self, data):
        type_val = data.get('type')
        if type_val == 'geofence' and data.get('geometry') is None:
            raise serializers.ValidationError("A Geofence must have geometry.")
        return data

class IncidentReportSerializer(serializers.ModelSerializer):
    guard_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    def get_guard_name(self, obj):
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return "System"

    class Meta:
        model = IncidentReport
        fields = '__all__'

class OperatorAlertSerializer(serializers.ModelSerializer):
    operator_name = serializers.SerializerMethodField()
    def get_operator_name(self, obj):
        return obj.operator.first_name if obj.operator else None
    class Meta:
        model = OperatorAlert
        fields = '__all__'
