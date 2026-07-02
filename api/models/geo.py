from __future__ import annotations

from typing import Optional

from django.db import models

from api.models.organization import Organization
from api.models.personnel import GuardSupervisor


class MapObject(models.Model):
    TYPES: list[tuple[str, str]] = [('poi', 'POI'), ('geofence', 'Geofence')]

    organization: Organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='map_objects'
    )
    name: str = models.CharField(max_length=200)
    type: str = models.CharField(max_length=20, choices=TYPES)
    geometry: Optional[dict] = models.JSONField(null=True, blank=True,
        help_text="Coordinate list for markers or polygons")
    radius: Optional[int] = models.IntegerField(null=True, blank=True,
        help_text="Radius for POI/Circle objects")
    assigned_personnel: models.ManyToManyField = models.ManyToManyField(
        GuardSupervisor, blank=True, related_name='assigned_map_objects'
    )
    entry_msg: Optional[str] = models.CharField(max_length=500, blank=True, null=True)
    exit_msg: Optional[str] = models.CharField(max_length=500, blank=True, null=True)
    geo_shape: Optional[str] = models.CharField(max_length=50, blank=True, null=True)
    intrusion_alarm: bool = models.BooleanField(default=False)
    fetch_location_on_scan: bool = models.BooleanField(default=False,
        help_text="Auto-fetch GPS location on first NFC scan")
    planned_duration_minutes: Optional[int] = models.IntegerField(default=5, null=True, blank=True,
        help_text="Countdown duration in minutes for NFC scan window")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"
