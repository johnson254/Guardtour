from rest_framework import viewsets, filters, status, serializers
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from api.models import Organization, Admin, Dispatcher, GuardSupervisor, Device, PatrolRoute, Checkpoint, ScanRecord, ShiftAssignment, MapObject, IncidentReport, OperatorAlert, DeviceProvisioning, CallSign, DeviceTrail
from django.db.models import F as models_F

from api.serializers import (UserSerializer, GuardSupervisorSerializer, DeviceSerializer, PatrolRouteSerializer, 
                         CheckpointSerializer, ScanRecordSerializer, ShiftAssignmentSerializer, CallSignSerializer, OrganizationSerializer, 
                         AdminSerializer, DispatcherSerializer, MapObjectSerializer, IncidentReportSerializer, OperatorAlertSerializer)
from rest_framework.decorators import api_view, permission_classes, action
import secrets
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
from datetime import datetime
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as django_login
from django.views.decorators.csrf import csrf_exempt
import math
import random

# ── htmx partial views (moved to api/views/partials/) ──────────────────────
# Kept here as re-exports for backward compatibility with api/urls.py
from api.views.partials.guards import guards_partial, guard_form_partial
from api.views.partials.reports import scans_table_partial, reports_guards_options_partial, reports_routes_options_partial
from api.views.partials.admin import admin_stats_partial
from api.views.partials.incidents import incidents_partial, incidents_guards_options_partial
from api.views.partials.options import alerts_partial


def _deactivate_assignments(queryset):
    """Bulk-deactivate ShiftAssignments and properly reset guard is_on_shift.

    Uses .update() for efficiency then manually fixes guard shift status
    since post_save signal does NOT fire on QuerySet.update().
    """
    now = timezone.now()
    guard_ids = set(
        queryset.exclude(guard_supervisor=None)
        .values_list('guard_supervisor_id', flat=True)
    )
    queryset.update(is_active=False, ended_at=now)
    for gid in guard_ids:
        still_active = ShiftAssignment.objects.filter(
            guard_supervisor_id=gid, is_active=True
        ).exists()
        if not still_active:
            GuardSupervisor.objects.filter(id=gid, is_on_shift=True).update(is_on_shift=False)


