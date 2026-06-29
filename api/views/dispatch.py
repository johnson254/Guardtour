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

    device = Device.objects.filter(device_id=device_id).first()
    if not device or device.password != password:
        return Response({'detail': 'Auth failed'}, status=401)

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
    checkpoints = []
    if route:
        cps = route.checkpoints.all().order_by('order')
        checkpoints = [{
            'id': cp.id,
            'name': cp.name,
            'nfc_tag': cp.nfc_tag or '',
            'order': cp.order,
            'planned_time': cp.planned_time.strftime('%H:%M:%S') if cp.planned_time else None,
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
