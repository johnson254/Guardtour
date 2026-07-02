from rest_framework import serializers
from api.models.organization import Organization, Admin
from api.serializers.auth import UserSerializer


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'contact_email', 'phone', 'address',
                  'default_time_tolerance', 'is_active', 'shift_mode',
                  'created_at', 'area_of_interest', 'operational_note']


class AdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Admin
        fields = '__all__'
