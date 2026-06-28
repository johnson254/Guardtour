from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import GuardSupervisor, Organization


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_scan_guard(request):
    # NOTE: manage.html posts to this endpoint as the authenticated dispatcher/admin.
    # If org context is missing, return a clear validation error instead of 500.

    """Scan-only Guard/Supervisor creator.

    Creates a GuardSupervisor record with user=None (no Django auth user created).
    """
    user = request.user

    payload = request.data or {}

    # Default to 'guard' but allow 'supervisor' if provided
    role = payload.get('role', 'guard')

    first_name = payload.get('first_name', '')
    last_name = payload.get('last_name', '')
    shift = payload.get('shift', 'Day')
    organization_id = payload.get('organization')

    # Determine org scope
    org = None
    if user.is_superuser:
        if organization_id:
            org = Organization.objects.filter(id=organization_id).first()
        if not org:
            org = Organization.objects.first()
    else:
        # Dispatcher/org-scoped creation
        if hasattr(user, 'dispatcher_profile'):
            org = user.dispatcher_profile.organization
        elif hasattr(user, 'admin_profile'):
            # Admin_profile isn't used in your current admin create flow for this endpoint,
            # but allow fallback to first org if provided.
            org = Organization.objects.first()

    if not org:
        raise PermissionDenied('Organization context missing.')

    obj = GuardSupervisor.objects.create(
        user=None,
        first_name=first_name or '',
        last_name=last_name or '',
        callsign=None, # Callsign is now assigned via hardware linking
        organization=org,
        role=role,
        shift=shift,
        nfc_tags_scanned=0,
        is_on_shift=False,
        last_scan=None,
    )

    return Response({
        'id': obj.id,
        'first_name': obj.first_name,
        'last_name': obj.last_name,
        'callsign': obj.callsign,
        'organization': obj.organization.id if obj.organization else None,
        'role': obj.role,
        'shift': obj.shift,
        'created_at': obj.created_at,
    }, status=201)
