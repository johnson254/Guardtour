# Feature Prompt — Zone Verification, Dwell-State Machine, Sensor Fallback, and Mission Scoring (Backend Slot 2 Only)

## Role
You are a scoped backend subagent. You do not own this repo.
This is a single deliverable: one feature block shipped as one commit.
Sequential workflow: frontend Slot 1 is assumed complete. This slot must not touch templates/static except where explicitly called out below.

## Goal
Implement the full zone-verification and device-state layer: stage-aware telemetry, dwell-trail validation, sensor-assisted NFC fallback, probability scoring, and mission lifecycle — all wired together so the backend *controls* what the device sends and *verifies* every scan before it counts.

## Design Intent (from APP_ISSUES.md and existing models)
- `APP_ISSUES.md` documents why `device_id == operator_id`, why LocationManager not Play Services, and why the app is intentionally thin.
- `DESIGN.md` governs visual design — irrelevant here.
- Existing models to honor: `Device`, `ShiftAssignment`, `PatrolRoute`, `Checkpoint`, `ScanRecord`, `MapObject`.
- Existing helpers to reuse: `_haversine_meters`, `_point_in_polygon`, `validate_timestamp_drift`, `correct_gps_trail`.
- Current `ScanRecord.validity_score` exists but is barely computed. This feature makes it meaningful.

## Recommended Python Modules (add to requirements.txt if missing)
- `geopy` — haversine/distance/bearing (replace custom if not present)
- `shapely` — robust point-in-polygon, buffered zones, prepared geometries for geofence queries
- `numpy` — vectorized GPS trail math (speed, acceleration, outlier detection)
- `scipy.signal.savgol_filter` — smooth GPS trails before anomaly detection
- Optional (add only if baseline proves too slow):
  - `rtree` — spatial index for fast geofence containment queries when org has >200 geofences
  - `django-q2` or `celery` + `redis` — async command queue and batch processing when heartbeat p95 >200ms

## State Machine (explicit stages)

Create `DeviceSession` model (one FK to Device, queryable).
States:

1. **AUTHENTICATED** — registered but not yet on-route.
2. **ON_ROUTE** — active assignment loaded, normal telemetry.
3. **CHECKPOINT_DUE** — within geofence radius of a pending checkpoint.
4. **COMPLETING** — finished last checkpoint, draining buffer, awaiting mission_end.
5. **COMPLETED** — mission over, session wrapping up.
6. **EMERGENCY_PAUSE** — dispatcher halted; no reminders, but location tracked.
7. **OFFLINE_BUFFERING** — no signal; local queue building.
8. **SESSION_EXPIRED** — shift over or timeout.

Per-state contract:
- `telemetry_interval` (ms) the app must use for GPS
- `constellation_required` (bool) — GNSS/GLONASS/BEIDOU active?
- `sensor_activation` (str) — `none`, `pir_plus_accel`, `accel_only`
- `expected_checkpoint_radius` (m) — per-checkpoint or system default
- `tolerance_window` (min) — arrival window before scan is deemed “too early / too late”

State transitions triggered by:
- Heartbeat state evaluations
- Scan events (success, failure, dwell complete)
- Dispatcher override (stub for now, backend-driven only in this sprint)
- Mission completion rules (see below)

---

## Mission Lifecycle

Mission stages (store on `ShiftAssignment` as `mission_stage` CharField):

```
ASSIGNED → DEPLOYED → ACTIVE → COMPLETING → COMPLETED / CANCELLED
```

- **ASSIGNED**: ShiftAssignment created, not yet started. Device in AUTHENTICATED.
- **DEPLOYED**: device sends first heartbeat with valid location after assignment. Device → ON_ROUTE. First lead-time alert may fire.
- **ACTIVE**: device has at least one successful scan on route. State remains ON_ROUTE.
- **COMPLETING**: device scans last checkpoint or mission end time hits. State → COMPLETING. Device drains last GPS batch.
- **COMPLETED**: all scans validated, trail checked, dwell scored. Device → COMPLETED.
- **CANCELLED**: dispatcher stops mission. Device → EMERGENCY_PAUSE then SESSION_EXPIRED.

Append transition entries to a simple state log (append-only JSON on ShiftAssignment or a small `MissionStateLog` model — your call, keep it queryable).

---

## Telemetry Contract (heartbeat response)

Heartbeat response dict must include:

```
{
  "session_state": "<state>",
  "mission_stage": "<stage>",
  "telemetry": {
    "gps_interval_ms": 60000,
    "constellation_required": false,
    "sensor_activation": "none",
    "accuracy_min_meters": 10
  },
  "directives": { ... existing directives ... },
  "map_update": {  // new: tells map widget device just entered/left a zone
    "event": "zone_enter" | "zone_exit" | "dwell_update",
    "checkpoint_id": 123,
    "radius_m": 5,
    "confidence": 0.87
  }
}
```

