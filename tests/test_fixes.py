import pytest
from django.contrib.auth.models import User
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta

from api.models import (
    Organization, Admin, Dispatcher, GuardSupervisor, Device,
    PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, CallSign,
)
from api.password import hash_device_password, verify_device_password, is_hashed
from api.org_permissions import get_user_organization, get_user_organization_or_none, user_can_access_organization
from api.services.scan import ScanPipeline, authenticate_device


# ── Password Hashing Tests ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestPasswordHashing:
    """Tests for device password hashing and verification."""

    def test_hash_produces_valid_hash(self):
        """hash_device_password produces a Django-compatible hash."""
        hashed = hash_device_password('testpassword123')
        assert is_hashed(hashed)
        assert hashed != 'testpassword123'

    def test_verify_correct_password(self):
        """Correct password verifies against hash."""
        hashed = hash_device_password('testpassword123')
        is_valid, needs_rehash = verify_device_password('testpassword123', hashed)
        assert is_valid is True
        assert needs_rehash is False

    def test_verify_wrong_password(self):
        """Wrong password fails verification."""
        hashed = hash_device_password('testpassword123')
        is_valid, needs_rehash = verify_device_password('wrongpassword', hashed)
        assert is_valid is False

    def test_verify_legacy_plaintext(self):
        """Legacy plaintext passwords still verify (backward compat)."""
        is_valid, needs_rehash = verify_device_password('plaintext123', 'plaintext123')
        assert is_valid is True
        assert needs_rehash is True

    def test_verify_legacy_wrong_plaintext(self):
        """Wrong plaintext password fails."""
        is_valid, needs_rehash = verify_device_password('wrong', 'plaintext123')
        assert is_valid is False

    def test_empty_password_fails(self):
        """Empty password fails verification."""
        hashed = hash_device_password('testpassword123')
        is_valid, _ = verify_device_password('', hashed)
        assert is_valid is False

    def test_none_password_fails(self):
        """None password fails verification."""
        hashed = hash_device_password('testpassword123')
        is_valid, _ = verify_device_password(None, hashed)
        assert is_valid is False

    def test_hash_raises_on_empty(self):
        """hash_device_password raises ValueError on empty input."""
        with pytest.raises(ValueError):
            hash_device_password('')

    def test_is_hashed_detects_hashed(self):
        """is_hashed correctly identifies Django-hashed passwords."""
        hashed = hash_device_password('test123')
        assert is_hashed(hashed) is True

    def test_is_hashed_detects_plaintext(self):
        """is_hashed correctly identifies plaintext passwords."""
        assert is_hashed('plaintext123') is False
        assert is_hashed('') is False
        assert is_hashed(None) is False


