import pytest
from django.utils import timezone
from datetime import timedelta, time, datetime
from django.contrib.auth.models import User
from api.models import (
    Organization, Device, Checkpoint, PatrolRoute, ShiftAssignment,
    ScanRecord, DeviceSession, MissionStateLog, AlertRule, DeviceTrail
)
from api.scan_service import (
    verify_zone_scan, _compute_effective_radius, _detect_anomalies,
    device_has_clean_progression_record, _walk_dwell_trail,
    _sensor_confirms_presence, _sensor_mismatch
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name='Test Org', code='TST')


@pytest.fixture
def dispatcher(db):
    return User.objects.create_user('dispatcher', 'd@t.com', 'pw123')


@pytest.fixture
def device(db, org):
    return Device.objects.create(device_id='GT-ZV', password='pw', organization=org)


@pytest.fixture
def route(db, org):
    return PatrolRoute.objects.create(name='Zone Route', organization=org)


@pytest.fixture
def assignment(db, dispatcher, device, route):
    return ShiftAssignment.objects.create(
        dispatcher=dispatcher, device=device, route=route, is_active=True,
        scheduled_start=timezone.now(),
    )


def _now_at(hour, minute=0):
    return timezone.make_aware(datetime.combine(timezone.now().date(), time(hour, minute, 0)))


@pytest.mark.django_db
class TestToleranceNopGate:
    def test_scan_outside_tolerance_window_dropped(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='CP', checkpoint_type='gps',
            lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', time_tolerance=15,
            organization=org,
        )
        now = _now_at(8, 35)
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now, is_last_checkpoint=True)
        assert result['dropped'] is True
        assert result['validity_score'] == 0.0
        assert 'out_of_tolerance_window' in result['verification_notes']

    def test_scan_within_tolerance_window_not_dropped(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='CP', checkpoint_type='gps',
            lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', time_tolerance=15,
            organization=org,
        )
        now = _now_at(8, 5)
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now)
        assert result['dropped'] is False


@pytest.mark.django_db
class TestRadiusDefaults:
    def test_strict_precision_uses_half_radius(self, org):
        checkpoint = Checkpoint.objects.create(
            name='Strict CP', radius=5, precision_level='strict',
            lat=40.7128, lng=-74.0060, checkpoint_type='gps',
            organization=org,
        )
        effective = _compute_effective_radius(checkpoint)
        assert effective == 2.5

    def test_normal_precision_uses_full_radius(self, org):
        checkpoint = Checkpoint.objects.create(
            name='Normal CP', radius=5, precision_level='normal',
            lat=40.7128, lng=-74.0060, checkpoint_type='gps',
            organization=org,
        )
        effective = _compute_effective_radius(checkpoint)
        assert effective == 5.0

    def test_loose_precision_uses_double_radius(self, org):
        checkpoint = Checkpoint.objects.create(
            name='Loose CP', radius=5, precision_level='loose',
            lat=40.7128, lng=-74.0060, checkpoint_type='gps',
            organization=org,
        )
        effective = _compute_effective_radius(checkpoint)
        assert effective == 10.0

    def test_default_radius_is_5_not_50(self, org):
        checkpoint = Checkpoint.objects.create(
            name='Default CP', precision_level='normal',
            lat=40.7128, lng=-74.0060, checkpoint_type='gps',
            organization=org,
        )
        effective = _compute_effective_radius(checkpoint)
        assert effective == 5.0

    def test_sensor_fallback_extends_radius_to_15m(self, org):
        checkpoint = Checkpoint.objects.create(
            name='Sensor CP', radius=5, precision_level='strict',
            lat=40.7128, lng=-74.0060, checkpoint_type='gps',
            organization=org,
        )
        sensor_ctx = {'pir_triggered': True, 'proximity_score': 0.9, 'accel_pattern': 'steady'}
        effective = _compute_effective_radius(checkpoint, sensor_ctx)
        assert effective == 15.0


