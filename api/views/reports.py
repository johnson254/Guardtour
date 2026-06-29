from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from api.models import (
    Device,
    Dispatcher,
    GuardSupervisor,
    Organization,
    PatrolRoute,
    ScanRecord,
    ShiftAssignment,
    IncidentReport,
    OperatorAlert,
    MapObject,
    Checkpoint,
)
from api.serializers import (
    ScanRecordSerializer,
    PatrolRouteSerializer,
    ShiftAssignmentSerializer,
    IncidentReportSerializer,
    OperatorAlertSerializer,
    MapObjectSerializer,
    CheckpointSerializer,
    GuardSupervisorSerializer,
)


@api_view(['GET'])
def admin_stats(request):
    if not (request.user.is_superuser or hasattr(request.user, 'admin_profile')):
        return Response({'error': 'Unauthorized'}, status=403)

    today = timezone.now().date()

    return Response({
        'total_users': GuardSupervisor.objects.count(),
        'total_organizations': Organization.objects.count(),
        'total_devices': Device.objects.count(),
        'online_devices': Device.objects.filter(is_online=True).count(),
        'scans_today': ScanRecord.objects.filter(timestamp__date=today).count(),
        'total_scans': ScanRecord.objects.count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_stats(request):
    devices = Device.objects.none()
    scans = ScanRecord.objects.none()
    routes = PatrolRoute.objects.none()
    guards = GuardSupervisor.objects.none()
    active_shifts = ShiftAssignment.objects.none()
    map_objects = MapObject.objects.none()
    standalone_checkpoints = Checkpoint.objects.none()
    incidents = IncidentReport.objects.none()
    alerts = OperatorAlert.objects.none()
    org = None

    user = request.user

    default_org = Organization.objects.first()

    if user.is_superuser or hasattr(user, 'admin_profile'):
        devices = Device.objects.all()
        scans = ScanRecord.objects.all()
        routes = PatrolRoute.objects.all()
        guards = GuardSupervisor.objects.all()
        active_shifts = ShiftAssignment.objects.filter(is_active=True)
        map_objects = MapObject.objects.all()
        incidents = IncidentReport.objects.all()
        alerts = OperatorAlert.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher_profile = user.dispatcher_profile
        org = dispatcher_profile.organization

        if not org:
            dispatcher_profile.organization = default_org
            dispatcher_profile.save(update_fields=['organization'])
            org = default_org

        if org:
            devices = Device.objects.filter(organization=org)
            scans = ScanRecord.objects.filter(
                Q(guard_supervisor__organization=org) |
                Q(device__organization=org) |
                Q(route__organization=org)
            ).distinct()
            routes = PatrolRoute.objects.filter(Q(organization=org) | Q(organization=None))
            guards = GuardSupervisor.objects.filter(organization=org)
            active_shifts = ShiftAssignment.objects.filter(
                Q(guard_supervisor__organization=org) | Q(dispatcher=user),
                is_active=True
            ).distinct()
            map_objects = MapObject.objects.filter(organization=org)
            standalone_checkpoints = Checkpoint.objects.filter(organization=org, route=None)
            incidents = IncidentReport.objects.filter(organization=org)
            alerts = OperatorAlert.objects.filter(organization=org)

    now = timezone.now()
    today = now.date()
    today_scans = scans.filter(timestamp__date=today)

    hourly_density = [0] * 24
    for scan in today_scans:
        hour = scan.timestamp.hour
        hourly_density[hour] += 1

    shift_perf = {
        'Day': {'onTime': today_scans.filter(guard_supervisor__shift='Day', is_on_time=True).count(),
                'late': today_scans.filter(guard_supervisor__shift='Day', is_on_time=False).count()},
        'Night': {'onTime': today_scans.filter(guard_supervisor__shift='Night', is_on_time=True).count(),
                  'late': today_scans.filter(guard_supervisor__shift='Night', is_on_time=False).count()}
    }

    unified_map_assets = (
        MapObjectSerializer(map_objects, many=True).data +
        CheckpointSerializer(standalone_checkpoints, many=True).data
    )

    return Response({
        'online_devices': devices.filter(is_online=True).count(),
        'total_devices': devices.count(),
        'total_routes': routes.count(),
        'active_guards': guards.filter(is_on_shift=True).count(),
        'total_guards': guards.count(),
        'total_scans_today': today_scans.count(),
        'late_scans_today': today_scans.filter(is_on_time=False).count(),
        'hourly_density': hourly_density,
        'shift_performance': shift_perf,
        'recent_scans': ScanRecordSerializer(today_scans.order_by('-timestamp')[:20], many=True).data,
        'scans_history_today': ScanRecordSerializer(today_scans.order_by('timestamp'), many=True).data,
        'active_deployments': ShiftAssignmentSerializer(active_shifts, many=True).data,
        'blueprints': PatrolRouteSerializer(routes, many=True).data,
        'map_objects': unified_map_assets,
        'unresolved_incidents_count': incidents.filter(is_resolved=False).count(),
        'resolved_incidents_count': incidents.filter(is_resolved=True).count(),
        'security_incidents_count': incidents.filter(category='security', is_resolved=False).count(),
        'maintenance_incidents_count': incidents.filter(category='maintenance', is_resolved=False).count(),
        'unread_alerts_count': alerts.filter(is_read=False).count(),
        'recent_incidents': IncidentReportSerializer(incidents.order_by('-timestamp')[:5], many=True).data,
        'pending_alerts': OperatorAlertSerializer(alerts.filter(is_read=False).order_by('-created_at')[:5], many=True).data,
    })


def _resolve_guard_queryset(user):
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return GuardSupervisor.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher = user.dispatcher_profile
        if not dispatcher.organization:
            default_org = Organization.objects.first()
            if default_org:
                dispatcher.organization = default_org
                dispatcher.save(update_fields=['organization'])
        if dispatcher.organization:
            return GuardSupervisor.objects.filter(organization=dispatcher.organization)
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return GuardSupervisor.objects.filter(organization=user.guardsupervisor.organization)
    return GuardSupervisor.objects.none()


def _profile_create_or_update(request, user):
    guard_id = request.POST.get('guardId') or request.data.get('guard_id')
    data = {
        'first_name': request.POST.get('first_name') or request.data.get('first_name', ''),
        'last_name': request.POST.get('last_name') or request.data.get('last_name', ''),
        'callsign': request.POST.get('callsign') or request.data.get('callsign', ''),
        'shift': request.POST.get('shift') or request.data.get('shift', 'Day'),
    }

    if not data['first_name']:
        return Response({'error': 'First name required'}, status=400)

    if guard_id:
        try:
            profile = GuardSupervisor.objects.get(pk=int(guard_id))
        except (GuardSupervisor.DoesNotExist, ValueError):
            return Response({'error': 'Profile not found'}, status=404)
        serializer = GuardSupervisorSerializer(profile, data=data, partial=True)
    else:
        org = None
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            org = user.dispatcher_profile.organization
        elif hasattr(user, 'admin_profile') and user.admin_profile.organization:
            org = user.admin_profile.organization
        elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
            org = user.guardsupervisor.organization
        data['organization'] = org
        data['role'] = 'guard'
        serializer = GuardSupervisorSerializer(data=data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200 if guard_id else 201)
    return Response(serializer.errors, status=400)


@api_view(['GET', 'POST'])
def profile_list(request):
    user = request.user

    if request.method == 'POST':
        return _profile_create_or_update(request, user)

    role = request.GET.get('role', None)
    queryset = _resolve_guard_queryset(user)

    if role:
        queryset = queryset.filter(role=role)

    return Response(GuardSupervisorSerializer(queryset, many=True).data)


@api_view(['GET', 'PUT', 'DELETE'])
def profile_detail(request, pk):
    try:
        profile = GuardSupervisor.objects.get(pk=pk)
    except GuardSupervisor.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=404)

    if not (request.user.is_superuser or hasattr(request.user, 'admin_profile')):
        try:
            dispatcher = request.user.dispatcher_profile
            if dispatcher.organization and profile.organization and dispatcher.organization != profile.organization:
                return Response({'error': 'Permission denied'}, status=403)
        except Dispatcher.DoesNotExist:
            return Response({'error': 'Permission denied'}, status=403)

    if request.method == 'GET':
        return Response(GuardSupervisorSerializer(profile).data)

    elif request.method == 'PUT':
        serializer = GuardSupervisorSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    elif request.method == 'DELETE':
        profile.delete()
        return Response({'status': 'deleted'})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def seed_attendance(request):
    import random
    days = int(request.data.get('days', 30))
    org = Organization.objects.first()
    if not org:
        return Response({'error': 'No organization exists'}, status=400)

    guards = list(GuardSupervisor.objects.filter(organization=org))
    routes = list(PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True)))

    if not guards:
        return Response({'error': 'No guards found. Create guards first via the Staff page.'}, status=400)
    if not routes:
        return Response({'error': 'No routes found. Create routes first via the Blueprints page.'}, status=400)

    cp_names = ['Main Gate', 'Building A', 'Building B', 'Storage', 'Parking Lot',
                'Perimeter NE', 'Perimeter SW', 'Control Room', 'Loading Dock', 'Rooftop']
    cp_created = 0
    for route in routes:
        existing = list(route.checkpoints.all())
        if len(existing) >= 3:
            continue
        needed = 5 - len(existing)
        offset = len(existing)
        for i in range(needed):
            tag = ''.join(random.choices('0123456789ABCDEF', k=14))
            Checkpoint.objects.create(
                route=route, organization=org,
                name=f"{route.name[:16]} - {random.choice(cp_names)}",
                checkpoint_type='nfc', nfc_tag=tag, order=offset + i,
            )
            cp_created += 1

    all_cps = list(Checkpoint.objects.filter(route__in=routes))
    if not all_cps:
        return Response({'error': 'Could not create checkpoints'}, status=400)

    now = timezone.now()
    batch = []
    scans_count = 0

    for day_offset in range(days):
        day = (now - timedelta(days=day_offset)).date()
        for guard in guards:
            if guard.shift == 'Day':
                start_h, end_h = 6, 18
            elif guard.shift == 'Night':
                start_h, end_h = 18, 6
            else:
                start_h, end_h = 8, 20

            n = random.randint(8, 15)
            for _ in range(n):
                cp = random.choice(all_cps)
                route = cp.route or random.choice(routes)

                if start_h <= end_h:
                    h = random.randint(start_h, end_h - 1)
                else:
                    h = random.choice(list(range(start_h, 24)) + list(range(0, end_h)))

                m, s = random.randint(0, 59), random.randint(0, 59)
                ts = timezone.make_aware(datetime(day.year, day.month, day.day, h, m, s))

                batch.append(ScanRecord(
                    guard_supervisor=guard, route=route, checkpoint=cp,
                    checkpoint_name=cp.name, nfc_value=cp.nfc_tag,
                    is_on_time=random.random() < 0.8,
                    timestamp=ts,
                ))
                scans_count += 1
                if len(batch) >= 500:
                    ScanRecord.objects.bulk_create(batch)
                    batch = []

    if batch:
        ScanRecord.objects.bulk_create(batch)

    templates = [
        ('security', 'Unauthorized Access Attempt', 'Suspicious individual attempted to enter a restricted area.'),
        ('maintenance', 'Faulty Lighting', 'Lighting fixture in the parking lot needs replacement.'),
        ('safety', 'Slippery Surface', 'Spilled liquid near the main entrance.'),
        ('security', 'Perimeter Breach', 'Fence damage detected during patrol.'),
        ('maintenance', 'Broken Lock', 'Storage room lock needs replacement.'),
        ('safety', 'Trip Hazard', 'Uneven pavement near Building B loading dock.'),
    ]
    inc_count = 0
    for cat, title, desc in templates:
        guard = random.choice(guards)
        IncidentReport.objects.create(
            organization=org, guard_supervisor=guard,
            category=cat, title=title, description=desc,
            is_resolved=random.random() < 0.4,
        )
        inc_count += 1

    return Response({
        'checkpoints_created': cp_created,
        'scans_created': scans_count,
        'incidents_created': inc_count,
        'message': f'Generated {scans_count} scan records, {cp_created} checkpoints, {inc_count} incidents over {days} days',
    })
