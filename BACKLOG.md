# Backlog — Feature Requests & Backend+App Mismatches

## How to read this

- **🔴 Fix needed** = Logic bug that causes incorrect behavior
- **🟡 Enhancement** = New capability needed on backend or app
- **🟢 Design** = Intentional but worth documenting
- **✅ DONE** = Implemented in this session

---

## 0. Completed in This Session

| Item | What was done | Files changed |
|------|---------------|---------------|
| 1.1 — Password generation | Backend now generates + persists password on `register_device` if device has none. Android uses server-returned password. | `api/views.py`, `LoginActivity.kt` |
| 1.2 — route_id in scans | Android reads `route_id` from heartbeat → stores in prefs → sends in `sendScanFull` + `bufferScanLocal` | `NfcScanService.kt`, `ApiManager.kt`, `SharedPreferencesManager.kt`, `AppConstants.kt` |
| 1.3 — verification_key | Android now sends `verification_key` in scan requests | `ApiManager.kt` |
| 1.5 — Persist TTS for retry | Lead-time reminder + geofence TTS now save `device.tts_pending` before returning | `api/views.py` |
| 9.1 — Dual heartbeat TTS | Dashboard no longer sends heartbeats — only displays GPS + recent scans. Single heartbeat in `NfcScanService` | `GuardDashboardActivity.kt` |
| 9.2 — Ack clear before HTTP | Ack flag now cleared only after successful HTTP response | `ApiManager.kt` |
| 9.3 — TTS delivery/ack ordering | `_heartbeat_tts_ack` now runs before `_heartbeat_tts_delivery` — no duplicate TTS | `api/views.py` |
| 9.4 — `_original_index` in batch sync | Backend now includes `_original_index` in scan batch results | `api/views.py` |
| 9.5 — peer_key in offline sync | Android sends `verification_key` (read as `verification_key` or `peer_key`) in batch sync | `api/views.py`, `SyncManager.kt` |
| 9.6 — SyncManager scope leak | `NfcScanService` now holds reference to `SyncManager` and calls `stop()` on destroy | `NfcScanService.kt` |
| 9.7 — extractNdefText NPE | Null-check for `ndefMessage` + empty payload guard | `NfcScanService.kt` |
| 9.8 — Empty payload AIOOBE | Check `payload.isEmpty()` before indexing | `NfcScanService.kt` |
| 9.10 — route_id from heartbeat | Android reads `route_id` from heartbeat response and stores it | `NfcScanService.kt`, `SharedPreferencesManager.kt` |
| 9.11 — routeId in bufferScanLocal | `bufferScanLocal` now receives and sets `routeId` | `NfcScanService.kt` |
| 10.1 — hit_count NameError | `hit_count = len(hit_cp_ids)` added to `deployment_checkpoint_live` | `api/views.py` |
| 10.2 — resolve_asset org filter | `resolve_asset` now accepts `organization` param and filters by org | `api/scan_service.py` |
| 10.3 — foregroundServiceType | Documented — deferred to API 34 build (not needed on API 29 target) | `AndroidManifest.xml` (no change needed for API 29) |
| 10.4 — ACTION_TAG_DISCOVERED | Added to `onStartCommand` check + manifest intent filter | `NfcScanService.kt`, `AndroidManifest.xml` |
| 10.7 — scheduled_date in dispatch POST | Dispatch page POST now sets `scheduled_date=today` | `api/views.py` |
| 10.8 — Deactivate device assignments | Dispatch POST now deactivates previous device assignments too | `api/views.py` |
| 10.9 — Set org in register_device | `register_device` now infers org from CallSign if missing | `api/views.py` |
| 10.13 — Persist geofence TTS | Geofence TTS now saves `device.tts_pending` | `api/views.py` |
| §8 — HCE peer-to-peer NFC | New `PeerHceService.kt` (HostApduService), heartbeat sends `peer_mode` directives, manifest registers HCE service | `PeerHceService.kt`, `NfcScanService.kt`, `AndroidManifest.xml`, `peer_apdu_service.xml`, `api/views.py`, `api/models.py` |
| §11 — sdk_int storage | Android sends `sdk_int` in registration, backend stores on Device model | `LoginActivity.kt`, `api/models.py`, `api/views.py` |
| §12 — shift_mode | `Organization.shift_mode` field added (default `'simple'`), migration created, serializer updated | `api/models.py`, `api/serializers.py`, migration `0066` |

**APK built:** `GuardTourNFC/app/build/outputs/apk/debug/app-debug.apk` (3.3MB)
**Backend tests:** 10/10 pass
**Migration:** `0066_add_sdk_int_shift_mode_nfc_mode.py` applied

---

## 1. Frontend ↔ Backend Logic Mismatches (from graph analysis)

### 1.1 🔴 Client-Side Password Generation Breaks Auth
**Android:** `LoginActivity.kt:156-159`  
**Backend:** `api/views.py:216-239` (`register_device`)  
When backend returns empty `password` (device created in admin without one), Android generates `(10000000 + random)` locally. Backend never persists this — `device.password` stays empty. Every subsequent request (heartbeat, scans) compares `""` vs the generated password → **401 auth failure on all calls**.

### 1.2 🔴 Missing `route_id` in Android Scan Requests
**Android:** `ApiManager.kt:91-101` (`sendScanFull`)  
**Backend:** `api/scan_service.py:302-341` (`process_scan`)  
Android builds scan body with `device_id`, `password`, `nfc_value`, `lat`, `lng`, `raw_nfc` — **no `route_id`**.  
Backend reads `route_id` (always `None`) → `resolve_assignment()` falls back to `order_by('-assigned_at').first()` → scans attributed to wrong route when device has multiple active assignments.  
Same issue in offline sync (`NfcScanService.kt:289-296` — `bufferScanLocal` never sets `routeId`).

### 1.3 🔴 Missing `verification_key` (Peer-to-Peer Scan Broken)
**Android:** `ApiManager.kt:91-101`  
**Backend:** `api/views.py:1018`  
Android never sends `verification_key`. Backend reads it as `None`. `validate_peer_exchange()` cannot function — peer-to-peer auditing dead on arrival.

### 1.4 🟡 Unused `callsign` / `operator_id` in Heartbeat Request
**Android:** `ApiManager.kt:80-81` — sends `callsign` and `operator_id` in every heartbeat  
**Backend:** `api/views.py:316-369` — never reads these fields. Identity resolved from `CallSign` model, not heartbeat payload. Wasted bandwidth.

### 1.5 🟡 TTS Reminder Lost on Network Error
**Backend:** `api/views.py:446-458`  
Lead-time reminder sets `directives['tts_pending']` in the response but does **not** save `device.tts_pending` to DB. If device misses the heartbeat response, the TTS message is lost forever. Manual TTS (via `send_tts`) correctly saves `device.tts_pending = msg`, enabling retry.

### 1.6 🟡 Error Responses Silently Discarded
**Android:** `LoginActivity.kt:120-128` and all `postJson()` callers  
Backend returns `{'detail': 'Operator ID not found...'}` with 404. Android sees non-2xx, returns `null`, caller shows "Connection failed - check network". **All server error details hidden**. Happens on every API call.

### 1.7 🟡 Password Sent as GET Query Parameter
**Android:** `ApiManager.kt:121-135`  
`device-scans` endpoint calls `URL("${DEVICE_SCANS_URL}?device_id=$deviceId&password=${URLEncoder.encode(password)}&_=${timestamp}")`. Password exposed in server logs, browser history, referrer headers.

