from rest_framework import serializers

from api.models.dispatch import ShiftAssignment


class ShiftAssignmentSerializer(serializers.ModelSerializer):
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

    def get_dispatcher_name(self, obj: ShiftAssignment) -> str | None:
        return obj.dispatcher.username if obj.dispatcher else None

    def get_guard_supervisor_name(self, obj: ShiftAssignment) -> str:
        if obj.guard_supervisor:
            return f"{obj.guard_supervisor.first_name} {obj.guard_supervisor.last_name}".strip()
        return 'Device Only'

    def get_guard_supervisor_id(self, obj: ShiftAssignment) -> int | None:
        return obj.guard_supervisor.id if obj.guard_supervisor else None

    def get_guard_callsign(self, obj: ShiftAssignment) -> str | None:
        return obj.guard_supervisor.callsign if obj.guard_supervisor else None

    def get_device_name(self, obj: ShiftAssignment) -> str | None:
        return (obj.device.device_id or obj.device.device_name) if obj.device else None

    def get_device_id_code(self, obj: ShiftAssignment) -> str | None:
        return obj.device.device_id if obj.device else None

    def get_route_name(self, obj: ShiftAssignment) -> str | None:
        return obj.route.name if obj.route else None

    def get_route_id(self, obj: ShiftAssignment) -> int | None:
        return obj.route.id if obj.route else None

    def validate(self, data: dict) -> dict:
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
            'total_checkpoints', 'completed_checkpoints',
        ]
        read_only_fields = ['dispatcher', 'assigned_at']
