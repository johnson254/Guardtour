from __future__ import annotations

from django.db import models

from api.models.organization import Organization
from api.models.device import DeviceSession


class AlertRule(models.Model):
    organization: Organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='alert_rules'
    )
    session_state: str = models.CharField(max_length=20, choices=DeviceSession.STATE_CHOICES)
    first_alert_minutes: int = models.IntegerField(default=15)
    repeat_minutes: int = models.IntegerField(default=15)
    is_active: bool = models.BooleanField(default=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('organization', 'session_state')]
        ordering = ['session_state']

    def __str__(self) -> str:
        return f"{self.organization.name} / {self.session_state}: {self.first_alert_minutes}min + {self.repeat_minutes}min repeat"
