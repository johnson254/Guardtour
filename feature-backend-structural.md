# Feature Prompt — Backend Structural Refactor + Zone Verification Spine (Backend Slot 2 Only)

## Role
You are a scoped backend subagent. You do not own this repo.
This is a single commit: structural refactor of the backend into production-ready form, PLUS the zone-verification state machine.
Sequential workflow: frontend Slot 1 is assumed already committed. This slot touches `api/`, `guardtour/`, and `requirements.txt` only. No templates, no static, no Android.

## Background
The backend is currently one 2,839-line `api/views/core.py` that owns every endpoint, every helper, every viewset. The mobile API function views share a file with admin viewsets and HTMX partials. It works, but it is fragile and unmaintainable.

You are here to break it down properly and add the missing spine: the device state machine and zone verification engine.

## Output
One commit. One diff. Real files, real migrations, real tests. No stubs.

---

## PHASE 1 — Structural Refactor

### 1.1 Split `api/views/core.py` into modules

Create this layout and **rehome every function/view from `core.py` into the right module**:

```
api/views/
├── __init__.py
├── auth.py          # register(), login(), generate_operator_id(), operator_id_next(), _build_operator_identity()
├── devices.py       # register_device(), provision_device(), _heartbeat_update_device(), device-side APIs
├── heartbeat.py     # heartbeat() view, _heartbeat_fetch_directives(), _heartbeat_lead_time_reminder(), _heartbeat_geofence_tts(), _heartbeat_tts_delivery(), _heartbeat_tts_ack(), _heartbeat_peer_mode(), _heartbeat_active_missions(), _heartbeat_operator_identity()
├── scans.py         # scan endpoint, gps-batch, scan-batch, everything that receives telemetry
├── dispatch.py      # ShiftAssignment deployment, mission staging, route assignment logic
├── manage.py        # Admin panels: org, dispatcher, guard, device, fleet management viewsets and partials
├── maps.py          # MapObject, geofence queries, map residency publishing
├── reports.py       # Reports, analytics, audit panels
├── core.py          # ONLY true cross-cutting helpers that don't belong elsewhere:
│                     # _haversine_meters, _point_in_polygon, _deactivate_assignments,
│                     #   _heartbeat_device_lookup (if used by multiple views)
├── partials/
│   ├── __init__.py
│   ├── manage.py     # existing partials (keep content, just move file)
│   └── routes.py     # map residency partial, route fragments
```

**Constraint:** after refactor, `api/views/core.py` must be < 300 lines (only standalone helpers). No functional behavior may change — imports are the only thing that shifts.

### 1.2 Split `api/scan_service.py` into focused modules

```
api/services/
├── __init__.py
├── dwell.py        # dwell trail validation, continuous presence calculation
├── gps.py          # correct_gps_trail, GPS quality checks, speed/bearing/acceleration
├── anomalies.py    # sudden jump detection, GPS hop, drift, prolonged dwell flags
├── scoring.py      # probability scoring (weighted factors), progression-record check
├── fallback.py     # sensor fallback logic (NFC failure recovery via PIR/accel/proximity)
├── drift.py        # validate_timestamp_drift and time-drift anomaly logic
└── scan.py         # main scan processing pipeline that calls all the above
```

**Constraint:** `api/scan_service.py` must become a thin `scan.py` that calls `dwell.validate()`, `gps.correct_trail()`, `anomalies.detect()`, `scoring.compute()`, etc. Original logic preserved, just extracted.

### 1.3 Cache geofence and session lookups

Add `django-redis` to `requirements.txt` if not present.

In `guardtour/settings.py`:
- Add `CACHES` config pointing to redis (default `localhost:6379` for dev, env-var for prod)
- Add `REST_FRAMEWORK` throttle rates: device heartbeats at 30/min, scans at 60/min, admin at 120/min

In `api/views/` modules that query geofences or device states:
- Cache `MapObject` geofences per `organization_id` with 5-minute TTL
- Cache `DeviceSession` reads with 30-second TTL (write-through on every heartbeat)

Use `django.core.cache` directly. Do NOT add a new caching library.

### 1.4 Add transaction safety to heartbeat and scan paths

Wrap `register_device`, `heartbeat`, and `process_scan` in `transaction.atomic()`. Use `select_for_update()` on Device rows you modify inside those blocks to prevent lost writes under concurrent heartbeats.

---

## PHASE 2 — Zone Verification and State Machine

### 2.1 New models in `api/models.py` (additive, do not rename existing fields)