### 1.8 🟢 GPS Corrected Data Ignored
**Backend:** `api/views.py:2184-2193` — `gps_batch_sync` returns `corrected` array of smoothed positions  
**Android:** `SyncManager.kt:54-58` — only checks `result.isSuccess`, marks points synced. Corrected data never applied to local Room DB.

### 1.9 🟢 `device_id` Sent in Registration but Unused
**Android:** `ApiManager.kt:50` — sends `device_id` from prefs  
**Backend:** `api/views.py:216-239` — never reads `device_id` from body, only uses `operator_id`

### 1.10 🟢 `mission-status` Endpoint Never Called
**Backend:** `api/views.py:2064-2090` — exists but no Android caller. Returns next checkpoint, dwell state, time remaining, missed windows.

### 1.11 🟢 Dead Code — `guard_name` Persisted but Never Used
**Android:** `AppConstants.kt:21`, `SharedPreferencesManager.kt:28-29` — `saveGuardName()`/`getGuardName()` exist but are never called. Guard name only rendered inline from heartbeat response.

### 1.12 🟢 NFC Hex Case Inconsistency
When no NDEF text present:
- `NfcScanService.kt:247`: `tag.id.joinToString("") { "%02x".format(it) }` → **lowercase**, no separators
- `NfcScanService.kt:304` (raw_nfc uid): `tag.id.joinToString(":") { "%02X".format(it) }` → **UPPERCASE** with colons
- Backend `parse_nfc_payload()`: `uid.replace(':', '').lower()` → lower, no separators  
Coincidentally consistent but fragile.

### 1.13 🟢 Duplicate Catch Block
**Android:** `ApiManager.kt:51-57` — try and catch blocks execute **identical code**: `put("hardware_info", JSONObject(hardwareInfo))`. Catch would throw the same exception.

### 1.14 🟢 `ensureDeviceRegistered()` is a No-Op
**Android:** `NfcScanService.kt:153-158` — comment says "not a no-op" but body is completely empty.

---

## 2. Feature: TTS Profiles & Voice Selection

### 2.1 TTS Voice Profiles
**Request:** Save TTS configurations as reusable profiles (not just per-route settings).

**Suggested model:**

```
TtsProfile
  id              PK
  organization    FK -> Organization
  name            "Male Deep", "Female Clear", "Custom 1"
  voice           "en-US", "en-GB", etc.
  rate            0.5 - 2.0
  pitch           0.5 - 2.0
  is_default      bool
```

**Backend changes needed:**
- New model `TtsProfile` with org scope
- Admin CRUD via API (or manage.html)
- Route gets optional `tts_profile` FK
- Heartbeat returns profile fields merged with route overrides

**Android changes needed:**
- Read `tts_pending_voice`, `tts_pending_rate`, `tts_pending_pitch` from heartbeat
- Apply to `TextToSpeech` engine (currently only uses route-level defaults)

### 2.2 Male Voice Option
**Request:** Specifically a male voice option.

**Implementation:**
- Add a `gender` field to TTS profile or route: `'male'`, `'female'`, `'default'`
- On Android, filter `TextToSpeech` engines by `gender` via `Voices` API (API 21+):
  ```kotlin
  val voice = TextToSpeech.Engine().voices?.find { it.gender == Voice.GENDER_MALE }
  ```
- Fallback: use locale-based heuristics (some locales default to male/female)

### 2.3 TTS Acknowledgement Status in Web UI
**Request:** See in the web UI whether a TTS message has been spoken (acked) by the device.

**Backend already has:**
- `device.tts_pending` — current queued message
- `device.tts_acked` — bool, set to `True` when device confirms
- `device.tts_pending_at` — when it was queued

**What's missing:**
- Display in `manage.html` device detail panel: "Last TTS: [message] — Spoken ✅ / Pending ⏳ / Failed ❌"
- Show history of past TTS messages with ack status

---

## 3. Feature: Peer-to-Peer NFC Without Screen Tapping

### 3.1 Problem
Android Beam requires tapping the screen to confirm each scan. It's deprecated on API 29+ and removed on many OEM builds. Devices with different Android versions can't Beam to each other. We need peer-to-peer NFC that works hands-free across all API levels.

### 3.2 Solution: Server-Negotiated HCE
See **§8** for the full technical design. Summary:

- **HCE (Host Card Emulation)** — API 19+, no screen tap, works on all target Android versions
- Server assigns roles via heartbeat: target device emulates an NFC tag, auditor reads it
- Server stores `sdk_int` on each device for feature gating and diagnostics
- No Beam fallback needed — HCE is universal across both builds (API 29 and API 34)
- Server-side verification unchanged — `raw_nfc` dump still sent, `validate_peer_exchange` still validates

---

## 4. Feature: NFC Scan Dump in Manage Device

### 4.1 Request
See all NFC scans for a specific device in the web UI (`manage.html` device panel), including raw NFC payload dump.

### 4.2 What exists
- `ScanRecord` model stores `raw_nfc` (JSONField), `nfc_value`, `timestamp`, `checkpoint`, `route`, `lat`, `lng`, `validity_score`, `validity_reason`
- `DeviceViewSet` has `device_recent_scans` endpoint (`views.py:2328-2349`)
- Device scans endpoint: `GET /api/device-scans/?device_id=X&password=Y`

### 4.3 What's needed

**Backend:**
- New endpoint or extend existing to return full raw_nfc dump per device
- Include: tag UID, NDEF records, tech list, sensor data, GPS
- Admin-only access (not device-password auth)

**Frontend (manage.html):**
- New tab or section in device detail panel: "NFC Scans"
- Table: Timestamp | Checkpoint | Route | NFC Tag | Validity | Actions
- Click to expand raw_nfc JSON viewer
- Include TTS section showing pending/acked history

### 4.4 Mockup idea

```
┌─────────────────────────────────────────────────────────┐
│  Device: GT-TEST001                            [Back]  │
├─────────────────────────────────────────────────────────┤
│  [Info] [Missions] [TTS] [NFC Scans] [Settings]        │
├─────────────────────────────────────────────────────────┤
│  NFC Scans (47 total)                      [Export]     │
│                                                         │
│  ┌────────┬──────────┬────────┬──────┬────────┬──────┐  │
│  │ Time   │Checkpoint│ Route  │ Tag  │Valid%  │ Raw  │  │
│  ├────────┼──────────┼────────┼──────┼────────┼──────┤  │
│  │ 09:15  │ Gate     │Mornin..│TAG-..│ 92%    │ ▶    │  │
│  │ 08:30  │ Lobby    │Mornin..│TAG-..│ 85%    │ ▶    │  │
│  └────────┴──────────┴────────┴──────┴────────┴──────┘  │
│                                                         │
│  ▶ Expanded raw_nfc:                                     │
│  {                                                       │
│    "uid": "04:2A:6B:ED:8C:12:F3",                       │
│    "tech": ["NfcA", "MifareClassic", "Ndef"],           │
│    "ndef": [{ "tnf": 1, "type": "T", "payload": "..." }]│
│    "sensors": { "accel": {...}, "gyro": {...} }         │
│  }                                                       │
└─────────────────────────────────────────────────────────┘
```

---

## 5. Feature: TTS Setup in Manage Device Panel

### 5.1 Request
Configure TTS (voice, rate, pitch, test playback, profile selection) from the device management page in the web UI.

### 5.2 What exists
- Route-level TTS fields: `tts_voice`, `tts_rate`, `tts_pitch`
- Device-level TTS fields: `tts_voice`, `tts_rate`, `tts_pitch`, `tts_pending`, `tts_acked`
- `send_tts` action on `DeviceViewSet`
- Heartbeat returns route TTS config + processes TTS ack