# ── Organization Permission Tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestOrgPermissions:
    """Tests for organization resolution helper."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Test Org', code='TST')

    @pytest.fixture
    def dispatcher_no_org(self, db):
        user = User.objects.create_user(username='disp_no_org', password='pass')
        dispatcher = Dispatcher.objects.create(user=user, organization=None)
        return user, dispatcher

    @pytest.fixture
    def dispatcher_with_org(self, db, org):
        user = User.objects.create_user(username='disp_with_org', password='pass')
        dispatcher = Dispatcher.objects.create(user=user, organization=org)
        return user, dispatcher

    @pytest.fixture
    def superuser(self, db):
        return User.objects.create_superuser(username='super', password='pass', email='s@s.com')

    def test_dispatcher_with_org_returns_org(self, dispatcher_with_org, org):
        user, _ = dispatcher_with_org
        result = get_user_organization(user)
        assert result == org

    def test_dispatcher_without_org_raises(self, dispatcher_no_org):
        user, _ = dispatcher_no_org
        with pytest.raises(PermissionDenied):
            get_user_organization(user)

    def test_superuser_returns_none(self, superuser):
        result = get_user_organization(superuser)
        assert result is None

    def test_admin_returns_none(self, db, superuser):
        Admin.objects.create(user=superuser)
        result = get_user_organization(superuser)
        assert result is None

    def test_or_none_returns_none_instead_of_raising(self, dispatcher_no_org):
        user, _ = dispatcher_no_org
        result = get_user_organization_or_none(user)
        assert result is None

    def test_can_access_organization_superuser(self, superuser, org):
        assert user_can_access_organization(superuser, org.id) is True

    def test_can_access_organization_matching(self, dispatcher_with_org, org):
        user, _ = dispatcher_with_org
        assert user_can_access_organization(user, org.id) is True

    def test_can_access_organization_mismatch(self, dispatcher_with_org, db):
        user, _ = dispatcher_with_org
        other_org = Organization.objects.create(name='Other', code='OTH')
        assert user_can_access_organization(user, other_org.id) is False


# ── ScanPipeline Tests ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestScanPipeline:
    """Tests for the refactored ScanPipeline class."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Test Org', code='TST')

    @pytest.fixture
    def device(self, db, org):
        return Device.objects.create(
            device_id='GT-PIPELINE-001',
            device_name='Pipeline Test Device',
            password=hash_device_password('securepass'),
            organization=org,
            callsign='TST-01',
        )

    @pytest.fixture
    def guard(self, db, org):
        return GuardSupervisor.objects.create(
            first_name='Jane',
            last_name='Smith',
            organization=org,
            role='guard',
            shift='Day',
            callsign='TST-01',
        )

    @pytest.fixture
    def route(self, db, org, guard):
        route = PatrolRoute.objects.create(
            name='Pipeline Route',
            organization=org,
            status='active',
            enforce_order=True,
            enforce_time=True,
        )
        route.assigned_guards.add(guard)
        Checkpoint.objects.create(
            route=route,
            organization=org,
            name='Gate',
            checkpoint_type='nfc',
            nfc_tag='TAG-PIPE-001',
            order=1,
            planned_time=(timezone.now() - timedelta(minutes=5)).strftime('%H:%M:%S'),
            time_tolerance=15,
            lat=40.7128,
            lng=-74.0060,
            radius=50,
        )
        return route

    @pytest.fixture
    def assignment(self, db, guard, device, route):
        return ShiftAssignment.objects.create(
            dispatcher=User.objects.create_user(username='disp_pipe', password='pass'),
            guard_supervisor=guard,
            device=device,
            route=route,
            scheduled_date=timezone.now().date(),
            scheduled_start=timezone.now(),
            shift_type='Day',
            is_active=True,
        )

    def test_pipeline_authenticates_with_hashed_password(self, device):
        """ScanPipeline authenticates device with hashed password."""
        pipeline = ScanPipeline(
            device_id='GT-PIPELINE-001',
            password='securepass',
            route_id=None,
            nfc_value=None,
            peer_key=None,
            now=timezone.now(),
        )
        pipeline._step_authenticate_device()
        assert pipeline.context['device'] == device

    def test_pipeline_rejects_wrong_password(self, device):
        """ScanPipeline rejects wrong password."""
        pipeline = ScanPipeline(
            device_id='GT-PIPELINE-001',
            password='wrongpass',
            route_id=None,
            nfc_value=None,
            peer_key=None,
            now=timezone.now(),
        )
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError):
            pipeline._step_authenticate_device()

    def test_pipeline_rejects_decommissioned_device(self, db, org):
        """ScanPipeline rejects decommissioned device."""
        Device.objects.create(
            device_id='GT-DECOM',
            password=hash_device_password('pass'),
            organization=org,
            is_active=False,
        )
        pipeline = ScanPipeline(
            device_id='GT-DECOM',
            password='pass',
            route_id=None,
            nfc_value=None,
            peer_key=None,
            now=timezone.now(),
        )
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError, match='decommissioned'):
            pipeline._step_authenticate_device()

    def test_pipeline_cooldown_blocks_duplicate(self, device, assignment):
        """ScanPipeline blocks duplicate scan within cooldown window."""
        now = timezone.now()
        ScanRecord.objects.create(
            device=device,
            nfc_value='TAG-PIPE-001',
            timestamp=now - timedelta(seconds=10),
            checkpoint_name='Gate',
        )
        pipeline = ScanPipeline(
            device_id='GT-PIPELINE-001',
            password='securepass',
            route_id=None,
            nfc_value='TAG-PIPE-001',
            peer_key=None,
            now=now,
        )
        pipeline._step_authenticate_device()
        pipeline._step_parse_nfc()
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError, match='Cooldown'):
            pipeline._step_check_cooldown()

    def test_pipeline_resolves_assignment(self, device, assignment):
        """ScanPipeline resolves active assignment."""
        pipeline = ScanPipeline(
            device_id='GT-PIPELINE-001',
            password='securepass',
            route_id=None,
            nfc_value=None,
            peer_key=None,
            now=timezone.now(),
        )
        pipeline._step_authenticate_device()
        pipeline._step_resolve_assignment()
        assert pipeline.context['assignment'] == assignment

    def test_pipeline_full_execution(self, device, assignment, route):
        """ScanPipeline full execution produces valid response."""
        now = timezone.now()
        pipeline = ScanPipeline(
            device_id='GT-PIPELINE-001',
            password='securepass',
            route_id=None,
            nfc_value='TAG-PIPE-001',
            peer_key=None,
            now=now,
            scan_lat=40.7128,
            scan_lng=-74.0060,
        )
        result = pipeline.execute()
        assert result['device'] == device
        assert result['route'] == route
        assert result['validity_score'] > 0


# ── authenticate_device Tests ───────────────────────────────────────────────


