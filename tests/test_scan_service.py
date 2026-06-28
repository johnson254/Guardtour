import pytest
from api.scan_service import (
    calculate_scan_validity,
    is_on_time,
    resolve_asset,
    resolve_assignment,
    _haversine
)
from api.models import Device, Checkpoint, PatrolRoute, ShiftAssignment, ScanRecord
from datetime import time


@pytest.mark.django_db
class TestValidityScoring:
    """Tests for validity score calculation (TC-E2E-004, TC-E2E-005)"""

    def test_gps_proximity_high_score(self, db):
        """Close to checkpoint = high GPS proximity score"""
        device = Device.objects.create(
            device_id='GT-VALIDITY',
            device_name='Validity Test',
            password='test123'
        )
        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='gps',
            nfc_tag='TAG-TEST',
            lat=40.7128,
            lng=-74.0060,
            radius=50
        )

        score, reason = calculate_scan_validity(
            device=device,
            checkpoint=checkpoint,
            scan_lat=40.7129,
            scan_lng=-74.0061,
            now=timezone.now()
        )

        assert score >= 0.6
        assert 'Within' in reason or 'Near' in reason

    def test_gps_far_from_checkpoint_low_score(self, db):
        """Far from checkpoint = low score"""
        device = Device.objects.create(
            device_id='GT-VALIDITY2',
            device_name='Validity Test 2',
            password='test123'
        )
        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='gps',
            nfc_tag='TAG-TEST2',
            lat=40.7128,
            lng=-74.0060,
            radius=50
        )

        score, reason = calculate_scan_validity(
            device=device,
            checkpoint=checkpoint,
            scan_lat=40.7200,
            scan_lng=-74.0100,
            now=timezone.now()
        )

        assert score < 0.3
        assert 'Far from checkpoint' in reason

    def test_low_battery_penalty(self, db):
        """Low battery reduces validity score"""
        device = Device.objects.create(
            device_id='GT-LOWBAT',
            device_name='Low Battery Device',
            password='test123',
            battery_pct=10
        )
        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='nfc',
            nfc_tag='TAG-TEST3',
            lat=40.7128,
            lng=-74.0060,
            radius=50
        )

        score, reason = calculate_scan_validity(
            device=device,
            checkpoint=checkpoint,
            scan_lat=40.7129,
            scan_lng=-74.0061,
            now=timezone.now()
        )

        assert score < 0.6
        assert 'Low battery' in reason

    def test_score_clamps_between_0_and_1(self, db):
        """Validity score is always between 0.0 and 1.0"""
        device = Device.objects.create(
            device_id='GT-CLAMP',
            device_name='Clamp Test',
            password='test123',
            battery_pct=5
        )
        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='nfc',
            nfc_tag='TAG-TEST4',
            lat=40.7128,
            lng=-74.0060,
            radius=50
        )

        score, reason = calculate_scan_validity(
            device=device,
            checkpoint=checkpoint,
            scan_lat=40.9900,
            scan_lng=-74.5000,
            now=timezone.now()
        )

        assert 0.0 <= score <= 1.0


@pytest.mark.django_db
class TestIsOnTime:
    """Tests for on-time calculation"""

    def test_scan_within_tolerance_is_on_time(self, db):
        """Scan within planned_time ± tolerance is on time"""
        from django.utils import timezone as dj_tz
        from datetime import datetime

        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='nfc',
            nfc_tag='TAG-TIME',
            planned_time=time(10, 0),
            time_tolerance=15
        )

        now = dj_tz.make_aware(datetime.combine(dj_tz.now().date(), time(10, 10)))
        result = is_on_time(checkpoint, now)
        assert result is True

    def test_scan_outside_tolerance_is_late(self, db):
        """Scan outside tolerance is late"""
        from django.utils import timezone as dj_tz
        from datetime import datetime

        checkpoint = Checkpoint.objects.create(
            name='Test CP',
            checkpoint_type='nfc',
            nfc_tag='TAG-TIME2',
            planned_time=time(10, 0),
            time_tolerance=15
        )

        now = dj_tz.make_aware(datetime.combine(dj_tz.now().date(), time(10, 30)))
        result = is_on_time(checkpoint, now)
        assert result is False


class TestHaversineDistance:
    """Test haversine distance calculation"""

    def test_same_point_zero_distance(self):
        """Same point returns 0 distance"""
        dist = _haversine(40.7128, -74.0060, 40.7128, -74.0060)
        assert dist == 0

    def test_known_distance_calculation(self):
        """NYC to LA is approximately 3,940 km"""
        dist = _haversine(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3900000 < dist < 4000000


@pytest.mark.django_db
class TestResolveAsset:
    """Test checkpoint resolution from NFC tag"""

    def test_resolve_existing_checkpoint(self, db):
        """Known NFC tag resolves to checkpoint"""
        org = Organization.objects.create(name='Test Org')
        route = PatrolRoute.objects.create(name='Test Route', organization=org)
        cp = Checkpoint.objects.create(
            route=route,
            organization=org,
            name='Gate',
            checkpoint_type='nfc',
            nfc_tag='TAG-GATE'
        )

        resolved_cp, resolved_route = resolve_asset('TAG-GATE')
        assert resolved_cp == cp
        assert resolved_route == route

    def test_resolve_unknown_tag_returns_none(self, db):
        """Unknown NFC tag returns None checkpoint"""
        resolved_cp, resolved_route = resolve_asset('UNKNOWN-TAG')
        assert resolved_cp is None
        assert resolved_route is None

    def test_peer_scan_returns_none_checkpoint(self, db):
        """Peer scan type doesn't resolve to checkpoint"""
        resolved_cp, resolved_route = resolve_asset('SOME-DEVICE-ID', scan_type='peer')
        assert resolved_cp is None
        assert resolved_route is None


@pytest.mark.django_db
class TestResolveAssignment:
    """Test shift assignment resolution"""

    def test_resolve_by_route_id(self, db, default_organization):
        """Assignment resolved by route_id parameter"""
        from django.contrib.auth.models import User

        user = User.objects.create_user('dispatcher', 'dispatcher@test.com', 'pass123')
        device = Device.objects.create(
            device_id='GT-RESOLVE',
            device_name='Resolve Test',
            password='test123',
            organization=default_organization
        )
        route = PatrolRoute.objects.create(
            name='Test Route',
            organization=default_organization
        )
        assignment = ShiftAssignment.objects.create(
            dispatcher=user,
            device=device,
            route=route,
            is_active=True
        )

        resolved = resolve_assignment(device, route.id, None)
        assert resolved == assignment


from api.models import Organization
from django.utils import timezone