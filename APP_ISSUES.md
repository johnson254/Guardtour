# GuardTour — Changelog & Known Issues

> **Last APK build:** 24-Jun-2026 — `app-debug.apk`
> All backend migrations applied: `0063_backend_fixes_operator_null_and_checkpoint_setnull`

---

## ✅ Fixed

### 1.1 Offline Scans Silently Dropped ✅
**Fix:** `NfcScanService.handleNfcTag()` now calls `bufferScanLocal()` when the network call fails, writing to `ScanBuffer` via Room DB. `SyncManager` picks it up on next periodic sync.

### 1.2 Heartbeat Directives Processed ✅
**Fix:** `NfcScanService.startHeartbeat()` now processes the response via `processHeartbeatResponse()`. Reads `fetch_nfc`, `fetch_gps`, `tts_pending`, and `missions[]` from every heartbeat.

### 1.3 Scan Attaches GPS + Raw NFC + Sensors ✅
**Fix:** `handleNfcTag()` now sends `lat`, `lng`, and a full `raw_nfc` JSON payload including tag UID, tech list, NDEF records, accelerometer, and gyroscope data. Server can now calculate validity scores properly.

### 1.4 Missions List in Heartbeat + Dashboard ✅
**Backend:** Heartbeat returns `missions[]` array with all active assignments for the device. First mission is also set as `route_id`/`route_name` for backward compat.
**App Dashboard:** Shows all missions as a numbered list (► primary, • secondary).
**Background Notification:** Shows "N missions active" or the primary route name.

### 1.5 Multiple Active Missions Supported ✅
**Backend:** Heartbeat iterates ALL active assignments (no longer `.first()`). Primary route fields kept for backward compat.
**App:** Dashboard lists all missions; background service shows mission count in notification.

### 1.6 Google Play Services Removed ✅
**Fix:** `GpsCollector` rewritten to use Android's built-in `LocationManager` instead of `FusedLocationProviderClient`. Works on Android 7-10 without Play Store. `play-services-location` dependency removed from `build.gradle`.

### 1.7 TTS Playback ✅
**Fix:** `NfcScanService` initializes Android `TextToSpeech` engine on startup. Speaks `tts_pending` messages aloud with locale, rate, and pitch from server. Falls back to default locale if TTS engine fails.

### 1.8 Audio/Vibration Feedback on Scan ✅
**Fix:** Both `NfcScanService` and `GuardDashboardActivity` play a beep (`ToneGenerator.TONE_PROP_ACK`) and vibrate (200ms) when a scan succeeds. `play_sound`/`vibrate` directives from heartbeat also trigger feedback.

### 1.9 Body Sensor Data in Scans ✅
**Fix:** `NfcScanService` registers `SensorEventListener` for accelerometer and gyroscope. Latest values are attached to every scan's `raw_nfc.sensors` payload for server-side context-aware validity scoring.

### 1.10 Offline Sync Works ✅
**Fix:** Scans buffered locally via `bufferScanLocal()` when offline. `SyncManager` uploads buffered scans via `scan-batch` endpoint every 120s. GPS points also buffered and uploaded.

### 1.11 Backend: DeviceSerializer Duplicate Meta Removed ✅
**Fix:** Second `class Meta` removed — TTS pending fields are now properly read-only via API.

### 1.12 Backend: OperatorAlert.operator Nullable ✅
**Fix:** `null=True, blank=True` added to FK. Device-only TTS no longer crashes with IntegrityError. Migration 0063 applied.

### 1.13 Backend: ScanRecord.checkpoint SET_NULL ✅
**Fix:** Changed from `CASCADE` to `SET_NULL` — deleting a checkpoint no longer wipes scan history. Migration 0063 applied.

### 1.14 Backend: generate_operator_id No Collision ✅
**Fix:** Now scans actual `device_id` values for max sequence number instead of using `count()`.

### 1.15 Backend: Guard is_on_shift Bidirectional ✅
**Fix:** Signal now handles both activation AND deactivation. `swap_operator` also cleans up old guard's shift status.

### 1.16 Backend: gps_batch_sync Proper Errors ✅
**Fix:** Returns 404 "Device not found" vs 401 "Auth failed" separately.

### 1.17 Backend: device_trails Safe Lookup ✅
**Fix:** Changed `get()` → `filter().first()`.

### 1.18 Backend: No Auto-Create Default Org ✅
**Fix:** `register`, `login`, `dispatch_page` no longer auto-create "Default Organization". Return 400 if no org exists.

