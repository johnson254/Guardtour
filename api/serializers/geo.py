from rest_framework import serializers

from api.models.geo import MapObject
from api.serializers.personnel import GuardSupervisorSerializer


class GeometryField(serializers.Field):
    def to_representation(self, value: object) -> list | None:
        if not value:
            return None
        if isinstance(value, dict):
            coords = value.get('coordinates')
            if coords and isinstance(coords, list) and len(coords) >= 2:
                return [coords[1], coords[0]]
        if isinstance(value, list) and len(value) >= 2:
            return value
        return None

    def to_internal_value(self, data: object) -> list | None:
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
            'entry_msg', 'exit_msg', 'geo_shape', 'intrusion_alarm',
            'fetch_location_on_scan', 'planned_duration_minutes',
        ]

    def validate(self, data: dict) -> dict:
        type_val = data.get('type')
        if type_val == 'geofence' and data.get('geometry') is None:
            raise serializers.ValidationError("A Geofence must have geometry.")
        return data