**`DeviceSession`**
- `device` — OneToOne FK to `Device`, `on_delete=CASCADE`, `related_name='session'`
- `session_token` — CharField, max_length=64, unique=True, db_index=True, default=uuid4_hex
- `state` — CharField, max_length=32, choices from explicit state list, default=`STATE_ON_ROUTE`
- `metadata` — JSONField, default=dict (stores `supports_gnss`, `supports_sensors`, etc.)
- `telemetry_interval_ms` — IntegerField, default=60000
- `constellation_required` — BooleanField, default=False
- `sensor_activation` — CharField, max_length=32, default=`none`
- `expires_at` — DateTimeField
- `last_seen_at` — DateTimeField, auto_now=True
- `created_at` — DateTimeField, auto_now_add=True

**`AlertRule`**
- `organization` — FK to `Organization`, `on_delete=CASCADE`
- `state` — CharField, max_length=32 (the device session state this rule applies to)
- `first_alert_minutes` — IntegerField, default=15
- `repeat_interval_minutes` — IntegerField, default=15
- `event_time_field` — CharField, default=`route.scheduled_start_time`, max_length=64
- `tts_enabled` — BooleanField, default=True
- `vibration_enabled` — BooleanField, default=True

**`MissionStateLog`** (append-only audit trail)
- `assignment` — FK to `ShiftAssignment`, `on_delete=CASCADE`, `related_name='state_logs'`
- `from_state` — CharField, max_length=32
- `to_state` — CharField, max_length=32
- `triggered_by` — CharField, max_length=32 (e.g. `heartbeat`, `scan`, `dispatcher`)
- `metadata` — JSONField, default=dict
- `created_at` — DateTimeField, auto_now_add=True

**State constants (use these exact strings everywhere):**
```python
STATE_AUTHENTICATED = 'authenticated'
STATE_ON_ROUTE = 'on_route'
STATE_CHECKPOINT_DUE = 'checkpoint_due'
STATE_COMPLETING = 'completing'
STATE_COMPLETED = 'completed'
STATE_EMERGENCY_PAUSE = 'emergency_pause'
STATE_OFFLINE_BUFFERING = 'offline_buffering'
STATE_SESSION_EXPIRED = 'session_expired'
```

### 2.2 State-aware heartbeat (`api/views/heartbeat.py`)

Rewrite heartbeat to:
1. Look up `DeviceSession`. Create default `STATE_ON_ROUTE` if missing (backfill).
2. Evaluate state transitions from:
   - Active `ShiftAssignment` presence (ASSIGNED → ON_ROUTE)
   - Scan outcomes (success/failure on last checkpoint)
   - Mission end time (ON_ROUTE → COMPLETING)
   - Device offline threshold (ON_ROUTE → OFFLINE_BUFFERING)
   - Dispatcher override (future stub: emergency button)
3. Look up `AlertRule` for current state + org. Compute next alert window.
4. Expand response dict with `session_state`, `mission_stage`, `telemetry` contract (see App Contract below).
5. Publish map residency event if device just entered a checkpoint radius (reuse `_heartbeat_geofence_tts` location logic, but publish to HTMX partial instead of just TTS).

### 2.3 Zone verification engine (`api/services/scan.py` + submodules)

This is the "magic of verification." Called from the scan endpoint.

**Pipeline order:**
1. **Tolerance nop gate** — `scan.timestamp` outside `[planned_time - tolerance_min, planned_time + tolerance_min + dwell_time]` → `validity_score = 0.0`, `verification_notes = "out_of_tolerance_window"`, DROP.
2. **Radius check** — default 5m, strict=2.5m, loose=10m. NOT 50m. If sensor confirms presence and state is `CHECKPOINT_DUE`, extend ceiling to 15m. Outside radius = `validity_score *= 0.3`, note `outside_radius`.
3. **Dwell trail validation** — pull last N minutes of `GpsBatch` points, walk for continuous presence inside radius. Compare against `checkpoint.dwell_time` (default 0). Insufficient dwell = `validity_score *= 0.5`.
4. **Anomaly detection** — sudden jump (>120 m/min), GPS hop (hdop 1.8 to >6.0), drift (>0.5 m/s constant inside radius), prolonged dwell (>2.5x expected). Each flag = `validity_score *= 0.6`.
5. **Sensor fallback** — if NFC weak but PIR+accel+proximity confirm presence, floor score at 0.75. If accel erratic or proximity <0.4, halve score.
6. **Probability scoring** — weighted sum across all factors (0.25 NFC + 0.20 radius + 0.25 dwell + 0.15 anomaly-free + 0.10 sensor + 0.05 timestamp drift).
7. **Progression-record degradation** — guard with <80% on-time ratio or avg validity <0.6 gets score capped at 0.7x.
8. **Mission stall penalty** — last checkpoint, stayed past `window_end + tolerance`, score *= 0.8.

**New ScanRecord fields to set:**
- `validity_score`
- `dwell_valid`
- `dwell_seconds`
- `insufficient_dwell_time`
- `anomaly_flags` (JSON list)
- `sensor_aided`
- `time_drift_seconds`
- `time_drift_suspicious`
- `verification_notes`

### 2.4 Map residency signal

