import re

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver


class Organization(models.Model):
    name = models.CharField(max_length=200)
    # Short uppercase code used as the prefix in operator IDs (ORG-SEQ, e.g. TCN-01).
    # Unique per organization so two orgs can never produce colliding operator IDs.
    code = models.CharField(max_length=8, unique=True, null=True, blank=True,
                            help_text="Short uppercase org code used as operator-ID prefix (e.g. TCN)")
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    default_time_tolerance = models.IntegerField(default=15, help_text="Default minutes allowed for scheduled scans")
    is_active = models.BooleanField(default=True)
    shift_mode = models.CharField(
        max_length=20,
        choices=[('simple', 'Simple (no shift tracking)'), ('structured', 'Structured (Day/Night/Flex)')],
        default='simple',
        help_text="Controls whether shift-based logic (Day/Night/Flex) is enforced"
    )

    @staticmethod
    def _derive_code(name):
        """Derive a 2-4 letter uppercase code from an org name (first letters of words)."""
        words = [w for w in re.split(r'[\s\-_&]+', name or '') if w]
        if not words:
            return 'ORG'
        code = ''.join(w[0] for w in words).upper()
        # Single-word names yield a single letter — take first 3 chars instead
        if len(code) == 1 and words and len(words[0]) >= 3:
            code = words[0][:3].upper()
        code = re.sub(r'[^A-Z0-9]', '', code)
        return (code[:4] or 'ORG')

    def propose_code(self):
        """Return a unique code for this org, appending a digit if needed to avoid collisions."""
        base = self._derive_code(self.name)
        candidate = base
        n = 1
        qs = Organization.objects.exclude(pk=self.pk)
        while qs.filter(code__iexact=candidate).exists():
            # Truncate base so the digit still fits within max_length=8
            candidate = f"{base[:7]}{n}"
            n += 1
        return candidate

    def save(self, *args, **kwargs):
        # Auto-assign a code when none is present so every org has one.
        if not self.code:
            self.code = self.propose_code()
        else:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Admin(models.Model):
    """
    System-level administrator who can manage multiple organizations.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    organizations = models.ManyToManyField(Organization, related_name='admins')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        count = self.organizations.count()
        return f"{self.user.username} (Admin - Managing {count} Orgs)"

class Dispatcher(models.Model):
    """
    Organization-level dispatcher who manages shift assignments and has an NFC tag.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dispatcher_profile')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='dispatchers', null=True, blank=True)
    
    # Permission Flags
    can_manage_routes = models.BooleanField(default=True)
    can_manage_guards = models.BooleanField(default=True)
    can_view_reports = models.BooleanField(default=True)
    can_manage_devices = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        if self.organization:
            return f"{self.user.username} (Dispatcher - {self.organization.name})"
        return f"{self.user.username} (Dispatcher - No Org)"