### 1.19 Backend: end_shift Returns JSON ✅
**Fix:** Changed from `redirect('dispatch')` to `Response({'status': 'ended', 'assignment_id': ...})`.

### 1.20 Password Numeric-Only ✅
**Fix:** `mgGeneratePassword()` generates 8 random digits. Server fallback uses `secrets.randbelow(90000000) + 10000000`.

### 1.21 Officer → Operator Labels ✅
**Fix:** Three device-related labels changed in `manage.html`.

---

## 🔴 Remaining Issues (Not Yet Fixed)

### 2.1 Error Responses Parsed as Success
**File:** `ApiManager.kt:25-28`  
**Issue:** `postJson()` reads `errorStream` for non-2xx responses and tries `JSONObject(text)`. If the server returns non-JSON errors, the exception is swallowed and `null` is returned. The caller can't distinguish error types.

---

## 2. Design Gaps (Server Features the App Ignores)

| # | Server Sends | App Does | Impact |
|---|-------------|----------|--------|
| 2.1 | `fetch_nfc` (bool) | ❌ Ignored | Server can't trigger NFC scan remotely |
| 2.2 | `fetch_gps` (bool) + `gps_accuracy` (int) | ❌ Ignored | Server can't request GPS fix remotely |
| 2.3 | `tts_rate`, `tts_pitch` (float) | ❌ Ignored | Dashboard only shows `tts_voice` |
| 2.4 | `play_sound`, `vibrate` (bool) | ❌ Ignored | No audio/vibration feedback on the device |
| 2.5 | `route_id` (int) | ❌ Ignored | App only reads `route_name` — can't link to route data |
| 2.6 | `guard_name` | ❌ Not persisted | `SharedPreferencesManager.saveGuardName()` exists but never called |
| 2.7 | `callsign`, `operator_id` in heartbeat | ❌ Ignored by server | Server never reads these fields from heartbeat request — identity only managed via `CallSign` model |

### 2.8 TTS Pending Never Reaches the Device
**Files:** `api/views.py:527-572` (send_tts), `api/views.py:364-374` (heartbeat)  
**Issue:** `DeviceViewSet.send_tts` sets `device.tts_pending` + voice/rate/pitch/at fields.  
But the heartbeat view (**`views.py:364`**) never reads `device.tts_pending` — it only returns route-level TTS fields.  
Even if the heartbeat DID return it, the Android app **never reads heartbeat response fields beyond `guard_name`, `callsign`, `status`, `battery_pct`, `route_name`, `tts_voice`**.

---

## 3. API Call Verification

### 3.1 register-device (`POST /api/register-device/`)
| App sends | Server expects | Status |
|-----------|---------------|--------|
| `operator_id` (string) | `operator_id` | ✅ |
| `device_id` (from prefs, may be empty) | — | ✅ (optional extra) |
| `hardware_info` (JSON object) | `hardware_info` (dict) | ✅ |

**Key insight:** Server looks up `Device.objects.filter(device_id=operator_id)` — so `operator_id` IS `device_id`.  
The human-readable operator ID (e.g. `"TCN-01"`) is the **same value** as the `device_id` field on Device.

### 3.2 heartbeat (`POST /api/heartbeat/`)
| App sends | Server reads | Status |
|-----------|-------------|--------|
| `device_id` | `device_id` | ✅ |
| `password` | `password` | ✅ |
| `battery_pct`, `lat`, `lng`, `gps_accuracy` | Same | ✅ |
| `callsign` | ❌ **Ignored** | Server never reads `callsign` from heartbeat — identity is from `CallSign` model |
| `operator_id` | ❌ **Ignored** | No `operator_id` parameter exists in heartbeat view |

### 3.3 Scan (`POST /api/scans/`)
| App sends | Server expects | Status |
|-----------|---------------|--------|
| `device_id`, `password` | `device_id`, `password` | ✅ |
| `nfc_value` | `nfc_value` | ✅ |
| — | `route_id?` | ❌ Never sent |
| — | `lat?`, `lng?` | ❌ Never sent — validity score = 0 |
| — | `raw_nfc?` | ❌ Never sent — can't detect peer-to-peer scans |
| — | `verification_key?` | ❌ Never sent |

### 3.4 gps-batch (`POST /api/gps-batch/`) ✅
App sends `points[]` with `lat`, `lng`, `accuracy`, `battery_pct`, `speed`, `bearing`, `recorded_at`.  
Server expects the same. **Match.**

