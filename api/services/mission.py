from django.utils import timezone
from rest_framework.exceptions import ValidationError


VALID_MISSION_STAGE_TRANSITIONS = {
    'assigned': {'deployed', 'cancelled'},
    'deployed': {'active', 'cancelled', 'completing'},
    'active': {'completing', 'cancelled', 'emergency_pause'},
    'completing': {'completed', 'cancelled'},
    'completed': set(),
    'cancelled': set(),
    'emergency_pause': {'active', 'cancelled'},
}

VALID_STATUS_TRANSITIONS = {
    'active': {'completed', 'emergency_active', 'cancelled', 'handover'},
    'emergency_active': {'active', 'cancelled', 'handover'},
    'handover': {'active', 'completed', 'cancelled'},
    'completed': set(),
    'cancelled': set(),
}


def transition_mission_stage(assignment, new_stage, reason='', device=None, scan=None):
    """Transition a mission through its lifecycle stages.

    Enforces valid stage transitions and creates a MissionStateLog entry.
    This is the single source of truth for mission stage changes — all
    code that changes mission_stage should go through this function.

    Args:
        assignment: ShiftAssignment instance
        new_stage: target stage string
        reason: human-readable reason for the transition
        device: optional Device that triggered the transition
        scan: optional ScanRecord that triggered the transition

    Returns:
        The created MissionStateLog instance

    Raises:
        ValidationError: if the transition is not allowed
    """
    from api.models import MissionStateLog

    current = assignment.mission_stage
    allowed = VALID_MISSION_STAGE_TRANSITIONS.get(current, set())

    if new_stage not in allowed:
        raise ValidationError(
            f"Invalid mission stage transition: {current} -> {new_stage}. "
            f"Allowed: {allowed}"
        )

    log = MissionStateLog.objects.create(
        assignment=assignment,
        from_stage=current,
        to_stage=new_stage,
        reason=reason,
        device=device,
        scan=scan,
    )

    assignment.mission_stage = new_stage
    assignment.save(update_fields=['mission_stage'])

    return log


def transition_mission_status(assignment, new_status, reason='', device=None, scan=None):
    """Transition a mission's status.

    Enforces valid status transitions and creates a MissionStateLog entry.

    Args:
        assignment: ShiftAssignment instance
        new_status: target status string
        reason: human-readable reason
        device: optional Device
        scan: optional ScanRecord

    Returns:
        The created MissionStateLog instance
    """
    from api.models import MissionStateLog

    current = assignment.status
    allowed = VALID_STATUS_TRANSITIONS.get(current, set())

    if new_status not in allowed:
        raise ValidationError(
            f"Invalid mission status transition: {current} -> {new_status}. "
            f"Allowed: {allowed}"
        )

    log = MissionStateLog.objects.create(
        assignment=assignment,
        from_stage=current,
        to_stage=new_status,
        reason=reason,
        device=device,
        scan=scan,
    )

    assignment.status = new_status
    assignment.save(update_fields=['status'])

    return log


def complete_mission(assignment, device=None, scan=None):
    """Mark a mission as fully completed.

    Sets both stage and status to completed, deactivates the assignment,
    and creates the final state log.
    """
    from api.models import MissionStateLog

    now = timezone.now()

    log = MissionStateLog.objects.create(
        assignment=assignment,
        from_stage=assignment.mission_stage,
        to_stage='completed',
        reason='all_checkpoints_scanned',
        device=device,
        scan=scan,
    )

    assignment.mission_stage = 'completed'
    assignment.status = 'completed'
    assignment.is_completed = True
    assignment.is_active = False
    assignment.ended_at = now
    assignment.save(update_fields=[
        'mission_stage', 'status', 'is_completed', 'is_active', 'ended_at'
    ])

    return log


def get_mission_timeline(assignment):
    """Get the full state transition history for a mission."""
    from api.models import MissionStateLog
    return list(
        MissionStateLog.objects.filter(assignment=assignment)
        .select_related('device', 'scan')
        .order_by('created_at')
    )
