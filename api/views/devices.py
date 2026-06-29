import secrets

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status

from api.models import (
    CallSign,
    Device,
    DeviceProvisioning,
    GuardSupervisor,
    Organization,
    ShiftAssignment,
)
from api.serializers import DeviceSerializer
from api.views.auth import generate_operator_id


@api_view(['POST'])
@permission_classes([AllowAny])
def register_device(request):
    operator_id = request.data.get('operator_id')
    hardware_info = request.data.get('hardware_info', {})

    if not operator_id:
        return Response({'detail': 'Operator ID required'}, status=400)

    device = Device.objects.filter(device_id=operator_id).first()
    if not device:
        # Auto-create device from callsign for demo/self-service onboarding
        # Looks up CallSign by callsign to find org, or uses first org
        from api.models import CallSign, Organization
        cs = CallSign.objects.filter(callsign=operator_id).first()
        org = cs.organization if cs else Organization.objects.first()
        device = Device.objects.create(
            device_id=operator_id,
            device_name=f"Device-{operator_id}",
            organization=org,
            callsign=operator_id,
        )
        if cs:
            cs.device = device
            cs.save()

    for field in ['imei', 'imsi', 'sim_phone_number', 'os_version', 'manufacturer', 'model', 'sdk_int']:
        if field in hardware_info:
            setattr(device, field, hardware_info[field])

    if not device.password:
        device.password = str(secrets.randbelow(90000000) + 10000000)

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
@permission_classes([IsAuthenticated])
def provision_device(request):
    device_id = request.data.get('device_id')
    guard_id = request.data.get('guard_id')
    scheduled_start = request.data.get('scheduled_start')
    scheduled_end = request.data.get('scheduled_end')

    if not device_id:
        return Response({'detail': 'device_id required'}, status=400)

    guard = get_object_or_404(GuardSupervisor, id=guard_id)
    org = guard.organization

    with transaction.atomic():
        device, created = Device.objects.get_or_create(
            device_id=device_id,
            defaults={'device_name': f"Device-{device_id[-4:]}", 'organization': org}
        )

        if created and not device.callsign and org:
            device.callsign = guard.callsign if guard.callsign else generate_operator_id(org)
            device.save()

        cs, _ = CallSign.objects.get_or_create(device=device, organization=org)
        cs.callsign = device.callsign
        cs.current_guard = guard
        cs.active_shift = guard.shift
        cs.save()

        if device.callsign:
            guard.callsign = device.callsign
            guard.save(update_fields=['callsign'])

        device.is_online = True
        device.last_seen = timezone.now()
        device.save()

        DeviceProvisioning.objects.update_or_create(
            device=device,
            guard=guard,
            defaults={
                'callsign_snapshot': device.callsign,
                'organization': org,
            }
        )

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