### 3.5 scan-batch (`POST /api/scan-batch/`) ✅
App sends `scans[]` with `nfc_value`, `recorded_at`, `lat?`, `lng?`, `raw_nfc?`, `route_id?`.  
Server expects the same. **Match.**

---

## 4. Google Play Services — Won't Work on Target Devices

**File:** `GuardTourNFC/.../GpsCollector.kt:19`, `build.gradle.kts:51`  
**Issue:** GPS collection depends on `com.google.android.gms:play-services-location:21.2.0` → `FusedLocationProviderClient`.  
This **requires** Google Play Services — your target devices (Android 7-10, no Play Store) **will not have GPS**.

**Fix:** Replace `FusedLocationProviderClient` with Android's built-in `LocationManager` API (`android.location`), which requires zero Play Services.

---

## 5. Redundant Loops & Duplicate Work

### 5.1 Two Heartbeat Loops Running Simultaneously
- `NfcScanService`: every **60s** (`HEARTBEAT_INTERVAL_MS`)
- `GuardDashboardActivity`: every **15s** (`startPolling()`)
Doubles server load when dashboard is open.

### 5.2 GPS Collector Started Twice
- `MainActivity.kt:36` starts it on app launch
- `GuardDashboardActivity.kt:42` starts it again  
Harmless (`stopCollecting()` guard) but wasteful.

### 5.3 Redundant Fallback GPS Poll
**File:** `GpsCollector.kt:65-76`  
Runs `fusedClient.lastLocation` every `intervalMs` alongside the main callback, even if the callback is already getting frequent updates.

---

## 6. Configuration & Maintenance

| # | Issue | File:Line |
|---|-------|-----------|
| 6.1 | **Hardcoded ngrok URL** — breaks when tunnel resets | `AppConstants.kt:4` |
| 6.2 | `targetSdk = 29` (Android 10) — intentional for older devices | `build.gradle.kts:13` ✅ **By design** |
| 6.3 | `usesCleartextTraffic="true"` — allows HTTP, remove for production | `AndroidManifest.xml:23` |
| 6.4 | No ProGuard/R8 minification even in release | `build.gradle.kts:20` |

---

## 7. Feature Request: Active Logins in Web UI

Currently no mechanism to:
- List which devices are currently logged in / authenticated
- See which Operator ID + password is active on each device
- Remotely switch/swap operator identity from the web UI

**Existing infrastructure that could support this:**
- `DeviceViewSet.swap_operator` action (`api/views.py:574`) — already swaps guard identity remotely
- `CallSign` model links device ↔ guard ↔ organization
- Heartbeat shows `is_online = True` when device is active

**What's needed:**
- A new endpoint or dashboard panel listing actively logged-in devices
- A UI to view current operator/password per device and trigger `swap_operator`
- A way to force re-login (clear device credentials server-side)

---

## 8. Body Sensors & Context-Aware Scanning (Already Supported by Backend)

### Backend already supports:
| Feature | Location | Status |
|---------|----------|--------|
| `raw_nfc` JSON field (UID, NDEF, tech, **sensors**) | `api/models.py:344` | ✅ Field exists |
| `validity_score` (0.0-1.0) | `api/models.py:348` | ✅ Computed server-side |
| `validity_reason` (human-readable) | `api/models.py:349` | ✅ Computed server-side |
| GPS proximity scoring | `api/scan_service.py:124-135` | ✅ Already implemented |
| Movement plausibility check | `api/scan_service.py:146-157` | ✅ Already implemented |
| Battery mitigator | `api/scan_service.py:159-162` | ✅ Already implemented |
| 30s scan cooldown (anti-spam) | `api/scan_service.py:18-27` | ✅ Already implemented |
| Peer-to-peer verification | `api/scan_service.py:79-114` | ✅ Already implemented |

### What's missing (app-side):
- The Android app never sends `raw_nfc` payload — server receives `None` for all sensor/context data
- The app never attaches GPS to scans — all validity scores are 0
- The app never uses `SensorManager` (accelerometer, gyroscope) to detect walking, stationary, pickup, etc.

---

## 9. Known Design Quirk: `device_id` = `operator_id`

**This is intentional but confusing.** The single point of conflation:

```python
# api/views.py:210
device = Device.objects.filter(device_id=operator_id).first()
```

