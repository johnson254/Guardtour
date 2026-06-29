from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from api.models import (
    CallSign,
    Device,
    DeviceProvisioning,
    DeviceSession,
    GuardSupervisor,
    OperatorAlert,
    Organization,
    PatrolRoute,
    ScanRecord,
    ShiftAssignment,
)
from api.services.scan import get_mission_status, route_gap_analysis, transfer_shift as transfer_shift_logic


SHIFT_TYPE_CHOICES = ['Day', 'Night', 'Flex']


@api_view(['POST'])
def end_shift(request, pk):
    assignment = get_object_or_404(ShiftAssignment, pk=pk)
    assignment.is_active = False
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=['is_active', 'ended_at'])

    if assignment.guard_supervisor:
        assignment.guard_supervisor.is_on_shift = False
        assignment.guard_supervisor.save(update_fields=['is_on_shift'])

    if assignment.device:
        has_other_active = ShiftAssignment.objects.filter(
            device=assignment.device, is_active=True, is_completed=False
        ).exclude(pk=assignment.pk).exists()
        if not has_other_active:
            assignment.device.is_online = False
            assignment.device.save(update_fields=['is_online'])

    return Response({'status': 'ended', 'assignment_id': assignment.id})


@api_view(['GET'])
def blueprint_shift_availability(request):
    route_id = request.query_params.get('route_id')
    if not route_id:
        return Response({'detail': 'route_id required'}, status=400)

    route = get_object_or_404(PatrolRoute, id=route_id)

    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            if route.organization and route.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)

    eligible_guards_qs = route.assigned_guards.all()
    eligible_ids = list(eligible_guards_qs.values_list('id', flat=True))

    active_assignments = ShiftAssignment.objects.filter(
        route=route,
        is_active=True,
        guard_supervisor_id__in=eligible_ids,
    )

    flex_qs = eligible_guards_qs.filter(shift='Flex')
    all_assigned_flex_ids = set(active_assignments.filter(
        guard_supervisor_id__in=list(flex_qs.values_list('id', flat=True))
    ).values_list('guard_supervisor_id', flat=True))
    free_flex_count = flex_qs.exclude(id__in=all_assigned_flex_ids).count()

    result = {}
    for st in SHIFT_TYPE_CHOICES:
        st_active = active_assignments.filter(shift_type=st).values('guard_supervisor_id').distinct().count()
        st_eligible = eligible_guards_qs.filter(shift=st).count()

        if st in ['Day', 'Night']:
            st_eligible += free_flex_count

        result[st] = {
            'eligible_count': st_eligible,
            'on_shift_count': st_active,
            'available_count': max(0, st_eligible - st_active),
        }

    return Response({
        'route_id': route.id,
        'route_name': route.name,
        'shift_availability': result,
    })