class GuardSupervisor(models.Model):
    """Guard/Supervisor officer profile.

    Guards are data-driven only (no Django auth user). Duty/assignment comes
    from ShiftAssignment and device provisioning.

    Identifiers like callsign and auth_nfc_tag can be bound later.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='guardsupervisor', null=True, blank=True)
    SHIFT_CHOICES = [
        ('Day', 'Day'),
        ('Night', 'Night'),
        ('Flex', 'Flex'),
    ]
    

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    # Officer identifier fields (optional).
    # You can create a guard/officer record with ONLY name + organization + role + shift,
    # then bind device/NFC later via device provisioning.
    callsign = models.CharField(max_length=100, null=True, blank=True, help_text="User-facing identifier (e.g. H-01@twocan). Typed at login.")



    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='guards_supervisors', null=True, blank=True)
    role = models.CharField(max_length=20, choices=[
        ('guard', 'Guard'),
        ('supervisor', 'Supervisor')
    ], default='guard')
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='Day')
    nfc_tags_scanned = models.IntegerField(default=0)
    last_scan = models.DateTimeField(null=True, blank=True)
    is_on_shift = models.BooleanField(default=False)
    last_shift_change = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip() or "Unnamed"
        if self.organization:
            return f"{full_name} ({self.role}) - {self.organization.name}"
        return f"{full_name} ({self.role}) - No Org"

class Device(models.Model):
    device_id = models.CharField(max_length=200, unique=True, null=True, blank=True)

    device_name = models.CharField(max_length=200, null=True, blank=True)
    callsign = models.CharField(max_length=100, null=True, blank=True, help_text="System-generated hardware callsign")
    is_active = models.BooleanField(default=True, help_text="If False, device is decommissioned and all auth requests are rejected")
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    last_sequence_id = models.IntegerField(default=0, help_text="Last processed monotonic sequence ID from this device for offline scan ordering")
    peer_session_key = models.CharField(max_length=100, null=True, blank=True, help_text="Rolling key for server-side scan verification")
    password = models.CharField(max_length=128, null=True, blank=True, help_text="Device auth password, generated on registration")
    
    # NFC/GPS fetch request tracking (for offline devices)
    nfc_fetch_requested = models.DateTimeField(null=True, blank=True)
    gps_fetch_requested = models.DateTimeField(null=True, blank=True)
    gps_accuracy_threshold = models.IntegerField(default=10, null=True, blank=True, help_text="Required GPS accuracy in meters for a valid fetch")
    
    # Last received NFC/GPS data (from device)
    last_nfc_scan = models.DateTimeField(null=True, blank=True)
    last_nfc_scan_uid = models.CharField(max_length=100, null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_gps_accuracy = models.FloatField(null=True, blank=True, help_text="Accuracy of the last GPS fix in meters")
    
    battery_pct = models.SmallIntegerField(null=True, blank=True, help_text="Device battery percentage 0-100")
    
    # Hardware & telephony info (reported by device on registration)
    imei = models.CharField(max_length=50, null=True, blank=True, help_text="IMEI number of the device")
    imsi = models.CharField(max_length=50, null=True, blank=True, help_text="IMSI of the SIM card")
    sim_phone_number = models.CharField(max_length=30, null=True, blank=True, help_text="SIM card phone number (MSISDN)")
    os_version = models.CharField(max_length=100, null=True, blank=True, help_text="OS version (e.g. Android 14)")
    manufacturer = models.CharField(max_length=100, null=True, blank=True, help_text="Device manufacturer (e.g. Samsung)")
    model = models.CharField(max_length=100, null=True, blank=True, help_text="Device model (e.g. Galaxy S24)")
    sdk_int = models.IntegerField(null=True, blank=True, help_text="Android API level (Build.VERSION.SDK_INT)")
    nfc_mode = models.CharField(max_length=20, blank=True, default='auto', help_text="Server-assigned NFC mode: 'hce_emulator', 'hce_reader', 'tag_reader', 'auto'")
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='devices', null=True, blank=True)
    
    # Default TTS config for this device
    tts_voice = models.CharField(max_length=50, blank=True, default='en-US', help_text="Default TTS voice locale for this device")
    tts_rate = models.FloatField(default=1.0, help_text="Default TTS speech rate 0.5-2.0")
    tts_pitch = models.FloatField(default=1.0, help_text="Default TTS speech pitch 0.5-2.0")
    tts_pending = models.TextField(null=True, blank=True, help_text="Pending TTS message to deliver on next heartbeat")
    tts_pending_voice = models.CharField(max_length=50, blank=True, default='', help_text="Voice override for pending TTS")
    tts_pending_rate = models.FloatField(default=1.0, help_text="Rate override for pending TTS")
    tts_pending_pitch = models.FloatField(default=1.0, help_text="Pitch override for pending TTS")
    tts_pending_at = models.DateTimeField(null=True, blank=True, help_text="When the pending TTS was queued")
    tts_acked = models.BooleanField(default=True, help_text="True when device confirmed receipt of last tts_pending. If False, resend on next heartbeat.")
    last_reminder_at = models.DateTimeField(null=True, blank=True, help_text="When the last lead-time reminder TTS was spoken")
    geofence_states = models.JSONField(null=True, blank=True, default=dict, help_text="Tracks entered geofence IDs to avoid duplicate TTS: {map_object_id: entered_at_iso}")
    
    def __str__(self):
        return self.device_id or self.device_name


class CallSign(models.Model):
    """Binds a device to a guard's identity via shared callsign."""
    callsign = models.CharField(max_length=100)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='callsign_registry')
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='active_callsign')
    current_guard = models.ForeignKey(GuardSupervisor, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_callsign_assignment')
    active_shift = models.CharField(max_length=10, choices=GuardSupervisor.SHIFT_CHOICES, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'callsign')

    def __str__(self):
        return f"{self.callsign} -> {self.current_guard.first_name if self.current_guard else 'Unassigned'}"

class DeviceProvisioning(models.Model):
    """Binds an installed hardware device (device_id) to a guard callsign (callsign)."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='provisionings')
    guard = models.ForeignKey(GuardSupervisor, on_delete=models.CASCADE, related_name='device_provisionings')
    callsign_snapshot = models.CharField(max_length=100)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='device_provisionings')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('device', 'guard')
        indexes = [models.Index(fields=['organization', 'callsign_snapshot'])]

    def __str__(self):
        return f"{self.device.device_id} -> {self.callsign_snapshot}"

class PatrolRoute(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft/Staging'),
        ('scheduled', 'Scheduled/Upcoming'),
        ('active', 'Active/Daily'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    FREQUENCY_CHOICES = [
        ('once', 'One-Time'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('adhoc', 'Ad-Hoc/Flexible'),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='routes', null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='once', blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    enforce_order = models.BooleanField(default=False)
    enforce_time = models.BooleanField(default=False)
    is_geofence = models.BooleanField(default=False, help_text="If true, patrol relies on GPS perimeters")
    is_emergency = models.BooleanField(default=False)
    is_audit = models.BooleanField(default=False, help_text="If true, guards scan other devices (Peer-to-Peer)")
    is_daily = models.BooleanField(default=False, help_text="If true, this route resets and alerts daily")
    scheduled_start_time = models.TimeField(null=True, blank=True, help_text="Time to alert operator to start")
    send_start_alert = models.BooleanField(default=False)
    send_announcement = models.BooleanField(default=False, help_text="If true, the readout_text will be broadcasted.")
    start_alert_lead_time = models.IntegerField(default=15, help_text="Minutes before start to send alert")
    readout_text = models.TextField(blank=True, help_text="Instructional text for POC radio TTS")
    tts_voice = models.CharField(max_length=50, blank=True, default='', help_text="TTS voice locale (e.g. en-US, en-GB-Standard-A)")
    tts_rate = models.FloatField(default=1.0, help_text="TTS speech rate 0.5-2.0")
    tts_pitch = models.FloatField(default=1.0, help_text="TTS speech pitch 0.5-2.0")
    assigned_guards = models.ManyToManyField(GuardSupervisor, blank=True, related_name='assigned_blueprints')
    assigned_devices = models.ManyToManyField(Device, blank=True, related_name='assigned_blueprints')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_routes')
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def logic_type(self):
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

    def __str__(self):
        return self.name

class Checkpoint(models.Model):
    CHECKPOINT_TYPES = [
        ('nfc', 'NFC'),
        ('gps', 'GPS'),
        ('peer', 'Peer'),
        ('custom', 'Custom'),
        ('geo', 'Geofence'),
    ]

    # Decouple from Route: A checkpoint can now be a standalone "Asset" in an organization's library
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='global_checkpoints', null=True, blank=True)
    route = models.ForeignKey(PatrolRoute, on_delete=models.CASCADE, related_name='checkpoints', null=True, blank=True)
    name = models.CharField(max_length=200)
    checkpoint_type = models.CharField(max_length=10, choices=CHECKPOINT_TYPES, default='nfc')


    nfc_tag = models.CharField(max_length=100, blank=True, null=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    order = models.IntegerField(default=0)
    planned_time = models.TimeField(null=True, blank=True)
    time_tolerance = models.IntegerField(default=15, blank=True)
    dwell_time = models.IntegerField(default=0, blank=True, help_text="Minutes expected to stay at checkpoint")
    radius = models.IntegerField(default=50, blank=True, help_text="Acceptable GPS radius in meters")
    precision_level = models.CharField(
        max_length=10,
        choices=[('strict', 'Strict'), ('normal', 'Normal'), ('loose', 'Loose')],
        default='normal',
        blank=True,
        help_text="Context-aware radius multiplier: strict=0.5x, normal=1x, loose=2x"
    )
    next_announcement_text = models.TextField(blank=True, null=True, help_text="Per-checkpoint TTS announcement text")

    class Meta:
        ordering = ['order']

    def clean(self):
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

        # Prevent duplicate planned_time within same route
        if self.planned_time and self.route_id:
            dupes = Checkpoint.objects.filter(route_id=self.route_id, planned_time=self.planned_time)
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError({'planned_time': f'Another checkpoint in this route already has planned time {self.planned_time}.'})

        # Prevent duplicate order within same route
        if self.route_id and self.order is not None:
            dupes = Checkpoint.objects.filter(route_id=self.route_id, order=self.order)
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError({'order': f'Duplicate order {self.order} for this route.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ScanRecord(models.Model):
    guard_supervisor = models.ForeignKey(GuardSupervisor, on_delete=models.CASCADE, related_name='scans', null=True, blank=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, related_name='scans')
    route = models.ForeignKey(PatrolRoute, on_delete=models.CASCADE, related_name='scans', null=True, blank=True)
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.SET_NULL, related_name='scans', null=True, blank=True)
    checkpoint_name = models.CharField(max_length=200)
    nfc_value = models.CharField(max_length=200, blank=True, null=True)
    is_on_time = models.BooleanField(default=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    client_timestamp = models.DateTimeField(null=True, blank=True, help_text="Original timestamp reported by the client device")
    server_received_timestamp = models.DateTimeField(null=True, blank=True, help_text="Server wall-clock time when the scan was received")
    sequence_id = models.IntegerField(null=True, blank=True, help_text="Monotonic counter from the client for offline scan ordering")
    time_drift_seconds = models.IntegerField(null=True, blank=True, help_text="Seconds between client_timestamp and server_received_timestamp. Positive = client behind.")

    # Raw NFC payload and server-side determination
    raw_nfc = models.JSONField(null=True, blank=True, help_text="Full NFC payload from device (UID, NDEF, tech, sensors)")
    scan_type = models.CharField(max_length=20, null=True, blank=True, help_text="Server-determined: 'tag' or 'peer'")
    
    # Validity scoring
    validity_score = models.FloatField(null=True, blank=True, help_text="0.0-1.0 probability that this scan is legitimate")
    validity_reason = models.CharField(max_length=300, null=True, blank=True, help_text="Human-readable explanation of the score")

    out_of_sequence = models.BooleanField(default=False, help_text="True if scanned in wrong order per route sequence")
    insufficient_dwell_time = models.BooleanField(default=False, help_text="True if guard left before dwell_time elapsed")
    dwell_seconds = models.IntegerField(null=True, blank=True, help_text="Actual seconds spent at checkpoint before this scan")
    
    def __str__(self):
        name = f"{self.guard_supervisor.first_name}" if self.guard_supervisor else 'Unknown'
        return f"{name} scanned {self.checkpoint_name}"

class ShiftAssignment(models.Model):
    """
    Tracks which guards/supervisors are on shift and managed by dispatchers.
    """
    dispatcher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dispatched_assignments', help_text="The Dispatcher or Admin who created this assignment")
    guard_supervisor = models.ForeignKey(GuardSupervisor, on_delete=models.CASCADE, null=True, blank=True, related_name='shift_assignments')
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_assignments')
    route = models.ForeignKey(PatrolRoute, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_shifts')
    scheduled_date = models.DateField(null=True, blank=True, help_text="The date this mission is intended to occur")
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    shift_type = models.CharField(max_length=10, choices=GuardSupervisor.SHIFT_CHOICES)
    is_active = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False, help_text="True when all checkpoints have been scanned")
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('completed', 'Completed'), ('emergency_active', 'Emergency Active'), ('cancelled', 'Cancelled'), ('handover', 'Handed Over')],
        default='active',
        blank=True,
        help_text="Lifecycle status of the assignment"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
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

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.guard_supervisor:
            return f"{self.guard_supervisor.first_name} - {self.shift_type} shift"
        return f"Device Only - {self.shift_type} shift"
    
    @property
    def total_checkpoints(self):
        if self.route:
            return self.route.checkpoints.count()
        return 0
    
    @property
    def completed_checkpoints(self):
        if self.route and self.guard_supervisor:
            hit_count = ScanRecord.objects.filter(
                guard_supervisor=self.guard_supervisor,
                route=self.route,
                timestamp__gte=self.assigned_at
            ).values('checkpoint').distinct().count()
            return hit_count
        return 0

class OperatorAlert(models.Model):
    """Queue for sending alerts/tasks to POC radios."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    operator = models.ForeignKey(GuardSupervisor, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=[('low', 'Low'), ('normal', 'Normal'), ('urgent', 'Urgent')], default='normal')
    play_sound = models.BooleanField(default=True, help_text="Play notification sound on device")
    vibrate = models.BooleanField(default=True, help_text="Vibrate device on alert")
    tts_voice = models.CharField(max_length=50, blank=True, default='', help_text="TTS voice locale override")
    tts_rate = models.FloatField(default=1.0, help_text="TTS speech rate override 0.5-2.0")
    tts_pitch = models.FloatField(default=1.0, help_text="TTS speech pitch override 0.5-2.0")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.operator.first_name if self.operator else "Unknown"
        return f"Alert to {name}: {self.title}"

@receiver(post_save, sender=ShiftAssignment)
def update_guard_shift_status(sender, instance, created, **kwargs):
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

class IncidentReport(models.Model):
    """Intelligence reported from the field (Safety, Maintenance, Breach)."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='incidents')
    guard_supervisor = models.ForeignKey(GuardSupervisor, on_delete=models.CASCADE, related_name='reported_incidents')
    category = models.CharField(max_length=50, choices=[('security', 'Security Breach'), ('maintenance', 'Maintenance'), ('safety', 'Safety Hazard')])
    title = models.CharField(max_length=200)
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.category.upper()}: {self.title}"

class MapObject(models.Model):
    """Persistent POIs and Geofences for Open Maps."""
    TYPES = [('poi', 'POI'), ('geofence', 'Geofence')]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='map_objects')
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPES)
    
    # Spatial data
    geometry = models.JSONField(null=True, blank=True, help_text="Coordinate list for markers or polygons")
    radius = models.IntegerField(null=True, blank=True, help_text="Radius for POI/Circle objects")
    assigned_personnel = models.ManyToManyField(GuardSupervisor, blank=True, related_name='assigned_map_objects')
    
    entry_msg = models.CharField(max_length=500, blank=True, null=True)
    exit_msg = models.CharField(max_length=500, blank=True, null=True)
    geo_shape = models.CharField(max_length=50, blank=True, null=True)
    intrusion_alarm = models.BooleanField(default=False)
    fetch_location_on_scan = models.BooleanField(default=False, help_text="Auto-fetch GPS location on first NFC scan")
    planned_duration_minutes = models.IntegerField(default=5, null=True, blank=True, help_text="Countdown duration in minutes for NFC scan window")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.type})"

class DeviceTrail(models.Model):
    """Timestamped GPS breadcrumb for device movement trails and offline GPS buffering."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='trail_points')
    assignment = models.ForeignKey(ShiftAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name='trail_points')
    lat = models.FloatField()
    lng = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")
    battery_pct = models.SmallIntegerField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Speed in m/s at capture time")
    bearing = models.FloatField(null=True, blank=True, help_text="Bearing in degrees")
    recorded_at = models.DateTimeField(help_text="Device timestamp of capture")
    synced_at = models.DateTimeField(auto_now_add=True, help_text="Server receipt timestamp")
    is_corrected = models.BooleanField(default=False, help_text="True if this point was adjusted by GPS correction")

    class Meta:
        ordering = ['recorded_at']
        indexes = [
            models.Index(fields=['device', 'recorded_at']),
            models.Index(fields=['device', 'assignment']),
        ]

    def __str__(self):
        return f"{self.device.device_id or self.device.device_name} @ ({self.lat:.4f}, {self.lng:.4f})"