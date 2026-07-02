from rest_framework import serializers

from api.models.scanning import ScanRecord


class ScanRecordSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    guard_callsign = serializers.SerializerMethodField()
    guard_shift = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    device_id_code = serializers.SerializerMethodField()
    route_name = serializers.SerializerMethodField()
    route_id = serializers.SerializerMethodField()

    def get_user_name(self, obj: ScanRecord) -> str:
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return 'Unknown'

    def get_guard_callsign(self, obj: ScanRecord) -> str | None:
        return obj.guard_supervisor.callsign if obj.guard_supervisor else None

    def get_guard_shift(self, obj: ScanRecord) -> str | None:
        return obj.guard_supervisor.shift if obj.guard_supervisor else None

    def get_device_name(self, obj: ScanRecord) -> str:
        return (obj.device.device_id or obj.device.device_name) if obj.device else 'External/Virtual'

    def get_device_id_code(self, obj: ScanRecord) -> str | None:
        return obj.device.device_id if obj.device else None

    def get_route_name(self, obj: ScanRecord) -> str:
        return obj.route.name if obj.route else 'Unassigned/Free Patrol'

    def get_route_id(self, obj: ScanRecord) -> int | None:
        return obj.route.id if obj.route else None

    class Meta:
        model = ScanRecord
        fields = ['id', 'timestamp', 'client_timestamp', 'server_received_timestamp',
                  'sequence_id', 'time_drift_seconds',
                  'guard_supervisor', 'user_name', 'guard_callsign',
                  'guard_shift', 'device', 'device_name', 'device_id_code',
                  'route', 'route_name', 'route_id',
                  'checkpoint', 'checkpoint_name', 'nfc_value', 'is_on_time',
                  'lat', 'lng', 'raw_nfc', 'scan_type',
                  'validity_score', 'validity_reason',
                  'out_of_sequence', 'insufficient_dwell_time', 'dwell_seconds']


ScanSerializer = ScanRecordSerializer
