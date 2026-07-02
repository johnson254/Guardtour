from __future__ import annotations

from typing import Optional

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from api.models.organization import Organization
from api.models.personnel import GuardSupervisor
from api.models.device import Device
from api.models.patrol import PatrolRoute
from api.models.scanning import ScanRecord


class ShiftAssignment(models.Model):
    dispatcher: User = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='dispatched_assignments',
        help_text="The Dispatcher or Admin who created this assignment"
    )
    guard_supervisor: Optional[GuardSupervisor] = models.ForeignKey(
        GuardSupervisor, on_delete=models.CASCADE, null=True, blank=True,
        related_name='shift_assignments'
    )
    device: Optional[Device] = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='current_assignments'
    )
    route: Optional[PatrolRoute] = models.ForeignKey(
        PatrolRoute, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='current_shifts'
    )
    scheduled_date: Optional[models.DateField] = models.DateField(null=True, blank=True,
        help_text="The date this mission is intended to occur")
    scheduled_start: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    scheduled_end: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    shift_type: str = models.CharField(max_length=10, choices=GuardSupervisor.SHIFT_CHOICES)
    is_active: bool = models.BooleanField(default=True)
    is_completed: bool = models.BooleanField(default=False,
        help_text="True when all checkpoints have been scanned")
    mission_stage: str = models.CharField(
        max_length=20,
        choices=[
            ('assigned', 'Assigned'), ('deployed', 'Deployed'), ('active', 'Active'),
            ('completing', 'Completing'), ('completed', 'Completed'), ('cancelled', 'Cancelled')
        ],
        default='assigned', blank=True,
        help_text="Lifecycle stage of the mission"
    )
    status: str = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'), ('completed', 'Completed'),
            ('emergency_active', 'Emergency Active'), ('cancelled', 'Cancelled'),
            ('handover', 'Handed Over')
        ],
        default='active', blank=True,
        help_text="Lifecycle status of the assignment"
    )
    assigned_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    ended_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)

    def clean(self) -> None:
        if self.guard_supervisor and self.scheduled_start and self.scheduled_end:
            overlapping = ShiftAssignment.objects.filter(
                guard_supervisor=self.guard_supervisor,
                status__in=['active', 'emergency_active', 'handover'],
                scheduled_start__lt=self.scheduled_end,
                scheduled_end__gt=self.scheduled_start,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    f"Guard {self.guard_supervisor} already has an active shift overlapping "
                    f"with {self.scheduled_start} - {self.scheduled_end}"
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.guard_supervisor:
            return f"{self.guard_supervisor.first_name} - {self.shift_type} shift"
        return f"Device Only - {self.shift_type} shift"

    @property
    def total_checkpoints(self) -> int:
        if self.route:
            return self.route.checkpoints.count()
        return 0

    @property
    def completed_checkpoints(self) -> int:
        if self.route and self.guard_supervisor:
            hit_count = ScanRecord.objects.filter(
                guard_supervisor=self.guard_supervisor,
                route=self.route,
                timestamp__gte=self.assigned_at
            ).values('checkpoint').distinct().count()
            return hit_count
        return 0


class MissionStateLog(models.Model):
    assignment: ShiftAssignment = models.ForeignKey(
        ShiftAssignment, on_delete=models.CASCADE, related_name='state_logs'
    )
    from_stage: str = models.CharField(max_length=20, blank=True, default='')
    to_stage: str = models.CharField(max_length=20)
    reason: str = models.CharField(max_length=200, blank=True, default='')
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    device: Optional[Device] = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, blank=True
    )
    scan: Optional[ScanRecord] = models.ForeignKey(
        ScanRecord, on_delete=models.SET_NULL, null=True, blank=True
    )
    metadata_json: Optional[dict] = models.JSONField(null=True, blank=True, default=dict)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['assignment', 'created_at'])]

    def __str__(self) -> str:
        return f"Assignment {self.assignment_id}: {self.from_stage} -> {self.to_stage}"


# Signal: update GuardSupervisor.is_on_shift when ShiftAssignment changes
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=ShiftAssignment)
def update_guard_shift_status(sender: object, instance: ShiftAssignment, created: bool, **kwargs: object) -> None:
    if not instance.guard_supervisor:
        return
    g = instance.guard_supervisor
    if instance.is_active:
        g.is_on_shift = True
        g.last_shift_change = instance.assigned_at
        g.save(update_fields=['is_on_shift', 'last_shift_change'])
    elif not instance.is_active:
        has_other_active = ShiftAssignment.objects.filter(
            guard_supervisor=g, is_active=True
        ).exclude(pk=instance.pk).exists()
        if not has_other_active:
            g.is_on_shift = False
            g.save(update_fields=['is_on_shift'])
