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
