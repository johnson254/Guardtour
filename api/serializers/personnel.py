import re

from rest_framework import serializers
from django.contrib.auth.models import User

from api.models.personnel import Dispatcher, GuardSupervisor
from api.serializers.auth import UserSerializer


class DispatcherSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    organization_name = serializers.SerializerMethodField()
    email = serializers.EmailField(write_only=True, required=False)
    username = serializers.CharField(write_only=True, required=False)

    def get_organization_name(self, obj: Dispatcher) -> str | None:
        return obj.organization.name if obj.organization else None

    def create(self, validated_data: dict) -> Dispatcher:
        validated_data.pop('user', None)
        organization = validated_data.pop('organization', None)
        email = validated_data.pop('email', None)
        username = validated_data.pop('username', None)

        if username:
            user = User.objects.create_user(
                username=username,
                email=email or '',
                password=User.objects.make_random_password()
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

    def get_organization_name(self, obj: GuardSupervisor) -> str | None:
        return obj.organization.name if obj.organization else None

    def validate_callsign(self, value: str) -> str:
        if value:
            if not re.match(r'^[A-Z]{2,4}-\d{2,}$', value):
                raise serializers.ValidationError("Operator ID must be ORG-NN format (e.g. TCN-01)")
        return value

    class Meta:
        model = GuardSupervisor
        fields = [
            'id', 'first_name', 'last_name', 'callsign', 'organization',
            'organization_name', 'role', 'shift', 'is_on_shift',
            'nfc_tags_scanned', 'last_scan', 'created_at',
        ]
