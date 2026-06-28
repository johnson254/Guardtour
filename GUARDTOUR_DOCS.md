# GuardTour — System Documentation

> **Version:** 1.0  
> **Last updated:** 24-Jun-2026  
> **Android target:** API 24-29 (Android 7-10), no Google Play Services required

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Web UI Pages](#3-web-ui-pages)
4. [Android App Features](#4-android-app-features)
5. [API Reference](#5-api-reference)
6. [End-to-End Workflow](#6-end-to-end-workflow)
7. [Data Model](#7-data-model)
8. [Deployment Checklist](#8-deployment-checklist)

---

## 1. System Overview

GuardTour is a security patrol management system. Guards carry Android devices that scan NFC tags at checkpoints. A web dashboard lets dispatchers create routes, assign guards, deploy missions, and monitor progress in real time.

**Core loop:**
```
Admin creates route + checkpoints → Deploys to guard → Guard scans NFC tags
→ Server records scans + calculates validity → Dispatch monitors live status
```

---

## 2. Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│   Android App        │     │   Django Backend     │     │   Web Dashboard      │
│  (Kotlin, no GPS)    │◄───►│  (DRF API, SQLite)   │◄───►│  (HTML/JS, manage)   │
│                      │     │                      │     │                      │
│  • NFC scanning      │     │  • REST API          │     │  • Route designer    │
│  • GPS tracking      │     │  • Scan processing   │     │  • Dispatch console  │
│  • TTS playback      │     │  • Validity scoring  │     │  • Live monitoring   │
│  • Offline buffering │     │  • Mission staging   │     │  • Reports           │
│  • Pin lock          │     │  • JWT auth          │     │  • Admin panel       │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

### Key Design Decisions

- **No Google Play Services** — GPS uses Android's built-in `LocationManager`. Works on Android 7-10 without Play Store.
- **Offline-first scanning** — NFC scans buffer locally when offline, sync when connected.
- **ID collisions** — Device operator IDs (e.g. `TCN-01`) are the same as `device_id`. The `register_device` endpoint matches `operator_id` against `Device.device_id`.
- **TTS ack** — The server clears `tts_pending` immediately on heartbeat response. Confirmation is tracked via `OperatorAlert.is_read`.
- **Multiple missions** — A device can have multiple active `ShiftAssignments`. The heartbeat returns all of them in `missions[]`.

---

## 3. Web UI Pages

All served from `http://<host>/` (no `/api/` prefix):

| Path | Page | Description |
|---|---|---|
| `/` | Login | Django session login |
| `/register/` | Register | Create new dispatcher/guard account |
| `/dashboard/` | Operations Hub | Live stats, on-duty guards, active deployments, daily routes |
| `/dispatch/` | Dispatch Console | Assign shifts, deploy guards, monitor missions |
| `/manage/` | Fleet & Personnel | Manage devices, guards, callsigns, checkpoints |
| `/routes/` | Blueprint Designer | Create routes with checkpoint sequences |
| `/incidents/` | Incidents | Report and track field incidents |
| `/analytics/` | Reports | Scan history, shift performance, density charts |
| `/map-view/` | Intelligence Map | Map-based view of checkpoints, assets, device trails |
| `/control/` | Admin Panel | System-wide settings, organization management |
| `/admin/` | Django Admin | Raw database access (superuser only) |

---

## 4. Android App Features

### 4.1 App Overview

The Android app is a **background service** with an optional dashboard activity. It runs persistently with a foreground notification.

**Package:** `com.example.guardtournfc`  
**Entry points:**
- `LoginActivity` — first screen, operator login + PIN setup
- `GuardDashboardActivity` — live status with missions, scans, GPS
- `MainActivity` — headless startup for permission requests (finishes immediately)
- `NfcScanService` — background service (heartbeat + NFC + TTS)
- `GpsCollector` — background GPS collection (no Play Services)

### 4.2 Feature List

| Feature | Description | File |
|---|---|---|
| **Operator Login** | Guard enters operator ID (e.g. `TCN-01`), sets 4-digit PIN. App registers via `POST /api/register-device/` with hardware info. | `LoginActivity.kt` |
| **PIN Lock** | 4-digit overlay locks the screen. Guard enters PIN to unlock. Re-lock via button. Survives activity restart. | `GuardDashboardActivity.kt` |
| **NFC Scanning** | Reads NFC tag UID or NDEF text. Sends to server with GPS + raw payload (UID, tech list, NDEF records, sensors). Buffers locally on failure. | `NfcScanService.kt` |
| **Raw NFC Payload** | Full tag data sent as `raw_nfc` JSON: UID, tech list, NDEF records, accelerometer + gyroscope values. Server uses this for peer-to-peer detection and validity scoring. | `NfcScanService.buildRawNfcPayload()` |
| **Body Sensors** | Accelerometer and gyroscope listeners registered in service. Latest values embedded in every scan's `raw_nfc.sensors`. | `NfcScanService.kt:93-101` |
| **GPS Tracking** | Background GPS collection via `LocationManager` (GPS + Network providers). Points stored locally in Room DB, uploaded in batches every 2 minutes via `POST /api/gps-batch/`. | `GpsCollector.kt` |
| **Heartbeat** | Every 60 seconds: sends device state (GPS, battery, callsign). Processes response directives: `fetch_nfc`, `fetch_gps`, `tts_pending`, `missions[]`. | `NfcScanService.startHeartbeat()` |
| **Mission Display** | Dashboard shows all active missions from `missions[]` array. Primary mission displayed first (►), additional missions listed (•). | `GuardDashboardActivity.renderHeartbeat()` |
| **TTS Playback** | Android TextToSpeech engine speaks `tts_pending` messages with locale, rate, pitch from server. Falls back to default locale on error. Queues messages if engine not ready. | `NfcScanService.speakTts()` |
| **Audio/Vibration** | Beep (ToneGenerator) + vibrate (200ms) on successful scan. `play_sound`/`vibrate` directives from heartbeat also trigger feedback. | `NfcScanService`, `GuardDashboardActivity` |
| **Offline Buffering** | Failed scans saved to Room `ScanBuffer` table. `SyncManager` uploads via `POST /api/scan-batch/` every 2 minutes. GPS points also buffered. | `NfcScanService.bufferScanLocal()`, `SyncManager` |
| **Boot Auto-Start** | `BootReceiver` starts NFC + GPS services on device boot. | `BootReceiver.kt` |
| **Last Known GPS** | Dashboard shows last GPS time and accuracy from Room DB. | `GuardDashboardActivity.updateGpsStatus()` |
| **Recent Scans** | Dashboard shows last 5 scans from server (checkpoint name + time). | `GuardDashboardActivity.renderScans()` |
| **Background Service** | Foreground service with persistent notification: shows mission count or route name. Runs even when app is closed. | `NfcScanService` |

### 4.3 Heartbeat Response Processing

The app processes these fields from `POST /api/heartbeat/`:

| Field | Processed by | Action |
|---|---|---|
| `status` | Dashboard | Shows Online/Offline |
| `guard_name` | Dashboard | Shows guard name |
| `callsign` | Dashboard | Shows operator ID |
| `battery_pct` | Dashboard | Shows battery level |
| `missions[]` | Dashboard + Service | Shows mission list + notification |
| `route_name` | Dashboard + Service | Primary mission name |
| `tts_voice` | Dashboard | "TTS: en-US" display |
| `tts_pending` | Service | Speaks message aloud |
| `tts_pending_voice` | Service | TTS voice locale |
| `tts_pending_rate` | Service | Speech rate |
| `tts_pending_pitch` | Service | Speech pitch |
| `fetch_nfc` | Service | Notification: "Server requested NFC scan" |
| `fetch_gps` | Service | Notification: "Server requested GPS" |
| `play_sound` | Dashboard | Plays beep |
| `vibrate` | Dashboard | Vibrates |

---

## 5. API Reference

### 5.1 Authentication

**JWT tokens** are used for API authentication. Set header:
```
Authorization: Bearer <access_token>
```

**Token lifetimes** (configurable in `settings.py`):
- Access token: 24 hours
- Refresh token: 7 days

**Session auth** is also used for server-rendered pages via `JwtTokenMiddleware`.

### 5.2 Endpoint Summary

#### AllowAny (device-facing)

| Method | URL | Purpose |
|---|---|---|
| POST | `/api/register-device/` | Device self-registration |
| POST | `/api/heartbeat/` | Device heartbeat + directives |
| POST | `/api/scans/` | Single NFC scan submission |
| POST | `/api/gps-batch/` | Offline GPS batch upload |
| POST | `/api/scan-batch/` | Offline scan batch upload |
| GET | `/api/mission-status/<id>/` | Single mission staging status |
| POST | `/api/register/` | Web user registration |
| POST | `/api/login/` | Web user login |

#### IsAuthenticated (web UI + dispatcher)

| Method | URL | Purpose |
|---|---|---|
| CRUD | `/api/organizations/` | Organizations |
| CRUD | `/api/admins/` | Admin profiles |
| CRUD | `/api/dispatchers/` | Dispatcher profiles |
| CRUD | `/api/guards/` | Guard/supervisor profiles |
| CRUD | `/api/callsigns/` | Device↔guard bindings |
| CRUD | `/api/devices/` | Device management |
| POST | `/api/devices/<id>/fetch_nfc/` | Request NFC fetch from device |
| POST | `/api/devices/<id>/fetch_gps/` | Request GPS fetch from device |
| POST | `/api/devices/<id>/send_tts/` | Send TTS to device |
| POST | `/api/devices/<id>/swap_operator/` | Swap device operator identity |
| CRUD | `/api/routes/` | Patrol route blueprints |
| POST | `/api/routes/<id>/deploy/` | Deploy route to assigned personnel |
| CRUD | `/api/checkpoints/` | Checkpoint assets |
| CRUD | `/api/shifts/` | Shift assignments/missions |
| CRUD | `/api/map-objects/` | Map POIs/geofences |
| POST | `/api/map-objects/bulk_create/` | Bulk create map objects |
| CRUD | `/api/incidents/` | Field incident reports |
| CRUD | `/api/alerts/` | Operator alerts/TTS queue |
| GET | `/api/deployment-checkpoint-live/` | Live mission status dashboard |
| GET | `/api/org-stats/` | Organization statistics |
| GET | `/api/profiles/` | List guard profiles |
| GET/PUT/DELETE | `/api/profiles/<id>/` | Profile detail/edit/delete |
| POST | `/api/provision-device/` | Provision device to guard |
| POST | `/api/end-shift/<id>/` | End shift assignment |
| POST | `/api/scan-guards/` | Create scan-only guard |
| POST | `/api/resend-tts/` | Resend TTS announcement |
| GET | `/api/blueprint-shift-availability/` | Shift availability per route |
| POST | `/api/assign-guard-to-blueprint-shift/` | Assign guard to shift |
| GET | `/api/device-trails/<device_id>/` | Device GPS trail history |
| GET | `/api/operator-id-next/` | Next available operator ID |

#### Admin-only

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/admin-stats/` | System-wide statistics |

### 5.3 Key Endpoint Details

#### `POST /api/register-device/`

**Purpose:** First thing the Android app calls after the guard enters their operator ID.

```
Request:  { "operator_id": "TCN-01", "hardware_info": { "os_version": "...", ... } }
Response: { "status": "registered", "device_id": "TCN-01", "password": "84920371" }
```

The server looks up `Device.objects.filter(device_id=operator_id)`. The device must have been pre-created in the web UI with that Login Code.

#### `POST /api/heartbeat/`

**Purpose:** Periodic device check-in. Sends device state, receives missions + directives.

```
Request:  { "device_id": "TCN-01", "password": "84920371", "battery_pct": 85, "lat": 40.71, "lng": -74.00 }
Response: {
  "status": "ok",
  "callsign": "TCN-01",
  "guard_name": "John Doe",
  "missions": [
    { "assignment_id": 5, "route_id": 3, "route_name": "Morning Patrol", "shift_type": "Day" }
  ],
  "route_name": "Morning Patrol",
  "tts_voice": "en-US",
  "tts_pending": "Proceed to Gate checkpoint",
  "tts_pending_voice": "en-US",
  "fetch_nfc": true
}
```

#### `POST /api/scans/`

**Purpose:** Submit a single NFC tag scan with full context.

```
Request: {
  "device_id": "TCN-01",
  "password": "84920371",
  "nfc_value": "TAG-GATE",
  "lat": 40.7128,
  "lng": -74.0060,
  "raw_nfc": {
    "uid": "04:A2:B3:C4",
    "tech": ["android.nfc.tech.NfcA", "android.nfc.tech.Ndef"],
    "ndef_records": [{"tnf": 1, "type": "TEXT", "payload_text": "TAG-GATE"}],
    "sensors": { "accelerometer": [0.1, 9.8, 0.2], "gyroscope": [0.01, 0.0, -0.01] }
  }
}
Response: { "id": 123, "checkpoint_name": "Gate", "nfc_value": "TAG-GATE", "is_on_time": true, "validity_score": 0.85, "validity_reason": "Within 5m of checkpoint; Movement plausible (80 m/min)" }
```

The server:
1. Authenticates device
2. Parses raw NFC (detects peer handshake vs tag)
3. Checks 30s cooldown
4. Resolves checkpoint by nfc_tag, scoped to device's active route
5. Calculates validity score from GPS proximity + movement + battery
6. Creates ScanRecord
7. Updates guard's last_scan + nfc_tags_scanned

#### `POST /api/devices/<id>/send_tts/`

**Purpose:** Queue a TTS message for a specific device.

```
Request:  { "message": "Gate breach detected at Sector 7", "tts_voice": "en-US", "tts_rate": 1.2 }
Response: { "status": "queued", "message": "TTS queued for TCN-01: Gate breach detected at Sector 7" }
```

Also creates an `OperatorAlert` if the device has an active assignment with a guard.

#### `GET /api/deployment-checkpoint-live/`

**Purpose:** Real-time mission status for dispatch console.

```
Response: {
  "items": [
    {
      "assignment_id": 5,
      "route_name": "Morning Patrol",
      "logic_type": "Scheduled",
      "device_name": "TCN-01",
      "guard_supervisor_name": "John Doe",
      "has_missed_checkpoints": false,
      "next_checkpoint": {
        "name": "Gate",
        "planned_time": "18:30:00",
        "time_remaining_seconds": 540,
        "dwell_time_minutes": 5,
        "dwell_remaining_seconds": 300,
        "is_present": false,
        "is_window_missed": false
      },
      "alert_config": {
        "send_start_alert": true,
        "start_alert_lead_time": 15,
        "send_announcement": true,
        "readout_text": "Begin patrol at Gate",
        "scheduled_start_time": "18:00"
      }
    }
  ]
}
```

---

## 6. End-to-End Workflow

### Step 1: Create an Organization

```bash
# Via Django admin or API:
POST /api/organizations/
{"name": "TwoCan Security", "code": "TCN"}
```

### Step 2: Create a Guard Profile

```bash
POST /api/scan-guards/
{"first_name": "John", "last_name": "Doe", "role": "guard", "shift": "Day"}
```

### Step 3: Create a Device (in Web UI)

1. Go to `/manage/` → Fleet tab
2. Click "Register Device"
3. Set Login Code: `TCN-01` (this is the operator ID the guard will type)
4. Set password or leave blank for auto-generate (8 digits)
5. Assign to organization
6. (Optional) Assign initial operator

The server auto-creates a `CallSign` record linking device ↔ callsign.

### Step 4: Log in on Android App

1. Guard opens app
2. Types operator ID: `TCN-01`
3. Sets 4-digit PIN (e.g. `1234`)
4. App calls `POST /api/register-device/` with operator_id
5. Server returns `device_id: "TCN-01"` + `password: "84920371"`
6. App stores credentials, starts NFC + GPS services

### Step 5: Create a Route with Checkpoints

```bash
POST /api/routes/
{
  "name": "Morning Patrol",
  "organization": 1,
  "status": "active",
  "logic_type": "Scheduled",
  "scheduled_start_time": "18:00",
  "assigned_guards": [1],
  "assigned_devices": [1],
  "checkpoints": [
    {"name": "Gate", "checkpoint_type": "nfc", "nfc_tag": "TAG-GATE", "order": 1, "planned_time": "18:30", "time_tolerance": 15, "dwell_time": 5, "lat": 40.7128, "lng": -74.0060},
    {"name": "Lobby", "checkpoint_type": "nfc", "nfc_tag": "TAG-LOBBY", "order": 2, "planned_time": "19:00", "time_tolerance": 10}
  ]
}
```

### Step 6: Deploy the Mission

```bash
POST /api/routes/<route_id>/deploy/
# Response: { "status": "deployed", "assignments_count": 1 }
```

This creates a `ShiftAssignment` with `is_active=True`. The guard now has an active mission.

### Step 7: Heartbeat picks up the mission

The Android app's background service sends a heartbeat. The server responds:
```json
{
  "missions": [{"assignment_id": 5, "route_id": 3, "route_name": "Morning Patrol", "shift_type": "Day"}],
  "route_name": "Morning Patrol"
}
```

The dashboard shows: `► Morning Patrol (Day)`

### Step 8: Guard scans NFC tags

Guard taps phone to checkpoint NFC tag. The app:
1. Reads the tag (UID + NDEF text)
2. Gets latest GPS location from Room DB
3. Builds raw NFC payload (UID, tech list, NDEF, accelerometer/gyroscope)
4. Sends `POST /api/scans/` with all data
5. On success: plays beep + vibrates
6. On failure: buffers to Room DB for later sync

Server processes the scan:
- Matches `nfc_value` against checkpoints in the device's active route
- Checks 30s cooldown
- Calculates validity score (GPS proximity + movement + battery)
- Creates ScanRecord
- Advances mission progress

### Step 9: Monitor in Dispatch Console

`GET /api/deployment-checkpoint-live/` shows real-time status:
- Which checkpoint is next
- Time remaining
- Dwell countdown
- Missed windows
- Auto-completes when all checkpoints done or deadlines passed

### Step 10: Mission Completion

The mission auto-completes when:
- All checkpoints are scanned (hit_count = total)
- OR all checkpoints are past their deadlines (missed + hit = total)

```python
all_done = (not next_cp) or (hit_count + missed_count >= total)
if all_done:
    assignment.is_completed = True
    assignment.is_active = False
```

---

## 7. Data Model

### Core Entities

| Model | Purpose | Key Fields |
|---|---|---|
| **Organization** | Tenant/company | `name`, `code` (e.g. "TCN"), `is_active` |
| **GuardSupervisor** | Guard or supervisor profile | `first_name`, `last_name`, `callsign`, `role`, `shift`, `is_on_shift` |
| **Device** | Hardware device | `device_id` (operator ID), `password`, `is_online`, `battery_pct`, `tts_pending`, `tts_voice/rate/pitch` |
| **CallSign** | Device↔guard binding (source of truth) | `callsign`, `device` (OneToOne), `current_guard` |
| **PatrolRoute** | Blueprint/mission template | `name`, `status`, `enforce_order`, `enforce_time`, `is_audit`, `is_geofence`, `tts_voice/rate/pitch` |
| **Checkpoint** | Waypoint on a route | `name`, `nfc_tag`, `lat`, `lng`, `checkpoint_type`, `order`, `planned_time`, `time_tolerance`, `dwell_time`, `radius` |
| **ShiftAssignment** | Active deployment/mission | `guard_supervisor`, `device`, `route`, `is_active`, `is_completed`, `shift_type`, `scheduled_date` |
| **ScanRecord** | Single NFC scan event | `device`, `guard_supervisor`, `checkpoint`, `route`, `nfc_value`, `lat`, `lng`, `is_on_time`, `validity_score`, `validity_reason`, `raw_nfc` (JSON), `scan_type` |
| **OperatorAlert** | TTS/alert queue | `operator`, `title`, `message`, `priority`, `play_sound`, `vibrate`, `tts_voice/rate/pitch`, `is_read` |
| **DeviceTrail** | GPS breadcrumb | `device`, `lat`, `lng`, `accuracy`, `speed`, `bearing`, `recorded_at`, `is_corrected` |

### Key Relationships

```
Organization
  ├── Device (FK)
  ├── GuardSupervisor (FK)
  ├── PatrolRoute (FK)
  ├── Checkpoint (FK, standalone assets)
  ├── CallSign (FK, device binding registry)
  ├── OperatorAlert (FK)
  └── IncidentReport (FK)

PatrolRoute
  ├── Checkpoint (FK, ordered waypoints)
  ├── assigned_guards (M2M GuardSupervisor)
  └── assigned_devices (M2M Device)

ShiftAssignment
  ├── guard_supervisor (FK, nullable for device-only)
  ├── device (FK)
  ├── route (FK)
  └── dispatcher (FK User)

ScanRecord
  ├── device (FK, SET_NULL)
  ├── guard_supervisor (FK)
  ├── checkpoint (FK, SET_NULL — preserves audit trail)
  └── route (FK)
```

### Staging Logic (`deployment_checkpoint_live`)

```
For each active ShiftAssignment:
  1. Get all checkpoints ordered by `order`
  2. Get set of scanned checkpoint IDs since assigned_at
  3. next_cp = first checkpoint not in hit set
  4. For each pending checkpoint:
     - Timed: deadline = planned_time + time_tolerance + dwell_time
     - Untimed: deadline = shift_end (6PM Day / 6AM Night / +24h device)
     - If now > deadline: mark missed
  5. If no next_cp OR (hit + missed >= total): auto-complete
```

### Validity Scoring (`calculate_scan_validity`)

| Factor | Max Score | Condition |
|---|---|---|
| GPS proximity to checkpoint | 0.6 | Distance < radius = full, < 3x radius = half |
| Device GPS history consistency | 0.15 | Current location within 200m of device's last known |
| Movement plausibility | 0.25 | Speed < 500 m/min from last scan |
| Low battery penalty | -0.1 | Battery ≤ 15% |

Score is clamped to [0.0, 1.0].

---

## 8. Deployment Checklist

### Backend Setup

- [ ] Change `SECRET_KEY` in `guardtour/settings.py`
- [ ] Set `DEBUG = False`
- [ ] Set `ALLOWED_HOSTS` to specific domains
- [ ] Set `SESSION_COOKIE_SECURE = True` (HTTPS only)
- [ ] Configure proper database (not SQLite for production)
- [ ] Reduce `ACCESS_TOKEN_LIFETIME` from 24h to 30min
- [ ] Add rate limiting for AllowAny endpoints
- [ ] Configure `LOGGING` for error tracking
- [ ] Set `CORS_ALLOWED_ORIGINS` instead of `CORS_ALLOW_ALL_ORIGINS`

### Android App Configuration

- [ ] Update `AppConstants.BASE_URL` to production server URL
- [ ] Remove `usesCleartextTraffic="true"` from `AndroidManifest.xml` (HTTPS only)
- [ ] Update `build.gradle.kts` versionCode/versionName for releases
- [ ] Enable minification (`isMinifyEnabled = true`) for release builds

### First-Time Setup

1. Create Organization (via `/admin/` or API)
2. Create Admin user (via `/register/` or `/admin/`)
3. Create Guard profile (via `/manage/` → Guards tab)
4. Create Device with Login Code (via `/manage/` → Fleet tab)
5. Create Route with checkpoints (via `/routes/`)
6. Assign guard + device to route
7. Deploy route
8. Guard logs into Android app with operator ID
9. Guard scans NFC checkpoints
10. Monitor via `/dispatch/` or `/api/deployment-checkpoint-live/`
