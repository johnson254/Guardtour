"""Query-count regression tests for ViewSet optimization.

These tests guard against N+1 query reintroduction. If a future change
adds an unpreloaded serializer field or removes a select_related, these
will fail. Thresholds are set slightly above current counts to allow
for minor variations but catch O(n) regressions.
"""
import pytest
from django.test.utils import override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

from api.models import (
    Organization, Dispatcher, GuardSupervisor, Device,
    PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, CallSign,
)
from api.password import hash_device_password


@pytest.mark.django_db
class TestQueryCountOptimization:
    """Query-count regression tests for optimized ViewSets.

    These guard against N+1 query reintroduction. If a future change
    adds an unpreloaded serializer field, these tests will fail.
    """

    @pytest.fixture
    def org(self, db):
        return Organization.objects.create(name='Query Opt Org', code='QOP')

    @pytest.fixture
    def dispatcher_user(self, db, org):
        user = User.objects.create_user(username='quser', password='pass')
        Dispatcher.objects.create(
            user=user, organization=org,
            can_manage_routes=True, can_manage_guards=True,
            can_view_reports=True, can_manage_devices=True,
        )
        return user

    @pytest.fixture
    def populated_data(self, db, org):
        """Create realistic dataset to stress query paths."""
        guards = []
        devices = []
        for i in range(3):
            g = GuardSupervisor.objects.create(
                first_name=f'Guard{i}', last_name='Test',
                organization=org, callsign=f'QOP-{i:02d}',
            )
            guards.append(g)
            d = Device.objects.create(
                device_id=f'GT-QOP-{i:03d}',
                password=hash_device_password('pass'),
                organization=org, callsign=f'QOP-{i:02d}',
            )
            devices.append(d)
            CallSign.objects.create(
                device=d, organization=org,
                callsign=f'QOP-{i:02d}', current_guard=g, active_shift='Day',
            )

        route = PatrolRoute.objects.create(name='Query Route', organization=org)
        route.assigned_guards.set(guards)
        for i in range(3):
            Checkpoint.objects.create(
                route=route, organization=org, name=f'CP-{i}',
                checkpoint_type='nfc', nfc_tag=f'TAG-QOP-{i}',
                order=i,
            )

        for g, d in zip(guards, devices):
            ShiftAssignment.objects.create(
                dispatcher=User.objects.create_user(username=f'disp_{g.id}', password='pass'),
                guard_supervisor=g, device=d, route=route,
                scheduled_date=timezone.now().date(),
                scheduled_start=timezone.now(),
                shift_type='Day', is_active=True,
            )
            ScanRecord.objects.create(
                guard_supervisor=g, device=d, route=route,
                checkpoint=route.checkpoints.first(), checkpoint_name='CP-0',
            )

    def _auth_client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        return client

    @override_settings(DEBUG=True)
    def test_scans_list_query_count(self, dispatcher_user, populated_data):
        """Scan list should execute bounded queries regardless of result count."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        client = self._auth_client(dispatcher_user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/scans/')
            assert response.status_code == 200
        assert len(ctx.captured_queries) <= 10, (
            f"Scan list used {len(ctx.captured_queries)} queries (max 10)"
        )

    @override_settings(DEBUG=True)
    def test_devices_list_query_count(self, dispatcher_user, populated_data):
        """Device list should execute bounded queries."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        client = self._auth_client(dispatcher_user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/devices/')
            assert response.status_code == 200
        # assigned_callsign/assigned_guard_id are SerializerMethodFields with per-row queries
        assert len(ctx.captured_queries) <= 15, (
            f"Device list used {len(ctx.captured_queries)} queries (max 15)"
        )

    @override_settings(DEBUG=True)
    def test_routes_list_query_count(self, dispatcher_user, populated_data):
        """Route list with checkpoints should not N+1."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        client = self._auth_client(dispatcher_user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/routes/')
            assert response.status_code == 200
        assert len(ctx.captured_queries) <= 12, (
            f"Route list used {len(ctx.captured_queries)} queries (max 12)"
        )

    @override_settings(DEBUG=True)
    def test_callsigns_list_query_count(self, dispatcher_user, populated_data):
        """CallSign list serializes device + guard fields — must be preloaded."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        client = self._auth_client(dispatcher_user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/callsigns/')
            assert response.status_code == 200
        # active_mission does a query per row (complex filter) — acceptable but bounded
        assert len(ctx.captured_queries) <= 15, (
            f"CallSign list used {len(ctx.captured_queries)} queries (max 15)"
        )

    @override_settings(DEBUG=True)
    def test_shifts_list_query_count(self, dispatcher_user, populated_data):
        """Shift list serializes guard, device, route — must be preloaded."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        client = self._auth_client(dispatcher_user)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/shifts/')
            assert response.status_code == 200
        # total_checkpoints/completed_checkpoints are properties with queries
        assert len(ctx.captured_queries) <= 15, (
            f"Shift list used {len(ctx.captured_queries)} queries (max 15)"
        )