When radius check passes in step 2:
- Call `publish_map_residency(device, checkpoint, confidence)` which uses the existing HTMX infrastructure to update `templates/partials/routes/map_residency.html` (or creates it if missing — ask before creating templates).

### 2.5 Sensor-aware scan endpoint

`api/views/scans.py` scan endpoint must accept and forward to scan service:
```json
{
  "session_token": "...",
  "nfc_value": "...",
  "lat": ..., "lng": ..., "accuracy": ...,
  "gps_metadata": {"hdop": ..., "satellites_used": ..., "constellations": {...}},
  "sensor_context": {"pir_triggered": true, "accel_pattern": "walking", "proximity_score": 0.94, "duration_seconds": 42},
  "gps_trail_last_30s": [...]
}
```

### 2.6 Telemetry contract in heartbeat

Heartbeat response must include:
```json
{
  "session_state": "checkpoint_due",
  "mission_stage": "active",
  "telemetry": {
    "gps_interval_ms": 5000,
    "constellation_required": true,
    "sensor_activation": "pir_plus_accel",
    "accuracy_min_meters": 5
  },
  "map_update": {"event": "zone_enter", "checkpoint_id": 42, "radius_m": 5, "confidence": 0.92}
}
```

The app reads `telemetry` and reconfigures `GpsCollector` interval + GNSS + sensors on next heartbeat. Backend dictates data volume.

---

## PHASE 3 — Migration + Seed

1. **Add missing DB fields**: `DeviceSession`, `AlertRule`, `MissionStateLog`, new `ScanRecord` fields.
2. **Backfill**: every existing `Device` gets a default `DeviceSession` with `state=STATE_ON_ROUTE`. Any existing `ScanRecord` gets `validity_score=1.0, dwell_valid=True` as a one-time backfill assumption.
3. **Correct checkpoint radii**: existing `Checkpoint` with `radius=50` and `precision_level=normal` → set to 5. If `precision_level` was explicitly set to `loose` or `strict`, honor the user's old intent and skip auto-fix.
4. **Seed `AlertRule`** per org: `ON_ROUTE` 15/15, `CHECKPOINT_DUE` 5/0, `COMPLETING` none.
5. **`makemigrations --check`** must pass clean.

---

## TDD Discipline (REQUIRED)

Write tests first. See them fail. Make minimal fix. Re-verify.

1. `test_tolerance_nop_gate`
2. `test_radius_defaults`
3. `test_dwell_trail_validation`
4. `test_anomaly_sudden_jump`
5. `test_anomaly_gps_hop`
6. `test_sensor_fallback_upgrades_score`
7. `test_sensor_mismatch_downgrades_score`
8. `test_probability_scoring_weighted`
9. `test_progression_record_degradation`
10. `test_prolonged_dwell_penalty`
11. `test_state_transitions`
12. `test_map_residency_event`
13. `test_mission_stall_penalty`

---

## Validation Checklist

1. All 13 new tests pass.
2. All 54 existing baseline tests still pass (no regression).
3. `python manage.py makemigrations --check` clean.
4. `python manage.py sqlmigrate` shows correct schema changes.
5. After refactor, `python -c "import api.views.heartbeat"` succeeds (all imports resolve).
6. No `import` in any file points to a deleted path. Old `from api.views.core import ...` patterns are all demolished.
7. `core.py` is < 300 lines.
8. `scan_service.py` is < 150 lines (thin orchestrator).
9. No cache call blocks writes (write-through pattern).
10. No template in `api/` was modified.

---

## Scope Guards

- Backend only. No templates/static/Android touches.
- Do NOT rename existing models or fields.
- Do NOT change functionality of auth, register, login endpoints.
- Do NOT add new third-party apps (only add Python packages to requirements.txt).
- Do NOT run Git operations.
- Do NOT start the server.
- REPORT first, fix second. If you hit contradictory constraints, stop and list them.

---

## Expected Output Format

When you finish, return to me in this exact order so I can review in-chat:

1. **DIFF SUMMARY** — file paths touched, one-line purpose each.
2. **MIGRATION PLAN** — new tables, new fields, backfills, corrections.
3. **NEW/CHANGED FILE MAP** — what goes where in the new structure.
4. **MODEL CODE** — `DeviceSession`, `AlertRule`, `MissionStateLog`.
5. **SERVICE CODE** — `scan.py`, `dwell.py`, `anomalies.py`, `scoring.py`, `fallback.py` implementations.
6. **VIEW CODE** — `heartbeat.py`, `scans.py` key logic.
7. **TEST CODE** — all 13 tests.
8. **REQUIREMENTS ADDITIONS** — new packages needed.
9. **SETTINGS CHANGES** — cache, throttle, any new config.
10. **RISK ASSESSMENT** — what could break in existing flows.
11. **OPEN QUESTIONS** — anything you couldn't decide.