**Flow:**
1. Web UI admin creates Device with `device_id = "TCN-01"` (via "Login Code" field)
2. Guard types `"TCN-01"` into the Android app's Operator ID field
3. App sends `POST /api/register-device/` with `operator_id: "TCN-01"`
4. Server matches `Device.objects.filter(device_id="TCN-01")` — finds the device
5. Server returns `device_id: "TCN-01"` back to the app
6. App stores `"TCN-01"` as the device_id in SharedPreferences
7. All subsequent calls use `device_id: "TCN-01"`

**If you changed device_id recently**, check that the web UI's "Login Code" field (`manage.html:1860`) still saves the value the guard will type. The `register_device` view must be able to match the typed value against `Device.device_id`.

---

## 10. Password Must Be Numeric-Only

The Android app uses a numeric keypad for login — passwords must be digits only.

### ✅ Fixed
| Location | Before | After |
|----------|--------|-------|
| `manage.html:2197` — `mgGeneratePassword()` | 12-char alphanumeric (`ABCDEF...`) | **8 random digits** |
| `api/views.py:650` — server fallback | `secrets.token_hex(16)` (32 hex chars) | `secrets.randbelow(90000000) + 10000000` (8 digits) |

Both the "Generate" button in the Register Device modal and the server-side auto-generation now produce 8-digit numeric passwords.

---

## 11. "Officer" → "Operator" Label Change

**Scope:** Label-only changes in `manage.html`. No logic, no database, no API changes.

| Location | Before | After |
|----------|--------|-------|
| `manage.html:1771` — Device inline panel | `Officer` | `Operator` |
| `manage.html:2405` — Callsign edit modal | `Active Officer Assignment` | `Active Operator Assignment` |
| `manage.html:2494` — Register Device modal | `Initial Officer Assignment` | `Initial Operator Assignment` |

The guard management section ("Add Officer", "Onboard Field Officer") was left unchanged — those are in the Guards tab, not the device menu.

---

## 12. Backend API Issues

### 12.1 `DeviceSerializer` Duplicate `class Meta` — TTS Fields Writable
**File:** `api/serializers.py:99-101` and `api/serializers.py:131-133`  
**Bug:** The serializer has TWO `class Meta` blocks. The first sets `read_only_fields` for TTS pending fields. The **second overrides it entirely**, making `tts_pending`, `tts_pending_at`, `tts_pending_voice`, `tts_pending_rate`, `tts_pending_pitch` all **writable via PUT/PATCH**. Anyone can overwrite queued TTS messages.

### 12.2 `generate_operator_id` Can Produce Duplicate IDs
**File:** `api/views.py:114-117`  
**Bug:** `seq = Device.objects.filter(organization=org).count() + 1`. If a device is deleted, `count()` returns fewer devices. The new ID might collide with an existing one (e.g. TCN-03 deleted, `count=4`, next is `TCN-05` — but TCN-05 still exists → **IntegrityError**).

