from __future__ import annotations

from typing import Optional

from django.db import models
from django.contrib.auth.models import User

from api.models.organization import Organization


class Dispatcher(models.Model):
    user: User = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dispatcher_profile')
    organization: Optional[Organization] = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='dispatchers', null=True, blank=True
    )
    can_manage_routes: bool = models.BooleanField(default=True)
    can_manage_guards: bool = models.BooleanField(default=True)
    can_view_reports: bool = models.BooleanField(default=True)
    can_manage_devices: bool = models.BooleanField(default=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        if self.organization:
            return f"{self.user.username} (Dispatcher - {self.organization.name})"
        return f"{self.user.username} (Dispatcher - No Org)"


class GuardSupervisor(models.Model):
    SHIFT_CHOICES: list[tuple[str, str]] = [
        ('Day', 'Day'),
        ('Night', 'Night'),
        ('Flex', 'Flex'),
    ]

    user: Optional[User] = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='guardsupervisor', null=True, blank=True
    )
    first_name: str = models.CharField(max_length=100, blank=True)
    last_name: str = models.CharField(max_length=100, blank=True)
    callsign: Optional[str] = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="User-facing identifier (e.g. H-01@twocan). Typed at login."
    )
    organization: Optional[Organization] = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='guards_supervisors', null=True, blank=True
    )
    role: str = models.CharField(max_length=20, choices=[
        ('guard', 'Guard'), ('supervisor', 'Supervisor')
    ], default='guard')
    shift: str = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='Day')
    nfc_tags_scanned: int = models.IntegerField(default=0)
    last_scan: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    is_on_shift: bool = models.BooleanField(default=False)
    last_shift_change: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip() or "Unnamed"
        if self.organization:
            return f"{full_name} ({self.role}) - {self.organization.name}"
        return f"{full_name} ({self.role}) - No Org"
