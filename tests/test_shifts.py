import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from api.models import ShiftAssignment, ScanRecord, GuardSupervisor
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