### 5.3 What's needed

**Backend:**
- Device-level TTS defaults should serve as fallback when route has no explicit TTS config
- Endpoint to test TTS: POST `/api/devices/{id}/test-tts/` → queues a test message
- Return TTS status in device detail endpoint

**Frontend (manage.html):**
- TTS section in device detail panel:
  - Dropdown: TTS Profile (from profiles in §2.1)
  - Sliders: Rate (0.5-2.0), Pitch (0.5-2.0)
  - Voice selector: "en-US Female", "en-GB Male", etc.
  - "Test TTS" button → queues test message
  - Status: "Last TTS: Spoken ✅ at 09:15" / "Pending ⏳"
  - History: list of recent TTS messages with ack timestamps

---

## 6. Body Sensors & Telemetry Not Available

### 6.1 Why body sensor data isn't being sent
**Root cause:** The Android app never registers a `SensorEventListener` or requests the `BODY_SENSORS` permission.

**What the backend supports** (`api/models.py:344`):
- `raw_nfc` JSON field stores `sensors` sub-object with accelerometer + gyroscope readings
- `validity_score` (0.0-1.0) uses movement plausibility — if no sensor data, score is low

**What's missing on Android:**

| Sensor | Permission | API | Status |
|--------|-----------|-----|--------|
| Accelerometer | None (regular sensor) | `Sensor.TYPE_ACCELEROMETER` | ❌ Not registered |
| Gyroscope | None (regular sensor) | `Sensor.TYPE_GYROSCOPE` | ❌ Not registered |
| Magnetometer | None | `Sensor.TYPE_MAGNETIC_FIELD` | ❌ Not registered |
| Step counter | `ACTIVITY_RECOGNITION` (API 29+) | `Sensor.TYPE_STEP_COUNTER` | ❌ Not registered |
| Heart rate | `BODY_SENSORS` (dangerous) | `Sensor.TYPE_HEART_RATE` | ❌ Not registered |

**Implementation needed in `NfcScanService.kt` or `GpsCollector.kt`:**
```kotlin
// Register sensor listener
val sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_NORMAL)

// Store latest readings
override fun onSensorChanged(event: SensorEvent) {
    latestSensorData[event.sensor.type] = event.values.clone()
}

// Attach to raw_nfc on scan
rawNfc.put("sensors", JSONObject(mapOf(
    "accel" to latestSensorData[Sensor.TYPE_ACCELEROMETER],
    "gyro" to latestSensorData[Sensor.TYPE_GYROSCOPE]
)))
```

### 6.2 Why telephony info isn't being sent
**Root cause:** `READ_PHONE_STATE` is a **dangerous permission** (requires user grant at runtime). The app requests it in `AndroidManifest.xml` but never actually calls telephony APIs.

**Available telephony fields** (backend model `Device` has these fields already):
- `imei` — requires `READ_PHONE_STATE` permission + deprecated on API 29+
- `imsi` — requires `READ_PHONE_STATE` + deprecated on API 29+
- `sim_phone_number` — requires `READ_PHONE_STATE` + `READ_SMS` on newer APIs
- `os_version` — `Build.VERSION.RELEASE` (no permission needed) — ✅ already sent in hardware_info
- `manufacturer` — `Build.MANUFACTURER` (no permission needed) — ✅ already sent
- `model` — `Build.MODEL` (no permission needed) — ✅ already sent

**Problem:** IMEI/IMSI are deprecated from API 29+ (Android 10+). The API returns null or throws SecurityException. Even on older devices, the user must explicitly grant `READ_PHONE_STATE` which many reject.

**What can be sent without permission:**
```kotlin
hardware_info.put("os_version", Build.VERSION.RELEASE)         // ✅ already sent
hardware_info.put("manufacturer", Build.MANUFACTURER)           // ✅ already sent
hardware_info.put("model", Build.MODEL)                         // ✅ already sent
hardware_info.put("build_id", Build.DISPLAY)                    // easy add
hardware_info.put("sdk_int", Build.VERSION.SDK_INT)             // easy add
hardware_info.put("wifi_mac", /* requires LOCATION permission */) // harder
hardware_info.put("bluetooth_mac", /* requires BLUETOOTH permission */) // harder
```

**Recommendation:** Stop trying to get IMEI/IMSI (deprecated/unreliable) and instead expand hardware_info with what's freely available: `build_id`, `sdk_int`, `board`, `bootloader`, `radio_version`, `fingerprint` — all from `Build` class, no permissions needed.

---

## 7. Feature: Default NFC App Confirmation on Tag Tap

### 7.1 Request
When the user taps an NFC tag, show a confirmation prompt: "Use GuardTour as the default NFC app for this action?" — especially important when multiple NFC apps are installed.

### 7.2 Implementation

**Android approach** (no backend changes needed):

**Option A — NFC Foreground Dispatch (recommended)**
```kotlin
// In NfcScanService or MainActivity
override fun onCreate() {
    super.onCreate()
    nfcAdapter = NfcAdapter.getDefaultAdapter(this)
}

override fun onResume() {
    super.onResume()
    val intent = Intent(this, javaClass).apply {
        addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
    }
    val pendingIntent = PendingIntent.getActivity(this, 0, intent,
        PendingIntent.FLAG_IMMUTABLE)
    val filters = arrayOf(
        IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED),
        IntentFilter(NfcAdapter.ACTION_TECH_DISCOVERED),
        IntentFilter(NfcAdapter.ACTION_TAG_DISCOVERED)
    )
    nfcAdapter?.enableForegroundDispatch(this, pendingIntent, filters, null)
}

// Prompt on first tap
private var nfcDefaultPromptShown = false

override fun onNewIntent(intent: Intent) {
    if (NfcAdapter.ACTION_TAG_DISCOVERED == intent.action ||
        NfcAdapter.ACTION_TECH_DISCOVERED == intent.action ||
        NfcAdapter.ACTION_NDEF_DISCOVERED == intent.action) {

        if (!nfcDefaultPromptShown) {
            AlertDialog.Builder(this)
                .setTitle("NFC Scan")
                .setMessage("Use GuardTour to scan this NFC tag?")
                .setPositiveButton("Scan") { _, _ ->
                    handleNfcTag(intent)
                    nfcDefaultPromptShown = true
                }
                .setNegativeButton("Cancel") { _, _ -> }
                .show()
        } else {
            handleNfcTag(intent)
        }
    }
}
```

**Option B — NFC Settings Intent**
Open system NFC settings so user can set GuardTour as default:
```kotlin
startActivity(Intent(Settings.ACTION_NFC_SETTINGS))
```

**Option C — Per-scan confirmation checkbox**
```kotlin
AlertDialog.Builder(this)
    .setTitle("NFC Tag Detected")
    .setMessage("Tag: ${tagId}")
    .setView(CheckBox(this).apply {
        text = "Don't ask again for this session"
    })
    .setPositiveButton("Scan") { _, _ -> handleNfcTag(intent) }
    .setNegativeButton("Ignore") { _, _ -> }
    .show()
```

### 7.3 Caveats
- This is Android-only — no backend involvement
- Foreground dispatch requires the Activity to be in the foreground
- If using a background Service (`NfcScanService`), the prompt must come from an Activity
- The "Don't ask again" preference should persist to `SharedPreferences`

---

## 8. Peer-to-Peer NFC — Server-Negotiated HCE (No Screen Tap)

### 8.1 The problem
Two devices with different Android API levels need to complete a peer-to-peer scan (audit route) **without tapping the screen**. Android Beam requires a screen tap and is deprecated/removed on API 29+. There is no way to make Beam work hands-free.