@api_view(['POST'])
def assign_guard_to_blueprint_shift(request):
    guard_id = request.data.get('guard_id')
    route_id = request.data.get('route_id')
    shift_type = request.data.get('shift_type')
    device_id = request.data.get('device_id')
    scheduled_start = request.data.get('scheduled_start')
    scheduled_end = request.data.get('scheduled_end')
    scheduled_date = request.data.get('scheduled_date')

    if not guard_id or not route_id or not shift_type:
        return Response({'detail': 'guard_id, route_id, shift_type required'}, status=400)
    if shift_type not in SHIFT_TYPE_CHOICES:
        return Response({'detail': 'Invalid shift_type'}, status=400)

    route = get_object_or_404(PatrolRoute, id=route_id)
    guard = get_object_or_404(GuardSupervisor, id=guard_id)

    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            if route.organization and route.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)
            if not guard.organization or guard.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)

    if route.assigned_guards.exists() and not route.assigned_guards.filter(id=guard.id).exists():
        return Response({'detail': 'Guard not eligible for this blueprint'}, status=400)

    with transaction.atomic():
        device = None
        if device_id:
            device = get_object_or_404(Device, id=device_id)
            cs, _ = CallSign.objects.get_or_create(device=device, organization=guard.organization)
            cs.callsign = cs.callsign or device.callsign
            cs.current_guard = guard
            cs.active_shift = shift_type if shift_type in ['Day', 'Night', 'Flex'] else guard.shift
            cs.save()

            guard.callsign = cs.callsign
            guard.save(update_fields=['callsign'])

            DeviceProvisioning.objects.update_or_create(
                device=device,
                guard=guard,
                defaults={
                    'callsign_snapshot': cs.callsign,
                    'organization': guard.organization,
                }
            )

            device.is_online = True
            device.last_seen = timezone.now()
            device.save(update_fields=['is_online', 'last_seen'])

        else:
            cs = CallSign.objects.filter(current_guard=guard).select_related('device').first()
            if cs and cs.device_id:
                device = cs.device

        ShiftAssignment.objects.create(
            dispatcher=user,
            guard_supervisor=guard,
            device=device,
            route=route,
            scheduled_date=scheduled_date or route.scheduled_date or timezone.now().date(),
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            shift_type=shift_type,
            is_active=True,
            is_completed=False,
        )

    return Response({'status': 'assigned', 'guard_id': guard.id, 'route_id': route.id, 'shift_type': shift_type}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_audit_shift(request):
    """Create peer-to-peer audit shifts for multiple guards on an audit route.

    Creates ShiftAssignments for all selected guards and sets up peer
    session keys so their devices know to scan each other.

    Request body:
    {
        "route_id": 1,
        "guard_ids": [1, 2, 3],
        "scheduled_date": "2027-07-15",
        "shift_type": "Day",
        "start_time": "08:00",
        "end_time": "16:00"
    }
    """
    import secrets
    from api.models import PatrolRoute, GuardSupervisor, ShiftAssignment, CallSign

    route_id = request.data.get('route_id')
    guard_ids = request.data.get('guard_ids', [])
    scheduled_date = request.data.get('scheduled_date')
    shift_type = request.data.get('shift_type', 'Day')
    start_time = request.data.get('start_time')
    end_time = request.data.get('end_time')

    if not route_id or not guard_ids:
        return Response({'detail': 'route_id and guard_ids required'}, status=400)
    if shift_type not in SHIFT_TYPE_CHOICES:
        return Response({'detail': 'Invalid shift_type. Must be Day, Night, or Flex.'}, status=400)
    if not isinstance(guard_ids, list) or len(guard_ids) < 2:
        return Response({'detail': 'At least 2 guards required for peer audit.'}, status=400)

    try:
        route = PatrolRoute.objects.get(id=route_id)
    except PatrolRoute.DoesNotExist:
        return Response({'detail': 'Route not found'}, status=404)

    if not route.is_audit:
        return Response({'detail': 'Route is not an audit route. Set is_audit=True first.'}, status=400)

    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            if route.organization and route.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)

    with transaction.atomic():
        guards = GuardSupervisor.objects.filter(id__in=guard_ids)
        if guards.count() != len(guard_ids):
            return Response({'detail': 'One or more guards not found'}, status=404)

        # Verify all guards belong to route's organization
        for guard in guards:
            if route.organization and guard.organization != route.organization:
                return Response({
                    'detail': f'Guard {guard.first_name} {guard.last_name} belongs to different organization'
                }, status=400)

        # Build peer scan expectations (all pairs)
        guard_list = list(guards)
        peer_pairs = []
        for i, g1 in enumerate(guard_list):
            for g2 in guard_list[i+1:]:
                peer_pairs.append({
                    'scanner': g1,
                    'target': g2,
                })
                peer_pairs.append({
                    'scanner': g2,
                    'target': g1,
                })

        # Create shifts for all guards
        created_shifts = []
        for guard in guards:
            # Get or create device for this guard
            cs = CallSign.objects.filter(current_guard=guard).select_related('device').first()
            device = cs.device if cs else None

            # Generate peer session key for this guard's device
            nonce = secrets.token_hex(8)
            if device:
                device.peer_session_key = nonce
                device.save(update_fields=['peer_session_key'])

            # Parse scheduled times
            scheduled_start_dt = None
            scheduled_end_dt = None
            if scheduled_date and start_time:
                start_str = f"{scheduled_date} {start_time}:00"
                scheduled_start_dt = timezone.make_aware(
                    timezone.datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S'),
                    timezone=timezone.get_current_timezone()
                )
            if scheduled_date and end_time:
                end_str = f"{scheduled_date} {end_time}:00"
                scheduled_end_dt = timezone.make_aware(
                    timezone.datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S'),
                    timezone=timezone.get_current_timezone()
                )

            shift = ShiftAssignment.objects.create(
                dispatcher=user,
                guard_supervisor=guard,
                device=device,
                route=route,
                scheduled_date=scheduled_date,
                scheduled_start=scheduled_start_dt,
                scheduled_end=scheduled_end_dt,
                shift_type=shift_type,
                is_active=True,
                is_completed=False,
            )
            created_shifts.append(shift)

    return Response({
        'status': 'created',
        'route_id': route.id,
        'route_name': route.name,
        'is_audit': True,
        'shifts_created': len(created_shifts),
        'shifts': [{
            'id': s.id,
            'guard_id': s.guard_supervisor.id,
            'guard_name': f"{s.guard_supervisor.first_name} {s.guard_supervisor.last_name}".strip(),
            'device_id': s.device.device_id if s.device else None,
            'peer_session_key': s.device.peer_session_key if s.device else None,
        } for s in created_shifts],
        'peer_pairs': [{
            'scanner': {'id': p['scanner'].id, 'name': f"{p['scanner'].first_name} {p['scanner'].last_name}".strip()},
            'target': {'id': p['target'].id, 'name': f"{p['target'].first_name} {p['target'].last_name}".strip()},
        } for p in peer_pairs],
        'total_pairs': len(peer_pairs),
    }, status=201)


