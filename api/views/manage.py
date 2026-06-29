import secrets

from django.db.models import Q
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.utils import timezone
from django.shortcuts import get_object_or_404

from api.models import (
    Admin,
    CallSign,
    Checkpoint,
    Device,
    DeviceProvisioning,
    Dispatcher,
    GuardSupervisor,
    IncidentReport,
    MapObject,
    OperatorAlert,
    Organization,
    PatrolRoute,
    ScanRecord,
    ShiftAssignment,
)
from api.serializers import (
    UserSerializer,
    GuardSupervisorSerializer,
    DeviceSerializer,
    PatrolRouteSerializer,
    CheckpointSerializer,
    ScanRecordSerializer,
    ShiftAssignmentSerializer,
    CallSignSerializer,
    OrganizationSerializer,
    AdminSerializer,
    DispatcherSerializer,
    MapObjectSerializer,
    IncidentReportSerializer,
    OperatorAlertSerializer,
)
from api.views.auth import generate_operator_id
from api.views.scans import _deactivate_assignments
from api.org_permissions import get_user_organization, get_user_organization_or_none
from api.password import hash_device_password


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        if self.request.user.is_superuser or hasattr(self.request.user, 'admin_profile'):
            return Organization.objects.all()
        if hasattr(self.request.user, 'dispatcher_profile') and self.request.user.dispatcher_profile.organization:
            return Organization.objects.filter(id=self.request.user.dispatcher_profile.organization.id)
        return Organization.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if not (user.is_superuser or hasattr(user, 'admin_profile')):
            raise PermissionDenied("Only admins can create organizations")
        serializer.save()


class CallSignViewSet(viewsets.ModelViewSet):
    serializer_class = CallSignSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return CallSign.objects.select_related('organization', 'device', 'current_guard').prefetch_related('current_guard__shift_assignments')
        org = get_user_organization_or_none(user)
        if org:
            return CallSign.objects.filter(organization=org).select_related('organization', 'device', 'current_guard').prefetch_related('current_guard__shift_assignments')
        return CallSign.objects.none()


class AdminViewSet(viewsets.ModelViewSet):
    serializer_class = AdminSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Admin.objects.all()
        return Admin.objects.filter(user=user)


class DispatcherViewSet(viewsets.ModelViewSet):
    serializer_class = DispatcherSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return Dispatcher.objects.all()
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            return Dispatcher.objects.filter(organization=user.dispatcher_profile.organization)
        return Dispatcher.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            serializer.save()
        elif hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.can_manage_guards:
            org = user.dispatcher_profile.organization
            if org:
                serializer.save(organization=org)
            else:
                raise PermissionDenied("Dispatcher must be assigned to an organization to create profiles.")
        else:
            raise PermissionDenied("Only admins or managers can create dispatchers")