### 8.2 The approach: HCE + Reader Mode with server-assigned roles

**HCE (Host Card Emulation)** works on API 19+ — covers both the API 29 build and the API 34 build. One device emulates an NFC tag, the other reads it like a normal tag. No Beam, no screen tap, no OEM dependency.

**The server decides who does what.** Both devices already report to the server via heartbeat. The server knows each device's Android API level (stored during registration). When an audit route is active, the server assigns roles:

- **Target device** (being scanned/audited) → runs `HostApduService`, emulates an NFC tag containing its `device_id` + `nonce` + `timestamp`
- **Auditor device** (doing the scanning) → runs in NFC reader mode, reads the emulated tag like any other NFC tag, sends full dump to server

### 8.3 Why HCE eliminates the API version problem entirely

| Scenario | Beam (current) | HCE (proposed) |
|----------|---------------|----------------|
| API 28 scans API 29 | Beam may work | HCE works (both API 19+) |
| API 29 scans API 34 | Beam removed | HCE works |
| API 34 scans API 29 | Beam removed | HCE works |
| API 34 scans API 34 | Beam removed | HCE works |
| API 29 scans API 29 | Beam deprecated | HCE works |
| Screen tap required? | Yes | **No** |
| OEM-stripped Beam? | Fails | **HCE unaffected** |

HCE works on **every** Android version from 4.4 (API 19) onward. Both target builds (API 29 and API 34) are well above this floor. There is no compatibility gap — no need for a "mode in between" or fallback negotiation. HCE is the single solution.

### 8.4 What needs to change

#### Backend changes

**1. Store `sdk_int` on Device model** (currently only stores `os_version` as a string)

```python
# models.py — add to Device
sdk_int = models.IntegerField(null=True, blank=True, help_text="Android API level (Build.VERSION.SDK_INT)")
nfc_mode = models.CharField(max_length=10, blank=True, default='auto',
    help_text="Server-assigned NFC mode: 'hce_emulator', 'hce_reader', 'tag_reader', 'auto'")
```

**2. Android sends `sdk_int` during registration**

```kotlin
// LoginActivity.kt — in doLogin()
hardware_info.put("sdk_int", android.os.Build.VERSION.SDK_INT)
```

Backend `register_device` already reads `hardware_info` dict and sets fields — just add `sdk_int`.

**3. Heartbeat sends peer mode directives**

When a device has an active audit route assignment, the heartbeat response includes:

```json
{
  "peer_mode": "hce_emulator",
  "peer_target_device_id": "TCN-02",
  "peer_route_id": 5,
  "peer_nonce": "a1b2c3...",
  "peer_session_expires": "2026-06-25T14:30:00Z"
}
```

