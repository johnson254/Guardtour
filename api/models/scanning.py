from __future__ import annotations

from typing import Optional

from django.db import models as models
from django.db.models import Q

from api.models.organization import Organization
from api.models.personnel import GuardSupervisor
from api.models.patrol import PatrolRoute, Checkpoint
from api.models.device import Device


class ScanRecord(models.Model):
    guard_supervisor: Optional[GuardSupervisor] = models.ForeignKey(
        GuardSupervisor, on_delete=models.SET_NULL, related_name='scans', null=True, blank=True
    )
    device: Optional[Device] = models.ForeignKey(
        Device, on_delete=models.SET_NULL, null=True, related_name='scans'
    )
    route: Optional[PatrolRoute] = models.ForeignKey(
        PatrolRoute, on_delete=models.SET_NULL, related_name='scans', null=True, blank=True
    )
    checkpoint: Optional[Checkpoint] = models.ForeignKey(
        Checkpoint, on_delete=models.SET_NULL, related_name='scans', null=True, blank=True
    )
    checkpoint_name: str = models.CharField(max_length=200)
    nfc_value: Optional[str] = models.CharField(max_length=200, blank=True, null=True)
    is_on_time: bool = models.BooleanField(default=True)
    lat: Optional[float] = models.FloatField(null=True, blank=True)
    lng: Optional[float] = models.FloatField(null=True, blank=True)
    timestamp: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    client_timestamp: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True,
        help_text="Original timestamp reported by the client device")
    server_received_timestamp: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True,
        help_text="Server wall-clock time when the scan was received")
    sequence_id: Optional[int] = models.IntegerField(null=True, blank=True,
        help_text="Monotonic counter from the client for offline scan ordering")
    time_drift_seconds: Optional[int] = models.IntegerField(null=True, blank=True,
        help_text="Seconds between client_timestamp and server_received_timestamp. Positive = client behind.")
    raw_nfc: Optional[dict] = models.JSONField(null=True, blank=True,
        help_text="Full NFC payload from device (UID, NDEF, tech, sensors)")
    scan_type: Optional[str] = models.CharField(max_length=20, null=True, blank=True,
        help_text="Server-determined: 'tag' or 'peer'")
    validity_score: Optional[float] = models.FloatField(null=True, blank=True,
        help_text="0.0-1.0 probability that this scan is legitimate")
    validity_reason: Optional[str] = models.CharField(max_length=300, null=True, blank=True,
        help_text="Human-readable explanation of the score")
    verification_notes: Optional[str] = models.TextField(null=True, blank=True,
        help_text="Machine-readable verification notes (pipe-separated tags)")
    dwell_valid: bool = models.BooleanField(default=False,
        help_text="True if dwell trail met checkpoint.dwell_time requirement")
    anomaly_flags: Optional[list] = models.JSONField(null=True, blank=True, default=list,
        help_text="List of anomaly codes detected during dwell trail walk")
    sensor_aided: bool = models.BooleanField(default=False,
        help_text="True if sensor context upgraded a weak NFC score")
    time_drift_suspicious: bool = models.BooleanField(default=False,
        help_text="True if client timestamp drift exceeded threshold")
    sensor_context: Optional[dict] = models.JSONField(null=True, blank=True,
        help_text="Sensor context from device (pir, accel, proximity, gps_trail)")
    out_of_sequence: bool = models.BooleanField(default=False,
        help_text="True if scanned in wrong order per route sequence")
    insufficient_dwell_time: bool = models.BooleanField(default=False,
        help_text="True if guard left before dwell_time elapsed")
    dwell_seconds: Optional[int] = models.IntegerField(null=True, blank=True,
        help_text="Actual seconds spent at checkpoint before this scan")

    def __str__(self) -> str:
        name = f"{self.guard_supervisor.first_name}" if self.guard_supervisor else 'Unknown'
        return f"{name} scanned {self.checkpoint_name}"


class OperatorAlert(models.Model):
    organization: Organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    operator: Optional[GuardSupervisor] = models.ForeignKey(
        GuardSupervisor, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts'
    )
    title: str = models.CharField(max_length=200)
    message: str = models.TextField()
    priority: str = models.CharField(
        max_length=20,
        choices=[('low', 'Low'), ('normal', 'Normal'), ('urgent', 'Urgent')],
        default='normal'
    )
    play_sound: bool = models.BooleanField(default=True, help_text="Play notification sound on device")
    vibrate: bool = models.BooleanField(default=True, help_text="Vibrate device on alert")
    tts_voice: str = models.CharField(max_length=50, blank=True, default='',
        help_text="TTS voice locale override")
    tts_rate: float = models.FloatField(default=1.0, help_text="TTS speech rate override 0.5-2.0")
    tts_pitch: float = models.FloatField(default=1.0, help_text="TTS speech pitch override 0.5-2.0")
    is_read: bool = models.BooleanField(default=False)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        name = self.operator.first_name if self.operator else "Unknown"
        return f"Alert to {name}: {self.title}"

    @property
    def device_info(self) -> Optional[str]:
        guard = self.operator
        if not guard:
            return None
        cs = guard.current_callsign_assignment.first() if hasattr(guard, 'current_callsign_assignment') else None
        if cs and cs.device:
            return cs.device.device_id
        return None


class IncidentReport(models.Model):
    organization: Organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='incidents'
    )
    guard_supervisor: GuardSupervisor = models.ForeignKey(
        GuardSupervisor, on_delete=models.CASCADE, related_name='reported_incidents'
    )
    category: str = models.CharField(
        max_length=50,
        choices=[('security', 'Security Breach'), ('maintenance', 'Maintenance'), ('safety', 'Safety Hazard')]
    )
    title: str = models.CharField(max_length=200)
    description: str = models.TextField()
    is_resolved: bool = models.BooleanField(default=False)
    lat: Optional[float] = models.FloatField(null=True, blank=True)
    lng: Optional[float] = models.FloatField(null=True, blank=True)
    timestamp: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.category.upper()}: {self.title}"