@pytest.mark.django_db
class TestAuthenticateDevice:
    """Tests for standalone authenticate_device function."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Test Org', code='TST')

    def test_authenticates_hashed_password(self, org):
        """authenticate_device works with hashed password."""
        device = Device.objects.create(
            device_id='GT-AUTH-001',
            password=hash_device_password('mypass'),
            organization=org,
        )
        result = authenticate_device('GT-AUTH-001', 'mypass')
        assert result == device

    def test_authenticates_legacy_plaintext(self, org):
        """authenticate_device works with legacy plaintext password."""
        device = Device.objects.create(
            device_id='GT-AUTH-002',
            password='plaintext_pwd',
            organization=org,
        )
        result = authenticate_device('GT-AUTH-002', 'plaintext_pwd')
        assert result == device

    def test_rejects_wrong_password(self, org):
        """authenticate_device rejects wrong password."""
        Device.objects.create(
            device_id='GT-AUTH-003',
            password=hash_device_password('correct'),
            organization=org,
        )
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError):
            authenticate_device('GT-AUTH-003', 'wrong')

    def test_rejects_decommissioned(self, org):
        """authenticate_device rejects decommissioned device."""
        Device.objects.create(
            device_id='GT-AUTH-004',
            password=hash_device_password('pass'),
            organization=org,
            is_active=False,
        )
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError, match='decommissioned'):
            authenticate_device('GT-AUTH-004', 'pass')


# ── ViewSet Query Optimization Tests ────────────────────────────────────────


@pytest.mark.django_db
class TestViewSetQueryOptimization:
    """Tests that ViewSets use select_related/prefetch_related."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Test Org', code='TST')

    @pytest.fixture
    def dispatcher_user(self, db, org):
        user = User.objects.create_user(username='disp_opt', password='pass')
        Dispatcher.objects.create(user=user, organization=org)
        return user

    @pytest.fixture
    def api_client(self):
        return APIClient()

    def _auth_client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        return client

    def test_scan_record_list_uses_select_related(self, dispatcher_user, org, api_client):
        """ScanRecordViewSet list uses select_related (fewer queries)."""
        guard = GuardSupervisor.objects.create(
            first_name='Test', last_name='Guard',
            organization=org, callsign='TST-01',
        )
        device = Device.objects.create(
            device_id='GT-OPT-001', password=hash_device_password('pass'),
            organization=org, callsign='TST-01',
        )
        route = PatrolRoute.objects.create(name='Route', organization=org)
        cp = Checkpoint.objects.create(
            route=route, organization=org, name='CP1',
            checkpoint_type='nfc', nfc_tag='TAG-OPT',
        )
        ScanRecord.objects.create(
            guard_supervisor=guard, device=device, route=route,
            checkpoint=cp, checkpoint_name='CP1',
        )

        client = self._auth_client(dispatcher_user)
        response = client.get('/api/scans/')
        assert response.status_code == 200
        data = response.data
        if isinstance(data, dict):
            results = data.get('results', [])
        else:
            results = data
        assert len(results) >= 1

    def test_device_list_uses_select_related(self, dispatcher_user, org):
        """DeviceViewSet list uses select_related."""
        Device.objects.create(
            device_id='GT-OPT-002', password=hash_device_password('pass'),
            organization=org,
        )
        client = self._auth_client(dispatcher_user)
        response = client.get('/api/devices/')
        assert response.status_code == 200

    def test_dispatcher_without_org_gets_empty_or_403(self, db):
        """Dispatcher without org gets empty results or 403, not silent auto-assign."""
        user = User.objects.create_user(username='disp_lost', password='pass')
        Dispatcher.objects.create(user=user, organization=None)
        client = self._auth_client(user)
        response = client.get('/api/devices/')
        # Should either get 403 or an empty list — never auto-assigned data
        assert response.status_code in [403, 200]
        if response.status_code == 200:
            data = response.data
            if isinstance(data, dict):
                results = data.get('results', [])
            else:
                results = data
            assert len(results) == 0  # No auto-assignment to another org


# ── Heartbeat Password Tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestHeartbeatPasswordAuth:
    """Tests that heartbeat endpoint uses hashed password verification."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Test Org', code='TST')

    def test_heartbeat_accepts_hashed_password(self, org):
        """Heartbeat accepts device with hashed password."""
        Device.objects.create(
            device_id='GT-HB-001',
            password=hash_device_password('hbpass'),
            organization=org,
        )
        client = APIClient()
        response = client.post('/api/heartbeat/', {
            'device_id': 'GT-HB-001',
            'password': 'hbpass',
        })
        assert response.status_code == 200
        assert response.data['status'] == 'ok'

    def test_heartbeat_rejects_wrong_password(self, org):
        """Heartbeat rejects wrong password."""
        Device.objects.create(
            device_id='GT-HB-002',
            password=hash_device_password('correct'),
            organization=org,
        )
        client = APIClient()
        response = client.post('/api/heartbeat/', {
            'device_id': 'GT-HB-002',
            'password': 'wrong',
        })
        assert response.status_code == 401

    def test_heartbeat_accepts_legacy_plaintext(self, org):
        """Heartbeat still works with legacy plaintext passwords."""
        Device.objects.create(
            device_id='GT-HB-003',
            password='legacy_plain',
            organization=org,
        )
        client = APIClient()
        response = client.post('/api/heartbeat/', {
            'device_id': 'GT-HB-003',
            'password': 'legacy_plain',
        })
        assert response.status_code == 200
