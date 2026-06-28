import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.utils import timezone
import json

from api.models import (
    Organization, Admin, Dispatcher, GuardSupervisor, Device,
    PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, CallSign,
    DeviceProvisioning
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def default_organization(db):
    org, _ = Organization.objects.get_or_create(
        name="Test Organization",
        defaults={
            'code': 'TST',
            'contact_email': 'test@test.com',
            'is_active': True
        }
    )
    if not org.code:
        org.code = 'TST'
        org.save()
    return org


@pytest.fixture
def dispatcher_user(db, default_organization):
    user = User.objects.create_user(
        username='dispatcher1',
        password='testpass123',
        email='dispatcher@test.com'
    )
    dispatcher = Dispatcher.objects.create(
        user=user,
        organization=default_organization,
        can_manage_routes=True,
        can_manage_guards=True,
        can_view_reports=True,
        can_manage_devices=True
    )
    return user, dispatcher


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        username='admin',
        password='adminpass',
        email='admin@test.com'
    )
    Admin.objects.create(user=user)
    return user


@pytest.fixture
def guard_supervisor(db, default_organization):
    return GuardSupervisor.objects.create(
        first_name='John',
        last_name='Doe',
        organization=default_organization,
        role='guard',
        shift='Day',
        callsign='TST-01'
    )


@pytest.fixture
def registered_device(db, default_organization, guard_supervisor):
    device = Device.objects.create(
        device_id='GT-TEST001',
        device_name='Test Device',
        password='testpassword123',
        organization=default_organization,
        callsign='TST-01'
    )
    CallSign.objects.create(
        device=device,
        organization=default_organization,
        callsign='TST-01',
        current_guard=guard_supervisor,
        active_shift='Day'
    )
    DeviceProvisioning.objects.create(
        device=device,
        guard=guard_supervisor,
        callsign_snapshot='TST-01',
        organization=default_organization
    )
    return device


@pytest.fixture
def patrol_route_with_checkpoints(db, default_organization, guard_supervisor):
    route = PatrolRoute.objects.create(
        name='Morning Patrol',
        organization=default_organization,
        status='active',
        enforce_order=True,
        enforce_time=True
    )
    route.assigned_guards.add(guard_supervisor)

    Checkpoint.objects.create(
        route=route,
        organization=default_organization,
        name='Gate',
        checkpoint_type='nfc',
        nfc_tag='TAG-GATE',
        order=1,
        planned_time='08:00:00',
        time_tolerance=15
    )
    Checkpoint.objects.create(
        route=route,
        organization=default_organization,
        name='Lobby',
        checkpoint_type='nfc',
        nfc_tag='TAG-LOBBY',
        order=2,
        planned_time='08:30:00',
        time_tolerance=10
    )
    return route


@pytest.fixture
def active_assignment(db, dispatcher_user, guard_supervisor, registered_device, patrol_route_with_checkpoints):
    user, dispatcher = dispatcher_user
    return ShiftAssignment.objects.create(
        dispatcher=user,
        guard_supervisor=guard_supervisor,
        device=registered_device,
        route=patrol_route_with_checkpoints,
        scheduled_date=timezone.now().date(),
        scheduled_start=timezone.now(),
        shift_type='Day',
        is_active=True
    )


@pytest.fixture
def auth_headers(dispatcher_user):
    user, _ = dispatcher_user
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


@pytest.fixture
def admin_headers(admin_user):
    refresh = RefreshToken.for_user(admin_user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}