class GuardSupervisorViewSet(viewsets.ModelViewSet):
    serializer_class = GuardSupervisorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'callsign']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return GuardSupervisor.objects.select_related('organization')

        org = get_user_organization_or_none(user)
        if org:
            return GuardSupervisor.objects.filter(organization=org).select_related('organization')
        return GuardSupervisor.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            serializer.save()
        elif hasattr(user, 'dispatcher_profile'):
            org = get_user_organization_or_none(user)
            if org:
                serializer.save(organization=org)
            else:
                raise PermissionDenied("Dispatcher must be assigned to an organization to create profiles.")
        else:
            raise PermissionDenied("Only admins or dispatchers can create guard supervisors.")


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return Device.objects.select_related('organization')

        org = get_user_organization_or_none(user)
        if org:
            return Device.objects.filter(organization=org).select_related('organization')
        return Device.objects.none()

    @action(detail=True, methods=['post'])
    def fetch_nfc(self, request, pk=None):
        device = self.get_object()
        from django.utils import timezone
        device.nfc_fetch_requested = timezone.now()
        device.save(update_fields=['nfc_fetch_requested'])
        return Response({'status': 'requested', 'message': f'NFC fetch requested for {device.device_id or device.device_name}'})

    @action(detail=True, methods=['post'])
    def fetch_gps(self, request, pk=None):
        device = self.get_object()
        from django.utils import timezone
        device.gps_fetch_requested = timezone.now()
        accuracy = request.data.get('accuracy')
        if accuracy is not None:
            device.gps_accuracy_threshold = int(accuracy)
        device.save(update_fields=['gps_fetch_requested', 'gps_accuracy_threshold'])
        return Response({'status': 'requested', 'message': f'GPS fetch ({device.gps_accuracy_threshold}m) requested for {device.device_id or device.device_name}'})

    @action(detail=True, methods=['post'])
    def send_tts(self, request, pk=None):
        from django.utils import timezone
        device = self.get_object()
        msg = request.data.get('message', '').strip()
        if not msg:
            return Response({'detail': 'Message required'}, status=400)

        voice = request.data.get('tts_voice', device.tts_voice or 'en-US')
        rate = request.data.get('tts_rate', device.tts_rate)
        pitch = request.data.get('tts_pitch', device.tts_pitch)

        device.tts_voice = voice
        device.tts_rate = rate
        device.tts_pitch = pitch

        device.tts_pending = msg
        device.tts_pending_voice = voice
        device.tts_pending_rate = rate
        device.tts_pending_pitch = pitch
        device.tts_pending_at = timezone.now()
        device.tts_acked = False
        device.save(update_fields=['tts_voice', 'tts_rate', 'tts_pitch', 'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at', 'tts_acked'])

        active = ShiftAssignment.objects.filter(device=device, is_active=True).first()
        if active and active.guard_supervisor:
            OperatorAlert.objects.create(
                operator=active.guard_supervisor,
                organization=device.organization,
                title=f"TTS: {device.device_id or device.device_name}",
                message=msg,
                priority='urgent',
                play_sound=request.data.get('play_sound', True),
                vibrate=request.data.get('vibrate', True),
                tts_voice=voice,
                tts_rate=rate,
                tts_pitch=pitch,
            )

        return Response({'status': 'queued', 'message': f'TTS queued for {device.device_id or device.device_name}: {msg[:60]}'})

    @action(detail=True, methods=['post'])
    def swap_operator(self, request, pk=None):
        device = self.get_object()
        guard_id = request.data.get('guard_id')
        callsign = request.data.get('callsign')

        if not guard_id and not callsign:
            return Response({'detail': 'Provide guard_id or callsign'}, status=400)

        if guard_id:
            guard = get_object_or_404(GuardSupervisor, id=guard_id)
        else:
            cs = CallSign.objects.filter(callsign=callsign).first()
            if not cs or not cs.current_guard:
                return Response({'detail': f'No guard found for callsign {callsign}'}, status=404)
            guard = cs.current_guard

        org = guard.organization
        now = timezone.now()

        old_assignments = list(ShiftAssignment.objects.filter(device=device, is_active=True))
        old_guard_ids = set(a.guard_supervisor_id for a in old_assignments if a.guard_supervisor_id)
        ShiftAssignment.objects.filter(device=device, is_active=True).update(
            is_active=False, ended_at=now
        )
        if old_guard_ids:
            still_active_guard_ids = set(
                ShiftAssignment.objects.filter(
                    guard_supervisor_id__in=old_guard_ids, is_active=True
                ).exclude(device=device).values_list('guard_supervisor_id', flat=True)
            )
            inactive_guard_ids = old_guard_ids - still_active_guard_ids
            if inactive_guard_ids:
                GuardSupervisor.objects.filter(
                    id__in=inactive_guard_ids, is_on_shift=True
                ).update(is_on_shift=False)

        if guard.callsign:
            device.callsign = guard.callsign
            device.save(update_fields=['callsign'])

        cs, _ = CallSign.objects.get_or_create(device=device, organization=org)
        cs.callsign = guard.callsign or device.callsign
        cs.current_guard = guard
        cs.active_shift = guard.shift
        cs.save()

        ShiftAssignment.objects.create(
            dispatcher=request.user,
            guard_supervisor=guard,
            device=device,
            route=None,
            shift_type=guard.shift,
            is_active=True,
            is_completed=False,
        )

        return Response({
            'status': 'swapped',
            'device_id': device.device_id,
            'callsign': cs.callsign,
            'guard_name': f"{guard.first_name} {guard.last_name}".strip(),
        })

    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        elif hasattr(user, 'dispatcher_profile'):
            org = get_user_organization_or_none(user)

        if not org:
            raise PermissionDenied("Organization context required to create devices.")

        if org:
            generated_callsign = generate_operator_id(org)
            raw_pwd = self.request.data.get('password') or str(secrets.randbelow(90000000) + 10000000)
            hashed_pwd = hash_device_password(raw_pwd)

            serializer.save(organization=org, callsign=generated_callsign, password=hashed_pwd)
            DeviceObj = serializer.instance
            CallSign.objects.create(device=DeviceObj, organization=org, callsign=generated_callsign)
        else:
            raise PermissionDenied("Organization context required to create devices.")