---

## Zone Verification Engine (the “magic of verification”)

Call this from the scan endpoint **after** tolerance check and **before** `ScanRecord` finalizes.

### Step 1 — Tolerance Nop Gate
```python
planned_time = checkpoint.planned_time
tolerance_minutes = checkpoint.time_tolerance  (default 15, overridable)
arrival = scan.timestamp
window_start = planned_time - tolerance_minutes
window_end = planned_time + tolerance_minutes + (checkpoint.dwell_time or 0)
if arrival < window_start or arrival > window_end:
    scan.validity_score = 0.0
    scan.verification_notes = "out_of_tolerance_window"
    return DROP (noop, no exception, no save)
```
If the guard shows up too early or too late, the scan is silently dropped. It does not count. No partial credit.

### Step 2 — Radius Check with Corrected Defaults
```python
base_radius = checkpoint.radius  # MUST default to 5, NOT 50
precision_multiplier = {
    'strict': 0.5,
    'normal': 1.0,
    'loose': 2.0
}.get(checkpoint.precision_level, 1.0)
effective_radius = max(base_radius * precision_multiplier, 0.1)

# Sensor fallback extension: if state is CHECKPOINT_DUE and sensors confirm presence:
#   effective_radius = max(effective_radius, 15.0)   ← 15m correction ceiling
if scan.sensor_context and sensor_confirms_presence(scan.sensor_context):
    effective_radius = max(effective_radius, 15.0)

dist = _haversine_meters(scan.lat, scan.lng, checkpoint.lat, checkpoint.lng)
if dist > effective_radius:
    scan.validity_score = (scan.validity_score or 0.0) * 0.3
    scan.verification_notes = (scan.verification_notes or "") + " outside_radius"
```

### Step 3 — Dwell Trail Validation (replace current last_hit math)
- Pull last N minutes of GPS points for this device on this route (from `GpsBatch`).
- Walk the trail: for every GPS point within the checkpoint window, check if device was inside `effective_radius` for consecutive time.
- Define `continuous_presence_seconds`: longest uninterrupted streak inside radius.
- Compare against `checkpoint.dwell_time` (default 0 = no dwell required).

```python
if checkpoint.dwell_time and checkpoint.dwell_time > 0:
    if continuous_presence_seconds >= checkpoint.dwell_time * 60:
        scan.dwell_valid = True
        scan.dwell_seconds = continuous_presence_seconds
    else:
        scan.dwell_valid = False
        scan.insufficient_dwell_time = True
        scan.validity_score = (scan.validity_score or 0.0) * 0.5
```

### Step 4 — Anomaly Detection During Dwell
While walking the GPS trail:

- **Sudden jump**: consecutive points > max human walking speed (120 m/min). If more than 3 such jumps in the checkpoint window, flag `anomaly: sudden_jump`.
- **GPS hop / constellation loss**: if GNSS `hdop` jumps from < 3.0 to > 6.0 between two consecutive points within the same dwell window, flag `anomaly: gps_instability`.
- **Drift / creeping**: device moves > 0.5 m/s consistently but never exits radius. Flag `anomaly: prolonged_drift`.
- **Too much dwell**: if `continuous_presence_seconds > (checkpoint.dwell_time * 60 * 2.5)`, flag `anomaly: prolonged_dwell` — suspicious, could be socializing.

```python
if anomaly_detected:
    scan.anomaly_flags = list(set(scan.anomaly_flags or []) | set(detected_flags))
    scan.validity_score = (scan.validity_score or 0.0) * 0.6
```

### Step 5 — Sensor Fallback (NFC failure recovery)
If NFC scan is weak or retries fail, the app sends sensor context with the scan (see App Contract below).

```python
if scan.nfc_value and scan.sensor_context:
    ctx = scan.sensor_context
    if (ctx.get('pir_triggered') and 
        ctx.get('proximity_score', 0) >= 0.8 and 
        ctx.get('accel_pattern') in ('steady', 'walking')):
        scan.validity_score = max(scan.validity_score or 0.0, 0.75)
        scan.verification_notes = (scan.verification_notes or "") + " sensor_confirmed_presence"
        scan.sensor_aided = True
    elif ctx.get('accel_pattern') == 'erratic' or ctx.get('proximity_score', 0) < 0.4:
        scan.anomaly_flags = list(set(scan.anomaly_flags or []) | {'sensor_mismatch'})
        scan.validity_score = (scan.validity_score or 0.0) * 0.5
```

