"""Tests for device endpoint rate limiting.

Verifies that DeviceHeartbeatThrottle (30/min) and DeviceScanThrottle (60/min)
correctly throttle per-device without affecting other devices or authenticated users.
"""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import Organization, Dispatcher, GuardSupervisor, Device, PatrolRoute, Checkpoint, ShiftAssignment, CallSign
from api.password import hash_device_password


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache between tests to reset throttle counters."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestDeviceRateThrottle:
    """Tests for device endpoint rate limiting."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Throttle Org', code='THR')

    @pytest.fixture
    def device(self, db, org):
        return Device.objects.create(
            device_id='GT-THROTTLE-001',
            device_name='Throttle Test',
            password=hash_device_password('throttlepass'),
            organization=org,
        )

    @pytest.fixture
    def dispatcher_user(self, db, org):
        user = User.objects.create_user(username='thr_disp', password='pass')
        Dispatcher.objects.create(user=user, organization=org)
        return user

    def test_heartbeat_allows_within_limit(self, device):
        """Heartbeat succeeds when under rate limit."""
        client = APIClient()
        for _ in range(5):
            response = client.post('/api/heartbeat/', {
                'device_id': 'GT-THROTTLE-001',
                'password': 'throttlepass',
            })
            assert response.status_code == 200

    def test_heartbeat_throttles_after_limit(self, device):
        """Heartbeat gets throttled after exceeding 30 requests."""
        client = APIClient()
        # The throttle rate is 30/min — send 35 requests
        responses = []
        for _ in range(35):
            response = client.post('/api/heartbeat/', {
                'device_id': 'GT-THROTTLE-001',
                'password': 'throttlepass',
            })
            responses.append(response.status_code)

        # At least one should be throttled (429)
        assert 429 in responses, f"Expected at least one 429, got: {set(responses)}"

    def test_scan_endpoint_throttles(self, device, org):
        """Scan endpoint gets throttled after exceeding limit."""
        client = APIClient()
        responses = []
        for _ in range(70):
            response = client.post('/api/scans/', {
                'device_id': 'GT-THROTTLE-001',
                'password': 'throttlepass',
                'nfc_tag': 'TAG-001',
            })
            responses.append(response.status_code)

        # Should see some 429s after 60 requests
        assert 429 in responses, f"Expected at least one 429 on scan endpoint, got: {set(responses)}"

    def test_gps_batch_throttles(self, device):
        """GPS batch endpoint gets throttled."""
        client = APIClient()
        responses = []
        for _ in range(70):
            response = client.post('/api/gps-batch/', {
                'device_id': 'GT-THROTTLE-001',
                'password': 'throttlepass',
                'points': [{'lat': 40.7, 'lng': -74.0, 'recorded_at': '2024-01-01T00:00:00Z'}],
            })
            responses.append(response.status_code)

        assert 429 in responses, f"Expected at least one 429 on gps-batch, got: {set(responses)}"

    def test_throttle_is_per_device(self, org):
        """Throttling one device doesn't affect another device."""
        Device.objects.create(
            device_id='GT-THR-A', password=hash_device_password('passA'), organization=org
        )
        Device.objects.create(
            device_id='GT-THR-B', password=hash_device_password('passB'), organization=org
        )
        client = APIClient()

        # Exhaust device A's limit
        for _ in range(35):
            client.post('/api/heartbeat/', {'device_id': 'GT-THR-A', 'password': 'passA'})

        # Device B should still work
        response = client.post('/api/heartbeat/', {
            'device_id': 'GT-THR-B',
            'password': 'passB',
        })
        assert response.status_code == 200

    def test_authenticated_endpoints_not_throttled(self, dispatcher_user, org):
        """Authenticated dispatcher endpoints don't use device throttle."""
        client = APIClient()
        refresh = RefreshToken.for_user(dispatcher_user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        # Should not be throttled even after many requests
        for _ in range(5):
            response = client.get('/api/devices/')
            assert response.status_code == 200