@api_view(['POST'])
def resend_tts(request):
    assignment_id = request.data.get('assignment_id')
    if not assignment_id:
        return Response({'detail': 'assignment_id required'}, status=400)
    try:
        a = ShiftAssignment.objects.get(id=assignment_id)
        route = a.route
        if not route:
            return Response({'detail': 'No route on assignment'}, status=404)
        msg = request.data.get('message') or route.readout_text or f"Next checkpoint: {route.name}"
        org = route.organization or (a.guard_supervisor.organization if a.guard_supervisor else None) or (a.device.organization if a.device else None)
        if not org:
            return Response({'detail': 'Cannot send TTS: no organization associated with this route or assignment'}, status=400)
        if request.user.is_authenticated:
            OperatorAlert.objects.create(
                operator=a.guard_supervisor or None,
                organization=org,
                title=f"TTS: {route.name}",
                message=msg,
                priority='urgent',
                play_sound=request.data.get('play_sound', True),
                vibrate=request.data.get('vibrate', True),
                tts_voice=request.data.get('tts_voice', route.tts_voice or ''),
                tts_rate=request.data.get('tts_rate', route.tts_rate),
                tts_pitch=request.data.get('tts_pitch', route.tts_pitch),
            )
        return Response({'detail': 'TTS sent', 'message': msg})
    except ShiftAssignment.DoesNotExist:
        return Response({'detail': 'Assignment not found'}, status=404)


