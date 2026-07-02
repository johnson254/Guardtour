from rest_framework import serializers

from api.models.device import Device, CallSign
from api.models.dispatch import ShiftAssignment
from api.models.scanning import ScanRecord
from api.models.patrol import Checkpoint


class DeviceSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    assigned_callsign = serializers.SerializerMethodField()
    assigned_guard_id = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    current_mission = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            'id', 'device_id', 'device_name', 'callsign', 'is_active', 'is_online',
            'last_seen', 'registered_at', 'organization', 'organization_name',
            'assigned_callsign', 'assigned_guard_id', 'status', 'current_mission',
            'imei', 'imsi', 'sim_phone_number', 'os_version', 'manufacturer', 'model', 'sdk_int',
            'nfc_mode', 'last_nfc_scan', 'last_nfc_scan_uid',
            'last_latitude', 'last_longitude', 'last_gps_accuracy', 'battery_pct',
            'nfc_fetch_requested', 'gps_fetch_requested', 'gps_accuracy_threshold',
            'tts_voice', 'tts_rate', 'tts_pitch',
            'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at',
            'tts_acked', 'last_reminder_at', 'geofence_states',
            'password',
        ]
        read_only_fields = [
            'id', 'registered_at', 'last_seen',
            'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at',
            'tts_voice', 'tts_rate', 'tts_pitch',
            'last_sequence_id', 'peer_session_key',
            'last_nfc_scan', 'last_nfc_scan_uid',
            'last_gps_accuracy', 'battery_pct',
        ]
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def get_device_name(self, obj: Device) -> str:
        return obj.device_name or obj.device_id or 'Device'

    def get_organization_name(self, obj: Device) -> str | None:
        return obj.organization.name if obj.organization else None

    def get_assigned_callsign(self, obj: Device) -> str | None:
        try:
            if hasattr(obj, 'active_callsign') and obj.active_callsign is not None:
                return obj.active_callsign.callsign
        except Exception:
            pass
        return obj.callsign

    def get_assigned_guard_id(self, obj: Device) -> int | None:
        try:
            if hasattr(obj, 'active_callsign') and obj.active_callsign and obj.active_callsign.current_guard:
                return obj.active_callsign.current_guard.id
        except Exception:
            pass
        return None

    def get_status(self, obj: Device) -> str:
        if not obj.is_online:
            return 'offline'
        from django.utils import timezone as dj_timezone
        now = dj_timezone.now()
        if obj.last_seen and (now - obj.last_seen).total_seconds() <= 120:
            return 'online'
        return 'idle'

    def get_current_mission(self, obj: Device) -> dict | None:
        from django.utils import timezone as dj_timezone
        from django.db.models import Q

        active = None
        if hasattr(obj, 'prefetched_active_shifts') and obj.prefetched_active_shifts:
            active = obj.prefetched_active_shifts[0]
        else:
            active = ShiftAssignment.objects.filter(
                device=obj, is_active=True, is_completed=False
            ).select_related('route', 'guard_supervisor').order_by('-assigned_at').first()

        if not active:
            return None

        total = 0
        completed = 0
        next_cp = None
        progress_pct = 0

        if active.route:
            today = dj_timezone.now().date()
            cps = active.route.checkpoints.filter(
                Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=today)
            )
            total = cps.count()

            if total > 0:
                scan_filter = {
                    'route': active.route,
                    'timestamp__gte': active.assigned_at,
                    'checkpoint__isnull': False,
                }
                if active.guard_supervisor:
                    scan_filter['guard_supervisor'] = active.guard_supervisor
                else:
                    scan_filter['device'] = obj

                hit_ids = set(
                    ScanRecord.objects.filter(**scan_filter)
                    .values_list('checkpoint_id', flat=True)
                    .distinct()
                )
                completed = len(hit_ids)
                progress_pct = int((completed / total) * 100) if total > 0 else 0

                for cp in cps.order_by('scheduled_date', 'order'):
                    if cp.id not in hit_ids:
                        next_cp = {
                            'id': cp.id,
                            'name': cp.name,
                            'planned_time': cp.planned_time.strftime('%H:%M') if cp.planned_time else None,
                            'scheduled_date': cp.scheduled_date.isoformat() if cp.scheduled_date else None,
                        }
                        break

        return {
            'assignment_id': active.id,
            'route_name': active.route.name if active.route else None,
            'shift_type': active.shift_type,
            'guard_name': f"{active.guard_supervisor.first_name} {active.guard_supervisor.last_name}".strip() if active.guard_supervisor else None,
            'total_checkpoints': total,
            'completed_checkpoints': completed,
            'progress_pct': progress_pct,
            'next_checkpoint': next_cp,
        }


class CallSignSerializer(serializers.ModelSerializer):
    device_name = serializers.SerializerMethodField()
    device_id_code = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    guard_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    active_mission = serializers.SerializerMethodField()

    def get_device_name(self, obj: CallSign) -> str | None:
        if obj.device:
            return obj.device.device_id or obj.device.device_name
        return None

    def get_device_id_code(self, obj: CallSign) -> str | None:
        if obj.device:
            return obj.device.device_id
        return None

    def get_last_seen(self, obj: CallSign) -> object:
        return obj.device.last_seen if obj.device else None

    def get_is_online(self, obj: CallSign) -> bool:
        return obj.device.is_online if obj.device else False

    def get_organization_name(self, obj: CallSign) -> str | None:
        return obj.organization.name if obj.organization else None

    def get_guard_name(self, obj: CallSign) -> str:
        if obj.current_guard:
            name = f"{obj.current_guard.first_name} {obj.current_guard.last_name}".strip()
            return name if name else obj.current_guard.callsign or "Unnamed"
        return 'Unassigned'

    def get_active_mission(self, obj: CallSign) -> str:
        if obj.current_guard:
            active = ShiftAssignment.objects.filter(
                guard_supervisor=obj.current_guard, is_active=True
            ).exclude(route=None).order_by('-assigned_at').first()
            return active.route.name if active and active.route else 'Standby / Free Patrol'
        return '\u2014'

    class Meta:
        model = CallSign
        fields = '__all__'
