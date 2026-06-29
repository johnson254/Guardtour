"""Organization context resolution for multi-tenant access control.

WHY THIS EXISTS:
Before this module, 12+ locations across views.py had the same anti-pattern:
    if not user.organization:
        user.organization = Organization.objects.first()  # DANGEROUS
        user.save()

This silently assigned users to whatever org happened to be first in the DB.
In a multi-tenant system this is a DATA LEAK — dispatchers could see another
org's guards, devices, and routes if their org field was ever null.

This module centralizes org resolution and makes the failure mode explicit:
- get_user_organization() raises PermissionDenied instead of auto-assigning
- get_user_organization_or_none() returns None for optional contexts
- user_can_access_organization() is the guard for resource-level checks
"""
from rest_framework.exceptions import PermissionDenied


def get_user_organization(user):
    """Resolve the organization context for a user.

    Returns the Organization instance or None if the user is a superuser/admin
    without a specific org binding.

    Raises PermissionDenied if a non-privileged user has no organization
    context — this prevents silent auto-assignment to Organization.objects.first()
    which is a multi-tenant data isolation risk.
    """
    if user.is_superuser:
        return None

    if hasattr(user, 'admin_profile'):
        return None

    if hasattr(user, 'dispatcher_profile'):
        dispatcher = user.dispatcher_profile
        if not dispatcher.organization:
            raise PermissionDenied(
                "Dispatcher account is not assigned to an organization. "
                "Contact an administrator."
            )
        return dispatcher.organization

    if hasattr(user, 'guardsupervisor'):
        guard = user.guardsupervisor
        if not guard.organization:
            raise PermissionDenied(
                "Guard account is not assigned to an organization. "
                "Contact a dispatcher."
            )
        return guard.organization

    raise PermissionDenied(
        "User profile is not configured. Contact an administrator."
    )


def get_user_organization_or_none(user):
    """Like get_user_organization but returns None instead of raising."""
    try:
        return get_user_organization(user)
    except PermissionDenied:
        return None


def user_can_access_organization(user, organization_id):
    """Check if user can access resources for a given organization."""
    if user.is_superuser:
        return True

    if hasattr(user, 'admin_profile'):
        return True

    user_org = get_user_organization_or_none(user)
    if user_org is None:
        return False
    return user_org.id == organization_id
