import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from api.models import Device, CallSign, GuardSupervisor, Organization, DeviceProvisioning
import json


@pytest.mark.django_db
class TestDeviceRegistration:
    """TC-API-001: Device Registration looks up existing devices by operator_id"""

    def test_register_with_operator_id(self, api_client, default_organization):
        """Register with a valid operator_id returns the existing device"""
        Device.objects.create(
            device_id='TST-01',
            device_name='Test Device',
            password='testpassword123',
            organization=default_organization,
        )
        response = api_client.post('/api/register-device/', {
            'operator_id': 'TST-01'
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'registered'
        assert data['device_id'] == 'TST-01'
        assert data['password'] == 'testpassword123'

    def test_register_returns_same_password(self, api_client, default_organization):
        """Re-registering same operator_id returns same password (re-auth)"""
        Device.objects.create(
            device_id='TST-01',
            device_name='Test Device',
            password='testpassword123',
            organization=default_organization,
        )
        resp1 = api_client.post('/api/register-device/', {
            'operator_id': 'TST-01'
        }, format='json')
        assert resp1.status_code == 200

        resp2 = api_client.post('/api/register-device/', {
            'operator_id': 'TST-01'
        }, format='json')

        assert resp2.status_code == 200
        assert resp2.json()['password'] == 'testpassword123'
        assert resp2.json()['device_id'] == 'TST-01'

    def test_register_unknown_operator_id(self, api_client, default_organization):
        """Unknown operator_id returns 404"""
        response = api_client.post('/api/register-device/', {
            'operator_id': 'UNK-99'
        }, format='json')

        assert response.status_code == 404
        assert 'not found' in response.json()['detail'].lower()

    def test_register_missing_operator_id(self, api_client):
        """Missing operator_id returns 400"""
        response = api_client.post('/api/register-device/', {}, format='json')

        assert response.status_code == 400
        assert 'required' in response.json()['detail'].lower()


@pytest.mark.django_db
class TestDeviceHardwareInfo:
    """TC-API-002: Device Registration - Hardware Info Capture"""

    def test_hardware_info_captured(self, api_client, default_organization):
        """Registration captures hardware telemetry on the existing device"""
        device = Device.objects.create(
            device_id='TST-HW01',
            device_name='Hardware Test Device',
            password='testpw',
            organization=default_organization,
        )

        response = api_client.post('/api/register-device/', {
            'operator_id': 'TST-HW01',
            'hardware_info': {
                'imei': '123456789',
                'imsi': '987654321',
                'sim_phone_number': '+1234567890',
                'os_version': 'Android 14',
                'manufacturer': 'Samsung',
                'model': 'Galaxy S24'
            }
        }, format='json')

        assert response.status_code == 200

        device.refresh_from_db()
        assert device.imei == '123456789'
        assert device.os_version == 'Android 14'
        assert device.manufacturer == 'Samsung'


@pytest.mark.django_db
class TestHeartbeat:
    """TC-API-003: Heartbeat - Device Online Status"""

    def test_heartbeat_authenticates_and_updates_status(self, api_client, registered_device):
        """Device sends heartbeat and stays online"""
        response = api_client.post('/api/heartbeat/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123'
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'

        registered_device.refresh_from_db()
        assert registered_device.is_online is True
        assert registered_device.last_seen is not None

    def test_heartbeat_with_gps_and_battery(self, api_client, registered_device):
        """Heartbeat updates GPS and battery fields"""
        response = api_client.post('/api/heartbeat/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'battery_pct': 45,
            'lat': 40.7128,
            'lng': -74.0060,
            'gps_accuracy': 5
        }, format='json')

        assert response.status_code == 200

        registered_device.refresh_from_db()
        assert registered_device.battery_pct == 45
        assert registered_device.last_latitude == 40.7128
        assert registered_device.last_gps_accuracy == 5

    def test_heartbeat_wrong_password(self, api_client, registered_device):
        """Heartbeat with wrong password fails"""
        response = api_client.post('/api/heartbeat/', {
            'device_id': 'GT-TEST001',
            'password': 'wrongpassword'
        }, format='json')

        assert response.status_code == 401
        assert response.json()['status'] == 'auth_failed'

    def test_heartbeat_unknown_device(self, api_client):
        """Heartbeat with unknown device_id returns not found"""
        response = api_client.post('/api/heartbeat/', {
            'device_id': 'GT-UNKNOWN',
            'password': 'anypassword'
        }, format='json')

        assert response.status_code == 404
        assert response.json()['status'] == 'device_not_found'


@pytest.mark.django_db
class TestNfcFetchDirective:
    """TC-API-004: Heartbeat - NFC Fetch Directive"""

    def test_fetch_nfc_sets_flag(self, api_client, registered_device, admin_headers):
        """Server can request NFC fetch from device"""
        response = api_client.post(
            f'/api/devices/{registered_device.id}/fetch_nfc/',
            {},
            format='json',
            **admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'requested'

        registered_device.refresh_from_db()
        assert registered_device.nfc_fetch_requested is not None
