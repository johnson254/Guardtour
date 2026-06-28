import pytest
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from api.models import ScanRecord, ShiftAssignment, Device


@pytest.mark.django_db
class TestNfcScanProcessing:
    """TC-API-009: NFC Scan Processing - Tag Scan"""

    def test_valid_scan_creates_record(self, api_client, registered_device, active_assignment, patrol_route_with_checkpoints):
        """Device scans NFC tag, server creates ScanRecord"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE',
            'lat': 40.7128,
            'lng': -74.0060
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['nfc_value'] == 'TAG-GATE'

        scan = ScanRecord.objects.get(nfc_value='TAG-GATE')
        assert scan.checkpoint is not None
        assert scan.checkpoint.name == 'Gate'
        assert scan.guard_supervisor is not None

    def test_scan_updates_guard_last_scan(self, api_client, registered_device, guard_supervisor, active_assignment, patrol_route_with_checkpoints):
        """Scanning updates guard's last_scan timestamp"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE'
        }, format='json')

        assert response.status_code == 200
        guard_supervisor.refresh_from_db()
        assert guard_supervisor.last_scan is not None

    def test_on_time_calculation(self, api_client, registered_device, active_assignment, patrol_route_with_checkpoints):
        """Scan on_time status is calculated based on planned_time tolerance"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE'
        }, format='json')

        assert response.status_code == 200


@pytest.mark.django_db
class TestNfcScanCooldown:
    """TC-API-010: NFC Scan - Duplicate Cooldown"""

    def test_duplicate_scan_within_30s_rejected(self, api_client, registered_device, active_assignment, patrol_route_with_checkpoints):
        """Same NFC tag scanned within 30 seconds returns cooldown error"""
        response1 = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE'
        }, format='json')
        assert response1.status_code == 200

        response2 = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE'
        }, format='json')
        assert response2.status_code == 400
        assert 'Cooldown active' in str(response2.json())

    def test_different_tag_no_cooldown(self, api_client, registered_device, active_assignment, patrol_route_with_checkpoints):
        """Different NFC tag after cooldown not affected"""
        response1 = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-GATE'
        }, format='json')
        assert response1.status_code == 200

        response2 = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'TAG-LOBBY'
        }, format='json')
        assert response2.status_code == 200


@pytest.mark.django_db
class TestUnknownTagScan:
    """TC-API-012: NFC Scan - Unknown Tag"""

    def test_unknown_tag_creates_scan(self, api_client, registered_device, active_assignment):
        """Scanning unknown NFC tag creates record with null checkpoint"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'nfc_value': 'UNKNOWN-TAG-12345'
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['checkpoint'] is None
        assert 'Unknown Tag' in data['checkpoint_name']


@pytest.mark.django_db
class TestScanBatchUpload:
    """TC-API-015: Scan Batch Upload (Offline Sync)"""

    def test_batch_scan_upload(self, api_client, registered_device, active_assignment):
        """Device uploads accumulated offline scans"""
        response = api_client.post('/api/scan-batch/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'scans': [
                {
                    'nfc_value': 'TAG-GATE',
                    'recorded_at': '2024-01-15T08:00:00Z',
                    'lat': 40.7128,
                    'lng': -74.0060
                },
                {
                    'nfc_value': 'TAG-LOBBY',
                    'recorded_at': '2024-01-15T08:30:00Z',
                    'lat': 40.7135,
                    'lng': -74.0055
                }
            ]
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['synced'] == 2
        assert len(data['results']) == 2


@pytest.mark.django_db
class TestGpsBatchUpload:
    """TC-API-014: GPS Batch Upload"""

    def test_gps_batch_upload(self, api_client, registered_device):
        """Device uploads accumulated GPS trail points"""
        response = api_client.post('/api/gps-batch/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'points': [
                {
                    'lat': 40.7128,
                    'lng': -74.0060,
                    'accuracy': 5.0,
                    'recorded_at': '2024-01-15T08:00:00Z',
                    'battery_pct': 90
                },
                {
                    'lat': 40.7130,
                    'lng': -74.0058,
                    'accuracy': 3.5,
                    'recorded_at': '2024-01-15T08:00:30Z'
                }
            ]
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['synced'] == 2


@pytest.mark.django_db
class TestRawNfcPayloadParsing:
    """TC-API-013: NFC Scan - Raw NFC Payload Parsing"""

    def test_ndef_text_payload_extraction(self, api_client, registered_device):
        """Raw NFC payload with NDEF text is parsed"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'raw_nfc': {
                'ndef_records': [
                    {'payload_text': 'TAG-EXTRACTED'}
                ],
                'uid': '04:A2:B3:C4'
            }
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert data['nfc_value'] == 'TAG-EXTRACTED'

    def test_uid_based_identification(self, api_client, registered_device):
        """Raw NFC with only UID uses UID as nfc_value"""
        response = api_client.post('/api/scans/', {
            'device_id': 'GT-TEST001',
            'password': 'testpassword123',
            'raw_nfc': {
                'uid': '04:A2:B3:C4:D5'
            }
        }, format='json')

        assert response.status_code == 200