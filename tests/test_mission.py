"""Tests for the mission state machine (api.services.mission).

Verifies valid/invalid stage transitions, status transitions,
complete_mission helper, and timeline retrieval.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError
from django.utils import timezone

from api.models import (
    Organization, Dispatcher, GuardSupervisor, Device,
    PatrolRoute, ShiftAssignment, MissionStateLog,
)
from api.services.mission import (
    transition_mission_stage, transition_mission_status,
    complete_mission, get_mission_timeline,
    VALID_MISSION_STAGE_TRANSITIONS, VALID_STATUS_TRANSITIONS,
)
from api.password import hash_device_password


@pytest.mark.django_db
class TestMissionStageTransitions:
    """Tests for mission stage state machine."""

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Mission Org', code='MSN')

    @pytest.fixture
    def assignment(self, db, org):
        guard = GuardSupervisor.objects.create(
            first_name='Test', last_name='Guard',
            organization=org, callsign='MSN-01',
        )
        device = Device.objects.create(
            device_id='GT-MSN-001', password=hash_device_password('pass'),
            organization=org, callsign='MSN-01',
        )
        route = PatrolRoute.objects.create(name='Route', organization=org)
        return ShiftAssignment.objects.create(
            dispatcher=User.objects.create_user(username='msn_disp', password='pass'),
            guard_supervisor=guard, device=device, route=route,
            scheduled_date=timezone.now().date(),
            scheduled_start=timezone.now(),
            shift_type='Day', is_active=True,
            mission_stage='assigned', status='active',
        )

    def test_assigned_to_deployed(self, assignment):
        """assigned -> deployed is valid."""
        log = transition_mission_stage(assignment, 'deployed', reason='test')
        assert log.from_stage == 'assigned'
        assert log.to_stage == 'deployed'
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'deployed'

    def test_deployed_to_active(self, assignment):
        """deployed -> active is valid."""
        assignment.mission_stage = 'deployed'
        assignment.save()
        transition_mission_stage(assignment, 'active', reason='first_scan')
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'active'

    def test_active_to_completing(self, assignment):
        """active -> completing is valid."""
        assignment.mission_stage = 'active'
        assignment.save()
        transition_mission_stage(assignment, 'completing')
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'completing'

    def test_completing_to_completed(self, assignment):
        """completing -> completed is valid."""
        assignment.mission_stage = 'completing'
        assignment.save()
        transition_mission_stage(assignment, 'completed')
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'completed'

    def test_invalid_transition_raises(self, assignment):
        """assigned -> completed is NOT valid (must go through deployed/active)."""
        with pytest.raises(ValidationError, match='Invalid mission stage transition'):
            transition_mission_stage(assignment, 'completed')

    def test_cannot_transition_from_completed(self, assignment):
        """completed is a terminal state."""
        assignment.mission_stage = 'completed'
        assignment.save()
        with pytest.raises(ValidationError):
            transition_mission_stage(assignment, 'active')

    def test_emergency_pause_transition(self, assignment):
        """active -> emergency_pause -> active is valid."""
        assignment.mission_stage = 'active'
        assignment.save()
        transition_mission_stage(assignment, 'emergency_pause', reason='incident')
        transition_mission_stage(assignment, 'active', reason='resolved')
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'active'

    def test_transition_creates_log(self, assignment):
        """Each transition creates a MissionStateLog entry."""
        transition_mission_stage(assignment, 'deployed', reason='test')
        assert MissionStateLog.objects.filter(assignment=assignment).count() == 1

    def test_transition_with_device_and_scan(self, assignment, org):
        """Transition can record triggering device and scan."""
        device = Device.objects.get(callsign='MSN-01')
        log = transition_mission_stage(
            assignment, 'deployed', reason='test', device=device
        )
        assert log.device == device


@pytest.mark.django_db
class TestMissionStatusTransitions:
    """Tests for mission status state machine."""

    @pytest.fixture
    def assignment(self, db):
        org = Organization.objects.create(name='Status Org', code='STS')
        guard = GuardSupervisor.objects.create(
            first_name='Test', last_name='Guard',
            organization=org, callsign='STS-01',
        )
        device = Device.objects.create(
            device_id='GT-STS-001', password=hash_device_password('pass'),
            organization=org, callsign='STS-01',
        )
        route = PatrolRoute.objects.create(name='Route', organization=org)
        return ShiftAssignment.objects.create(
            dispatcher=User.objects.create_user(username='sts_disp', password='pass'),
            guard_supervisor=guard, device=device, route=route,
            scheduled_date=timezone.now().date(),
            scheduled_start=timezone.now(),
            shift_type='Day', is_active=True,
            mission_stage='assigned', status='active',
        )

    def test_active_to_emergency(self, assignment):
        """active -> emergency_active is valid."""
        transition_mission_status(assignment, 'emergency_active', reason='breach')
        assignment.refresh_from_db()
        assert assignment.status == 'emergency_active'

    def test_emergency_to_active(self, assignment):
        """emergency_active -> active is valid."""
        assignment.status = 'emergency_active'
        assignment.save()
        transition_mission_status(assignment, 'active', reason='resolved')
        assignment.refresh_from_db()
        assert assignment.status == 'active'

    def test_active_to_completed(self, assignment):
        """active -> completed is valid."""
        transition_mission_status(assignment, 'completed', reason='all done')
        assignment.refresh_from_db()
        assert assignment.status == 'completed'

    def test_invalid_status_transition(self, assignment):
        """completed -> active is NOT valid."""
        assignment.status = 'completed'
        assignment.save()
        with pytest.raises(ValidationError, match='Invalid mission status transition'):
            transition_mission_status(assignment, 'active')


@pytest.mark.django_db
class TestCompleteMission:
    """Tests for the complete_mission helper."""

    @pytest.fixture
    def assignment(self, db):
        org = Organization.objects.create(name='Complete Org', code='CMP')
        guard = GuardSupervisor.objects.create(
            first_name='Test', last_name='Guard',
            organization=org, callsign='CMP-01',
        )
        device = Device.objects.create(
            device_id='GT-CMP-001', password=hash_device_password('pass'),
            organization=org, callsign='CMP-01',
        )
        route = PatrolRoute.objects.create(name='Route', organization=org)
        return ShiftAssignment.objects.create(
            dispatcher=User.objects.create_user(username='cmp_disp', password='pass'),
            guard_supervisor=guard, device=device, route=route,
            scheduled_date=timezone.now().date(),
            scheduled_start=timezone.now(),
            shift_type='Day', is_active=True,
            mission_stage='active', status='active',
        )

    def test_complete_mission_sets_all_fields(self, assignment):
        """complete_mission sets stage, status, is_completed, is_active, ended_at."""
        complete_mission(assignment)
        assignment.refresh_from_db()
        assert assignment.mission_stage == 'completed'
        assert assignment.status == 'completed'
        assert assignment.is_completed is True
        assert assignment.is_active is False
        assert assignment.ended_at is not None

    def test_complete_mission_creates_log(self, assignment):
        """complete_mission creates a MissionStateLog."""
        log = complete_mission(assignment)
        assert log.to_stage == 'completed'
        assert log.reason == 'all_checkpoints_scanned'


@pytest.mark.django_db
class TestMissionTimeline:
    """Tests for get_mission_timeline."""

    @pytest.fixture
    def assignment(self, db):
        org = Organization.objects.create(name='Timeline Org', code='TML')
        guard = GuardSupervisor.objects.create(
            first_name='Test', last_name='Guard',
            organization=org, callsign='TML-01',
        )
        device = Device.objects.create(
            device_id='GT-TML-001', password=hash_device_password('pass'),
            organization=org, callsign='TML-01',
        )
        route = PatrolRoute.objects.create(name='Route', organization=org)
        return ShiftAssignment.objects.create(
            dispatcher=User.objects.create_user(username='tml_disp', password='pass'),
            guard_supervisor=guard, device=device, route=route,
            scheduled_date=timezone.now().date(),
            scheduled_start=timezone.now(),
            shift_type='Day', is_active=True,
            mission_stage='assigned', status='active',
        )

    def test_timeline_returns_chronological_order(self, assignment):
        """Timeline returns logs in chronological order."""
        transition_mission_stage(assignment, 'deployed', reason='step1')
        transition_mission_stage(assignment, 'active', reason='step2')
        transition_mission_stage(assignment, 'completing', reason='step3')

        timeline = get_mission_timeline(assignment)
        assert len(timeline) == 3
        assert timeline[0].to_stage == 'deployed'
        assert timeline[1].to_stage == 'active'
        assert timeline[2].to_stage == 'completing'

    def test_timeline_empty_for_new_assignment(self, assignment):
        """New assignment has no timeline entries."""
        timeline = get_mission_timeline(assignment)
        assert len(timeline) == 0