### 12.3 Heartbeat Never Returns `device.tts_pending`
**File:** `api/views.py:364-374`  
**Bug:** `send_tts` action queues a message on `device.tts_pending`, but the heartbeat endpoint only returns route-level TTS config. The device-level pending TTS never reaches the app. (App also doesn't read it — see 2.8.)

### 12.4 Guard `is_on_shift` Never Reset on Assignment End
**File:** `api/models.py:413-418` (signal) + `api/views.py:600, 735, 916`  
**Bug:** The `post_save` signal only sets `is_on_shift = True` when `ShiftAssignment` is created with `is_active=True`. When assignments are closed (via `swap_operator`, `deploy`, `perform_create`), the guard's `is_on_shift` is **never set to False**. Guards remain "on shift" permanently unless the `end_shift` endpoint is used.

### 12.5 `assign_guard_to_blueprint_shift` Uses `Device.id` Not `Device.device_id`
**File:** `api/views.py:1364`  
**Confusion:** The request parameter is named `device_id` but the code does `get_object_or_404(Device, id=device_id)` — matching against the **auto-increment PK**, not the string `device_id` field. Frontend must send a numeric PK ID here, not the operator ID like "TCN-01".

### 12.6 `provision_device` Also Confuses `device_id` and PK
**File:** `api/views.py:236, 249-250`  
**Confusion:** Reads `device_id` from request and uses `Device.objects.get_or_create(device_id=device_id)`. This matches against the **string** `device_id` field. But the inline panel's save button (`manage.html:1885`) sends `device_id: data.device_id` from the "Login Code" field (which is the string device_id). Different endpoints use different lookup strategies.

### 12.7 `gps_batch_sync` Misleading Auth Error
**File:** `api/views.py:1954-1956`  
**Bug:** If the device is not found, returns `{'detail': 'Auth failed'}` with status 401. Should return "Device not found" with 404. "Auth failed" misleadingly suggests wrong password.

### 12.8 `device_trails` Uses `get()` Not `filter()` — Crash Risk
**File:** `api/views.py:2095`  
**Bug:** `Device.objects.get(device_id=device_id)` will crash with `MultipleObjectsReturned` if somehow duplicate device_ids exist. Should use `filter().first()` or handle the exception.

### 12.9 `ScanRecordViewSet` — `AllowAny` Permission
**File:** `api/views.py:811`  
**Risk:** The scan creation endpoint has `permission_classes = [AllowAny]`. Auth is done via device_id+password inside `process_scan`, but the list endpoint also uses `AllowAny` (though `get_queryset` returns `none()` for unauthenticated users). No rate limiting.

### 12.10 Dispatch Page POST No Validation
**File:** `api/views.py:1551-1569`  
**Risk:** The `dispatch_page` POST handler creates a `ShiftAssignment` directly from POST data. No validation that guard, device, and route belong to the same organization.

### 12.11 `Checkpoint.clean()` — Duplicate Planned Time Check Can Fail
**File:** `api/models.py:317-322`  
**Bug:** The duplicate `planned_time` check within the same route doesn't account for `null` planned_times. If multiple checkpoints have `planned_time=None`, the filter `planned_time=None` on line 317 may behave unexpectedly depending on the DB.

### 12.12 `ScanRecord.checkpoint` Uses `CASCADE` Delete
**File:** `api/models.py:335`  
**Risk:** `on_delete=models.CASCADE` on the checkpoint FK means deleting a checkpoint **destroys all scan history** for that checkpoint. Should use `SET_NULL` to preserve audit trail.

### 12.13 `OperatorAlert.operator` Has No `null=True`
**File:** `api/models.py:398`  
**Bug:** `operator` FK has no `null=True`, but `send_tts` (views.py:557-570) and `resend_tts` (views.py:1888-1899) both `OperatorAlert.objects.create(operator=a.guard_supervisor or None)`. If `guard_supervisor` is None (device-only assignment), this will crash with **IntegrityError**.

### 12.14 `CallSign.objects.create` in `perform_create` Can Crash
**File:** `api/views.py:655`  
**Bug:** `CallSign.objects.create(device=DeviceObj, ...)` where `CallSign.device` is `OneToOneField`. If the device was previously created via `provision_device` (which also creates a CallSign), creating a new device through the API with the same device won't happen (device_id is unique), but if someone creates a device, deletes its CallSign, then recreates... this is a minor edge case but still a risk.

### 12.15 No Rate Limiting on Any Device Endpoint
**Risk:** All `AllowAny` endpoints (`register-device`, `heartbeat`, `scans`, `gps-batch`, `scan-batch`, `mission-status`) have no rate limiting. A malicious device could hammer the server.

---

## 13. Backend API Summary by Severity

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 12.1 | **HIGH** | TTS pending fields writable via API | `serializers.py:131` |
| 12.2 | **HIGH** | `generate_operator_id` can collide | `views.py:114` |
| 12.3 | **HIGH** | Pending TTS never reaches device | `views.py:364` |
| 12.4 | **HIGH** | Guards stay "on shift" forever | `models.py:413` |
| 12.13 | **HIGH** | `OperatorAlert` crashes on device-only assignments | `models.py:398` |
| 12.5 | MEDIUM | `device_id` parameter name confusion | `views.py:1364` |
| 12.7 | MEDIUM | Misleading auth error in gps-batch | `views.py:1954` |
| 12.8 | MEDIUM | `get()` crash risk in device_trails | `views.py:2095` |
| 12.12 | MEDIUM | Scan history lost on checkpoint delete | `models.py:335` |
| 12.9 | LOW | No rate limiting on scan endpoint | `views.py:811` |
| 12.10 | LOW | Dispatch POST no org validation | `views.py:1551` |
| 12.11 | LOW | Duplicate time check edge case | `models.py:317` |
| 12.14 | LOW | CallSign creation edge case | `views.py:655` |
| 12.15 | LOW | No rate limiting on any device API | All AllowAny endpoints |