### Step 6 — Probability Scoring (final validity_score)
Weighted composite from 0.0 to 1.0:

| Factor | Weight |
|---|---|
| NFC success (nfc_value present, not a duplicate re-read) | 0.25 |
| Radius proximity (dist / effective_radius, closer = higher) | 0.20 |
| Dwell trail (continuous_presence_seconds vs dwell_time) | 0.25 |
| Anomaly-free trail (no sudden jump, gps hop, drift, prolonged dwell) | 0.15 |
| Sensor confirmation (PIR + accel + proximity) | 0.10 |
| Timestamp drift (validate_timestamp_drift) | 0.05 |

**Progression-record gate** — validity_score is ONLY fully trustworthy if the device proceeds to the next checkpoint on time:

```python
if not device_has_clean_progression_record(current_mission):
    scan.validity_score = (scan.validity_score or 0.0) * 0.7
    scan.verification_notes = (scan.verification_notes or "") + " degraded_by_history"
```

`device_has_clean_progression_record` checks:
- Previous scans on this mission: on-time ratio >= 0.8
- Previous validity scores: average >= 0.6
- Previous dwell scores: average >= 0.7

A guard who always arrives on time and stays gets full trust. A guard with 3 late arrivals in a row gets their score capped.

**Mission-stall penalty**:
```python
if is_last_checkpoint and mission_stage != COMPLETED within (window_end + tolerance):
    scan.validity_score = (scan.validity_score or 0.0) * 0.8
    scan.verification_notes = (scan.verification_notes or "") + " mission_stall_penalty"
```

---

## Map Residency Signal

When radius check passes:
- Publish a map residency event via the existing HTMX endpoint or a new lightweight view.
- Event payload:
```
{
    "device_id": "...",
    "device_label": "...",
    "checkpoint_id": 123,
    "checkpoint_name": "Boiler Room",
    "entered_at": "2026-06-28T...",
    "confidence": 0.87,
    "state": "checkpoint_due"
}
```
- Frontend target: the existing dispatch map partial. This ensures the map updates live when a guard enters a checkpoint zone.

---

## App Contract (what the API expects and returns)

### Registration / Login
Android app sends:
```
POST /api/register-device/
{
  "operator_id": "TCN-01",
  "hardware_info": {
    "imei": "...",
    "imsi": "...",
    "sim_phone_number": "...",
    "model": "...",
    "os_version": "...",
    "sdk_int": 29,
    "supports_gnss": true,
    "supports_sensors": true,
    "sensor_types": ["pir", "accelerometer"],
    "vibration_modes": ["short", "long", "double"],
    "constellation_mask": "gps+glonass+beidou"
  }
}
```

Backend response:
```
{
  "session_token": "...",
  "expires_at": "...",
  "session_state": "on_route",
  "telemetry": {
    "gps_interval_ms": 60000,
    "constellation_required": false,
    "sensor_activation": "none",
    "accuracy_min_meters": 10
  }
}
```

### Heartbeat
App sends:
```
POST /api/heartbeat/
{
  "session_token": "...",
  "battery_pct": 84,
  "lat": -1.2921,
  "lng": 36.8219,
  "gps_accuracy": 8.3,
  "gps_metadata": {
    "hdop": 1.8,
    "satellites_in_view": 9,
    "satellites_used": 7,
    "constellations": {"GPS": {...}, "GLONASS": {...}, "BEIDOU": {...}}
  },
  "sensor_batch": {
    "alive_seconds": 120,
    "pir_events": 3,
    "accel_summary": "steady",
    "proximity_score": 0.0
  }
}
```

### Scan
App sends:
```
POST /api/scans/
{
  "session_token": "...",
  "nfc_value": "04-A3-B2-C1",
  "recorded_at": "2026-06-28T...",
  "lat": -1.292065,
  "lng": 36.821905,
  "accuracy": 4.2,
  "gps_metadata": { ... same as heartbeat ... },
  "sensor_context": {
    "pir_triggered": true,
    "accel_pattern": "walking",
    "proximity_score": 0.94,
    "duration_seconds": 42,
    "gps_trail_last_30s": [...]
  },
  "raw_nfc": { ... hex dump ... }
}
```

### Relevant Heartbeat Response Keys
```
{
  "session_state": "checkpoint_due",
  "mission_stage": "active",
  "telemetry": {
    "gps_interval_ms": 5000,
    "constellation_required": true,
    "sensor_activation": "pir_plus_accel",
    "accuracy_min_meters": 5
  },
  "map_update": {
    "event": "zone_enter",
    "checkpoint_id": 42,
    "radius_m": 5,
    "confidence": 0.92
  }
}
```

