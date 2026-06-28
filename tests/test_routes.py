import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from api.models import PatrolRoute, Checkpoint, ShiftAssignment, GuardSupervisor
from django.utils import timezone


@pytest.mark.django_db
class TestRouteCreation:
    """TC-API-007: Route (Blueprint) Creation with Checkpoints"""

    def test_create_route_with_checkpoints(self, api_client, default_organization, guard_supervisor, auth_headers):
        """Create a patrol route with embedded checkpoints"""
        response = api_client.post('/api/routes/', {
            'name': 'Test Patrol Route',
            'status': 'draft',
            'logic_type': 'Sequential',
            'assigned_guards': [guard_supervisor.id],
            'checkpoints': [
                {
                    'name': 'Gate',
                    'checkpoint_type': 'nfc',
                    'nfc_tag': 'TAG-GATE',
                    'order': 1,
                    'planned_time': '08:00:00',
                    'time_tolerance': 15
                },
                {
                    'name': 'Lobby',
                    'checkpoint_type': 'nfc',
                    'nfc_tag': 'TAG-LOBBY',
                    'order': 2,
                    'planned_time': '08:30:00',
                    'time_tolerance': 10
                }
            ]
        }, format='json', **auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data['name'] == 'Test Patrol Route'
        assert len(data['checkpoints']) == 2

        route = PatrolRoute.objects.get(id=data['id'])
        assert route.checkpoints.count() == 2
        assert route.organization == default_organization

    def test_checkpoint_type_gps_requires_coords(self, api_client, default_organization, auth_headers):
        """GPS checkpoint must have lat/lng coordinates"""
        response = api_client.post('/api/routes/', {
            'name': 'GPS Route',
            'checkpoints': [
                {
                    'name': 'GPS Point',
                    'checkpoint_type': 'gps',
                    'lat': 40.7128,
                    'lng': -74.0060,
                    'radius': 50,
                    'order': 1
                }
            ]
        }, format='json', **auth_headers)

        assert response.status_code == 201

    def test_nfc_checkpoint_auto_clears_coords(self, api_client, default_organization, auth_headers):
        """NFC checkpoint automatically clears lat/lng fields"""
        response = api_client.post('/api/routes/', {
            'name': 'NFC Route',
            'checkpoints': [
                {
                    'name': 'NFC Point',
                    'checkpoint_type': 'nfc',
                    'nfc_tag': 'TAG-TEST',
                    'lat': 40.7128,
                    'lng': -74.0060,
                    'order': 1
                }
            ]
        }, format='json', **auth_headers)

        assert response.status_code == 201
        cp_data = response.json()['checkpoints'][0]
        assert cp_data['lat'] is None
        assert cp_data['lng'] is None


@pytest.mark.django_db
class TestRouteDeployment:
    """TC-API-008: Route Deployment"""

    def test_deploy_creates_shift_assignments(self, api_client, patrol_route_with_checkpoints, auth_headers):
        """Deploy creates active shift assignments for assigned guards"""
        response = api_client.post(
            f'/api/routes/{patrol_route_with_checkpoints.id}/deploy/',
            {},
            format='json',
            **auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'deployed'
        assert data['assignments_count'] == 1

        assignment = ShiftAssignment.objects.get(route=patrol_route_with_checkpoints)
        assert assignment.is_active is True

    def test_deploy_empty_route_fails(self, api_client, default_organization, auth_headers):
        """Deploying route with no assigned guards/devices fails"""
        empty_route = PatrolRoute.objects.create(
            name='Empty Route',
            organization=default_organization
        )

        response = api_client.post(
            f'/api/routes/{empty_route.id}/deploy/',
            {},
            format='json',
            **auth_headers
        )

        assert response.status_code == 400
        assert 'No personnel or devices assigned' in response.json()['detail']


@pytest.mark.django_db
class TestCheckpointValidation:
    """TC-API-023: Checkpoint Validation - NFC without Tag"""

    def test_nfc_checkpoint_requires_nfc_tag(self, api_client, default_organization, auth_headers):
        """Cannot create NFC checkpoint without nfc_tag"""
        response = api_client.post('/api/checkpoints/', {
            'name': 'Invalid NFC',
            'checkpoint_type': 'nfc',
            'nfc_tag': '',
            'organization': default_organization.id
        }, format='json', **auth_headers)

        assert response.status_code == 400

    def test_gps_checkpoint_requires_coordinates(self, api_client, default_organization, auth_headers):
        """Cannot create GPS checkpoint without lat/lng"""
        response = api_client.post('/api/checkpoints/', {
            'name': 'Invalid GPS',
            'checkpoint_type': 'gps',
            'organization': default_organization.id
        }, format='json', **auth_headers)

        assert response.status_code == 400


@pytest.mark.django_db
class TestCheckpointDuplicateTime:
    """TC-API-024: Checkpoint Duplicate Planned Time"""

    def test_duplicate_planned_time_rejected(self, api_client, default_organization, auth_headers):
        """Cannot have two checkpoints on same route with same planned_time"""
        route = PatrolRoute.objects.create(
            name='Time Test Route',
            organization=default_organization
        )
        Checkpoint.objects.create(
            route=route,
            organization=default_organization,
            name='First Checkpoint',
            checkpoint_type='nfc',
            nfc_tag='TAG-001',
            planned_time='08:00:00',
            order=1
        )

        response = api_client.post('/api/checkpoints/', {
            'name': 'Duplicate Time',
            'checkpoint_type': 'nfc',
            'nfc_tag': 'TAG-002',
            'route': route.id,
            'organization': default_organization.id,
            'planned_time': '08:00:00',
            'order': 2
        }, format='json', **auth_headers)

        assert response.status_code == 400
        assert 'Another checkpoint in this route already has planned time' in str(response.json())