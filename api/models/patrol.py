from __future__ import annotations

from typing import Optional

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from api.models.organization import Organization
from api.models.personnel import GuardSupervisor
from api.models.device import Device


class PatrolRoute(models.Model):
    STATUS_CHOICES: list[tuple[str, str]] = [
        ('draft', 'Draft/Staging'),
        ('scheduled', 'Scheduled/Upcoming'),
        ('active', 'Active/Daily'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    FREQUENCY_CHOICES: list[tuple[str, str]] = [
        ('once', 'One-Time'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('adhoc', 'Ad-Hoc/Flexible'),
    ]

    organization: Optional[Organization] = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='routes', null=True, blank=True
    )
    name: str = models.CharField(max_length=200)
    description: str = models.TextField(blank=True)
    status: str = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', blank=True)
    frequency: str = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='once', blank=True)
    scheduled_date: Optional[models.DateField] = models.DateField(null=True, blank=True)
    enforce_order: bool = models.BooleanField(default=False)
    enforce_time: bool = models.BooleanField(default=False)
    is_geofence: bool = models.BooleanField(default=False,
        help_text="If true, patrol relies on GPS perimeters")
    is_emergency: bool = models.BooleanField(default=False)
    is_audit: bool = models.BooleanField(default=False,
        help_text="If true, guards scan other devices (Peer-to-Peer)")
    is_daily: bool = models.BooleanField(default=False,
        help_text="If true, this route resets and alerts daily")
    scheduled_start_time: Optional[models.TimeField] = models.TimeField(null=True, blank=True,
        help_text="Time to alert operator to start")
    send_start_alert: bool = models.BooleanField(default=False)
    send_announcement: bool = models.BooleanField(default=False,
        help_text="If true, the readout_text will be broadcasted.")
    start_alert_lead_time: int = models.IntegerField(default=15,
        help_text="Minutes before start to send alert")
    readout_text: str = models.TextField(blank=True,
        help_text="Instructional text for POC radio TTS")
    tts_voice: str = models.CharField(max_length=50, blank=True, default='',
        help_text="TTS voice locale (e.g. en-US, en-GB-Standard-A)")
    tts_rate: float = models.FloatField(default=1.0, help_text="TTS speech rate 0.5-2.0")
    tts_pitch: float = models.FloatField(default=1.0, help_text="TTS speech pitch 0.5-2.0")
    assigned_guards: models.ManyToManyField = models.ManyToManyField(
        GuardSupervisor, blank=True, related_name='assigned_blueprints'
    )
    assigned_devices: models.ManyToManyField = models.ManyToManyField(
        Device, blank=True, related_name='assigned_blueprints'
    )
    created_by: Optional[User] = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_routes'
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    is_archived: bool = models.BooleanField(default=False,
        help_text="If True, route is soft-deleted and hidden from queries")
    archived_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['is_archived'])]

    @property
    def logic_type(self) -> str:
        if self.is_audit:
            return "Audit"
        if self.is_emergency:
            return "Emergency"
        if self.enforce_order and self.enforce_time:
            return "Scheduled"
        if self.enforce_order:
            return "Sequential"
        if self.enforce_time:
            return "Flexible"
        return "Flexible"

    def delete(self, *args: object, **kwargs: object) -> None:
        from django.utils import timezone as dj_timezone
        active_shifts = self.current_shifts.filter(is_active=True).exists()
        if active_shifts:
            self.is_archived = True
            self.archived_at = dj_timezone.now()
            self.save(update_fields=['is_archived', 'archived_at'])
            return
        super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Checkpoint(models.Model):
    CHECKPOINT_TYPES: list[tuple[str, str]] = [
        ('nfc', 'NFC'),
        ('gps', 'GPS'),
        ('peer', 'Peer'),
        ('custom', 'Custom'),
        ('geo', 'Geofence'),
    ]

    organization: Optional[Organization] = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='global_checkpoints', null=True, blank=True
    )
    route: Optional[PatrolRoute] = models.ForeignKey(
        PatrolRoute, on_delete=models.CASCADE, related_name='checkpoints', null=True, blank=True
    )
    name: str = models.CharField(max_length=200)
    checkpoint_type: str = models.CharField(max_length=10, choices=CHECKPOINT_TYPES, default='nfc')
    nfc_tag: Optional[str] = models.CharField(max_length=100, blank=True, null=True)
    lat: Optional[float] = models.FloatField(null=True, blank=True)
    lng: Optional[float] = models.FloatField(null=True, blank=True)
    order: int = models.IntegerField(default=0)
    planned_time: Optional[models.TimeField] = models.TimeField(null=True, blank=True)
    time_tolerance: int = models.IntegerField(default=15, blank=True)
    dwell_time: int = models.IntegerField(default=0, blank=True,
        help_text="Minutes expected to stay at checkpoint")
    radius: int = models.IntegerField(default=5, blank=True,
        help_text="Acceptable GPS radius in meters")
    precision_level: str = models.CharField(
        max_length=10,
        choices=[('strict', 'Strict'), ('normal', 'Normal'), ('loose', 'Loose')],
        default='normal', blank=True,
        help_text="Context-aware radius multiplier: strict=0.5x, normal=1x, loose=2x"
    )
    next_announcement_text: Optional[str] = models.TextField(blank=True, null=True,
        help_text="Per-checkpoint TTS announcement text")
    scheduled_date: Optional[models.DateField] = models.DateField(null=True, blank=True,
        help_text="Date this checkpoint is scheduled for. Null = unscheduled/always active.")

    class Meta:
        ordering = ['scheduled_date', 'order']

    def clean(self) -> None:
        if self.checkpoint_type == 'nfc' and not self.nfc_tag:
            raise ValidationError({'nfc_tag': 'NFC tag required for NFC checkpoints.'})
        if self.checkpoint_type == 'gps' and (self.lat is None or self.lng is None):
            raise ValidationError({'lat': 'GPS coordinates required for GPS checkpoints.'})
        if self.checkpoint_type == 'nfc':
            self.lat = None
            self.lng = None
        if self.checkpoint_type == 'gps':
            self.nfc_tag = None
        if self.checkpoint_type == 'peer':
            self.nfc_tag = None
            self.lat = None
            self.lng = None
        if self.checkpoint_type == 'custom':
            self.nfc_tag = None
        if self.checkpoint_type == 'geo':
            self.nfc_tag = None

        if self.planned_time and self.route_id:
            dupes = Checkpoint.objects.filter(
                route_id=self.route_id, planned_time=self.planned_time,
                scheduled_date=self.scheduled_date
            )
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError(
                    f'Another checkpoint in this route already has planned time '
                    f'{self.planned_time} on {self.scheduled_date}.'
                )

        if self.route_id and self.order is not None:
            dupes = Checkpoint.objects.filter(
                route_id=self.route_id, order=self.order,
                scheduled_date=self.scheduled_date
            )
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError(
                    f'Duplicate order {self.order} for this route on {self.scheduled_date}.'
                )

        if self.organization_id and self.route_id:
            route_org = self.route.organization_id
            if route_org and self.organization_id != route_org:
                raise ValidationError(
                    f'Checkpoint organization must match route organization.'
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name