class PatrolRouteViewSet(viewsets.ModelViewSet):
    serializer_class = PatrolRouteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return PatrolRoute.objects.select_related('organization', 'created_by').prefetch_related('checkpoints', 'assigned_guards', 'assigned_devices')

        org = get_user_organization_or_none(user)
        if org:
            return PatrolRoute.objects.filter(
                Q(organization=org) | Q(organization__isnull=True)
            ).select_related('organization', 'created_by').prefetch_related('checkpoints', 'assigned_guards', 'assigned_devices')

        return PatrolRoute.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = None

        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        else:
            org = get_user_organization_or_none(user)

        if not org:
            raise PermissionDenied("Organization context missing. Cannot create blueprints without an organization.")

        serializer.save(organization=org, created_by=user)

    @action(detail=True, methods=['post'])
    def deploy(self, request, pk=None):
        route = self.get_object()
        guards = route.assigned_guards.all()
        devices = route.assigned_devices.all()

        if not guards.exists() and not devices.exists():
            return Response({'detail': 'Deployment aborted: No personnel or devices assigned to this blueprint.'}, status=400)

        now = timezone.now()
        results = []

        for guard in guards:
            _deactivate_assignments(ShiftAssignment.objects.filter(guard_supervisor=guard, is_active=True))

            device = None
            registry = CallSign.objects.filter(current_guard=guard).select_related('device').first()
            if registry:
                device = registry.device

            assignment = ShiftAssignment.objects.create(
                dispatcher=request.user,
                guard_supervisor=guard,
                device=device,
                route=route,
                scheduled_date=route.scheduled_date or now.date(),
                scheduled_start=now,
                shift_type=guard.shift,
                is_active=True
            )
            results.append(ShiftAssignmentSerializer(assignment).data)

        for device in devices:
            _deactivate_assignments(ShiftAssignment.objects.filter(device=device, is_active=True))
            assignment = ShiftAssignment.objects.create(
                dispatcher=request.user,
                guard_supervisor=None,
                device=device,
                route=route,
                scheduled_date=route.scheduled_date or now.date(),
                scheduled_start=now,
                shift_type='Day',
                is_active=True
            )
            results.append(ShiftAssignmentSerializer(assignment).data)

        return Response({'status': 'deployed', 'assignments_count': len(results)})


