import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from api.models import ShiftAssignment, ScanRecord, GuardSupervisor, PatrolRoute
from django.utils import timezone


@pytest.mark.django_db
class TestShiftAssignmentEnd:
    """TC-API-018: Shift Assignment End"""

    def test_end_shift_deactivates_assignment(self, api_client, active_assignment, guard_supervisor, auth_headers):
        """Manually ending shift sets is_active=False"""
        response = api_client.post(
            f'/api/end-shift/{active_assignment.id}/',
            {},
            format='json',
            **auth_headers
        )

        assert response.status_code in [200, 302]

        active_assignment.refresh_from_db()
        assert active_assignment.is_active is False
        assert active_assignment.ended_at is not None

    def test_end_shift_updates_guard_status(self, api_client, active_assignment, guard_supervisor, auth_headers):
        """Ending shift sets guard's is_on_shift to False"""
        api_client.post(
            f'/api/end-shift/{active_assignment.id}/',
            {},
            format='json',
            **auth_headers
        )

        guard_supervisor.refresh_from_db()
        assert guard_supervisor.is_on_shift is False


@pytest.mark.django_db
class TestMissionStatus:
    """TC-API-017: Mission Status - Active Patrol"""

    def test_mission_status_returns_next_checkpoint(self, api_client, active_assignment, registered_device, patrol_route_with_checkpoints, guard_supervisor):
        """Get mission status shows next checkpoint info"""

        ScanRecord.objects.create(
            guard_supervisor=guard_supervisor,
            device=registered_device,
            route=patrol_route_with_checkpoints,
            checkpoint=patrol_route_with_checkpoints.checkpoints.first(),
            checkpoint_name='Gate',
            nfc_value='TAG-GATE',
            is_on_time=True
        )

        response = api_client.get(
            f'/api/mission-status/{active_assignment.id}/',
            format='json'
        )

        assert response.status_code == 200
        data = response.json()
        assert 'staging' in data
        assert data['staging']['completed'] is False
        assert data['staging']['hit_count'] == 1
        assert data['staging']['next_checkpoint']['name'] == 'Lobby'

    def test_mission_status_completed_after_all_scans(self, api_client, active_assignment, registered_device, patrol_route_with_checkpoints, guard_supervisor):
        """Mission shows completed when all checkpoints scanned"""
        for cp in patrol_route_with_checkpoints.checkpoints.all():
            ScanRecord.objects.create(
                guard_supervisor=guard_supervisor,
                device=registered_device,
                route=patrol_route_with_checkpoints,
                checkpoint=cp,
                checkpoint_name=cp.name,
                nfc_value=cp.nfc_tag,
                is_on_time=True
            )

        response = api_client.get(
            f'/api/mission-status/{active_assignment.id}/',
            format='json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['staging']['completed'] is True


@pytest.mark.django_db
class TestShiftBulkCreate:
    """Test bulk shift creation"""

    def test_bulk_create_shifts(self, api_client, default_organization, guard_supervisor, auth_headers):
        """Creating multiple shifts with guard_ids list"""
        other_guard = guard_supervisor.__class__.objects.create(
            first_name='Jane',
            last_name='Doe',
            organization=default_organization,
            role='guard',
            shift='Night'
        )

        response = api_client.post('/api/shifts/', {
            'guard_ids': [guard_supervisor.id, other_guard.id],
            'shift_type': 'Day',
            'scheduled_date': str(timezone.now().date())
        }, format='json', **auth_headers)

        assert response.status_code == 201
        assignments = ShiftAssignment.objects.filter(shift_type='Day')
        assert assignments.count() == 2


@pytest.mark.django_db
class TestSwapOperator:
    """TC-API-016: Swap Operator"""

    def test_swap_operator_to_different_guard(self, api_client, registered_device, guard_supervisor, default_organization, auth_headers):
        """Remotely reassign device from one guard to another"""
        other_guard = GuardSupervisor.objects.create(
            first_name='New',
            last_name='Guard',
            organization=default_organization,
            role='guard',
            shift='Day'
        )

        response = api_client.post(
            f'/api/devices/{registered_device.id}/swap_operator/',
            {'guard_id': other_guard.id},
            format='json',
            **auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'swapped'

        old_assignment = ShiftAssignment.objects.filter(
            guard_supervisor=guard_supervisor,
            is_active=True
        ).first()
        assert old_assignment is None or old_assignment.is_active is False


@pytest.mark.django_db
class TestCreateAuditShift:
    """Tests for peer-to-peer audit shift creation."""

    @pytest.fixture
    def audit_route(self, db, default_organization):
        route = PatrolRoute.objects.create(
            name='Audit Route 1',
            organization=default_organization,
            is_audit=True,
            status='active',
        )
        return route

    @pytest.fixture
    def audit_guards(self, db, default_organization):
        g1 = GuardSupervisor.objects.create(
            first_name='Alice', last_name='Audit',
            organization=default_organization, role='guard', shift='Day',
            callsign='TST-A1',
        )
        g2 = GuardSupervisor.objects.create(
            first_name='Bob', last_name='Audit',
            organization=default_organization, role='guard', shift='Day',
            callsign='TST-A2',
        )
        g3 = GuardSupervisor.objects.create(
            first_name='Charlie', last_name='Audit',
            organization=default_organization, role='guard', shift='Day',
            callsign='TST-A3',
        )
        return [g1, g2, g3]

    def test_create_audit_shift_success(self, api_client, dispatcher_user, audit_route, audit_guards, auth_headers):
        """Creating audit shift creates assignments for all guards."""
        guard_ids = [g.id for g in audit_guards]
        response = api_client.post(
            '/api/v1/audit/create-shift/',
            {
                'route_id': audit_route.id,
                'guard_ids': guard_ids,
                'scheduled_date': '2027-07-15',
                'shift_type': 'Day',
                'start_time': '08:00',
                'end_time': '16:00',
            },
            format='json',
            **auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data['status'] == 'created'
        assert data['shifts_created'] == 3
        assert data['is_audit'] is True
        assert data['total_pairs'] == 6  # 3 guards × 2 directions = 6 pairs

        # Verify shifts were created in DB
        shifts = ShiftAssignment.objects.filter(route=audit_route, is_active=True)
        assert shifts.count() == 3

    def test_create_audit_shift_requires_audit_route(self, api_client, dispatcher_user, patrol_route_with_checkpoints, audit_guards, auth_headers):
        """Non-audit routes are rejected."""
        guard_ids = [g.id for g in audit_guards]
        response = api_client.post(
            '/api/v1/audit/create-shift/',
            {
                'route_id': patrol_route_with_checkpoints.id,
                'guard_ids': guard_ids,
                'shift_type': 'Day',
            },
            format='json',
            **auth_headers
        )

        assert response.status_code == 400
        assert 'not an audit route' in response.json()['detail'].lower()

    def test_create_audit_shift_requires_min_2_guards(self, api_client, dispatcher_user, audit_route, audit_guards, auth_headers):
        """Single guard is rejected for peer audit."""
        response = api_client.post(
            '/api/v1/audit/create-shift/',
            {
                'route_id': audit_route.id,
                'guard_ids': [audit_guards[0].id],
                'shift_type': 'Day',
            },
            format='json',
            **auth_headers
        )

        assert response.status_code == 400
        assert 'at least 2 guards' in response.json()['detail'].lower()

    def test_create_audit_shift_sets_peer_keys(self, api_client, dispatcher_user, audit_route, audit_guards, auth_headers):
        """Each guard's device gets a peer_session_key."""
        guard_ids = [g.id for g in audit_guards]
        response = api_client.post(
            '/api/v1/audit/create-shift/',
            {
                'route_id': audit_route.id,
                'guard_ids': guard_ids,
                'shift_type': 'Day',
            },
            format='json',
            **auth_headers
        )

        assert response.status_code == 201
        data = response.json()

        # Each shift should have a peer_session_key
        for shift in data['shifts']:
            if shift['device_id']:
                assert shift['peer_session_key'] is not None
                assert len(shift['peer_session_key']) == 16  # hex(8 bytes) = 16 chars