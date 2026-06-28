import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from api.models import GuardSupervisor, User, Dispatcher, Organization
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.mark.django_db
class TestGuardCreation:
    """TC-API-005: Guard/Supervisor Creation via scan-guards"""

    def test_create_guard_supervisor(self, api_client, default_organization, auth_headers):
        """Dispatcher creates a data-only guard (no Django user)"""
        response = api_client.post('/api/scan-guards/', {
            'first_name': 'Alice',
            'last_name': 'Johnson',
            'role': 'guard',
            'shift': 'Day'
        }, format='json', **auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data['first_name'] == 'Alice'
        assert data['last_name'] == 'Johnson'
        assert data['role'] == 'guard'
        assert data['shift'] == 'Day'

        guard = GuardSupervisor.objects.get(id=data['id'])
        assert guard.user is None

    def test_create_supervisor(self, api_client, default_organization, auth_headers):
        """Create a supervisor role guard"""
        response = api_client.post('/api/scan-guards/', {
            'first_name': 'Bob',
            'last_name': 'Manager',
            'role': 'supervisor',
            'shift': 'Night'
        }, format='json', **auth_headers)

        assert response.status_code == 201
        assert response.json()['role'] == 'supervisor'

    def test_guard_creation_requires_auth(self, api_client, default_organization):
        """Unauthenticated guard creation fails"""
        response = api_client.post('/api/scan-guards/', {
            'first_name': 'Test',
            'last_name': 'Guard',
            'role': 'guard',
            'shift': 'Day'
        }, format='json')

        assert response.status_code == 401


@pytest.mark.django_db
class TestGuardCallsignValidation:
    """TC-API-025: Guard Supervisor Callsign Validation"""

    def test_valid_callsign_format(self, api_client, default_organization, auth_headers):
        """Guard with valid ORG-SEQ callsign (e.g. TCN-01) is accepted"""
        guard = GuardSupervisor.objects.create(
            first_name='Test',
            last_name='Guard',
            organization=default_organization,
            role='guard',
            shift='Day',
            callsign='TCN-01'
        )

        response = api_client.get('/api/guards/', format='json', **auth_headers)
        assert response.status_code == 200

    def test_callsign_missing_dash_rejected(self, api_client, default_organization, auth_headers):
        """Callsign without dash+digits (e.g. 'TCN') is rejected"""
        guard = GuardSupervisor.objects.create(
            first_name='Test',
            last_name='Guard',
            organization=default_organization,
            role='guard',
            shift='Day'
        )
        response = api_client.put(
            f'/api/profiles/{guard.id}/',
            {
                'first_name': 'Test',
                'last_name': 'Guard',
                'callsign': 'TCN',  # Invalid - no -NN suffix
                'role': 'guard',
                'shift': 'Day'
            },
            format='json',
            **auth_headers
        )
        assert response.status_code == 400

    def test_callsign_lowercase_rejected(self, api_client, default_organization, auth_headers):
        """Lowercase callsign (e.g. 'tcn-01') is rejected"""
        guard = GuardSupervisor.objects.create(
            first_name='Test',
            last_name='Guard',
            organization=default_organization,
            role='guard',
            shift='Day'
        )
        response = api_client.put(
            f'/api/profiles/{guard.id}/',
            {
                'first_name': 'Test',
                'last_name': 'Guard',
                'callsign': 'tcn-01',  # Invalid - lowercase
                'role': 'guard',
                'shift': 'Day'
            },
            format='json',
            **auth_headers
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestGuardListFiltering:
    """TC-API-019: Dispatcher Organization Scoping"""

    def test_dispatcher_sees_only_own_org_guards(self, api_client, default_organization, auth_headers):
        """Dispatchers only see guards in their organization"""
        GuardSupervisor.objects.create(
            first_name='Org1',
            last_name='Guard',
            organization=default_organization,
            role='guard',
            shift='Day'
        )

        other_org = Organization.objects.create(
            name='Other Organization',
            is_active=True
        )
        GuardSupervisor.objects.create(
            first_name='Org2',
            last_name='Guard',
            organization=other_org,
            role='guard',
            shift='Day'
        )

        response = api_client.get('/api/guards/', format='json', **auth_headers)
        assert response.status_code == 200
        guards = response.json()
        assert all(g['organization'] == default_organization.id for g in guards)


@pytest.mark.django_db
class TestDeviceProvisioning:
    """TC-API-006: Device Provisioning to Guard"""

    def test_provision_device_to_guard(self, api_client, registered_device, guard_supervisor, auth_headers):
        """Bind a device to a guard and create active shift assignment"""
        response = api_client.post('/api/provision-device/', {
            'device_id': 'GT-TEST001',
            'guard_id': guard_supervisor.id,
            'scheduled_start': '2024-01-15T08:00:00Z',
            'scheduled_end': '2024-01-15T16:00:00Z'
        }, format='json', **auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data['status'] == 'provisioned'
        assert 'callsign' in data

        guard_supervisor.refresh_from_db()
        assert guard_supervisor.callsign is not None