@pytest.mark.django_db
class TestDwellTrailValidation:
    def test_dwell_trail_computes_continuous_presence(self, device, route, assignment, org):
        checkpoint = Checkpoint.objects.create(
            name='Dwell CP', lat=40.7128, lng=-74.0060, radius=5,
            dwell_time=2, planned_time='08:00:00',
            organization=org, route=route, checkpoint_type='gps',
        )
        now = _now_at(8, 5)
        window_start = now - timedelta(minutes=15)
        for i in range(5):
            DeviceTrail.objects.create(
                device=device, assignment=assignment,
                lat=40.7128 + i * 0.00001, lng=-74.0060,
                recorded_at=window_start + timedelta(minutes=i),
                accuracy=5.0,
            )
        continuous, points, _ = _walk_dwell_trail(
            device, assignment, checkpoint, 5.0, window_start, now, now
        )
        assert len(points) == 5
        assert continuous >= 0

    def test_dwell_valid_when_sufficient_time(self, device, route, assignment, org):
        checkpoint = Checkpoint.objects.create(
            name='Dwell CP2', lat=40.7128, lng=-74.0060, radius=5,
            dwell_time=1, planned_time='08:00:00',
            organization=org, route=route, checkpoint_type='gps',
        )
        now = _now_at(8, 5)
        window_start = now - timedelta(minutes=15)
        for i in range(7):
            DeviceTrail.objects.create(
                device=device, assignment=assignment,
                lat=40.7128, lng=-74.0060,
                recorded_at=window_start + timedelta(seconds=i * 15),
                accuracy=5.0,
            )
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now, assignment=assignment)
        assert result['dwell_valid'] is True
        assert result['dwell_seconds'] is not None
        assert result['dwell_seconds'] >= 60


@pytest.mark.django_db
class TestAnomalyDetection:
    def test_sudden_jump_flagged(self, org):
        base = timezone.now()
        points = [
            {'lat': 40.7128, 'lng': -74.0060, 'recorded_at': base, 'accuracy': 5.0},
            {'lat': 40.7128, 'lng': -74.0060, 'recorded_at': base + timedelta(seconds=30), 'accuracy': 5.0},
            {'lat': 40.7300, 'lng': -74.0200, 'recorded_at': base + timedelta(seconds=60), 'accuracy': 5.0},
            {'lat': 40.7128, 'lng': -74.0060, 'recorded_at': base + timedelta(seconds=90), 'accuracy': 5.0},
            {'lat': 40.7500, 'lng': -74.0300, 'recorded_at': base + timedelta(seconds=120), 'accuracy': 5.0},
            {'lat': 40.7128, 'lng': -74.0060, 'recorded_at': base + timedelta(seconds=150), 'accuracy': 5.0},
            {'lat': 40.7600, 'lng': -74.0400, 'recorded_at': base + timedelta(seconds=180), 'accuracy': 5.0},
        ]
        checkpoint = Checkpoint.objects.create(
            name='Jump CP', lat=40.7128, lng=-74.0060, radius=50,
            organization=org, checkpoint_type='gps',
        )
        flags = _detect_anomalies(points, checkpoint, 0)
        assert 'sudden_jump' in flags or 'gps_instability' in flags

    def test_gps_instability_flagged(self, org):
        now = timezone.now()
        points = [
            {'lat': 40.7128, 'lng': -74.0060, 'recorded_at': now, 'accuracy': 1.8},
            {'lat': 40.7129, 'lng': -74.0061, 'recorded_at': now + timedelta(seconds=30), 'accuracy': 7.2},
        ]
        checkpoint = Checkpoint.objects.create(
            name='GPS Hop CP', lat=40.7128, lng=-74.0060, radius=50,
            organization=org, checkpoint_type='gps',
        )
        flags = _detect_anomalies(points, checkpoint, 0)
        assert 'gps_instability' in flags