class CheckpointViewSet(viewsets.ModelViewSet):
    serializer_class = CheckpointSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return Checkpoint.objects.select_related('organization', 'route')
        org = get_user_organization_or_none(user)
        if org:
            return Checkpoint.objects.filter(
                Q(route__organization=org) | Q(organization=org)
            ).distinct().select_related('organization', 'route')
        return Checkpoint.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        else:
            org = get_user_organization_or_none(user)

        if not org:
            raise PermissionDenied("Organization context required to create checkpoints.")

        serializer.save(organization=org)

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        user = request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = request.data[0].get('organization') if request.data else None
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        else:
            org = get_user_organization_or_none(user)

        if not org:
            raise PermissionDenied("Organization context required for bulk checkpoint creation.")

        serializer.save(organization=org)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ShiftAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return ShiftAssignment.objects.select_related(
                'dispatcher', 'guard_supervisor', 'device', 'route'
            )

        org = get_user_organization_or_none(user)
        if org:
            return ShiftAssignment.objects.filter(
                Q(route__organization=org) |
                Q(guard_supervisor__organization=org) |
                Q(dispatcher=user)
            ).distinct().select_related('dispatcher', 'guard_supervisor', 'device', 'route')

        return ShiftAssignment.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        guard_sup = serializer.validated_data.get('guard_supervisor')
        route = serializer.validated_data.get('route')

        s_date = serializer.validated_data.get('scheduled_date')
        if not s_date:
            s_date = route.scheduled_date if route else timezone.now().date()

        if guard_sup:
            _deactivate_assignments(ShiftAssignment.objects.filter(
                guard_supervisor=guard_sup,
                is_active=True
            ))
        serializer.save(dispatcher=user, scheduled_date=s_date)

    def create(self, request, *args, **kwargs):
        guard_ids = request.data.get('guard_ids', [])

        if isinstance(guard_ids, list) and len(guard_ids) > 1:
            responses = []
            for g_id in guard_ids:
                data = request.data.copy()
                data['guard_supervisor'] = g_id
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                responses.append(serializer.data)
            return Response(responses, status=status.HTTP_201_CREATED)

        return super().create(request, *args, **kwargs)


class MapObjectViewSet(viewsets.ModelViewSet):
    serializer_class = MapObjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return MapObject.objects.select_related('organization').prefetch_related('assigned_personnel')
        org = get_user_organization_or_none(user)
        if org:
            return MapObject.objects.filter(organization=org).select_related('organization').prefetch_related('assigned_personnel')
        return MapObject.objects.none()

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        checkpoints_data = request.data.get('checkpoints', [])
        if not checkpoints_data:
            return Response({'detail': 'No checkpoints provided'}, status=400)

        org = None
        user = request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        else:
            org = get_user_organization_or_none(user)

        if not org:
            return Response({'detail': 'No organization found for user'}, status=400)

        created_objs = []
        errors = []
        for cp_data in checkpoints_data:
            try:
                data = cp_data.copy()
                frontend_type = data.pop('type', 'poi')
                if frontend_type == 'geo':
                    data['type'] = 'geofence'
                else:
                    data['type'] = 'poi'
                data.pop('checkpoint_type', None)
                data.pop('nfc_tag', None)
                data.pop('auditor_id', None)
                data.pop('target_id', None)
                data.pop('planned_time', None)
                data.pop('dwell_time', None)
                data.pop('time_tolerance', None)
                data.pop('order', None)

                data['organization'] = org.id
                serializer = MapObjectSerializer(data=data)
                if serializer.is_valid():
                    obj = serializer.save()
                    created_objs.append(serializer.data)
                else:
                    errors.append(serializer.errors)
            except Exception as e:
                errors.append({'error': str(e)})

        return Response({
            'status': 'success',
            'created_count': len(created_objs),
            'errors': errors
        }, status=201)

    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        else:
            org = get_user_organization_or_none(user)

        if not org:
            raise PermissionDenied("Organization context missing.")
        serializer.save(organization=org)


class IncidentReportViewSet(viewsets.ModelViewSet):
    serializer_class = IncidentReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return IncidentReport.objects.select_related('organization', 'guard_supervisor')
        org = get_user_organization_or_none(user)
        if org:
            return IncidentReport.objects.filter(organization=org).select_related('organization', 'guard_supervisor')
        return IncidentReport.objects.none()


class OperatorAlertViewSet(viewsets.ModelViewSet):
    serializer_class = OperatorAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return OperatorAlert.objects.select_related('organization', 'operator')
        org = get_user_organization_or_none(user)
        if org:
            return OperatorAlert.objects.filter(organization=org).select_related('organization', 'operator')
        return OperatorAlert.objects.none()