The server determines:
- Which device is the **target** (emulator) — the one being audited
- Which device is the **auditor** (reader) — the one doing the scanning
- A **nonce** for this peer session (used in the emulated NDEF payload for server-side verification)
- A **session expiry** (so the HCE service doesn't run forever)

Role assignment logic:
```python
def _heartbeat_peer_mode(device, active_assignments):
    """Assign HCE roles for audit routes."""
    for a in active_assignments:
        route = a.route
        if not route or not route.is_audit:
            continue
        # Find the peer device on this route
        peer_checkpoint = route.checkpoints.filter(checkpoint_type='peer').first()
        if not peer_checkpoint:
            continue
        # Resolve target device from the checkpoint's expected peer
        # The target is the device assigned to the same route as a "target"
        # or resolved from the checkpoint's nfc_tag field (stores peer device_id)
        target_device_id = peer_checkpoint.nfc_tag  # or another field
        
        if device.device_id == target_device_id:
            # This device is the target — emulate a tag
            nonce = secrets.token_hex(8)
            device.peer_session_key = nonce
            return {
                'peer_mode': 'hce_emulator',
                'peer_target_device_id': device.device_id,
                'peer_route_id': route.id,
                'peer_nonce': nonce,
            }
        else:
            # This device is the auditor — read the target's emulated tag
            return {
                'peer_mode': 'hce_reader',
                'peer_target_device_id': target_device_id,
                'peer_route_id': route.id,
            }
    return {}
```

**4. Server-side validation stays the same**

`validate_peer_exchange` already checks:
- Peer device exists
- Reciprocal scan within time window
- Nonce/timestamp match

The only change: the peer data now comes from an HCE-read NDEF payload instead of a Beam-received one. The `raw_nfc` dump sent by the auditor device contains the same structure — the server doesn't care how the NFC data was captured, only that the full dump is there for verification.

#### Android changes

**1. HCE Service** (emulator — runs on the target device)

```kotlin
// PeerHceService.kt
class PeerHceService : HostApduService() {
    companion object {
        var activeNonce: String? = null
        var activeDeviceId: String? = null
        var activeRouteId: Int? = null
    }

    override fun processCommandApdu(commandApdu: ByteArray, extras: Bundle?): ByteArray {
        val nonce = activeNonce ?: return ByteArray(0)
        val deviceId = activeDeviceId ?: return ByteArray(0)
        
        // Build NDEF payload — same structure as current peer_handshake
        val payload = JSONObject().apply {
            put("type", "peer_handshake")
            put("device_id", deviceId)
            put("nonce", nonce)
            put("timestamp", System.currentTimeMillis())
            put("route_id", activeRouteId)
        }
        
        val ndefRecord = NdefRecord.createMime(
            "application/vnd.guardtour.peer",
            payload.toString().toByteArray()
        )
        val ndefMessage = NdefMessage(ndefRecord)
        return ndefMessage.toByteArray()
    }

    override fun onDeactivated(reason: Int) {
        // Peer reader moved away — stay active for re-scan
    }
}
```

```xml
<!-- AndroidManifest.xml -->
<service
    android:name=".PeerHceService"
    android:exported="true"
    android:permission="android.permission.BIND_NFC_SERVICE">
    <intent-filter>
        <action android:name="android.nfc.cardemulation.action.HOST_APDU_SERVICE"/>
    </intent-filter>
    <meta-data
        android:name="android.nfc.cardemulation.host_apdu_service"
        android:resource="@xml/peer_apdu_service"/>
</service>
```

```xml
<!-- res/xml/peer_apdu_service.xml -->
<host-apdu-service xmlns:android="http://schemas.android.com/apk/res/android">
    <aid-group android:category="other" android:description="GuardTour Peer">
        <aid-filter android:name="F0010203040506"/>
    </aid-group>
</host-apdu-service>
```

**2. Heartbeat activates HCE mode**

```kotlin
// NfcScanService.kt — in processHeartbeatResponse()
val peerMode = hb.optString("peer_mode", "")
when (peerMode) {
    "hce_emulator" -> {
        val nonce = hb.optString("peer_nonce", "")
        val targetDeviceId = hb.optString("peer_target_device_id", "")
        val routeId = hb.optInt("peer_route_id", 0)
        PeerHceService.activeNonce = nonce
        PeerHceService.activeDeviceId = targetDeviceId
        PeerHceService.activeRouteId = routeId
        // Enable HCE for this app
        val adapter = NfcAdapter.getDefaultAdapter(this)
        adapter?.setPreferredService(this, ComponentName(this, PeerHceService::class.java))
        updateNotification("Peer mode: emulating tag for audit")
    }
    "hce_reader" -> {
        // Normal NFC reader mode — already handled by existing tag dispatch
        // The auditor just scans the target device like a normal tag
        updateNotification("Peer mode: scan target device ${hb.optString("peer_target_device_id")}")
    }
    else -> {
        // No peer mode — disable HCE if it was active
        val adapter = NfcAdapter.getDefaultAdapter(this)
        adapter?.unsetPreferredService(this)
    }
}
```

**3. Auditor reads the emulated tag as a normal scan**

No change needed! The auditor device already handles `ACTION_TECH_DISCOVERED` / `ACTION_NDEF_DISCOVERED` in `onStartCommand`. The HCE-emulated tag triggers the same intent. The existing `handleNfcTag()` → `buildRawNfcPayload()` → `sendScanFull()` pipeline works unchanged. The `raw_nfc` dump will contain the peer handshake NDEF record, and `parse_nfc_payload()` on the server already detects `peer_handshake` type.

**4. Disable HCE when peer session expires**

```kotlin
// In heartbeat loop — if peer_mode is no longer sent, disable HCE
if (peerMode.isEmpty() && hceWasActive) {
    val adapter = NfcAdapter.getDefaultAdapter(this)
    adapter?.unsetPreferredService(this)
    PeerHceService.activeNonce = null
    hceWasActive = false
}
```

### 8.5 Complete flow — step by step

```
1. Dispatcher creates audit route with peer checkpoint
   → Checkpoint nfc_tag = "TCN-02" (target device's device_id)

2. Both devices heartbeat normally
   → Server sees both have active audit assignments
   → Server sends "hce_emulator" + nonce to TCN-02 (target)
   → Server sends "hce_reader" to TCN-01 (auditor)

3. TCN-02 activates HCE service
   → Emulates NFC tag with NDEF payload: {type:"peer_handshake", device_id:"TCN-02", nonce:"abc123", timestamp:...}

4. TCN-01 taps TCN-02 (physically touches devices)
   → No screen tap needed — HCE tag is auto-detected
   → Android delivers ACTION_TECH_DISCOVERED to NfcScanService
   → handleNfcTag() builds raw_nfc dump with NDEF records
   → sendScanFull() sends to server

5. Server receives scan from TCN-01
   → parse_nfc_payload() detects peer_handshake in NDEF
   → validate_peer_exchange() checks:
      - TCN-02 exists ✓
      - Nonce matches device.peer_session_key ✓
      - Timestamp within window ✓
   → ScanRecord created with scan_type='peer'

6. Server clears nonce on TCN-02's next heartbeat
   → TCN-02 disables HCE (peer_mode no longer sent)
   → Peer scan complete — no Beam, no screen tap, any API level
```

### 8.6 Why not keep Beam as a fallback?

| Factor | HCE only | Beam + HCE hybrid |
|--------|---------|-------------------|
| Code complexity | One path | Two paths + negotiation |
| Testing | One flow | Must test both flows |
| Beam on API 28 | Works but needs tap | Works but needs tap |
| Beam on API 29+ | N/A | Doesn't work |
| HCE on API 19+ | Works everywhere | Works everywhere |
| User confusion | Consistent behavior | "Sometimes I tap, sometimes I don't" |

**Recommendation: HCE only.** Beam offers zero advantage — it still requires a screen tap, which is the exact problem we're solving. HCE works on every Android version we target (API 29 and API 34 both support it). Removing Beam entirely simplifies the codebase and eliminates a dead code path.

### 8.7 What about the `os_version` / `sdk_int` in the database?

The user's idea of using the Android version to negotiate mode is **correct in principle** but **unnecessary in practice** because HCE works on all target versions. However, storing `sdk_int` is still valuable for:

- **Feature gating**: Some devices may not have NFC at all (`sdk_int` + `PackageManager.hasSystemFeature(NFC)`)
- **Diagnostics**: Know which devices are old vs new for support tickets
- **Future features**: Different behavior for API 34+ (e.g. photo picker, new notification permissions)
- **Fallback to QR**: If a device reports no NFC capability, the server can instruct it to use QR code fallback instead

So: store `sdk_int` for feature gating and diagnostics, but don't use it for NFC mode negotiation — HCE is universal.

---

## 9. Newly Discovered Issues (Re-scan)

> Cross-referenced against sections 1–8. Items below are **new** — not previously documented.

### 9.1 🔴 Dual Heartbeat Loop — TTS Silently Dropped
**Android:** `NfcScanService.kt:160-181` (60s loop) + `GuardDashboardActivity.kt:100-108` (15s loop)

Both run simultaneously and call `api.sendHeartbeat()` with the same device. The dashboard's 15s loop fires 4× more often. When the dashboard's heartbeat receives `tts_pending` from the server, `renderHeartbeat()` (line 176-225) **only reads `tts_voice` for display** — it does NOT speak the TTS and does NOT set `tts_ack_pending`. The service's heartbeat may not fire for another 45s, by which point the server has already delivered the TTS to the dashboard (wasted). If the service is killed/stopped, TTS messages are received by the dashboard indefinitely but **never spoken and never acked** — the server keeps re-sending forever.

### 9.2 🔴 TTS Ack Flag Cleared Before Network Confirmation
**Android:** `ApiManager.kt:82-86`

```kotlin
if (prefs.isTtsAckPending()) {
    put("tts_acked", true)
    prefs.setTtsAckPending(false)  // ← cleared BEFORE postJson runs
}
```

The ack flag is cleared in SharedPreferences before the HTTP request completes. If the network call fails (timeout, 401, etc.), the ack is lost. The server never receives it. Next heartbeat won't re-send the ack. Server re-delivers the TTS (duplicate), but the device won't know it's a retry — it speaks it again.

### 9.3 🔴 Backend Re-delivers TTS on Ack Heartbeat
**Backend:** `api/views.py:464-496` (`_heartbeat_tts_delivery` + `_heartbeat_tts_ack`)

In the heartbeat handler, `_heartbeat_tts_delivery` (step 7) runs BEFORE `_heartbeat_tts_ack` (step 8). When the device sends `tts_acked: true`:
1. Step 7: `device.tts_pending` is still set (not yet cleared) → returns TTS in response
2. Step 8: clears `device.tts_pending = None`

The device receives the TTS in the same response where it sent the ack → speaks it again → sets `tts_ack_pending = true` again → next heartbeat sends ack again → server clears (no TTS to deliver) → cycle ends. Net result: **every TTS message is spoken twice**.

### 9.4 🔴 `scan_batch_sync` Missing `_original_index` — Per-item Sync Broken
**Backend:** `api/views.py:2264-2266`
**Android:** `SyncManager.kt:99`

Backend `scan_batch_sync` appends results as:
```python
{'status': 'created', 'id': record.id, 'checkpoint': record.checkpoint_name, ...}
```
No `_original_index` field. Android reads `item.optInt("_original_index", -1)` → always -1 → `if (originalIndex in chunk.indices)` always fails. Falls through to all-or-nothing fallback (lines 108-112). If one scan in the batch fails, either ALL are marked synced or NONE are — no per-item granularity.

### 9.5 🔴 Offline Peer Scans Completely Broken
**Android:** `SyncManager.kt:79-88`
**Backend:** `api/views.py:2245`

`SyncManager.syncScans` builds scan objects with `nfc_value`, `recorded_at`, `lat`, `lng`, `raw_nfc`, `route_id` — but never includes `peer_key` or `verification_key`. Backend `scan_batch_sync` reads `peer_key=s.get('peer_key')` → always None. Offline peer-to-peer scans cannot be validated. (Online path has the separate issue 1.3 where `verification_key` is never sent.)

### 9.6 🟡 `SyncManager` Coroutine Scope Leaked
**Android:** `NfcScanService.kt:72` + `SyncManager.kt:9`

`NfcScanService.onCreate` calls `SyncManager(this).startPeriodicSync()`. `SyncManager` creates its own `CoroutineScope` (line 9). When `NfcScanService.onDestroy` cancels `serviceScope`, the `SyncManager`'s scope is NOT cancelled — it's a separate instance. The periodic sync loop continues as a zombie coroutine, making network calls to a dead service context.

### 9.7 🟡 `extractNdefText` NPE on Null NdefMessage
**Android:** `NfcScanService.kt:358-359`

```kotlin
val msg = ndef.ndefMessage        // can be null
val record = msg.records.firstOrNull()  // NPE if msg is null
```

`ndef.ndefMessage` returns null when the tag has no NDEF data (common for Mifare Classic, Ultralight C without NDEF formatting). The broad `catch (e: Exception)` at line 364 catches the NPE and returns null, falling back to hex UID. Not a crash, but the fallback to hex UID may produce an `nfc_value` that doesn't match any checkpoint's `nfc_tag` field (which may store the UID in a different format).

### 9.8 🟡 `extractNdefText` AIOOBE on Empty Payload
**Android:** `NfcScanService.kt:361`

```kotlin
val statusByte = payload[0].toInt()  // crashes if payload is empty
```

Some NFC tags have NDEF records with zero-length payloads. `payload[0]` throws `ArrayIndexOutOfBoundsException`. Caught by broad catch, returns null, falls back to hex UID — same issue as 9.7.

### 9.9 🟡 GPS Dedup Race Condition
**Android:** `GpsCollector.kt:103-107`

`lastStoredLocTime` is a plain `Long` accessed from multiple threads:
- GPS listener callback (line 52: `serviceScope.launch { storePoint(loc) }`)
- Network listener callback (line 71: `serviceScope.launch { storePoint(loc) }`)
- Periodic fallback poll (line 95: `storePoint(loc)`)

All three can call `storePoint` concurrently. The check `if (locTime == lastStoredLocTime) return` + `lastStoredLocTime = locTime` is not atomic. Two calls with the same `loc.time` can both pass the check and insert duplicate GPS points. Should use `@Volatile` + compare-and-set, or a Mutex.

### 9.10 🟡 Heartbeat Returns `route_id` but Android Never Uses It
**Backend:** `api/views.py:375` — `directives['route_id'] = p['route_id']`
**Android:** `NfcScanService.kt:183-215` — `processHeartbeatResponse` never reads `route_id`

The backend already sends `route_id` in every heartbeat response for the primary mission. If the Android app read this value and passed it to `sendScanFull()`, issue 1.2 (missing `route_id` in scans) would be fixed without any user-facing change. The data is right there — it's just never consumed.

### 9.11 🟡 `bufferScanLocal` Never Sets `routeId`
**Android:** `NfcScanService.kt:287-298`

`ScanBuffer` has a `routeId: Int? = null` field (ScanBuffer.kt:15). `SyncManager.syncScans` reads `s.routeId` and includes it in the sync payload (line 87). But `bufferScanLocal` constructs `ScanBuffer` without ever setting `routeId` — it's always null. This is the offline-path equivalent of issue 1.2. Combined with 9.10, the fix would be: read `route_id` from heartbeat response → store in prefs → pass to both `sendScanFull` and `bufferScanLocal`.

### 9.12 🟡 Services Started Redundantly by 3 Components
**Android:** `MainActivity.kt:40-42` + `BootReceiver.kt:11-18` + `GuardDashboardActivity.kt:46-47`

All three call `NfcScanService.start()` and `GpsCollector.start()`. Android keeps a single service instance, but each `startForegroundService` triggers `onStartCommand` again:
- `GpsCollector.onStartCommand` → `startCollecting()` → `stopCollecting()` + re-register listeners → wasteful GPS listener churn
- `NfcScanService.onStartCommand` → checks for NFC intent action → no-op (harmless but wasteful)

Should use a singleton guard or check if service is already running.

### 9.13 🟢 `_heartbeat_tts_delivery` Conditional Branch Is Dead Code
**Backend:** `api/views.py:465-467`

```python
if device.tts_pending and device.tts_acked:
    device.tts_acked = False
    device.save(update_fields=['tts_acked'])
    return { 'tts_pending': device.tts_pending, ... }
```

This branch fires when `tts_pending` is set AND `tts_acked` is True. But `_heartbeat_tts_ack` (which sets `tts_acked = True`) also sets `tts_pending = None`. So `tts_pending` is always None when `tts_acked` is True. This branch is unreachable — unless a new TTS is set in steps 5/6 after the ack clears it, but steps 5/6 check `if device.tts_pending: return` and skip when TTS is pending (which it is, since ack hasn't run yet). The branch is dead code.

### 9.14 🟢 `operator_id` Parameter in `sendHeartbeat` Never Passed
**Android:** `ApiManager.kt:72` — parameter `operatorId: String? = null`
**Callers:** `NfcScanService.kt:169` and `GuardDashboardActivity.kt:123` — neither passes `operatorId`

The `sendHeartbeat` function accepts an `operatorId` parameter and includes it in the body if non-null. But neither caller ever passes it. Issue 1.4 documented this as "unused fields" but the root cause is different — the parameter exists in the API method but is simply never provided by any caller. Backend doesn't read it anyway (resolves identity from CallSign model).

---

## 10. Full Re-scan — Additional Issues Found

> Complete re-analysis of all backend + Android files. Items below are **new** — not in sections 1–9.

### 10.1 🔴 `deployment_checkpoint_live` Crashes — `hit_count` Never Defined
**Backend:** `api/views.py:2024-2025`

```python
'is_completed': hit_count + (len(missed_pending_ids) if next_cp else 0) >= total if total > 0 else True,
'hit_count': hit_count,
```

The variable `hit_cp_ids` (a set) is defined at line 1867/1872, but `hit_count = len(hit_cp_ids)` is **never assigned**. Line 2024 references `hit_count` → `NameError` on every call when there are active assignments with checkpoints. The dispatch live-tracking endpoint is **completely broken** — crashes 100% of the time.

### 10.2 🔴 `resolve_asset` Global Fallback Leaks Cross-Org Data
**Backend:** `api/scan_service.py:171-181`

When a tag doesn't match any checkpoint in the device's active route, it falls back to:
```python
checkpoint = Checkpoint.objects.filter(nfc_tag=nfc_value).first()
```
This is a **global query across ALL organizations**. If Org A's device scans an unknown tag that happens to match Org B's checkpoint UID, the scan is attributed to Org B's route. Multi-tenant data leak. Should filter by `organization=device.organization`.

### 10.3 🟡 `NfcScanService` Missing `foregroundServiceType` — Crashes on API 34+ build
**Android:** `AndroidManifest.xml:44-58`

`NfcScanService` is started via `startForegroundService()` but doesn't declare `android:foregroundServiceType`. On Android 14 (API 34+), this crashes with `ForegroundServiceTypeNotAllowed`. `GpsCollector` correctly has `foregroundServiceType="location"` (line 62), but `NfcScanService` is missing it. Since the service accesses location data (GPS coords in scans), it should declare `"location"` or a suitable type.

> **Note:** Current target is Android 10 (API 29) and below — this is not a crash on the current build. This must be fixed for the planned API 34 backward-compatible build (see §11).

### 10.4 🔴 `ACTION_TAG_DISCOVERED` Silently Ignored
**Android:** `NfcScanService.kt:124` + `AndroidManifest.xml:47-57`

`onStartCommand` only checks:
```kotlin
if (NfcAdapter.ACTION_NDEF_DISCOVERED == it.action || NfcAdapter.ACTION_TECH_DISCOVERED == it.action)
```
`ACTION_TAG_DISCOVERED` is not checked. The manifest also lacks a `TAG_DISCOVERED` intent filter. Tags without NDEF data that don't match the tech list are **silently dropped**. Many Mifare Classic and Ultralight tags without NDEF formatting will be ignored — the user taps the tag and nothing happens.

### 10.5 🟡 `is_on_time` Uses Wrong Date for Night Shifts
**Backend:** `api/scan_service.py:200-208`

```python
planned_dt = timezone.make_aware(
    timezone.datetime.combine(now.date(), checkpoint.planned_time),
    timezone=now.tzinfo
)
```

Uses `now.date()` instead of `assignment.scheduled_date`. For night shifts spanning midnight, a scan at 00:30 on the 26th for a shift scheduled on the 25th compares against the **26th's** date — marking the scan as on-time or late against the wrong day. Should use the assignment's `scheduled_date`.

### 10.6 🟡 Validity Scoring Ignores Sensor Data
**Backend:** `api/scan_service.py:120-166`

`calculate_scan_validity` uses GPS proximity, device GPS history, movement plausibility, and battery — but **never reads `raw_nfc.sensors`** (accelerometer/gyroscope). The backend stores it, the Android app sends it, but the anti-cheat engine ignores it. A phone sitting on a table gets the same validity score as one being carried during a patrol.

### 10.7 🟡 `dispatch_page` POST Creates Assignment Without `scheduled_date`
**Backend:** `api/views.py:1731-1748`

The dispatch page form POST creates a `ShiftAssignment` directly (bypassing `ShiftAssignmentViewSet.perform_create` which defaults `scheduled_date` to today). Direct creation → `scheduled_date = None` → breaks mission staging (`get_mission_status` checks `assignment.scheduled_date` at line 262) and checkpoint timing for any assignment created via the dispatch form.

### 10.8 🟡 `dispatch_page` POST Only Deactivates Guard, Not Device
**Backend:** `api/views.py:1737-1738`

```python
_deactivate_assignments(ShiftAssignment.objects.filter(guard_supervisor_id=guard_id, is_active=True))
```

Only deactivates previous assignments for the **guard**, not for the **device**. If the device was previously assigned to a different guard, both assignments remain active → `resolve_assignment` picks whichever was `order_by('-assigned_at').first()` → scans may be attributed to the wrong guard/route.

### 10.9 🟡 `register_device` Never Sets Organization
**Backend:** `api/views.py:216-239`

If a device was created in the admin without an organization, `register_device` only updates hardware info — it never sets `device.organization`. A device with `organization=None`:
- `_heartbeat_geofence_tts` skips (requires `device.organization_id`, line 428)
- Device won't appear in org-scoped querysets
- `resolve_asset` fallback (10.2) can't filter by org

### 10.10 🟡 `ShiftAssignment.is_completed` Never Auto-Set
**Backend:** `api/models.py:371` + all views

No logic anywhere automatically marks `is_completed = True` when all checkpoints are scanned. Completed assignments stay "active" forever unless manually ended via `end_shift`. This means:
- `resolve_assignment` may return a completed assignment (only filters `is_active=True`, not `is_completed=False`)
- `deployment_checkpoint_live` and `_heartbeat_active_missions` show completed missions as active
- Guards see "completed" missions in their heartbeat indefinitely

### 10.11 🟡 NDEF Intent Filter Only Matches `text/plain` MIME
**Android:** `AndroidManifest.xml:48-50`

```xml
<data android:mimeType="text/plain" />
```

Tags with other MIME types (application/json, application/octet-stream, etc.) won't trigger `NDEF_DISCOVERED`. Only `TECH_DISCOVERED` will catch them, and only if the tag's tech matches the filter list. Peer handshake NDEF records with custom MIME types may be missed.

### 10.12 🟡 `AppDatabase` Has No Migration Strategy
**Android:** `AppDatabase.kt:10-11`

```kotlin
@Database(entities = [GpsPoint::class, ScanBuffer::class], version = 1, exportSchema = false)
```

Version 1, no `Migration` objects, `exportSchema = false`. Any future schema change (adding a column, changing a type) will either:
- Crash with `IllegalStateException: Room cannot verify the data integrity`
- Silently wipe all offline data if `.fallbackToDestructiveMigration()` is added later

No schema export means no migration validation tooling either.

### 10.13 🟢 `_heartbeat_geofence_tts` Same Persistence Issue as 1.5
**Backend:** `api/views.py:427-461`

Same as issue 1.5 but separate code path. `_heartbeat_geofence_tts` saves `geofence_states` and `tts_acked = False` but does NOT save `device.tts_pending = msg`. The geofence TTS is in the response only. If the device misses the heartbeat, the geofence entry TTS is lost forever. The `geofence_states` dict was already updated, so the device won't get the message again even on the next heartbeat (it's marked as "inside" the geofence).

### 10.14 🟢 `end_shift` Redundantly Sets `is_on_shift`
**Backend:** `api/views.py:1786-1787`

```python
assignment.guard_supervisor.is_on_shift = False
assignment.guard_supervisor.save()
```

The `post_save` signal (`update_guard_shift_status`, models.py:417-432) already handles this. Not harmful but duplicated logic — and the direct save doesn't check if the guard has other active assignments first (the signal does).

### 10.15 🟢 `ScanRecordViewSet` `AllowAny` With No Rate Limiting
**Backend:** `api/views.py:980`

`permission_classes = [AllowAny]` on the scan endpoint. By design (devices have no JWT), but there's no throttling. An attacker who guesses a device_id + password (8-digit random number) can flood fake scans. Should add DRF throttling or rate limiting.

### 10.16 🟢 `post_save` Signal Fires on Every Save
**Backend:** `api/models.py:417-432`

`update_guard_shift_status` fires on every `ShiftAssignment.save()`, including saves that don't change `is_active` (e.g., updating `scheduled_end`). The signal runs guard status update queries unnecessarily. Minor performance waste.

---

## 11. Android Version Targeting Strategy

### 11.1 Current target: Android 10 (API 29) and below
- `compileSdk` / `targetSdk` should be set to 29 for the current build
- Android Beam is available on API 16-28 but **deprecated on API 29** — on Android 10 itself Beam may or may not work depending on OEM
- `foregroundServiceType` is **not required** on API 29 — issue 10.3 is deferred to the API 34 build
- `PendingIntent.FLAG_IMMUTABLE` is required from API 23+ (already used in code)
- `ACCESS_BACKGROUND_LOCATION` is required from API 29+ (already in manifest)

### 11.2 Planned: API 34 (Android 14) backward-compatible build
A separate build targeting API 34 but supporting older Android versions. Changes needed:

| Area | API 29 build | API 34 build | Action |
|------|-------------|-------------|--------|
| `foregroundServiceType` | Not required | **Required** — crash without it | Add `android:foregroundServiceType="location"` to `NfcScanService` |
| Android Beam | Deprecated but may work | **Removed** | Use HCE alternative (§8.3) |
| `READ_PHONE_STATE` (IMEI) | Works with permission | **Returns null** | Drop IMEI/IMSI, use `Build` fields |
| `BODY_SENSORS` | Works with permission | Works but requires explicit grant | Add runtime permission request |
| `ACCESS_BACKGROUND_LOCATION` | Required from API 29 | **Must request separately** | Already in manifest, need separate prompt |
| Photo picker | Not available | Available API 33+ | Optional for future NFC tag write feature |
| `POST_NOTIFICATIONS` | Not required | **Required API 33+** | Add runtime permission for notifications |
| Foreground service launch restrictions | None | **Restricted on API 34+** | Must launch from foreground or exempt type |
| `PendingIntent.FLAG_IMMUTABLE` | Required API 23+ | Required | Already used ✅ |

### 11.3 Build flavor approach
```
productFlavors {
    legacy {
        minSdk 21
        targetSdk 29
        // Android Beam, no foregroundServiceType requirement
    }
    modern {
        minSdk 21
        targetSdk 34
        // HCE instead of Beam, foregroundServiceType, POST_NOTIFICATIONS
    }
}
```

---

## 12. Shift Logic — Make Optional Per Organization

### 12.1 Problem
Currently shift logic (Day/Night/Flex) is **hardcoded into the core flow**:
- `ShiftAssignment.shift_type` is required (no default, no null option)
- `GuardSupervisor.shift` defaults to 'Day'
- `deployment_checkpoint_live` calculates shift end times based on `shift_type` (18:00 for Day, 06:00+1 for Night)
- `_heartbeat_active_missions` always returns `shift_type` in missions
- `assign_guard_to_blueprint_shift` requires `shift_type` parameter
- Dispatch page form requires `shift_type` selection
- `blueprint_shift_availability` groups availability by shift type

For small organizations with a single fleet or no day/night split, this is unnecessary friction. A guard should be able to just scan checkpoints without caring about shift windows.

### 12.2 Proposed: `Organization.shift_mode` field

```python
class Organization(models.Model):
    SHIFT_MODE_CHOICES = [
        ('structured', 'Structured (Day/Night/Flex shifts)'),
        ('simple', 'Simple (No shift tracking)'),
    ]
    shift_mode = models.CharField(
        max_length=20,
        choices=SHIFT_MODE_CHOICES,
        default='simple',  # Default to simple — most orgs are small
    )
```

### 12.3 Behavior by mode

#### Simple mode (`shift_mode='simple'`)
- `ShiftAssignment.shift_type` defaults to `'Day'` and is hidden in UI
- No shift availability check — any guard can be assigned to any route anytime
- `deployment_checkpoint_live` uses 24h from `assigned_at` as the deadline (no 18:00/06:00 logic)
- `blueprint_shift_availability` returns a single "available" count instead of per-shift breakdown
- Dispatch page hides the shift_type dropdown
- Heartbeat doesn't include `shift_type` in mission directives (or always sends 'Day')
- `is_on_time` for untimed checkpoints uses `assigned_at + 24h` as deadline
- Guard profile hides shift field

#### Structured mode (`shift_mode='structured'`)
- Current behavior — full Day/Night/Flex tracking
- Shift availability, shift-based deadlines, shift filtering
- All current UI elements visible

### 12.4 Migration plan
1. Add `shift_mode` field to `Organization` (default `'simple'`)
2. Update `ShiftAssignment` to allow `shift_type='Day'` as default (already is)
3. Update `deployment_checkpoint_live` — branch on `org.shift_mode`
4. Update `blueprint_shift_availability` — branch on `org.shift_mode`
5. Update dispatch page — conditionally show/hide shift dropdown
6. Update `_heartbeat_active_missions` — conditionally include `shift_type`
7. Update `assign_guard_to_blueprint_shift` — make `shift_type` optional when org is simple mode
8. Frontend: hide shift-related UI when `shift_mode='simple'`

### 12.5 Impact on existing issues
- **10.5** (`is_on_time` wrong date for night shifts) — becomes less critical in simple mode (no night shifts). Still needs fixing for structured mode.
- **10.7** (dispatch POST missing `scheduled_date`) — in simple mode, `scheduled_date` could default to today without shift complexity
- **10.10** (`is_completed` never auto-set) — in simple mode, completion is just "all checkpoints scanned" regardless of time windows

---

## 13. Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | 1.1 — Fix password generation | Small | **Critical** — all auth broken |
| P0 | 1.2 — Add route_id to scans | Medium | **Critical** — multi-route broken |
| P0 | 1.3 — Add verification_key | Medium | **Critical** — peer scan dead |
| P0 | 9.1 — Fix dual heartbeat / TTS drop | Medium | **Critical** — TTS silently lost |
| P0 | 9.4 — Add `_original_index` to batch sync | Small | **Critical** — offline sync per-item broken |
| P0 | 9.5 — Send `peer_key` in offline sync | Small | **Critical** — offline peer scan dead |
| P0 | 10.1 — Fix `hit_count` NameError | Small | **Critical** — live tracking crashes |
| P0 | 10.2 — Filter `resolve_asset` by org | Small | **Critical** — cross-org data leak |
| P0 | 10.4 — Handle `ACTION_TAG_DISCOVERED` | Small | **Critical** — tags silently dropped |
| P1 | 1.5 — Persist TTS for retry | Small | Medium |
| P1 | 1.6 — Surface error details | Small | Medium |
| P1 | 1.7 — POST not GET for password | Small | Medium |
| P1 | 4.0 — NFC scan dump in UI | Large | High |
| P1 | 9.2 — Defer ack clear until HTTP success | Small | Medium |
| P1 | 9.3 — Fix TTS delivery/ack ordering | Small | Medium |
| P1 | 9.10 — Read route_id from heartbeat | Small | Medium |
| P1 | 9.11 — Set routeId in bufferScanLocal | Small | Medium |
| P1 | 10.5 — Fix `is_on_time` for night shifts | Small | Medium |
| P1 | 10.7 — Set `scheduled_date` in dispatch POST | Small | Medium |
| P1 | 10.8 — Deactivate device assignments in dispatch | Small | Medium |
| P1 | 10.10 — Auto-set `is_completed` | Medium | Medium |
| P1 | 12.0 — Make shift logic optional per org | Medium | High |
| P2 | 2.0 — TTS profiles + voices | Medium | Medium |
| P2 | 3.0 — Peer-to-peer HCE (no screen tap) | Large | High |
| P2 | 5.0 — TTS setup in device panel | Medium | Medium |
| P2 | 9.6 — Cancel SyncManager scope | Small | Medium |
| P2 | 9.7 — Null-check ndefMessage | Small | Medium |
| P2 | 9.8 — Empty payload guard | Small | Medium |
| P2 | 9.9 — Fix GPS dedup race | Small | Medium |
| P2 | 9.12 — Singleton guard for services | Small | Medium |
| P2 | 10.6 — Use sensor data in validity | Medium | Medium |
| P2 | 10.9 — Set org in `register_device` | Small | Medium |
| P2 | 10.11 — Broaden NDEF MIME filter | Small | Medium |
| P2 | 10.12 — Add Room migration strategy | Small | Medium |
| P2 | 11.0 — API 34 backward-compatible build | Large | Medium |
| P3 | 1.4 — Remove unused heartbeat fields | Small | Low |
| P3 | 1.8 — Apply GPS corrections | Small | Low |
| P3 | 1.10 — Call mission-status endpoint | Medium | Low |
| P3 | 9.13 — Remove dead TTS branch | Small | Low |
| P3 | 9.14 — Remove unused operator_id param | Small | Low |
| P3 | 10.3 — Add `foregroundServiceType` (API 34 build) | Small | Low |
| P3 | 10.13 — Persist geofence TTS | Small | Low |
| P3 | 10.14 — Remove redundant `is_on_shift` set | Small | Low |
| P3 | 10.15 — Add scan rate limiting | Small | Low |
| P3 | 10.16 — Optimize post_save signal | Small | Low |
