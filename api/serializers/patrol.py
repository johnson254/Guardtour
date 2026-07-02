from rest_framework import serializers
from django.db import transaction

from api.models.organization import Organization
from api.models.patrol import PatrolRoute, Checkpoint


class CheckpointSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    asset_class = serializers.CharField(default='checkpoint', read_only=True)
    type = serializers.CharField(default='poi', read_only=True)
    geometry = serializers.SerializerMethodField()
    route = serializers.PrimaryKeyRelatedField(
        queryset=PatrolRoute.objects.all(), required=False, allow_null=True
    )

    def get_organization_name(self, obj: Checkpoint) -> str | None:
        if obj.organization:
            return obj.organization.name
        if obj.route and obj.route.organization:
            return obj.route.organization.name
        return None

    def get_geometry(self, obj: Checkpoint) -> list | None:
        if obj.lat is not None and obj.lng is not None:
            return [obj.lat, obj.lng]
        return None

    class Meta:
        model = Checkpoint
        fields = [
            'id', 'name', 'nfc_tag', 'lat', 'lng', 'order', 'planned_time',
            'time_tolerance', 'dwell_time', 'radius', 'precision_level', 'route', 'organization',
            'checkpoint_type', 'organization_name', 'asset_class', 'type', 'geometry',
            'next_announcement_text', 'scheduled_date',
        ]
        read_only_fields = ['organization']

    def validate(self, data: dict) -> dict:
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

        planned_time = data.get('planned_time')
        route = data.get('route') or (self.instance.route_id if self.instance else None)
        if planned_time and route:
            dupes = Checkpoint.objects.filter(route=route, planned_time=planned_time)
            if self.instance and self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                raise serializers.ValidationError(
                    f'Another checkpoint in this route already has planned time {planned_time}.'
                )

        return data


class PatrolRouteSerializer(serializers.ModelSerializer):
    checkpoints = CheckpointSerializer(many=True, required=False)
    organization_name = serializers.SerializerMethodField()
    checkpoint_count = serializers.SerializerMethodField()
    device_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    logic_type = serializers.CharField(required=False)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )

    def get_checkpoint_count(self, obj: PatrolRoute) -> int:
        try:
            return obj.checkpoints.count()
        except Exception:
            return 0

    def get_device_count(self, obj: PatrolRoute) -> int:
        try:
            return obj.assigned_devices.count()
        except Exception:
            return 0

    def to_representation(self, instance: PatrolRoute) -> dict:
        ret = super().to_representation(instance)
        try:
            if instance.is_audit:
                ret['logic_type'] = "Audit"
            elif instance.is_emergency:
                ret['logic_type'] = "Emergency"
            elif instance.enforce_order and instance.enforce_time:
                ret['logic_type'] = "Scheduled"
            elif instance.enforce_order and not instance.enforce_time:
                ret['logic_type'] = "Sequential"
            elif not instance.enforce_order and not instance.enforce_time:
                ret['logic_type'] = "Flexible"
            else:
                ret['logic_type'] = "Custom"
        except Exception:
            ret['logic_type'] = "Flexible"
        return ret

    def get_organization_name(self, obj: PatrolRoute) -> str | None:
        return obj.organization.name if obj.organization else None

    def get_created_by_name(self, obj: PatrolRoute) -> str | None:
        return obj.created_by.username if obj.created_by else None

    class Meta:
        model = PatrolRoute
        fields = [
            'id', 'name', 'description', 'status', 'frequency', 'scheduled_date',
            'enforce_order', 'enforce_time', 'is_geofence', 'is_emergency', 'is_audit', 'is_daily',
            'scheduled_start_time', 'send_start_alert', 'send_announcement', 'start_alert_lead_time',
            'readout_text', 'tts_voice', 'tts_rate', 'tts_pitch',
            'assigned_guards', 'assigned_devices',
            'checkpoints', 'organization', 'organization_name', 'checkpoint_count', 'device_count',
            'logic_type', 'created_by', 'created_by_name',
        ]
        read_only_fields = ['created_by']

    def _map_logic_to_flags(self, attrs: dict) -> dict:
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
    def create(self, validated_data: dict) -> PatrolRoute:
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
    def update(self, instance: PatrolRoute, validated_data: dict) -> PatrolRoute:
        checkpoints_data = validated_data.pop('checkpoints', None)
        assigned_guards_data = validated_data.pop('assigned_guards', None)
        assigned_devices_data = validated_data.pop('assigned_devices', None)
        validated_data = self._map_logic_to_flags(validated_data)

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
