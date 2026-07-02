from __future__ import annotations

import re
from typing import Optional

from django.db import models
from django.contrib.auth.models import User


class Organization(models.Model):
    name: str = models.CharField(max_length=200)
    code: Optional[str] = models.CharField(max_length=8, unique=True, null=True, blank=True,
        help_text="Short uppercase org code used as operator-ID prefix (e.g. TCN)")
    contact_email: str = models.EmailField(blank=True)
    phone: str = models.CharField(max_length=20, blank=True)
    address: str = models.TextField(blank=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    default_time_tolerance: int = models.IntegerField(default=15, help_text="Default minutes allowed for scheduled scans")
    is_active: bool = models.BooleanField(default=True)
    shift_mode: str = models.CharField(
        max_length=20,
        choices=[('simple', 'Simple (no shift tracking)'), ('structured', 'Structured (Day/Night/Flex)')],
        default='simple',
        help_text="Controls whether shift-based logic (Day/Night/Flex) is enforced"
    )
    is_archived: bool = models.BooleanField(default=False, help_text="If True, organization is soft-deleted and hidden from queries")
    archived_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    area_of_interest: Optional[dict] = models.JSONField(null=True, blank=True,
        help_text="Polygon defining the operational area. Format: [[lat,lng],...].")
    operational_note: str = models.TextField(blank=True, help_text="Notes about this operational zone")

    class Meta:
        indexes = [models.Index(fields=['is_archived'])]

    @staticmethod
    def _derive_code(name: str) -> str:
        words = [w for w in re.split(r'[\s\-_&]+', name or '') if w]
        if not words:
            return 'ORG'
        code = ''.join(w[0] for w in words).upper()
        if len(code) == 1 and words and len(words[0]) >= 3:
            code = words[0][:3].upper()
        code = re.sub(r'[^A-Z0-9]', '', code)
        return (code[:4] or 'ORG')

    def propose_code(self) -> str:
        base = self._derive_code(self.name)
        candidate = base
        n = 1
        qs = Organization.objects.exclude(pk=self.pk)
        while qs.filter(code__iexact=candidate).exists():
            candidate = f"{base[:7]}{n}"
            n += 1
        return candidate

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.code:
            self.code = self.propose_code()
        else:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Admin(models.Model):
    user: User = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    organizations: models.ManyToManyField = models.ManyToManyField(Organization, related_name='admins')
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        count = self.organizations.count()
        return f"{self.user.username} (Admin - Managing {count} Orgs)"