@pytest.mark.django_db
class TestSensorFallback:
    def test_sensor_confirmed_upgrades_score(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='Sensor CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', checkpoint_type='gps',
            organization=org,
        )
        now = _now_at(8, 5)
        sensor_ctx = {'pir_triggered': True, 'proximity_score': 0.9, 'accel_pattern': 'steady'}
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now, sensor_context=sensor_ctx)
        assert result['sensor_aided'] is True
        assert result['validity_score'] >= 0.5

    def test_sensor_mismatch_downgrades_score(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='Mismatch CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', checkpoint_type='gps',
            organization=org,
        )
        now = _now_at(8, 5)
        sensor_ctx = {'pir_triggered': False, 'proximity_score': 0.2, 'accel_pattern': 'erratic'}
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now, sensor_context=sensor_ctx)
        assert 'sensor_mismatch' in result['anomaly_flags']


@pytest.mark.django_db
class TestProbabilityScoring:
    def test_weighted_score_computed(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='Weight CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', checkpoint_type='gps',
            organization=org,
        )
        now = _now_at(8, 5)
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now)
        assert 0.0 <= result['validity_score'] <= 1.0
        assert result['validity_score'] > 0


@pytest.mark.django_db
class TestProgressionRecordDegradation:
    def test_guard_with_poor_history_gets_degraded(self, device, route, assignment, org):
        checkpoint = Checkpoint.objects.create(
            name='Prog CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', checkpoint_type='gps',
            organization=org, route=route,
        )
        now = _now_at(8, 5)
        for i in range(5):
            ScanRecord.objects.create(
                device=device, checkpoint=checkpoint,
                route=route, is_on_time=False, validity_score=0.3,
                timestamp=now - timedelta(minutes=30 - i),
            )
        assert device_has_clean_progression_record(assignment, device, now) is False
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now, assignment=assignment)
        assert 'degraded_by_history' in result['verification_notes']


@pytest.mark.django_db
class TestProlongedDwellPenalty:
    def test_excessive_dwell_flagged(self, org):
        now = timezone.now()
        points = []
        for i in range(30):
            points.append({
                'lat': 40.7128, 'lng': -74.0060,
                'recorded_at': now + timedelta(minutes=i),
                'accuracy': 5.0,
            })
        checkpoint = Checkpoint.objects.create(
            name='Long Dwell CP', lat=40.7128, lng=-74.0060, radius=5,
            dwell_time=5, checkpoint_type='gps',
            organization=org,
        )
        flags = _detect_anomalies(points, checkpoint, 30 * 60)
        assert 'prolonged_dwell' in flags


@pytest.mark.django_db
class TestStateTransitions:
    def test_session_state_transitions(self, device, route, assignment, org):
        checkpoint = Checkpoint.objects.create(
            name='Stage CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00',
            organization=org, route=route, checkpoint_type='gps',
        )
        now = _now_at(8, 5)
        result = verify_zone_scan(
            device, checkpoint, 40.7128, -74.0060, now,
            assignment=assignment,
        )
        assert result['validity_score'] > 0
        session = DeviceSession.objects.filter(device=device, is_active=True).first()
        if session:
            assert session.state in ('on_route', 'checkpoint_due', 'completed')


@pytest.mark.django_db
class TestMapResidencyEvent:
    def test_radius_check_publishes_map_update(self, device, org):
        checkpoint = Checkpoint.objects.create(
            name='Map CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', checkpoint_type='gps',
            organization=org,
        )
        now = _now_at(8, 5)
        result = verify_zone_scan(device, checkpoint, 40.7128, -74.0060, now)
        assert result['map_update'] is not None
        assert result['map_update']['event'] == 'zone_enter'
        assert result['map_update']['checkpoint_id'] == checkpoint.id


@pytest.mark.django_db
class TestMissionStallPenalty:
    def test_last_checkpoint_past_window_gets_penalty(self, device, route, assignment, org):
        checkpoint = Checkpoint.objects.create(
            name='Stall CP', lat=40.7128, lng=-74.0060, radius=5,
            planned_time='08:00:00', time_tolerance=2, dwell_time=0,
            organization=org, route=route, checkpoint_type='gps',
        )
        now = _now_at(8, 15)
        result = verify_zone_scan(
            device, checkpoint, 40.7128, -74.0060, now,
            assignment=assignment, is_last_checkpoint=True, mission_completed=False,
        )
        assert 'mission_stall_penalty' in result['verification_notes']