---

## Migration + Seed Data

1. **Migration**: add `DeviceSession` table, `ShiftAssignment.mission_stage`, `ScanRecord` new fields (`validity_score`, `dwell_seconds`, `dwell_valid`, `anomaly_flags`, `sensor_aided`, `time_drift_seconds`, `time_drift_suspicious`).
2. **Backfill**:
   - All existing `Device` rows get a default `DeviceSession` with `state=STATE_ON_ROUTE` so nothing breaks after deploy.
   - All existing `Checkpoint` rows: if `radius` is 50 and `precision_level` is `normal`, drop to 5. If they were intentionally 50+, leave them. Only auto-correct if the user never explicitly set a radius.
3. **Seed `AlertRule`** defaults per org:
   - `ON_ROUTE`: first_alert=15 min, repeat=15 min
   - `CHECKPOINT_DUE`: first_alert=5 min, repeat=0 (one-shot)
   - `COMPLETING`: no alerts
4. **Seed tolerance defaults**:
   - `time_tolerance = 15` (already exists at org level, now also at checkpoint)
   - `radius` system default: **5** (not 50)

---

## TDD Discipline (REQUIRED)

Write tests first for each rule, see them fail, then implement minimal fix:

1. **test_tolerance_nop_gate** — scan outside tolerance window returns validity_score=0.0 and does not save as confirmed scan.
2. **test_radius_defaults** — strict checkpoint uses 5m, normal uses 5m×1, loose uses 5m×2. Not 50m.
3. **test_dwell_trail_validation** — GPS trail walk correctly computes continuous presence seconds.
4. **test_anomaly_sudden_jump** — two points 200m apart in 60s flag `sudden_jump`.
5. **test_anomaly_gps_hop** — HDOP 1.8 → 7.2 within same dwell flags `gps_instability`.
6. **test_sensor_fallback_upgrades_score** — poor NFC score raised to 0.75 when PIR + accel confirm.
7. **test_sensor_mismatch_downgrades** — erratic accel with low proximity halves score.
8. **test_probability_scoring_weighted** — mock all factors, confirm weighted sum matches expected.
9. **test_progression_record_degradation** — guard with 3 prior late arrivals gets score capped at 0.7×.
10. **test_prolonged_dwell_penalty** — dwell_time 5 min, actual dwell 15 min flags `prolonged_dwell` and degrades score.
11. **test_state_transitions** — assignment created → ON_ROUTE, last scan → COMPLETING, end_time reached → COMPLETED.
12. **test_map_residency_event** — radius check publishes HTMX event on the map partial.
13. **test_mission_stall_penalty** — guard stays in last zone past window_end gets degraded score.

---

## Validation Checklist

1. All 13 TDD tests pass before code is committed.
2. Existing 54/54 baseline tests still pass (no regression).
3. `python manage.py makemigrations --check` reports no missing migrations.
4. No new code touches Django templates directly.
5. Map residency uses existing HTMX partial (`templates/partials/routes/map_residency.html` or create it in static if partial does not exist — ask via REPORT first if no partial found).
6. No changes to `guardtour/settings.py` or `guardtour/urls.py` outside explicit new URL entries.

---

## Scope Guards (YOU WILL BE REVERTED IF YOU VIOLATE THESE)

- Backend only. Do NOT modify `templates/`, `static/`, or frontend code.
- Do NOT change Android Kotlin files.
- Do NOT add new Django apps.
- Do NOT remove or rename existing models/fields.
- Do NOT run Git operations (no add, no commit, no push).
- Do NOT start the dev server.
- Do NOT run pytest unless explicitly instructed.
- REPORT first, fix second. If you hit contradictory constraints, stop and list them in your output.

---

## OUTPUT FORMAT

Return in this order:

1. **DIFF SUMMARY** — files to add/modify/delete (paths only, purpose one-liner each).
2. **MIGRATION SUMMARY** — new fields, new tables, default values.
3. **MODEL CODE** — `DeviceSession`, `AlertRule`, `MissionStateLog`, and any new models.
4. **SCAN SERVICE CODE** — new `verify_zone_scan()` function and helpers.
5. **VIEW CHANGES** — heartbeat expansion, scan endpoint hook, map residency endpoint.
6. **TEST CODE** — all 13 test functions.
7. **APP CONTRACT** — registration, heartbeat, scan request/response shapes (copy from above).
8. **RISK ASSESSMENT** — what could break in existing flows.
9. **VALIDATION PLAN** — how the assistant will verify after you return.
10. **OPEN QUESTIONS** — anything you couldn’t decide and need human input on.

Do NOT include passes or stubs. Write real code that would run if dropped into the project.
