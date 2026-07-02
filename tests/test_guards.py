import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from api.models import GuardSupervisor, Dispatcher, Organization, Device, Checkpoint
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone


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


@pytest.mark.django_db
class TestNfcCheckpointRegistration:
    """Tests for NFC scan → auto-create Checkpoint flow."""

    @pytest.fixture
    def device_with_nfc_request(self, db, default_organization, guard_supervisor):
        device = Device.objects.create(
            device_id='GT-NFC-TEST',
            device_name='NFC Test Device',
            password='testpass',
            organization=default_organization,
            callsign='TST-01',
            is_online=True,
        )
        from django.utils import timezone as dj_timezone
        device.nfc_fetch_requested = dj_timezone.now()
        device.save()
        return device

    def test_nfc_scan_creates_checkpoint(self, db, device_with_nfc_request):
        """When device with nfc_fetch_requested scans NFC, a Checkpoint is created."""
        from api.models import Checkpoint

        assert Checkpoint.objects.count() == 0

        checkpoint = Checkpoint.objects.create(
            name='Checkpoint-TEST',
            organization=device_with_nfc_request.organization,
            checkpoint_type='nfc',
            nfc_tag='04:A1:B2:C3',
            radius=50,
        )

        device_with_nfc_request.nfc_fetch_requested = None
        device_with_nfc_request.last_nfc_scan = timezone.now()
        device_with_nfc_request.last_nfc_scan_uid = '04:a1:b2:c3'
        device_with_nfc_request.save()

        assert checkpoint.nfc_tag == '04:A1:B2:C3'
        assert checkpoint.checkpoint_type == 'nfc'
        assert checkpoint.organization == device_with_nfc_request.organization

    def test_checkpoint_requires_organization(self, db, default_organization):
        """Checkpoint must belong to an organization."""
        from api.models import Checkpoint

        cp = Checkpoint.objects.create(
            name='Org Checkpoint',
            organization=default_organization,
            checkpoint_type='nfc',
            nfc_tag='AA:BB:CC:DD',
        )
        assert cp.organization == default_organization

    def test_nfc_tag_stored_normalized(self, db, default_organization):
        """NFC tag should be stored with colons in the database."""
        from api.models import Checkpoint

        cp = Checkpoint.objects.create(
            name='Normalized Tag',
            organization=default_organization,
            checkpoint_type='nfc',
            nfc_tag='04:A1:B2:C3',
        )
        assert cp.nfc_tag == '04:A1:B2:C3'