def _haversine_meters(lat1, lng1, lat2, lng2):
    """Distance in meters between two lat/lng points."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_in_polygon(lat, lng, polygon):
    """Ray-casting point-in-polygon. polygon = list of [lat, lng] points."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    role = request.data.get('role', 'dispatcher')  # Default to dispatcher for new users
    
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Username exists'}, status=400)
    
    default_org = Organization.objects.first()
    if not default_org:
        return Response({'error': 'No organization exists. Contact an administrator to create one first.'}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    
    organization_id = None
    organization_name = None
    
    # Only admin/superuser roles get a Django auth user.
    # Guards/supervisors are data-only (created via scan-guards endpoint).
    if role == 'admin' or user.is_superuser:
        role = 'admin'
        organization_id = [org.id for org in Organization.objects.all()]
        organization_name = "Global System"
    else:
        # Default: dispatcher role
        dispatcher = Dispatcher.objects.create(user=user, organization=default_org)
        role = 'dispatcher'
        organization_id = [dispatcher.organization.id]
        organization_name = dispatcher.organization.name
    
    refresh = RefreshToken.for_user(user)
    
    # Store token in session for middleware access
    request.session['access_token'] = str(refresh.access_token)

    # Also set access token cookie for server-rendered pages (JwtTokenMiddleware expects this)
    response = Response({
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': UserSerializer(user).data,
        'role': role,
        'organization_id': organization_id,
        'organization_name': organization_name
    })

    response.set_cookie(
        'gt_access_token',
        str(refresh.access_token),
        httponly=False,
        samesite='Lax'
    )
    return response

def generate_operator_id(org):
    """Generate ORG-SEQ operator ID (e.g., TCN-01), using max existing seq to avoid collisions."""
    prefix = f"{org.code}-"
    last = Device.objects.filter(organization=org, device_id__startswith=prefix).order_by('-device_id').first()
    max_seq = 0
    if last and last.device_id:
        try:
            seq = int(last.device_id[len(prefix):])
            max_seq = seq
        except (ValueError, IndexError):
            pass
    return f"{prefix}{max_seq + 1:02d}"

@api_view(['GET'])
def operator_id_next(request):
    """Return the next available ORG-SEQ operator ID for an organization.
    
    Query params: organization=<org_id>
    """
    org_id = request.GET.get('organization')
    if not org_id:
        return Response({'detail': 'organization query parameter required'}, status=400)
    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        return Response({'detail': 'Organization not found'}, status=404)
    return Response({'operator_id': generate_operator_id(org)})

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def login(request):
    from django.contrib.auth import authenticate
    username = request.data.get('username')
    password = request.data.get('password')
    
    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': 'Invalid credentials'}, status=400)
    
    role = 'unknown'
    organization_id = None
    organization_name = None
    
    # Store token in session for middleware access
    request.session['access_token'] = str(RefreshToken.for_user(user).access_token)
    
    default_org = Organization.objects.first()

    # Determine role and organization with priority: Admin > Dispatcher > Guard/Supervisor
    if user.is_superuser:
        role = 'admin'
        organization_id = [org.id for org in Organization.objects.all()]
        organization_name = "Global System"
    elif hasattr(user, 'admin_profile'):
        admin_profile = user.admin_profile
        organization_id = [org.id for org in admin_profile.organizations.all()]
        organization_name = "Enterprise Admin"
        role = 'admin'
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher_profile = user.dispatcher_profile
        role = 'dispatcher'
        # Ensure dispatcher has an organization
        if not dispatcher_profile.organization:
            dispatcher_profile.organization = default_org
            dispatcher_profile.save(update_fields=['organization'])
        if dispatcher_profile.organization:
            organization_id = [dispatcher_profile.organization.id]
            organization_name = dispatcher_profile.organization.name
    elif hasattr(user, 'guardsupervisor'):
        # User is a guard or supervisor
        guard_profile = user.guardsupervisor
        role = guard_profile.role
        if guard_profile.organization:
            organization_id = [guard_profile.organization.id]
            organization_name = guard_profile.organization.name

    refresh = RefreshToken.for_user(user)
    # Store token in session for middleware access
    request.session['access_token'] = str(refresh.access_token)
    
    # Log user into session for server-rendered pages
    django_login(request, user)
    
    return Response({'refresh': str(refresh), 'access': str(refresh.access_token), 'user': UserSerializer(user).data,
                     'role': role, 'organization_id': organization_id, 'organization_name': organization_name})

@api_view(['POST'])
@permission_classes([AllowAny])
def register_device(request):
    operator_id = request.data.get('operator_id')
    hardware_info = request.data.get('hardware_info', {})

    if not operator_id:
        return Response({'detail': 'Operator ID required'}, status=400)

    # Look up existing device by operator_id (created via web UI)
    device = Device.objects.filter(device_id=operator_id).first()
    if not device:
        return Response({'detail': 'Operator ID not found. Create a device in the web portal first.'}, status=404)

    for field in ['imei', 'imsi', 'sim_phone_number', 'os_version', 'manufacturer', 'model', 'sdk_int']:
        if field in hardware_info:
            setattr(device, field, hardware_info[field])

    # If device has no password, generate one and persist it so the app can authenticate
    if not device.password:
        device.password = str(secrets.randbelow(90000000) + 10000000)

    # If device has no organization, try to infer from CallSign or operator_id prefix
    if not device.organization:
        cs = CallSign.objects.filter(device=device).first()
        if cs and cs.organization:
            device.organization = cs.organization

    device.last_seen = timezone.now()
    device.is_online = True
    device.save()

    return Response({
        'status': 'registered',
        'device_id': device.device_id,
        'password': device.password,
    })

@api_view(['POST'])
def provision_device(request):
    """Provision a hardware device to a guard callsign (callsign) and create an active ShiftAssignment.



    Android is expected to POST the real hardware_id (device_id). If we previously created a placeholder device
    without hardware_id, bind it here.
    """
    device_id = request.data.get('device_id')
    guard_id = request.data.get('guard_id')
    scheduled_start = request.data.get('scheduled_start')
    scheduled_end = request.data.get('scheduled_end')

    if not device_id:
        return Response({'detail': 'device_id required'}, status=400)
    
    guard = get_object_or_404(GuardSupervisor, id=guard_id)
    org = guard.organization

    # Use get_or_create to allow "pre-registration" from the dashboard
    # even before the physical device has installed the app and connected.
    device, created = Device.objects.get_or_create(
        device_id=device_id,
        defaults={'device_name': f"Device-{device_id[-4:]}", 'organization': org}
    )

    if created and not device.callsign and org:
        device.callsign = guard.callsign if guard.callsign else generate_operator_id(org)
        device.save()

    # Sync to CallSign Model (The Source of Truth)
    cs, _ = CallSign.objects.get_or_create(device=device, organization=org)
    cs.callsign = device.callsign
    cs.current_guard = guard
    cs.active_shift = guard.shift
    cs.save()

    # Assign the hardware's callsign to the guard's profile
    if device.callsign:
        guard.callsign = device.callsign
        guard.save(update_fields=['callsign'])

    device.is_online = True
    device.last_seen = timezone.now()
    device.save()

    # Bind provisioning
    DeviceProvisioning.objects.update_or_create(
        device=device,
        guard=guard,
        defaults={
            'callsign_snapshot': device.callsign,
            'organization': org,
        }
    )

    # Create new active assignment (route left null/unassigned)
    ShiftAssignment.objects.create(
        dispatcher=request.user,
        guard_supervisor=guard,
        device=device,
        route=None,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        shift_type=guard.shift,
        is_active=True,
        is_completed=False,
    )

    return Response({'status': 'provisioned', 'device_id': device_id, 'callsign': guard.callsign}, status=201)


def _heartbeat_update_device(device, request):
    lat = request.data.get('lat')
    lng = request.data.get('lng')
    battery = request.data.get('battery_pct')
    gps_accuracy = request.data.get('gps_accuracy')
    if battery is not None:
        device.battery_pct = battery
    if lat is not None:
        device.last_latitude = lat
    if lng is not None:
        device.last_longitude = lng
    if gps_accuracy is not None:
        device.last_gps_accuracy = gps_accuracy
    device.last_seen = timezone.now()
    device.is_online = True
    return lat, lng, gps_accuracy


def _heartbeat_fetch_directives(device, lat, gps_accuracy):
    directives = {}
    if device.nfc_fetch_requested:
        directives['fetch_nfc'] = True
        device.nfc_fetch_requested = None
    if device.gps_fetch_requested:
        directives['fetch_gps'] = True
        directives['gps_accuracy'] = device.gps_accuracy_threshold or 10
    if device.gps_fetch_requested and lat is not None and gps_accuracy is not None:
        if gps_accuracy <= (device.gps_accuracy_threshold or 10):
            device.gps_fetch_requested = None
    return directives


def _heartbeat_operator_identity(device):
    cs = CallSign.objects.filter(device=device).first()
    if not cs:
        return {}
    return {
        'callsign': cs.callsign,
        'guard_name': f"{cs.current_guard.first_name} {cs.current_guard.last_name}".strip() if cs.current_guard else None,
    }


def _heartbeat_active_missions(device):
    assignments = ShiftAssignment.objects.filter(
        device=device, is_active=True, is_completed=False
    ).select_related('route')
    missions = []
    primary = None
    for a in assignments:
        if a.route:
            if not missions:
                primary = a.route
            missions.append({
                'assignment_id': a.id,
                'route_id': a.route.id,
                'route_name': a.route.name,
                'shift_type': a.shift_type,
            })
    directives = {'missions': missions}
    if primary:
        p = missions[0]
        directives['route_id'] = p['route_id']
        directives['route_name'] = p['route_name']
        directives['tts_voice'] = primary.tts_voice or 'en-US'
        directives['tts_rate'] = primary.tts_rate
        directives['tts_pitch'] = primary.tts_pitch
    return directives, assignments


def _heartbeat_lead_time_reminder(device, active_assignments, now):
    if device.tts_pending:
        return {}, False
    for a in active_assignments:
        route = a.route
        if not route or not route.send_start_alert:
            continue
        if not route.scheduled_start_time or not route.start_alert_lead_time:
            continue
        mission_date = a.scheduled_date or now.date()
        reminder_start_dt = timezone.make_aware(
            datetime.combine(mission_date, route.scheduled_start_time),
            timezone=now.tzinfo,
        ) - timedelta(minutes=route.start_alert_lead_time)
        if now < reminder_start_dt:
            continue
        scan_filter = {
            'route': route,
            'timestamp__gte': a.assigned_at,
            'checkpoint__isnull': False,
        }
        if a.guard_supervisor:
            scan_filter['guard_supervisor'] = a.guard_supervisor
        if ScanRecord.objects.filter(**scan_filter).exists():
            continue
        if device.last_reminder_at:
            elapsed = (now - device.last_reminder_at).total_seconds()
            if elapsed < route.start_alert_lead_time * 60:
                continue
        msg = route.readout_text or f"Reminder: {route.name} starts at {route.scheduled_start_time.strftime('%H:%M')}. Please proceed to your first checkpoint."
        device.last_reminder_at = now
        device.tts_acked = False
        device.tts_pending = msg
        device.tts_pending_voice = route.tts_voice or device.tts_voice or 'en-US'
        device.tts_pending_rate = route.tts_rate
        device.tts_pending_pitch = route.tts_pitch
        device.tts_pending_at = now
        device.save(update_fields=['last_reminder_at', 'tts_acked', 'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at'])
        return {
            'tts_pending': msg,
            'tts_pending_voice': route.tts_voice or device.tts_voice or 'en-US',
            'tts_pending_rate': route.tts_rate,
            'tts_pending_pitch': route.tts_pitch,
            'play_sound': True,
            'vibrate': True,
        }, True
    return {}, False


def _heartbeat_geofence_tts(device, lat, lng, now):
    if lat is None or lng is None or not device.organization_id:
        return {}
    geofences = MapObject.objects.filter(
        organization_id=device.organization_id,
        type='geofence',
    ).exclude(entry_msg__isnull=True).exclude(entry_msg__exact='')
    gf_states = device.geofence_states or {}
    for gf in geofences:
        inside = False
        if gf.geometry and isinstance(gf.geometry, list) and len(gf.geometry) >= 2:
            if gf.radius:
                dist = _haversine_meters(lat, lng, gf.geometry[0], gf.geometry[1])
                inside = dist <= gf.radius
            elif len(gf.geometry) >= 3 and isinstance(gf.geometry[0], list):
                inside = _point_in_polygon(lat, lng, gf.geometry)
        gf_key = str(gf.id)
        if not inside and gf_key in gf_states:
            del gf_states[gf_key]
            device.geofence_states = gf_states
            device.save(update_fields=['geofence_states'])
        elif inside and gf_key not in gf_states and not device.tts_pending:
            gf_states[gf_key] = now.isoformat()
            device.geofence_states = gf_states
            device.tts_acked = False
            device.tts_pending = gf.entry_msg
            device.tts_pending_voice = device.tts_voice or 'en-US'
            device.tts_pending_rate = device.tts_rate
            device.tts_pending_pitch = device.tts_pitch
            device.tts_pending_at = now
            device.save(update_fields=['geofence_states', 'tts_acked', 'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at'])
            return {
                'tts_pending': gf.entry_msg,
                'tts_pending_voice': device.tts_voice or 'en-US',
                'tts_pending_rate': device.tts_rate,
                'tts_pending_pitch': device.tts_pitch,
                'play_sound': True,
                'vibrate': True,
            }
    return {}


def _heartbeat_tts_delivery(device):
    if device.tts_pending:
        tts = {
            'tts_pending': device.tts_pending,
            'tts_pending_voice': device.tts_pending_voice,
            'tts_pending_rate': device.tts_pending_rate,
            'tts_pending_pitch': device.tts_pending_pitch,
        }
        if device.tts_acked:
            device.tts_acked = False
            device.save(update_fields=['tts_acked'])
        return tts
    return {}


def _heartbeat_tts_ack(device, request):
    if not request.data.get('tts_acked'):
        return
    device.tts_pending = None
    device.tts_pending_voice = ''
    device.tts_pending_rate = 1.0
    device.tts_pending_pitch = 1.0
    device.tts_pending_at = None
    device.tts_acked = True
    device.save(update_fields=[
        'tts_pending', 'tts_pending_voice', 'tts_pending_rate',
        'tts_pending_pitch', 'tts_pending_at', 'tts_acked',
    ])


def _heartbeat_peer_mode(device, active_assignments):
    """Assign HCE roles for audit routes.

    For each active audit route, find the peer checkpoint and determine
    whether this device is the target (emulator) or the auditor (reader).
    """
    result = {}
    for a in active_assignments:
        route = a.route
        if not route or not route.is_audit:
            continue
        peer_cp = route.checkpoints.filter(checkpoint_type='peer').first()
        if not peer_cp:
            continue
        target_device_id = peer_cp.nfc_tag
        if not target_device_id:
            continue
        if device.device_id == target_device_id:
            nonce = secrets.token_hex(8)
            device.peer_session_key = nonce
            result = {
                'peer_mode': 'hce_emulator',
                'peer_target_device_id': device.device_id,
                'peer_route_id': route.id,
                'peer_nonce': nonce,
            }
        else:
            result = {
                'peer_mode': 'hce_reader',
                'peer_target_device_id': target_device_id,
                'peer_route_id': route.id,
            }
        break
    return result


@api_view(['POST'])
@permission_classes([AllowAny])
def heartbeat(request):
    device_id = request.data.get('device_id')
    password = request.data.get('password')

    if not device_id:
        return Response({'status': 'error', 'message': 'device_id required'}, status=400)
    if not password:
        return Response({'status': 'error', 'message': 'password required'}, status=400)

    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return Response({'status': 'device_not_found'}, status=404)
    if device.password != password:
        return Response({'status': 'auth_failed'}, status=401)

    lat, lng, gps_accuracy = _heartbeat_update_device(device, request)

    directives = {'status': 'ok'}
    directives.update(_heartbeat_fetch_directives(device, lat, gps_accuracy))
    directives.update(_heartbeat_operator_identity(device))

    mission_directives, active_assignments = _heartbeat_active_missions(device)
    directives.update(mission_directives)

    now = timezone.now()
    reminder_directives, reminder_sent = _heartbeat_lead_time_reminder(device, active_assignments, now)
    directives.update(reminder_directives)

    if not reminder_sent:
        directives.update(_heartbeat_geofence_tts(device, lat, lng, now))

    _heartbeat_tts_ack(device, request)
    directives.update(_heartbeat_tts_delivery(device))
    directives.update(_heartbeat_peer_mode(device, active_assignments))

    device.save(update_fields=[
        'battery_pct', 'last_latitude', 'last_longitude', 'last_gps_accuracy',
        'last_seen', 'is_online', 'nfc_fetch_requested', 'gps_fetch_requested',
        'gps_accuracy_threshold', 'peer_session_key',
    ])
    return Response(directives)

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
            return CallSign.objects.all()
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            return CallSign.objects.filter(organization=user.dispatcher_profile.organization)
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
            # Admins can create dispatchers for any organization (or none)
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
            return GuardSupervisor.objects.all()
        
        # Dispatcher: check organization first, auto-assign if missing
        if hasattr(user, 'dispatcher_profile'):
            if not user.dispatcher_profile.organization:
                default_org = Organization.objects.first()
                if default_org:
                    user.dispatcher_profile.organization = default_org
                    user.dispatcher_profile.save(update_fields=['organization'])
            if user.dispatcher_profile.organization:
                return GuardSupervisor.objects.filter(organization=user.dispatcher_profile.organization)
        return GuardSupervisor.objects.none()
    
    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            # Admins can create guard supervisors for any organization (or none)
            serializer.save()
        elif hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
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
            return Device.objects.all()
        
        # Dispatcher: check organization first
        dispatcher_profile = getattr(user, 'dispatcher_profile', None)
        if dispatcher_profile:
            dispatcher = dispatcher_profile
            # Auto-assign default organization if dispatcher has none
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])
            if dispatcher.organization:
                return Device.objects.filter(organization=dispatcher.organization)
        return Device.objects.none()
    
    @action(detail=True, methods=['post'])
    def fetch_nfc(self, request, pk=None):
        """Request NFC tag fetch from device - works even if offline."""
        device = self.get_object()
        # Flag the device to fetch NFC when it comes online
        # Store request in a way that the device can pick up
        from django.utils import timezone
        from django.db.models import F
        # Add a fetch request to the device record
        device.nfc_fetch_requested = timezone.now()
        device.save(update_fields=['nfc_fetch_requested'])
        return Response({'status': 'requested', 'message': f'NFC fetch requested for {device.device_id or device.device_name}'})
    
    @action(detail=True, methods=['post'])
    def fetch_gps(self, request, pk=None):
        """Request GPS fetch from device - works even if offline.
        Optional: send {'accuracy': 5} for 5m precision."""
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
        """Send a TTS announcement directly to a device (no route required).
        Saves the message and TTS config on the device for pickup on next heartbeat,
        and also creates an OperatorAlert if the device has an assigned guard.
        Send: {'message': '...', 'tts_voice': 'en-US', 'tts_rate': 1.0, 'tts_pitch': 1.0}"""
        from django.utils import timezone
        device = self.get_object()
        msg = request.data.get('message', '').strip()
        if not msg:
            return Response({'detail': 'Message required'}, status=400)
        
        voice = request.data.get('tts_voice', device.tts_voice or 'en-US')
        rate = request.data.get('tts_rate', device.tts_rate)
        pitch = request.data.get('tts_pitch', device.tts_pitch)
        
        # Save TTS defaults back to device
        device.tts_voice = voice
        device.tts_rate = rate
        device.tts_pitch = pitch
        
        # Queue the pending TTS for device pickup
        device.tts_pending = msg
        device.tts_pending_voice = voice
        device.tts_pending_rate = rate
        device.tts_pending_pitch = pitch
        device.tts_pending_at = timezone.now()
        device.tts_acked = False
        device.save(update_fields=['tts_voice', 'tts_rate', 'tts_pitch', 'tts_pending', 'tts_pending_voice', 'tts_pending_rate', 'tts_pending_pitch', 'tts_pending_at', 'tts_acked'])
        
        # Also create an OperatorAlert if device has an active assignment with a guard
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
        """Remotely swap the operator identity on this device to a different guard.
        Closes the current active assignment and provisions a new one.
        Send: {'guard_id': 123} or {'callsign': 'H-02@org'}"""
        device = self.get_object()
        guard_id = request.data.get('guard_id')
        callsign = request.data.get('callsign')

        if not guard_id and not callsign:
            return Response({'detail': 'Provide guard_id or callsign'}, status=400)

        # Resolve the target guard
        if guard_id:
            guard = get_object_or_404(GuardSupervisor, id=guard_id)
        else:
            # Find guard by callsign via CallSign
            cs = CallSign.objects.filter(callsign=callsign).first()
            if not cs or not cs.current_guard:
                return Response({'detail': f'No guard found for callsign {callsign}'}, status=404)
            guard = cs.current_guard

        org = guard.organization
        now = timezone.now()

        # 1. Close current active assignments for this device
        old_assignments = list(ShiftAssignment.objects.filter(device=device, is_active=True))
        old_guard_ids = set(a.guard_supervisor_id for a in old_assignments if a.guard_supervisor_id)
        ShiftAssignment.objects.filter(device=device, is_active=True).update(
            is_active=False, ended_at=now
        )
        # Re-check guards whose assignments were bulk-closed (signal doesn't fire on update())
        for gid in old_guard_ids:
            still_active = ShiftAssignment.objects.filter(guard_supervisor_id=gid, is_active=True).exclude(device=device).exists()
            if not still_active:
                GuardSupervisor.objects.filter(id=gid, is_on_shift=True).update(is_on_shift=False)

        # 2. Update the device's callsign to match the guard's current callsign
        if guard.callsign:
            device.callsign = guard.callsign
            device.save(update_fields=['callsign'])

        # 3. Upsert CallSign record
        cs, _ = CallSign.objects.get_or_create(device=device, organization=org)
        cs.callsign = guard.callsign or device.callsign
        cs.current_guard = guard
        cs.active_shift = guard.shift
        cs.save()

        # 4. Create a new active ShiftAssignment
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
            org = user.dispatcher_profile.organization

        # Fallback to first available organization
        if not org:
            org = Organization.objects.first()

        if org:
            generated_callsign = generate_operator_id(org)
            pwd = self.request.data.get('password') or str(secrets.randbelow(90000000) + 10000000)
            
            serializer.save(organization=org, callsign=generated_callsign, password=pwd)
            # Pre-create the CallSign record
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
            return PatrolRoute.objects.all()
        
        # Dispatcher: check organization first
        dispatcher_profile = getattr(user, 'dispatcher_profile', None)
        if dispatcher_profile:
            dispatcher_org = dispatcher_profile.organization
            # Auto-assign default organization if dispatcher has none
            if not dispatcher_org:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher_profile.organization = default_org
                    dispatcher_profile.save(update_fields=['organization'])
                    dispatcher_org = default_org
            
            if dispatcher_org:
                # Show routes belonging to the dispatcher's organization or global ones.
                # Including Q(organization=None) ensures routes created without an organization
                # (e.g. via Django Admin) remain visible and assignable.
                return PatrolRoute.objects.filter(
                    Q(organization=dispatcher_org) | Q(organization__isnull=True)
                )
        
        return PatrolRoute.objects.none()
    
    def perform_create(self, serializer):
        user = self.request.user
        org = None

        if user.is_superuser or hasattr(user, 'admin_profile'):
            # Admins can choose the organization
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        elif hasattr(user, 'dispatcher_profile'):
            # Dispatchers can create routes for their organization
            org = user.dispatcher_profile.organization

        # Fallback to default organization if none found
        if not org:
            org = Organization.objects.first()
            if not org:
                raise PermissionDenied("Organization context missing. Cannot create blueprints without an organization.")

        # Force organization scoping on create/update to keep route visible to the
        # dispatcher that owns it (frontend filters by dispatcher_org).
        serializer.save(organization=org, created_by=user)

    @action(detail=True, methods=['post'])
    def deploy(self, request, pk=None):
        """Custom tactical action to immediately dispatch all personnel assigned to a blueprint.
        
        Supports both guard-based and device-only deployments:
        - Guard-based: Creates assignments with guard_supervisor = guard, device resolved from CallSign
        - Device-only: Creates assignments with guard_supervisor = null, device = assigned device
        """
        route = self.get_object()
        guards = route.assigned_guards.all()
        devices = route.assigned_devices.all()
        
        # Must have at least one assigned (guards or devices)
        if not guards.exists() and not devices.exists():
            return Response({'detail': 'Deployment aborted: No personnel or devices assigned to this blueprint.'}, status=400)
        
        now = timezone.now()
        results = []
        
        # Deploy for assigned guards
        for guard in guards:
            # Close any existing active mission for this officer
            _deactivate_assignments(ShiftAssignment.objects.filter(guard_supervisor=guard, is_active=True))
            
            # Attempt to find the hardware currently bound to this officer
            device = None
            registry = CallSign.objects.filter(current_guard=guard).select_related('device').first()
            if registry:
                device = registry.device
            
            # Create immediate mission assignment (ALWAYS active)
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
        
        # Deploy for assigned devices (device-only / autonomous mode)
        for device in devices:
            # Close any existing active assignments for this device (prevents duplicates)
            _deactivate_assignments(ShiftAssignment.objects.filter(device=device, is_active=True))
            # Create assignment without guard (autonomous/hardware mode)
            assignment = ShiftAssignment.objects.create(
                dispatcher=request.user,
                guard_supervisor=None,  # No guard for device-only
                device=device,
                route=route,
                scheduled_date=route.scheduled_date or now.date(),
                scheduled_start=now,
                shift_type='Day',  # Default shift for device-only
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
            return Checkpoint.objects.all()
        if hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
            if not org:
                org = Organization.objects.first()
            if org:
                # Filter checkpoints belonging to routes in this org OR standalone assets in this org
                return Checkpoint.objects.filter(
                    Q(route__organization=org) | Q(organization=org)
                ).distinct()
        return Checkpoint.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = None
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = self.request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        elif hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
        
        if not org:
            org = Organization.objects.first()
            
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
        elif hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
        if not org:
            org = Organization.objects.first()
        serializer.save(organization=org)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ScanRecordViewSet(viewsets.ModelViewSet):
    serializer_class = ScanRecordSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ScanRecord.objects.none()
        if user.is_superuser or hasattr(user, 'admin_profile'):
            queryset = ScanRecord.objects.all()
        elif hasattr(user, 'dispatcher_profile'):
            dispatcher = user.dispatcher_profile
            # Auto-assign default organization if dispatcher has none
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])
            org = dispatcher.organization
            if org:
                queryset = ScanRecord.objects.filter(
                    Q(guard_supervisor__organization=org) |
                    Q(device__organization=org) |
                    Q(route__organization=org)
                ).distinct()

        # Advanced Filtering for Reports
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        guard_id = self.request.query_params.get('guard_id')
        route_id = self.request.query_params.get('route_id')
        is_on_time = self.request.query_params.get('is_on_time')

        if start_date: queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date: queryset = queryset.filter(timestamp__date__lte=end_date)
        if guard_id: queryset = queryset.filter(guard_supervisor_id=guard_id)
        if route_id: queryset = queryset.filter(route_id=route_id)
        if is_on_time: 
            queryset = queryset.filter(is_on_time=is_on_time.lower() == 'true')

        return queryset.order_by('-timestamp')
    
    def create(self, request, *args, **kwargs):
        # The scan endpoint is not standard CRUD — the device sends device_id + password
        # + nfc_value, and process_scan() resolves the checkpoint, guard, route, etc.
        # Bypass serializer validation entirely and build the record from process_scan.
        from .scan_service import process_scan
        client_ts_str = request.data.get('client_timestamp')
        client_timestamp = None
        if client_ts_str:
            try:
                client_timestamp = datetime.fromisoformat(client_ts_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        result = process_scan(
            device_id=request.data.get('device_id'),
            password=request.data.get('password'),
            route_id=request.data.get('route_id'),
            nfc_value=request.data.get('nfc_value'),
            peer_key=request.data.get('verification_key'),
            now=timezone.now(),
            raw_nfc=request.data.get('raw_nfc'),
            scan_lat=request.data.get('lat'),
            scan_lng=request.data.get('lng'),
            client_timestamp=client_timestamp,
            sequence_id=request.data.get('sequence_id'),
        )
        # Pop response-only fields before creating the record
        extras = {
            'tts_message': result.pop('_tts_message', None),
            'tts_voice': result.pop('_tts_voice', 'en-US'),
            'tts_rate': result.pop('_tts_rate', 1.0),
            'tts_pitch': result.pop('_tts_pitch', 1.0),
            'play_sound': result.pop('_play_sound', True),
            'vibrate': result.pop('_vibrate', True),
        }
        record = ScanRecord.objects.create(**result)
        data = ScanRecordSerializer(record).data
        data['tts_message'] = extras.get('tts_message')
        data['tts_voice'] = extras.get('tts_voice')
        data['tts_rate'] = extras.get('tts_rate')
        data['tts_pitch'] = extras.get('tts_pitch')
        data['play_sound'] = extras.get('play_sound', True)
        data['vibrate'] = extras.get('vibrate', True)
        data['out_of_sequence'] = result.get('out_of_sequence', False)
        data['insufficient_dwell_time'] = result.get('insufficient_dwell_time', False)
        data['dwell_seconds'] = result.get('dwell_seconds', None)
        data['time_drift_seconds'] = result.get('time_drift_seconds', None)
        return Response(data, status=200)

    def perform_create(self, serializer):
        # No longer used — create() handles everything directly.
        # Kept for DRF internals that might call it.
        pass

class ShiftAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ShiftAssignmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return ShiftAssignment.objects.all()

        dispatcher_profile = getattr(user, 'dispatcher_profile', None)
        if dispatcher_profile:
            dispatcher = dispatcher_profile

            # Auto-assign default organization if dispatcher has none
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])

            if dispatcher.organization:
                org = dispatcher.organization

                # Visibility for dispatch UI must be consistent with how dispatch-page
                # filters/understands deployments: by route organization.
                #
                # Previously we used only:
                #   - guard_supervisor__organization=org
                #   - OR dispatcher=user
                # If deployments were created with route org but guard org / dispatcher user
                # didn't match exactly, the UI would show nothing.
                return ShiftAssignment.objects.filter(
                    Q(route__organization=org) |
                    Q(guard_supervisor__organization=org) |
                    Q(dispatcher=user)
                ).distinct()

        return ShiftAssignment.objects.none()

    
    def perform_create(self, serializer):
        user = self.request.user
        guard_sup = serializer.validated_data.get('guard_supervisor')
        route = serializer.validated_data.get('route')
        
        # Ensure scheduled_date defaults to today if not provided (Quick Deploy scenario)
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
        # Support bulk deployment for multiple guards or an entire shift
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
            return MapObject.objects.all()
        dispatcher_profile = getattr(user, 'dispatcher_profile', None)
        if dispatcher_profile:
            dispatcher = dispatcher_profile
            # Auto-assign default organization if dispatcher has none
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])
            if dispatcher.organization:
                return MapObject.objects.filter(organization=dispatcher.organization)
        return MapObject.objects.none()

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create assets/checkpoints from the Tactical Builder."""
        checkpoints_data = request.data.get('checkpoints', [])
        if not checkpoints_data:
            return Response({'detail': 'No checkpoints provided'}, status=400)
        
        org = None
        user = request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            org_id = request.data.get('organization')
            if org_id:
                org = Organization.objects.filter(id=org_id).first()
        elif hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
        
        # Must have an organization to proceed
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
                # Strip fields that belong to Checkpoint, not MapObject
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
        elif hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
        
        # Fallback to first available organization
        if not org:
            org = Organization.objects.first()

        if not org:
            raise PermissionDenied("Organization context missing.")
        serializer.save(organization=org)

class IncidentReportViewSet(viewsets.ModelViewSet):
    serializer_class = IncidentReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return IncidentReport.objects.all()
        if hasattr(user, 'dispatcher_profile'):
            dispatcher = user.dispatcher_profile
            # Auto-assign default organization if dispatcher has none
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])
            if dispatcher.organization:
                return IncidentReport.objects.filter(organization=dispatcher.organization)
        return IncidentReport.objects.none()

class OperatorAlertViewSet(viewsets.ModelViewSet):
    serializer_class = OperatorAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or hasattr(user, 'admin_profile'):
            return OperatorAlert.objects.all()
        if hasattr(user, 'dispatcher_profile'):
            dispatcher = user.dispatcher_profile
            if not dispatcher.organization:
                default_org = Organization.objects.first()
                if default_org:
                    dispatcher.organization = default_org
                    dispatcher.save(update_fields=['organization'])
            if dispatcher.organization:
                return OperatorAlert.objects.filter(organization=dispatcher.organization)
        return OperatorAlert.objects.none()

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





def organization_stats(request):
    
    # NOTE: Mission-control front-end uses separate endpoint(s) for per-checkpoint live status.
    

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
    
    # Use existing orgs only — do NOT auto-create here
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
        
        # Auto-assign default organization if dispatcher has none
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
    
    # Build Hourly Density (24 slots)
    hourly_density = [0] * 24
    for scan in today_scans:
        hour = scan.timestamp.hour
        hourly_density[hour] += 1

    # Performance by Shift
    shift_perf = {
        'Day': {'onTime': today_scans.filter(guard_supervisor__shift='Day', is_on_time=True).count(), 
                'late': today_scans.filter(guard_supervisor__shift='Day', is_on_time=False).count()},
        'Night': {'onTime': today_scans.filter(guard_supervisor__shift='Night', is_on_time=True).count(), 
                  'late': today_scans.filter(guard_supervisor__shift='Night', is_on_time=False).count()}
    }

    # Combine MapObjects and Standalone Checkpoints for a unified "Open Maps" view
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
    """Return the queryset of GuardSupervisor objects visible to this user."""
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
    """Handle POST from htmx guard form — create or update a GuardSupervisor."""
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
        # Determine organization for new profile
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
    """Get all guard/supervisor profiles for current organization, or create new."""
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
    """Get, update, or delete a specific guard/supervisor profile."""
    try:
        profile = GuardSupervisor.objects.get(pk=pk)
    except GuardSupervisor.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=404)
    
    # Check permission
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

# --- Blueprint-aware shift availability + unified assignment ---

SHIFT_TYPE_CHOICES = ['Day', 'Night', 'Flex']

@api_view(['GET'])
def blueprint_shift_availability(request):
    """Return per-blueprint shift availability for Day/Night/Flex.

    Query param: route_id (required)

    Eligibility rule (A): only guards in route.assigned_guards are eligible.
    Availability means: eligible guards minus currently active assignments for that route+shift_type.
    """
    route_id = request.query_params.get('route_id')
    if not route_id:
        return Response({'detail': 'route_id required'}, status=400)

    route = get_object_or_404(PatrolRoute, id=route_id)

    # Ensure dispatcher/org scoping like other endpoints (reuse org from route)
    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            if route.organization and route.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)

    eligible_guards_qs = route.assigned_guards.all()
    eligible_ids = list(eligible_guards_qs.values_list('id', flat=True))

    # Active assignments for this blueprint (strict route match)
    active_assignments = ShiftAssignment.objects.filter(
        route=route,
        is_active=True,
        guard_supervisor_id__in=eligible_ids,
    )

    # Flex guards can cover Day or Night, but not both — count unassigned Flex once
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
    """Link guard<->device and create an active ShiftAssignment bound to a blueprint.

    Expected JSON:
      - guard_id (required)
      - route_id (required)
      - shift_type (required: Day|Night|Flex)
      - device_id (optional)

    Device behavior:
      - If device_id provided: create/update provisioning binding (DeviceProvisioning + CallSign)
      - Else: keep existing device from guard's active CallSign if any
    """
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

    # Permission scoping
    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        if hasattr(user, 'dispatcher_profile') and user.dispatcher_profile.organization:
            if route.organization and route.organization != user.dispatcher_profile.organization:
                return Response({'detail': 'Permission denied'}, status=403)

    if route.assigned_guards.exists() and not route.assigned_guards.filter(id=guard.id).exists():
        return Response({'detail': 'Guard not eligible for this blueprint'}, status=400)

    # Resolve device
    device = None
    if device_id:
        device = get_object_or_404(Device, id=device_id)
        # Bind provisioning to guard
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
        # Use currently bound device for this guard if present
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


# --- Frontend Page Views ---

@login_required
def dashboard_page(request):
    """Server-rendered dashboard with org info, on-duty personnel, missions, and daily routes."""
    stats_response = organization_stats(request)
    context = stats_response.data if hasattr(stats_response, 'data') else {}

    user = request.user

    # 1. Organization info
    org = None
    if user.is_superuser or hasattr(user, 'admin_profile'):
        org = Organization.objects.first()
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if not org:
            org = Organization.objects.first()

    if org:
        context['org_info'] = {
            'name': org.name,
            'phone': org.phone or '',
            'email': org.contact_email or '',
            'address': org.address or '',
        }
        context['org'] = org

    # 2. On-duty guards with device info
    if org:
        on_duty_qs = GuardSupervisor.objects.filter(is_on_shift=True, organization=org)
    else:
        on_duty_qs = GuardSupervisor.objects.filter(is_on_shift=True)

    on_duty_guards = []
    for g in on_duty_qs:
        device = None
        battery = None
        device_online = False
        device_name = None
        cs = CallSign.objects.filter(current_guard=g).select_related('device').first()
        if cs and cs.device:
            device = cs.device
            device_name = device.device_id or device.device_name
            battery = device.battery_pct
            device_online = device.is_online
        on_duty_guards.append({
            'id': g.id,
            'name': f"{g.first_name} {g.last_name}".strip() or 'Unnamed',
            'callsign': g.callsign or '',
            'role': g.role,
            'shift': g.shift,
            'last_scan': g.last_scan,
            'device_name': device_name,
            'battery': battery,
            'device_online': device_online,
        })
    context['on_duty_guards'] = on_duty_guards

    # 3. Daily pinned routes
    if org:
        daily_routes_qs = PatrolRoute.objects.filter(
            Q(organization=org) | Q(organization=None),
            is_daily=True,
            status__in=['scheduled', 'active'],
        ).order_by('scheduled_start_time')
    else:
        daily_routes_qs = PatrolRoute.objects.filter(
            is_daily=True,
            status__in=['scheduled', 'active'],
        ).order_by('scheduled_start_time')
    context['daily_routes'] = PatrolRouteSerializer(daily_routes_qs, many=True).data

    # 4. Enhance active deployments with ETA + progress
    enhanced = []
    for dep in list(context.get('active_deployments', [])):
        dep = dict(dep)
        scheduled_end = dep.get('scheduled_end')
        eta_seconds = None
        eta_label = ''
        if scheduled_end:
            try:
                end_dt = datetime.fromisoformat(scheduled_end.replace('Z', '+00:00'))
                now = timezone.now()
                delta = end_dt - now
                eta_seconds = int(delta.total_seconds())
                if eta_seconds > 0:
                    hours = eta_seconds // 3600
                    mins = (eta_seconds % 3600) // 60
                    eta_label = f"{hours}h {mins}m" if hours else f"{mins}m"
                else:
                    eta_label = "Overdue"
            except (ValueError, TypeError):
                pass

        total = dep.get('total_checkpoints', 0) or 0
        completed = dep.get('completed_checkpoints', 0) or 0
        progress = int((completed / total) * 100) if total > 0 else 0

        dep['eta_seconds'] = eta_seconds
        dep['eta_label'] = eta_label
        dep['progress'] = progress
        enhanced.append(dep)
    context['active_deployments'] = enhanced

    return render(request, 'dashboard.html', context or {})

@login_required
def map_view_page(request):
    return render(request, 'map_view.html')

@login_required
def routes_page(request):
    """Blueprint Designer page - renders routes.html with full client-side functionality."""
    return render(request, 'routes.html')

@login_required
def dispatch_page(request):
    """Standard Dispatch page."""
    user = request.user

    # Deny access if user has no dispatcher_profile or admin_profile
    if not hasattr(user, 'dispatcher_profile') and not (user.is_superuser or hasattr(user, 'admin_profile')):
        return redirect('login')

    org = None
    if hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if not org:
            org = Organization.objects.first()
    elif user.is_superuser or hasattr(user, 'admin_profile'):
        org = Organization.objects.first()

    if request.method == "POST":
        guard_id = request.POST.get('guard_supervisor')
        route_id = request.POST.get('route')
        device_id = request.POST.get('device')
        shift_type = request.POST.get('shift_type')

        # Auto-deactivate previous assignments for both guard AND device
        _deactivate_assignments(ShiftAssignment.objects.filter(guard_supervisor_id=guard_id, is_active=True))
        if device_id:
            _deactivate_assignments(ShiftAssignment.objects.filter(device_id=device_id, is_active=True))

        ShiftAssignment.objects.create(
            dispatcher=user,
            guard_supervisor_id=guard_id,
            route_id=route_id,
            device_id=device_id,
            shift_type=shift_type,
            scheduled_date=timezone.now().date(),
            is_active=True
        )
        return redirect('dispatch')
    # Determine querysets based on role and organization context
    if user.is_superuser or hasattr(user, 'admin_profile'):
        # System admins see all global assets
        guards_qs = GuardSupervisor.objects.all()
        routes_qs = PatrolRoute.objects.all()
        devices_qs = Device.objects.all()
        active_assignments_qs = ShiftAssignment.objects.filter(is_active=True)
    else:
        # Dispatchers see org-specific assets + unassigned routes
        guards_qs = GuardSupervisor.objects.filter(organization=org)
        routes_qs = PatrolRoute.objects.filter(Q(organization=org) | Q(organization__isnull=True))
        devices_qs = Device.objects.filter(organization=org)
        active_assignments_qs = ShiftAssignment.objects.filter(
            Q(route__organization=org) |
            Q(guard_supervisor__organization=org) |
            Q(dispatcher=user),
            is_active=True
        ).distinct()

    context = {
        'guards': guards_qs,
        'routes': routes_qs,
        'devices': devices_qs,
        'active_assignments': active_assignments_qs.order_by('-assigned_at')
    }

    return render(request, 'dispatch.html', context)

@api_view(['POST'])
def end_shift(request, pk):
    """Terminate a shift assignment. Returns JSON; frontend redirects client-side if needed."""
    assignment = get_object_or_404(ShiftAssignment, pk=pk)
    assignment.is_active = False
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=['is_active', 'ended_at'])

    if assignment.guard_supervisor:
        assignment.guard_supervisor.is_on_shift = False
        assignment.guard_supervisor.save(update_fields=['is_on_shift'])

    return Response({'status': 'ended', 'assignment_id': assignment.id})

@login_required
def incidents_page(request):
    return render(request, 'incidents.html')

@login_required
def guards_page(request):
    return render(request, 'guards.html')

@login_required
def manage_page(request):
    return render(request, 'manage.html')

@login_required
def reports_page(request):
    return render(request, 'reports.html')

@login_required
def admin_panel_page(request):
    return render(request, 'admin_panel.html')

def login_page(request):
    return render(request, 'login.html')

def register_page(request):
    return render(request, 'register.html')


def logout_view(request):
    """Logout and redirect to login."""
    from django.contrib.auth import logout
    from django.shortcuts import redirect
    logout(request)
    return redirect('/')


def custom_404(request, exception=None):
    """Custom 404 page with GuardTour glass theme."""
    from django.http import HttpResponseNotFound
    return HttpResponseNotFound(render(request, '404.html').content)


def custom_500(request):
    """Custom 500 page with GuardTour glass theme."""
    from django.http import HttpResponseServerError
    return HttpResponseServerError(render(request, '404.html').content)


@api_view(['GET'])
def deployment_checkpoint_live(request):
    """Return live status for the next checkpoint of each active deployment.

    Response items per assignment:
      - assignment_id
      - route_id / route_name / logic_type
      - shift_type
      - next_checkpoint: { id, name, checkpoint_type, planned_time, time_remaining_seconds,
                            dwell_time_minutes, dwell_remaining_seconds, is_present, is_window_missed }

    Uses ScanRecord timestamps to determine last hit and dwell presence.
    """
    from rest_framework.permissions import IsAuthenticated
    from django.utils import timezone as dj_timezone

    if not isinstance(getattr(request, 'user', None), object):
        return Response({'detail': 'Unauthorized'}, status=401)

    now = dj_timezone.now()

    # Scope assignments by current user's dispatcher/org rules (reuse similar logic)
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

        # Next CP = first in order that is not in hit set
        next_cp = None
        for cp in cps:
            if cp.id not in hit_cp_ids:
                next_cp = cp
                break

        has_missed = False

        if not next_cp:
            # All checkpoints hit; mark as done but assignment is_active=false should normally handle.
            next_payload = None
        else:
            # Last hit time
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

            # Route Gap Analysis: identify all missed checkpoints
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

            # Determine shift end window for untimed / device-only fallback
            shift_end_dt = None
            if a.guard_supervisor:
                # Guard: shift ends at 18:00 (Day) or 06:00 next day (Night)
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
                # Device-only: 24 hours from blueprint scheduled_start_time (or assigned_at)
                bp_time = route.scheduled_start_time or dj_timezone.datetime.min.time()
                bp_base = a.scheduled_date or a.assigned_at.date() if a.assigned_at else now.date()
                shift_end_dt = dj_timezone.make_aware(
                    dj_timezone.datetime.combine(bp_base, bp_time) + timedelta(hours=24),
                    timezone=now.tzinfo,
                )

            # Scan ALL pending checkpoints (not just next) for missed state
            missed_pending_ids = set()
            for cp in cps:
                if cp.id in hit_cp_ids:
                    continue
                # Timed checkpoint
                if cp.planned_time and a.scheduled_date:
                    cp_deadline = dj_timezone.make_aware(
                        dj_timezone.datetime.combine(a.scheduled_date, cp.planned_time),
                        timezone=now.tzinfo,
                    ) + timedelta(minutes=int(cp.time_tolerance or 15) + int(cp.dwell_time or 0))
                    if now > cp_deadline:
                        missed_pending_ids.add(cp.id)
                else:
                    # Untimed: deadline = shift end (or 24h for device-only)
                    cp_deadline = shift_end_dt
                    if cp_deadline and now > cp_deadline:
                        missed_pending_ids.add(cp.id)
            has_missed = len(missed_pending_ids) > 0

            # Planned time window remaining (for the NEXT checkpoint only)
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
                # Untimed next checkpoint: missed if past shift end
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

@api_view(['POST'])
def resend_tts(request):
    """Resend TTS announcement for a route/checkpoint with voice config."""
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
    """Return the current staging status for a single assignment — next checkpoint,
    time remaining, dwell state, missed windows. Used by both the Android app
    and the dispatch frontend."""
    from .scan_service import get_mission_status
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
@permission_classes([IsAuthenticated])
def transfer_shift(request):
    """Transfer a partially completed route from one guard to another.

    Expected JSON:
      - assignment_id (required): current active assignment to transfer
      - new_guard_id (required): target guard supervisor ID
    """
    from .scan_service import transfer_shift as transfer_shift_logic

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
    """Return missed checkpoints for a given assignment.

    Used by the dispatcher dashboard to highlight skipped points.
    """
    from .scan_service import route_gap_analysis

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


# ── Offline Sync & GPS Trail ─────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def gps_batch_sync(request):
    """Accept an array of GPS points collected offline by the device.

    Expected body: { device_id, password, points: [{ lat, lng, accuracy, recorded_at, battery_pct, speed, bearing }] }

    Returns corrected trail data for the device.
    """
    from .scan_service import correct_gps_trail
    device_id = request.data.get('device_id')
    password = request.data.get('password')
    points = request.data.get('points', [])

    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)
    if not isinstance(points, list) or not points:
        return Response({'detail': 'points array required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)
    if device.password != password:
        return Response({'detail': 'Auth failed'}, status=401)

    # Resolve active assignment for context
    active_assignment = ShiftAssignment.objects.filter(device=device, is_active=True, is_completed=False).first()

    created = []
    raw_for_correction = []
    last_lat = None
    last_lng = None
    last_acc = None
    last_batt = None
    for p in points:
        recorded_at_str = p.get('recorded_at')
        if not recorded_at_str:
            continue
        try:
            recorded_at = datetime.fromisoformat(recorded_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            continue

        p_lat = p.get('lat')
        p_lng = p.get('lng')
        if p_lat is None or p_lng is None:
            continue

        trail = DeviceTrail.objects.create(
            device=device,
            assignment=active_assignment,
            lat=p_lat,
            lng=p_lng,
            accuracy=p.get('accuracy'),
            battery_pct=p.get('battery_pct'),
            speed=p.get('speed'),
            bearing=p.get('bearing'),
            recorded_at=recorded_at,
        )
        last_lat = trail.lat
        last_lng = trail.lng
        last_acc = trail.accuracy
        last_batt = trail.battery_pct

        created.append(trail.id)
        raw_for_correction.append({
            'lat': trail.lat,
            'lng': trail.lng,
            'accuracy': trail.accuracy or 50.0,
            'recorded_at': recorded_at,
        })

    if last_lat is not None:
        device.last_latitude = last_lat
        device.last_longitude = last_lng
        device.last_gps_accuracy = last_acc
        device.battery_pct = last_batt
        device.save(update_fields=['last_latitude', 'last_longitude', 'last_gps_accuracy', 'battery_pct'])

    # Run correction on the batch
    corrected = correct_gps_trail(raw_for_correction)

    # Mark corrected points in DB (simplified — update by position)
    for i, corr in enumerate(corrected):
        if corr.get('corrected') and i < len(created):
            DeviceTrail.objects.filter(id=created[i]).update(
                lat=corr['lat'], lng=corr['lng'], is_corrected=True
            )

    # Return corrected data to device for local storage update
    return Response({
        'synced': len(created),
        'corrected': [{
            'lat': c['lat'],
            'lng': c['lng'],
            'accuracy': c.get('accuracy'),
            'recorded_at': c['recorded_at'].isoformat() if hasattr(c['recorded_at'], 'isoformat') else c['recorded_at'],
            'corrected': c.get('corrected', False),
        } for c in corrected],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def scan_batch_sync(request):
    """Accept an array of NFC scans collected offline by the device.

    Expected body: { device_id, password, scans: [{ nfc_value, recorded_at, lat?, lng?, raw_nfc? }] }
    """
    from .serializers import ScanRecordSerializer
    from .scan_service import process_scan
    device_id = request.data.get('device_id')
    password = request.data.get('password')
    scans = request.data.get('scans', [])

    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)
    if not isinstance(scans, list) or not scans:
        return Response({'detail': 'scans array required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device or device.password != password:
        return Response({'detail': 'Auth failed'}, status=401)

    results = []
    for idx, s in enumerate(scans):
        nfc_value = s.get('nfc_value')
        recorded_at_str = s.get('recorded_at')
        if not nfc_value or not recorded_at_str:
            results.append({'_original_index': idx, 'status': 'skipped', 'reason': 'missing nfc_value or recorded_at'})
            continue
        try:
            recorded_at = datetime.fromisoformat(recorded_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            results.append({'_original_index': idx, 'status': 'skipped', 'reason': 'invalid recorded_at'})
            continue

        # Reuse existing process_scan logic
        try:
            server_now = timezone.now()
            scan_data = process_scan(
                device_id, password,
                route_id=s.get('route_id'),
                nfc_value=nfc_value,
                peer_key=s.get('verification_key') or s.get('peer_key'),
                now=server_now,
                raw_nfc=s.get('raw_nfc'),
                scan_lat=s.get('lat'),
                scan_lng=s.get('lng'),
                client_timestamp=recorded_at,
                sequence_id=s.get('sequence_id'),
            )
            # Pop response-only fields before creating the record
            tts_msg = scan_data.pop('_tts_message', None)
            tts_v = scan_data.pop('_tts_voice', 'en-US')
            tts_r = scan_data.pop('_tts_rate', 1.0)
            tts_p = scan_data.pop('_tts_pitch', 1.0)
            ps = scan_data.pop('_play_sound', True)
            vb = scan_data.pop('_vibrate', True)
            # Override timestamp to original capture time but keep real server receipt
            scan_data['server_received_timestamp'] = server_now
            record = ScanRecord.objects.create(
                **{k: v for k, v in scan_data.items() if k != 'guard_supervisor'},
                guard_supervisor=scan_data['guard_supervisor'],
                timestamp=recorded_at,
            )
            results.append({'_original_index': idx, 'status': 'created', 'id': record.id, 'checkpoint': record.checkpoint_name,
                            'tts_message': tts_msg, 'tts_voice': tts_v, 'tts_rate': tts_r, 'tts_pitch': tts_p,
                            'play_sound': ps, 'vibrate': vb})
        except Exception as e:
            results.append({'_original_index': idx, 'status': 'error', 'reason': str(e)})

    return Response({'synced': len([r for r in results if r['status'] == 'created']), 'results': results})


@api_view(['GET'])
def device_trails(request, device_id):
    """Return GPS trail for a device, optionally corrected.

    Query params:
      - assignment_id: filter by assignment
      - corrected: if 'true', return corrected positions
      - since: ISO datetime, only return points after this
    """
    from .scan_service import correct_gps_trail
    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)

    qs = DeviceTrail.objects.filter(device=device)

    assignment_id = request.GET.get('assignment_id')
    if assignment_id:
        qs = qs.filter(assignment_id=assignment_id)

    since = request.GET.get('since')
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            qs = qs.filter(recorded_at__gte=since_dt)
        except (ValueError, TypeError):
            pass

    qs = qs.order_by('recorded_at')

    points = list(qs.values('lat', 'lng', 'accuracy', 'recorded_at', 'battery_pct', 'speed', 'bearing', 'is_corrected'))

    if request.GET.get('corrected') == 'true' and len(points) > 1:
        raw = [{
            'lat': p['lat'],
            'lng': p['lng'],
            'accuracy': p['accuracy'] or 50.0,
            'recorded_at': p['recorded_at'],
        } for p in points]
        corrected = correct_gps_trail(raw)
        for i, c in enumerate(corrected):
            if i < len(points):
                points[i]['lat'] = c['lat']
                points[i]['lng'] = c['lng']
                points[i]['corrected'] = c.get('corrected', False)

    return Response({
        'device_id': device.device_id,
        'device_name': device.device_id or device.device_name,
        'point_count': len(points),
        'trail': points,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def device_recent_scans(request):
    """Return recent scans for a device, authenticated by device_id + password.

    Query params: device_id, password
    Used by the Android app dashboard (device has no JWT).
    """
    device_id = request.GET.get('device_id')
    password = request.GET.get('password')
    if not device_id or not password:
        return Response({'detail': 'device_id and password required'}, status=400)

    device = Device.objects.filter(device_id=device_id).first()
    if not device:
        return Response({'detail': 'Device not found'}, status=404)
    if device.password != password:
        return Response({'detail': 'Auth failed'}, status=401)

    scans = ScanRecord.objects.filter(device=device).order_by('-timestamp')[:10]
    data = []
    for s in scans:
        data.append({
            'id': s.id,
            'checkpoint_name': s.checkpoint_name,
            'timestamp': s.timestamp.isoformat(),
            'is_on_time': s.is_on_time,
            'route_name': s.route.name if s.route else None,
        })
    return Response({'results': data})


@api_view(['POST'])
@permission_classes([AllowAny])
def seed_attendance(request):
    """Generate realistic attendance data for testing the analytics/reports pages."""
    from datetime import date, timedelta

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




