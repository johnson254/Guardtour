from __future__ import annotations

from typing import Optional

from django.db import models

from api.models.organization import Organization
from api.models.personnel import GuardSupervisor


class Device(models.Model):
    device_id: Optional[str] = models.CharField(max_length=200, unique=True, null=True, blank=True)
    device_name: Optional[str] = models.CharField(max_length=200, null=True, blank=True)
    callsign: Optional[str] = models.CharField(max_length=100, null=True, blank=True,
        help_text="System-generated hardware callsign")
    is_active: bool = models.BooleanField(default=True,
        help_text="If False, device is decommissioned and all auth requests are rejected")
    is_online: bool = models.BooleanField(default=False)
    last_seen: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    registered_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    last_sequence_id: int = models.IntegerField(default=0,
        help_text="Last processed monotonic sequence ID from this device for offline scan ordering")
    peer_session_key: Optional[str] = models.CharField(max_length=100, null=True, blank=True,
        help_text="Rolling key for server-side scan verification")
    password: Optional[str] = models.CharField(max_length=128, null=True, blank=True,
        help_text="Device auth password, generated on registration")
    nfc_fetch_requested: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    gps_fetch_requested: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    gps_accuracy_threshold: Optional[int] = models.IntegerField(default=10, null=True, blank=True,
        help_text="Required GPS accuracy in meters for a valid fetch")
    last_nfc_scan: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    last_nfc_scan_uid: Optional[str] = models.CharField(max_length=100, null=True, blank=True)
    last_latitude: Optional[float] = models.FloatField(null=True, blank=True)
    last_longitude: Optional[float] = models.FloatField(null=True, blank=True)
    last_gps_accuracy: Optional[float] = models.FloatField(null=True, blank=True,
        help_text="Accuracy of the last GPS fix in meters")
    battery_pct: Optional[int] = models.SmallIntegerField(null=True, blank=True,
        help_text="Device battery percentage 0-100")
    imei: Optional[str] = models.CharField(max_length=50, null=True, blank=True,
        help_text="IMEI number of the device")
    imsi: Optional[str] = models.CharField(max_length=50, null=True, blank=True,
        help_text="IMSI of the SIM card")
    sim_phone_number: Optional[str] = models.CharField(max_length=30, null=True, blank=True,
        help_text="SIM card phone number (MSISDN)")
    os_version: Optional[str] = models.CharField(max_length=100, null=True, blank=True,
        help_text="OS version (e.g. Android 14)")
    manufacturer: Optional[str] = models.CharField(max_length=100, null=True, blank=True,
        help_text="Device manufacturer (e.g. Samsung)")
    model: Optional[str] = models.CharField(max_length=100, null=True, blank=True,
        help_text="Device model (e.g. Galaxy S24)")
    sdk_int: Optional[int] = models.IntegerField(null=True, blank=True,
        help_text="Android API level (Build.VERSION.SDK_INT)")
    nfc_mode: str = models.CharField(max_length=20, blank=True, default='auto',
        help_text="Server-assigned NFC mode: 'hce_emulator', 'hce_reader', 'tag_reader', 'auto'")
    organization: Optional[Organization] = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='devices', null=True, blank=True
    )
    tts_voice: str = models.CharField(max_length=50, blank=True, default='en-US',
        help_text="Default TTS voice locale for this device")
    tts_rate: float = models.FloatField(default=1.0, help_text="Default TTS speech rate 0.5-2.0")
    tts_pitch: float = models.FloatField(default=1.0, help_text="Default TTS speech pitch 0.5-2.0")
    tts_pending: Optional[str] = models.TextField(null=True, blank=True,
        help_text="Pending TTS message to deliver on next heartbeat")
    tts_pending_voice: str = models.CharField(max_length=50, blank=True, default='',
        help_text="Voice override for pending TTS")
    tts_pending_rate: float = models.FloatField(default=1.0, help_text="Rate override for pending TTS")
    tts_pending_pitch: float = models.FloatField(default=1.0, help_text="Pitch override for pending TTS")
    tts_pending_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True,
        help_text="When the pending TTS was queued")
    tts_acked: bool = models.BooleanField(default=True,
        help_text="True when device confirmed receipt of last tts_pending. If False, resend on next heartbeat.")
    last_reminder_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True,
        help_text="When the last lead-time reminder TTS was spoken")
    geofence_states: Optional[dict] = models.JSONField(null=True, blank=True, default=dict,
        help_text="Tracks entered geofence IDs to avoid duplicate TTS: {map_object_id: entered_at_iso}")

    def __str__(self) -> str:
        return self.device_id or self.device_name or ''