@api_view(['GET'])
@permission_classes([AllowAny])
def mission_status(request, assignment_id):
    try:
        assignment = ShiftAssignment.objects.get(id=assignment_id, is_active=True, is_completed=False)
    except ShiftAssignment.DoesNotExist:
        return Response({'detail': 'Assignment not found or completed'}, status=404)

    status = get_mission_status(assignment)
    if not status:
        return Response({'detail': 'No route or checkpoints on this assignment'}, status=404)

    return Response({
        'assignment_id': assignment.id,
        'route_id': assignment.route.id if assignment.route else None,
        'route_name': assignment.route.name if assignment.route else None,
        'guard_name': f"{assignment.guard_supervisor.first_name} {assignment.guard_supervisor.last_name}".strip() if assignment.guard_supervisor else None,
        'device_name': (assignment.device.device_id or assignment.device.device_name) if assignment.device else None,
        'device_id': assignment.device.device_id if assignment.device else None,
        'battery_pct': assignment.device.battery_pct if assignment.device else None,
        'is_online': assignment.device.is_online if assignment.device else None,
        'staging': status,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def my_mission(request):
    """Device self-service: get current mission + checkpoints by device auth.
    
    The app calls this after login to get:
    - Current active assignment
    - Route details + checkpoint list (for offline staging)
    - Next checkpoint + ETA
    - Recent scans
    """
    device_id = request.data.get('device_id')
    password = request.data.get('password')

    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)

    from api.models import Device, ShiftAssignment
    from api.services.scan import get_mission_status
    from api.password import verify_device_password, hash_device_password

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Auth failed'}, status=401)

    is_valid, needs_rehash = verify_device_password(password, device.password)
    if not is_valid:
        return Response({'detail': 'Auth failed'}, status=401)

    if needs_rehash:
        Device.objects.filter(id=device.id).update(password=hash_device_password(password))

    # Find active assignment for this device
    assignment = ShiftAssignment.objects.filter(
        device=device, is_active=True, is_completed=False
    ).select_related('route', 'guard_supervisor').order_by('-assigned_at').first()

    if not assignment:
        return Response({
            'has_mission': False,
            'device_id': device.device_id,
            'message': 'No active mission assigned',
        })

    route = assignment.route

    # Handle archived/deleted route: shift still active but blueprint gone
    if not route:
        return Response({
            'has_mission': True,
            'assignment_id': assignment.id,
            'device_id': device.device_id,
            'route': None,
            'guard': {
                'id': assignment.guard_supervisor.id if assignment.guard_supervisor else None,
                'name': f"{assignment.guard_supervisor.first_name} {assignment.guard_supervisor.last_name}".strip() if assignment.guard_supervisor else None,
                'callsign': assignment.guard_supervisor.callsign if assignment.guard_supervisor else None,
                'shift': assignment.guard_supervisor.shift if assignment.guard_supervisor else None,
            } if assignment.guard_supervisor else None,
            'checkpoints': [],
            'total_checkpoints': 0,
            'mission_status': {
                'completed': False,
                'error': 'blueprint_archived',
                'hit_count': 0,
                'total': 0,
            },
            'message': 'Blueprint has been archived. Mission data preserved for audit.',
        })

    checkpoints = []
    if route:
        from django.utils import timezone as dj_timezone
        today = dj_timezone.now().date()
        # Only show scheduled checkpoints for today or earlier (or unscheduled)
        cps = route.checkpoints.filter(
            Q(scheduled_date__isnull=True) | Q(scheduled_date__lte=today)
        ).order_by('scheduled_date', 'order')
        checkpoints = [{
            'id': cp.id,
            'name': cp.name,
            'nfc_tag': cp.nfc_tag or '',
            'order': cp.order,
            'planned_time': cp.planned_time.strftime('%H:%M:%S') if cp.planned_time else None,
            'scheduled_date': cp.scheduled_date.isoformat() if cp.scheduled_date else None,
            'time_tolerance': cp.time_tolerance or 15,
            'dwell_time': cp.dwell_time or 0,
            'lat': cp.lat,
            'lng': cp.lng,
            'radius': cp.radius or 50,
            'checkpoint_type': cp.checkpoint_type or 'nfc',
        } for cp in cps]

    mission_status = get_mission_status(assignment) if route else None

    return Response({
        'has_mission': True,
        'assignment_id': assignment.id,
        'device_id': device.device_id,
        'route': {
            'id': route.id if route else None,
            'name': route.name if route else None,
            'status': route.status if route else None,
            'enforce_order': route.enforce_order if route else False,
        },
        'guard': {
            'id': assignment.guard_supervisor.id if assignment.guard_supervisor else None,
            'name': f"{assignment.guard_supervisor.first_name} {assignment.guard_supervisor.last_name}".strip() if assignment.guard_supervisor else None,
            'callsign': assignment.guard_supervisor.callsign if assignment.guard_supervisor else None,
            'shift': assignment.guard_supervisor.shift if assignment.guard_supervisor else None,
        } if assignment.guard_supervisor else None,
        'checkpoints': checkpoints,
        'total_checkpoints': len(checkpoints),
        'mission_status': mission_status,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_shift(request):
    assignment_id = request.data.get('assignment_id')
    new_guard_id = request.data.get('new_guard_id')

    if not assignment_id or not new_guard_id:
        return Response({'detail': 'assignment_id and new_guard_id required'}, status=400)

    assignment = get_object_or_404(ShiftAssignment, id=assignment_id, is_active=True)
    new_guard = get_object_or_404(GuardSupervisor, id=new_guard_id)

    new_assignment = transfer_shift_logic(
        assignment=assignment,
        new_guard=new_guard,
        requested_by=request.user,
    )

    return Response({
        'status': 'transferred',
        'old_assignment_id': assignment.id,
        'new_assignment_id': new_assignment.id,
        'new_guard_id': new_guard.id,
        'new_guard_name': f"{new_guard.first_name} {new_guard.last_name}".strip(),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def route_gap_analysis_view(request, assignment_id):
    try:
        assignment = ShiftAssignment.objects.get(id=assignment_id, is_active=True)
    except ShiftAssignment.DoesNotExist:
        return Response({'detail': 'Assignment not found'}, status=404)

    missed = route_gap_analysis(assignment.route, assignment)

    return Response({
        'assignment_id': assignment.id,
        'route_id': assignment.route.id if assignment.route else None,
        'route_name': assignment.route.name if assignment.route else None,
        'missed_count': len(missed),
        'missed_checkpoints': missed,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def map_residency_events(request):
    from api.models import DeviceSession
    from api.services.gps import _haversine

    user = request.user
    qs = ShiftAssignment.objects.filter(is_active=True, is_completed=False)
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        dispatcher = getattr(user, 'dispatcher_profile', None)
        if dispatcher and dispatcher.organization:
            org = dispatcher.organization
            qs = qs.filter(Q(route__organization=org) | Q(guard_supervisor__organization=org) | Q(dispatcher=user)).distinct()
        else:
            return Response([])

    events = []
    now = timezone.now()
    for assignment in qs.select_related('route', 'device', 'guard_supervisor'):
        session = DeviceSession.objects.filter(device=assignment.device, is_active=True).order_by('-entered_at').first()
        if not assignment.route:
            continue
        cps = list(assignment.route.checkpoints.all().order_by('order'))
        if not cps:
            continue
        if not assignment.device.last_latitude or not assignment.device.last_longitude:
            continue
        device_lat = assignment.device.last_latitude
        device_lng = assignment.device.last_longitude
        for cp in cps:
            if not cp.lat or not cp.lng:
                continue
            dist = _haversine(device_lat, device_lng, cp.lat, cp.lng)
            radius = cp.radius if cp.radius and cp.radius > 0 else 5
            if dist <= radius:
                events.append({
                    'device_id': assignment.device.device_id,
                    'device_label': assignment.device.device_name or assignment.device.device_id,
                    'checkpoint_id': cp.id,
                    'checkpoint_name': cp.name,
                    'entered_at': session.last_heartbeat_at.isoformat() if session and session.last_heartbeat_at else now.isoformat(),
                    'confidence': max(0.0, 1.0 - (dist / radius)) if radius > 0 else 1.0,
                    'state': session.state if session else 'on_route',
                    'assignment_id': assignment.id,
                })
    return Response(events)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deployment_checkpoint_live(request):
    from rest_framework.permissions import IsAuthenticated
    from django.utils import timezone as dj_timezone

    if not isinstance(getattr(request, 'user', None), object):
        return Response({'detail': 'Unauthorized'}, status=401)

    now = dj_timezone.now()

    user = request.user
    qs = ShiftAssignment.objects.none()
    if user.is_authenticated and (user.is_superuser or hasattr(user, 'admin_profile')):
        qs = ShiftAssignment.objects.filter(is_active=True, is_completed=False)
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher = user.dispatcher_profile
        if dispatcher.organization:
            org = dispatcher.organization
            qs = ShiftAssignment.objects.filter(
                is_active=True,
                is_completed=False,
            ).filter(Q(route__organization=org) | Q(guard_supervisor__organization=org) | Q(dispatcher=user)).distinct()

    assignments = list(qs.select_related('guard_supervisor', 'route', 'device'))

    results = []

    def checkpoint_type(cp):
        return (cp.checkpoint_type or 'POI').upper()

    for a in assignments:
        route = a.route
        if not route:
            continue

        cps = list(route.checkpoints.all().order_by('order'))
        total = len(cps)
        hit_cp_ids = set()
        if total == 0:
            next_payload = None
        else:
            if a.guard_supervisor:
                hit_cp_ids = set(
                    ScanRecord.objects.filter(
                        guard_supervisor=a.guard_supervisor,
                        route=route,
                        timestamp__gte=a.assigned_at,
                        checkpoint__isnull=False,
                    ).values_list('checkpoint_id', flat=True).distinct()
                )
            else:
                hit_cp_ids = set(
                    ScanRecord.objects.filter(
                        route=route,
                        timestamp__gte=a.assigned_at,
                        checkpoint__isnull=False,
                    ).values_list('checkpoint_id', flat=True).distinct()
                )

        hit_count = len(hit_cp_ids)

        next_cp = None
        for cp in cps:
            if cp.id not in hit_cp_ids:
                next_cp = cp
                break

        has_missed = False

        if not next_cp:
            next_payload = None
        else:
            last_hit = None
            if a.guard_supervisor:
                last_hit = (
                    ScanRecord.objects.filter(
                        guard_supervisor=a.guard_supervisor,
                        route=route,
                        checkpoint=next_cp,
                        timestamp__gte=a.assigned_at,
                    )
                    .order_by('-timestamp')
                    .values_list('timestamp', flat=True)
                    .first()
                )
            else:
                last_hit = (
                    ScanRecord.objects.filter(
                        route=route,
                        checkpoint=next_cp,
                        timestamp__gte=a.assigned_at,
                    )
                    .order_by('-timestamp')
                    .values_list('timestamp', flat=True)
                    .first()
                )

            dwell_minutes = int(next_cp.dwell_time or 0)
            dwell_remaining_seconds = None
            is_present = False
            if last_hit and dwell_minutes > 0:
                dwell_total = dwell_minutes * 60
                end_present = last_hit + timedelta(seconds=dwell_total)
                dwell_remaining_seconds = max(0, int((end_present - now).total_seconds()))
                is_present = now <= end_present

            missed_checkpoints = []
            for cp in cps:
                if cp.id in hit_cp_ids:
                    continue
                missed_checkpoints.append({
                    'id': cp.id,
                    'name': cp.name,
                    'order': cp.order,
                    'checkpoint_type': cp.checkpoint_type,
                })

            shift_end_dt = None
            if a.guard_supervisor:
                shift_date = a.scheduled_date or now.date()
                if a.shift_type == 'Night':
                    shift_end_dt = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(shift_date, dj_timezone.datetime.min.time()) + timedelta(hours=30),
                        timezone=now.tzinfo,
                    )
                else:
                    shift_end_dt = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(shift_date, dj_timezone.datetime.min.time()) + timedelta(hours=18),
                        timezone=now.tzinfo,
                    )
            else:
                bp_time = route.scheduled_start_time or dj_timezone.datetime.min.time()
                bp_base = a.scheduled_date or a.assigned_at.date() if a.assigned_at else now.date()
                shift_end_dt = dj_timezone.make_aware(
                    dj_timezone.datetime.combine(bp_base, bp_time) + timedelta(hours=24),
                    timezone=now.tzinfo,
                )

            missed_pending_ids = set()
            for cp in cps:
                if cp.id in hit_cp_ids:
                    continue
                if cp.planned_time and a.scheduled_date:
                    cp_deadline = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(a.scheduled_date, cp.planned_time),
                        timezone=now.tzinfo,
                    ) + timedelta(minutes=int(cp.time_tolerance or 15) + int(cp.dwell_time or 0))
                    if now > cp_deadline:
                        missed_pending_ids.add(cp.id)
                else:
                    cp_deadline = shift_end_dt
                    if cp_deadline and now > cp_deadline:
                        missed_pending_ids.add(cp.id)
            has_missed = len(missed_pending_ids) > 0

            time_remaining_seconds = None
            is_window_missed = False
            planned_time = next_cp.planned_time
            if planned_time and a.scheduled_date:
                planned_dt = dj_timezone.make_aware(
                    dj_timezone.datetime.combine(a.scheduled_date, planned_time),
                    timezone=now.tzinfo,
                )
                time_remaining_seconds = int((planned_dt - now).total_seconds())
                tol_minutes = int(next_cp.time_tolerance or 15)
                dwell_min = int(next_cp.dwell_time or 0)
                miss_deadline = planned_dt + timedelta(minutes=tol_minutes + dwell_min)
                is_window_missed = now > miss_deadline
            else:
                if has_missed:
                    is_window_missed = True

            next_payload = {
                'id': next_cp.id,
                'name': next_cp.name,
                'checkpoint_type': checkpoint_type(next_cp),
                'planned_time': next_cp.planned_time.strftime('%H:%M:%S') if next_cp.planned_time else None,
                'time_remaining_seconds': time_remaining_seconds,
                'dwell_time_minutes': dwell_minutes,
                'dwell_remaining_seconds': dwell_remaining_seconds,
                'is_present': is_present,
                'is_window_missed': is_window_missed,
            }

        results.append({
            'assignment_id': a.id,
            'route_id': route.id,
            'route_name': route.name,
            'logic_type': route.logic_type,
            'shift_type': a.shift_type,
            'status': a.status,
            'device_name': (a.device.device_id or a.device.device_name) if a.device else None,
            'device_id': a.device.device_id if a.device else None,
            'battery_pct': a.device.battery_pct if a.device else None,
            'is_online': a.device.is_online if a.device else None,
            'guard_supervisor_name': (a.guard_supervisor.first_name + ' ' + a.guard_supervisor.last_name).strip() if a.guard_supervisor else None,
            'has_missed_checkpoints': has_missed,
            'missed_checkpoints': missed_checkpoints if next_cp else [],
            'is_completed': hit_count + (len(missed_pending_ids) if next_cp else 0) >= total if total > 0 else True,
            'hit_count': hit_count,
            'total': total,
            'alert_config': {
                'send_start_alert': route.send_start_alert,
                'start_alert_lead_time': route.start_alert_lead_time,
                'send_announcement': route.send_announcement,
                'readout_text': route.readout_text or '',
                'scheduled_start_time': route.scheduled_start_time.strftime('%H:%M') if route.scheduled_start_time else None,
            } if route.send_start_alert or route.send_announcement else None,
            'next_checkpoint': next_payload,
        })

    return Response({'items': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def peer_audit_report(request, route_id):
    """Peer-to-peer audit report for a route.

    Returns which guard pairs have scanned each other vs expected pairs.
    Only works for routes with is_audit=True.
    """
    from api.models import PatrolRoute, ShiftAssignment, GuardSupervisor, ScanRecord

    try:
        route = PatrolRoute.objects.get(id=route_id)
    except PatrolRoute.DoesNotExist:
        return Response({'detail': 'Route not found'}, status=404)

    if not route.is_audit:
        return Response({'detail': 'Route is not an audit route'}, status=400)

    # Get all guards assigned to this route who are on active shifts
    active_shifts = ShiftAssignment.objects.filter(
        route=route, is_active=True, is_completed=False
    ).select_related('guard_supervisor', 'device')

    guards = []
    for shift in active_shifts:
        if shift.guard_supervisor and shift.device:
            guards.append({
                'guard_id': shift.guard_supervisor.id,
                'guard_name': f"{shift.guard_supervisor.first_name} {shift.guard_supervisor.last_name}".strip(),
                'device_id': shift.device.device_id,
                'callsign': shift.guard_supervisor.callsign,
            })

    # Build expected pairs (every guard should scan every other guard)
    expected_pairs = []
    for i, g1 in enumerate(guards):
        for g2 in guards[i+1:]:
            expected_pairs.append({
                'scanner': g1,
                'target': g2,
            })
            expected_pairs.append({
                'scanner': g2,
                'target': g1,
            })

    # Get actual peer scans for this route
    peer_scans = ScanRecord.objects.filter(
        route=route, scan_type='peer', checkpoint__isnull=False
    ).select_related('guard_supervisor', 'device')

    scanned_pairs = set()
    for scan in peer_scans:
        if scan.guard_supervisor and scan.device:
            scanned_pairs.add((scan.guard_supervisor.id, scan.nfc_value))

    # Build report
    pairs_report = []
    for pair in expected_pairs:
        scanner_device_id = pair['scanner']['device_id']
        target_device_id = pair['target']['device_id']
        completed = (pair['scanner']['guard_id'], target_device_id) in scanned_pairs
        pairs_report.append({
            'scanner': pair['scanner'],
            'target': pair['target'],
            'scanned': completed,
        })

    return Response({
        'route_id': route_id,
        'route_name': route.name,
        'is_audit': route.is_audit,
        'total_guards': len(guards),
        'total_pairs': len(pairs_report),
        'scanned_pairs': sum(1 for p in pairs_report if p['scanned']),
        'completion_pct': round(
            (sum(1 for p in pairs_report if p['scanned']) / len(pairs_report) * 100)
            if pairs_report else 0, 1
        ),
        'guards': guards,
        'pairs': pairs_report,
    })
