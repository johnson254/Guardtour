import secrets

from django.contrib.auth import login as django_login
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import (
    Admin,
    CallSign,
    Device,
    Dispatcher,
    GuardSupervisor,
    Organization,
)
from api.serializers import UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    role = request.data.get('role', 'dispatcher')

    if User.objects.filter(username=username).exists():
        return Response({'error': 'Username exists'}, status=400)

    default_org = Organization.objects.first()
    if not default_org:
        return Response({'error': 'No organization exists. Contact an administrator to create one first.'}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)

    organization_id = None
    organization_name = None

    if role == 'admin' or user.is_superuser:
        role = 'admin'
        organization_id = [org.id for org in Organization.objects.all()]
        organization_name = "Global System"
    else:
        dispatcher = Dispatcher.objects.create(user=user, organization=default_org)
        role = 'dispatcher'
        organization_id = [dispatcher.organization.id]
        organization_name = dispatcher.organization.name

    refresh = RefreshToken.for_user(user)

    request.session['access_token'] = str(refresh.access_token)

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

    request.session['access_token'] = str(RefreshToken.for_user(user).access_token)

    default_org = Organization.objects.first()

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
        if not dispatcher_profile.organization:
            dispatcher_profile.organization = default_org
            dispatcher_profile.save(update_fields=['organization'])
        if dispatcher_profile.organization:
            organization_id = [dispatcher_profile.organization.id]
            organization_name = dispatcher_profile.organization.name
    elif hasattr(user, 'guardsupervisor'):
        guard_profile = user.guardsupervisor
        role = guard_profile.role
        if role == 'User Role':
            role = 'dispatcher'
        if guard_profile.organization:
            organization_id = [guard_profile.organization.id]
            organization_name = guard_profile.organization.name

    refresh = RefreshToken.for_user(user)
    request.session['access_token'] = str(refresh.access_token)
    django_login(request, user)

    return Response({
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'token': str(refresh.access_token),
        'user': UserSerializer(user).data,
        'role': role,
        'organization_id': organization_id,
        'organization_name': organization_name,
        'identity': _build_operator_identity(user),
    })


def _build_operator_identity(user):
    device_id = ''
    device_callsign = ''
    last_latitude = ''
    last_longitude = ''
    last_seen = ''
    guard_callsign = ''
    guard_shift = ''
    sim_phone_number = ''
    imei = ''
    imsi = ''

    if hasattr(user, 'guardsupervisor'):
        guard = user.guardsupervisor
        guard_callsign = guard.callsign or ''
        guard_shift = guard.shift or 'Day'
        cs = CallSign.objects.filter(current_guard=guard).select_related('device').first()
        if cs:
            device_callsign = cs.callsign or ''
            if cs.device:
                d = cs.device
                device_id = d.device_id or ''
                sim_phone_number = d.sim_phone_number or ''
                imei = d.imei or ''
                imsi = d.imsi or ''
                last_latitude = str(d.last_latitude) if d.last_latitude is not None else ''
                last_longitude = str(d.last_longitude) if d.last_longitude is not None else ''
                last_seen = d.last_seen.isoformat() if d.last_seen else ''
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher = user.dispatcher_profile
        cs = CallSign.objects.filter(organization=dispatcher.organization).select_related('device').order_by('-id').first()
        if cs:
            device_callsign = cs.callsign or ''
            if cs.device:
                d = cs.device
                device_id = d.device_id or ''
                sim_phone_number = d.sim_phone_number or ''
                imei = d.imei or ''
                imsi = d.imsi or ''
                last_latitude = str(d.last_latitude) if d.last_latitude is not None else ''
                last_longitude = str(d.last_longitude) if d.last_longitude is not None else ''
                last_seen = d.last_seen.isoformat() if d.last_seen else ''

    return {
        'device_id': device_id,
        'device_callsign': device_callsign,
        'last_latitude': last_latitude,
        'last_longitude': last_longitude,
        'last_seen': last_seen,
        'guard_callsign': guard_callsign,
        'guard_shift': guard_shift,
        'sim_phone_number': sim_phone_number,
        'imei': imei,
        'imsi': imsi,
    }