class CallSign(models.Model):
    callsign: str = models.CharField(max_length=100)
    organization: Organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='callsign_registry'
    )
    device: Device = models.OneToOneField(
        Device, on_delete=models.CASCADE, related_name='active_callsign'
    )
    current_guard: Optional[GuardSupervisor] = models.ForeignKey(
        GuardSupervisor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='current_callsign_assignment'
    )
    active_shift: str = models.CharField(max_length=10, choices=GuardSupervisor.SHIFT_CHOICES, blank=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'callsign')

    def __str__(self) -> str:
        name = self.current_guard.first_name if self.current_guard else 'Unassigned'
        return f"{self.callsign} -> {name}"


class DeviceProvisioning(models.Model):
    device: Device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name='provisionings'
    )
    guard: GuardSupervisor = models.ForeignKey(
        GuardSupervisor, on_delete=models.CASCADE, related_name='device_provisionings'
    )
    callsign_snapshot: str = models.CharField(max_length=100)
    organization: Organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='device_provisionings'
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('device', 'guard')
        indexes = [models.Index(fields=['organization', 'callsign_snapshot'])]

    def __str__(self) -> str:
        return f"{self.device.device_id} -> {self.callsign_snapshot}"


class DeviceTrail(models.Model):
    device: Device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='trail_points')
    assignment = models.ForeignKey(
        'api.ShiftAssignment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trail_points'
    )
    lat: float = models.FloatField()
    lng: float = models.FloatField()
    accuracy: Optional[float] = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")
    battery_pct: Optional[int] = models.SmallIntegerField(null=True, blank=True)
    speed: Optional[float] = models.FloatField(null=True, blank=True, help_text="Speed in m/s at capture time")
    bearing: Optional[float] = models.FloatField(null=True, blank=True, help_text="Bearing in degrees")
    recorded_at: models.DateTimeField = models.DateTimeField(help_text="Device timestamp of capture")
    synced_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, help_text="Server receipt timestamp")
    is_corrected: bool = models.BooleanField(default=False,
        help_text="True if this point was adjusted by GPS correction")

    class Meta:
        ordering = ['recorded_at']
        indexes = [
            models.Index(fields=['device', 'recorded_at']),
            models.Index(fields=['device', 'assignment']),
        ]

    def __str__(self) -> str:
        return f"{self.device.device_id or self.device.device_name} @ ({self.lat:.4f}, {self.lng:.4f})"


class DeviceSession(models.Model):
    STATE_AUTHENTICATED: str = 'authenticated'
    STATE_ON_ROUTE: str = 'on_route'
    STATE_CHECKPOINT_DUE: str = 'checkpoint_due'
    STATE_COMPLETING: str = 'completing'
    STATE_COMPLETED: str = 'completed'
    STATE_EMERGENCY_PAUSE: str = 'emergency_pause'
    STATE_OFFLINE_BUFFERING: str = 'offline_buffering'
    STATE_SESSION_EXPIRED: str = 'session_expired'

    STATE_CHOICES: list[tuple[str, str]] = [
        (STATE_AUTHENTICATED, 'Authenticated'),
        (STATE_ON_ROUTE, 'On Route'),
        (STATE_CHECKPOINT_DUE, 'Checkpoint Due'),
        (STATE_COMPLETING, 'Completing'),
        (STATE_COMPLETED, 'Completed'),
        (STATE_EMERGENCY_PAUSE, 'Emergency Pause'),
        (STATE_OFFLINE_BUFFERING, 'Offline Buffering'),
        (STATE_SESSION_EXPIRED, 'Session Expired'),
    ]

    device: Device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='sessions')
    assignment = models.ForeignKey(
        'api.ShiftAssignment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='device_sessions'
    )
    state: str = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_AUTHENTICATED)
    telemetry_interval_ms: int = models.IntegerField(default=60000)
    constellation_required: bool = models.BooleanField(default=False)
    sensor_activation: str = models.CharField(max_length=20, default='none', choices=[
        ('none', 'None'), ('pir_plus_accel', 'PIR + Accelerometer'), ('accel_only', 'Accelerometer Only')
    ])
    expected_checkpoint_radius: int = models.IntegerField(default=5)
    tolerance_window_min: int = models.IntegerField(default=15)
    entered_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)
    last_heartbeat_at: Optional[models.DateTimeField] = models.DateTimeField(null=True, blank=True)
    battery_pct_at_enter: Optional[int] = models.SmallIntegerField(null=True, blank=True)
    is_active: bool = models.BooleanField(default=True)

    class Meta:
        ordering = ['-entered_at']
        indexes = [
            models.Index(fields=['device', 'is_active']),
            models.Index(fields=['state']),
        ]

    def __str__(self) -> str:
        return f"{self.device.device_id} [{self.state}]"

    @property
    def telemetry_dict(self) -> dict:
        return {
            'gps_interval_ms': self.telemetry_interval_ms,
            'constellation_required': self.constellation_required,
            'sensor_activation': self.sensor_activation,
            'accuracy_min_meters': 10,
        }
