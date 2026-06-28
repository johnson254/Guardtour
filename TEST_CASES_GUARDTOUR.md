# GuardTour Full System - Test Cases

## Overview
GuardTour is a guard patrol NFC scanning system with:
- **Django REST API** backend (Python)
- **Android app** (Kotlin) for field guards
- Multi-tenant architecture with Organizations
- Device-based authentication (no JWT for device endpoints)

---

## Test Case Format
Each test case has:
- **Test ID**: `TC-XXX`
- **Component**: Backend API | Android App | End-to-End
- **Prerequisites**: What must exist before the test
- **Test Steps**: Numbered actions
- **Expected Result**: What should happen
- **API Endpoint**: For backend tests

---

## BACKEND API TEST CASES

---

### TC-API-001: Device Registration (New Device)

**Component:** Backend API  
**Endpoint:** `POST /api/register-device/`  
**Prerequisites:** None  
**Description:** New device registers and receives a password

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `/api/register-device/` with `{ "operator_id": "TCN-01" }` | Status 200, returns `{ status: 'registered', device_id, password }` |
| 2 | Verify the pre-provisioned Device for operator TCN-01 is returned with correct `device_id` and `password` | Device exists with correct fields |
| 3 | Verify CallSign record links device to guard's organization | CallSign has device, organization, callsign |
| 4 | Repeat registration with same device_id | Status 200, `is_new: false`, same password returned |

---

### TC-API-002: Device Registration - Hardware Info Capture

**Component:** Backend API  
**Endpoint:** `POST /api/register-device/`  
**Prerequisites:** None  
**Description:** Device registration captures hardware telemetry

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST with full hardware payload: `{ "device_id": "GT-TEST002", "device_name": "Test", "imei": "123456789", "imsi": "987654321", "sim_phone_number": "+1234567890", "os_version": "Android 14", "manufacturer": "Samsung", "model": "Galaxy S24", "battery_pct": 85 }` | Status 200, all fields saved to Device |
| 2 | Verify `device.imei="123456789"`, `device.os_version="Android 14"`, etc. | Hardware info persisted |
| 3 | Verify `device.last_seen` updated and `device.is_online=True` | Online status updated |

---

### TC-API-003: Heartbeat - Device Online Status

**Component:** Backend API  
**Endpoint:** `POST /api/heartbeat/`  
**Prerequisites:** Device registered via TC-API-001  
**Description:** Device sends periodic heartbeat to stay online and receive directives

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `/api/heartbeat/` with `{ "device_id": "GT-TEST001", "password": "<password>" }` | Status 200, `{ status: 'ok' }` |
| 2 | Verify `device.is_online=True` and `device.last_seen` updated | Device marked online |
| 3 | Heartbeat with battery `battery_pct: 45`, GPS `lat: 40.7128, lng: -74.0060, gps_accuracy: 5` | Fields updated, response contains any pending directives |

---

### TC-API-004: Heartbeat - NFC Fetch Directive

**Component:** Backend API  
**Endpoint:** `POST /api/devices/<id>/fetch_nfc/` then `POST /api/heartbeat/`  
**Prerequisites:** Registered device  
**Description:** Server requests device to fetch NFC data on next heartbeat

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `/api/devices/1/fetch_nfc/` (authenticated) | Status 200, `{ status: 'requested', message: 'NFC fetch requested...' }` |
| 2 | Verify `device.nfc_fetch_requested` is set to a timestamp | Field updated |
| 3 | Device sends heartbeat | Response includes `fetch_nfc: true` |
| 4 | Device sends second heartbeat | Response NO LONGER has `fetch_nfc` (flag cleared after first acknowledgment) |

---

### TC-API-005: Guard/Supervisor Creation via scan-guards

**Component:** Backend API  
**Endpoint:** `POST /api/scan-guards/`  
**Prerequisites:** Organization exists  
**Description:** Dispatcher creates a data-only guard (no Django user)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `{ "first_name": "John", "last_name": "Doe", "role": "guard", "shift": "Day" }` as authenticated dispatcher | Status 201, returns GuardSupervisor object |
| 2 | Verify `GuardSupervisor` created with `user=null`, `first_name="John"`, `role="guard"` | Guard record exists without Django user |
| 3 | Verify `guard.callsign=null` initially | Callsign not assigned yet |
| 4 | Attempt as unauthenticated user | Status 403 Forbidden |

---

### TC-API-006: Device Provisioning to Guard

**Component:** Backend API  
**Endpoint:** `POST /api/provision-device/`  
**Prerequisites:** Device registered, Guard created  
**Description:** Bind a device to a guard and create active shift assignment

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `{ "device_id": "GT-TEST001", "guard_id": "<guard_id>", "scheduled_start": "2024-01-15T08:00:00Z", "scheduled_end": "2024-01-15T16:00:00Z" }` | Status 201, `{ status: 'provisioned', device_id, callsign }` |
| 2 | Verify `CallSign` updated with `current_guard=guard`, `active_shift=guard.shift` | CallSign binding updated |
| 3 | Verify `guard.callsign` now set to device's callsign | Guard callsign populated |
| 4 | Verify `DeviceProvisioning` record created | Historical binding exists |
| 5 | Verify `ShiftAssignment` created with `is_active=True`, `route=null`, `guard_supervisor=guard` | Active assignment without route |
| 6 | Provision same device to different guard | Previous active assignment closed (is_active=False, ended_at set), new one created |

---

### TC-API-007: Route (Blueprint) Creation with Checkpoints

**Component:** Backend API  
**Endpoint:** `POST /api/routes/`  
**Prerequisites:** Organization, Guard created  
**Description:** Create a patrol route with embedded checkpoints

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST route with checkpoints: `{ "name": "Main Patrol", "status": "draft", "logic_type": "Sequential", "assigned_guards": ["<guard_id>"], "checkpoints": [ { "name": "Gate A", "checkpoint_type": "nfc", "nfc_tag": "TAG-001", "order": 1, "planned_time": "08:00:00", "time_tolerance": 15 }, { "name": "Lobby", "checkpoint_type": "nfc", "nfc_tag": "TAG-002", "order": 2, "planned_time": "08:30:00", "time_tolerance": 10 } ] }` | Status 201, full route with checkpoints returned |
| 2 | Verify 2 Checkpoint records created with `route` foreign key | Checkpoints linked to route |
| 3 | Verify `checkpoint.route.organization` inherited from parent route | Organization set on checkpoints |
| 4 | Create checkpoint with `checkpoint_type: "gps"` and `lat/lng` | Checkpoint created (requires coords for GPS type) |
| 5 | Attempt checkpoint with `checkpoint_type: "nfc"` but no `nfc_tag` | Validation error: 'NFC tag required for NFC checkpoints' |

---

### TC-API-008: Route Deployment

**Component:** Backend API  
**Endpoint:** `POST /api/routes/<id>/deploy/`  
**Prerequisites:** Route with assigned guards/devices from TC-API-007  
**Description:** Deploy creates active shift assignments for all assigned personnel

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST to deploy endpoint | Status 200, `{ status: 'deployed', assignments_count: N }` |
| 2 | Verify `ShiftAssignment` created for each assigned guard with `is_active=True`, `route=route` | Assignments active |
| 3 | Verify for device-only assignments, `guard_supervisor=null` | Device-only assignment created |
| 4 | Deploy same route again | New assignments created, old ones remain but marked inactive? Or replaced? (depends on deploy logic) |
| 5 | Attempt deploy on route with no assigned guards or devices | Status 400: 'Deployment aborted: No personnel or devices assigned' |

---

### TC-API-009: NFC Scan Processing - Tag Scan

**Component:** Backend API  
**Endpoint:** `POST /api/scans/`  
**Prerequisites:** Device registered, route deployed with checkpoints  
**Description:** Device scans NFC tag, server processes and validates

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST scan: `{ "device_id": "GT-TEST001", "password": "<pwd>", "nfc_value": "TAG-001", "lat": 40.7128, "lng": -74.0060 }` | Status 200, ScanRecord created |
| 2 | Verify `ScanRecord.guard_supervisor` set from active ShiftAssignment | Guard linked to scan |
| 3 | Verify `ScanRecord.checkpoint` resolved to correct Checkpoint | Checkpoint matched |
| 4 | Verify `is_on_time` calculated: true if within planned_time ± tolerance | On-time status set |
| 5 | Verify `validity_score` and `validity_reason` calculated | Validity scoring applied |
| 6 | Verify `guard_supervisor.last_scan` updated | Guard's last scan time updated |

---

### TC-API-010: NFC Scan - Duplicate Cooldown

**Component:** Backend API  
**Endpoint:** `POST /api/scans/`  
**Prerequisites:** Device registered, checkpoint exists  
**Description:** Same NFC tag scanned within 30 seconds returns cooldown error

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST valid scan for TAG-001 | Status 200, scan created |
| 2 | Immediately POST same scan again | Status 400: 'Cooldown active. Please wait 30s between scans' |
| 3 | Wait 30 seconds and rescan | Status 200, new scan created |
| 4 | Scan with different nfc_value after cooldown | Status 200, no cooldown (cooldown is per-nfc_value) |

---

### TC-API-011: NFC Scan - Invalid Device Password

**Component:** Backend API  
**Endpoint:** `POST /api/scans/`  
**Prerequisites:** Device registered  
**Description:** Scan with wrong password fails authentication

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST with correct device_id but wrong password | Status 400: validation error 'Device authentication failed' |
| 2 | POST with non-existent device_id | Status 400: 'Device authentication failed' |
| 3 | POST with empty device_id or password | Status 400: 'Device authentication failed' |

---

### TC-API-012: NFC Scan - Unknown Tag

**Component:** Backend API  
**Endpoint:** `POST /api/scans/`  
**Prerequisites:** Device registered  
**Description:** Scanning an unknown NFC tag creates scan with unknown checkpoint

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST scan with `nfc_value: "UNKNOWN-TAG"` | Status 200, ScanRecord created |
| 2 | Verify `checkpoint=null` for unknown tag | No checkpoint linked |
| 3 | Verify `checkpoint_name="Unknown Tag: UNKNOWN-TAG"` | Named appropriately |
| 4 | Verify `validity_score` calculated even without checkpoint | Score based on GPS proximity to device's last location only |

---

### TC-API-013: NFC Scan - Raw NFC Payload Parsing

**Component:** Backend API  
**Endpoint:** `POST /api/scans/`  
**Prerequisites:** Device registered  
**Description:** Raw NFC payload with NDEF records is parsed correctly

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST with `raw_nfc: { "ndef_records": [ { "payload_text": "TAG-003" } ], "uid": "04:A2:B3:..." }` and no `nfc_value` | `nfc_value` extracted from NDEF text payload |
| 2 | POST with peer handshake payload: `{ "ndef_records": [ { "payload_json": { "type": "peer_handshake", "device_id": "GT-PEER01", "nonce": "abc123", "timestamp": 1234567890 } } ], "uid": "..." }` | Scan type detected as 'peer', peer_device_id extracted |
| 3 | POST with raw NFC but empty/invalid payload | Falls back to uid-based identification |

---

### TC-API-014: GPS Batch Upload

**Component:** Backend API  
**Endpoint:** `POST /api/gps-batch/`  
**Prerequisites:** Device registered  
**Description:** Device uploads accumulated GPS trail points

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST batch: `{ "device_id": "GT-TEST001", "password": "<pwd>", "points": [ { "lat": 40.7128, "lng": -74.0060, "accuracy": 5.0, "recorded_at": "2024-01-15T08:00:00Z", "battery_pct": 90 }, { "lat": 40.7130, "lng": -74.0058, "accuracy": 3.5, "recorded_at": "2024-01-15T08:00:30Z" } ] }` | Status 200, `{ synced: 2, corrected: [...] }` |
| 2 | Verify 2 `DeviceTrail` records created | Trail points stored |
| 3 | Verify `corrected` flag set on points that were smoothed | GPS correction applied |

---

### TC-API-015: Scan Batch Upload (Offline Sync)

**Component:** Backend API  
**Endpoint:** `POST /api/scan-batch/`  
**Prerequisites:** Device registered  
**Description:** Device uploads accumulated offline scans

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST batch: `{ "device_id": "GT-TEST001", "password": "<pwd>", "scans": [ { "nfc_value": "TAG-001", "recorded_at": "2024-01-15T08:00:00Z", "lat": 40.7128, "lng": -74.0060 }, { "nfc_value": "TAG-002", "recorded_at": "2024-01-15T08:30:00Z", "lat": 40.7135, "lng": -74.0055 } ] }` | Status 200, `{ synced: 2, results: [...] }` |
| 2 | Verify 2 ScanRecords created with correct timestamps | Offline scans recorded |
| 3 | Verify duplicate detection still applies to batch uploads | If scan within 30s of existing, marked 'skipped' |

---

### TC-API-016: Swap Operator

**Component:** Backend API  
**Endpoint:** `POST /api/devices/<id>/swap_operator/`  
**Prerequisites:** Device provisioned to Guard A, Guard B exists  
**Description:** Remotely reassign device from one guard to another

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST `{ "guard_id": "<guard_b_id>" }` | Status 200, `{ status: 'swapped', device_id, callsign, guard_name }` |
| 2 | Verify Guard A's active ShiftAssignment closed (is_active=False, ended_at set) | Previous assignment ended |
| 3 | Verify CallSign now points to Guard B | Device linked to new guard |
| 4 | Verify new ShiftAssignment created for Guard B with `is_active=True` | New assignment active |
| 5 | Swap via callsign instead: POST `{ "callsign": "H-02@org" }` | Same result, resolved via callsign |

---

### TC-API-017: Mission Status - Active Patrol

**Component:** Backend API  
**Endpoint:** `POST /api/scans/` then `GET /api/mission-status/<id>/`  
**Prerequisites:** Route deployed, guard scanning checkpoints  
**Description:** Get current mission status including next checkpoint info

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Guard scans TAG-001 (first checkpoint) | Scan recorded |
| 2 | GET mission-status for the assignment | Status 200, `{ staging: { completed: false, hit_count: 1, total: 5, next_checkpoint: { id, name: "Checkpoint 2", ... } } }` |
| 3 | Guard scans remaining checkpoints | hit_count increments |
| 4 | After final checkpoint scanned, GET mission-status | `{ staging: { completed: true, hit_count: 5, total: 5 } }` |

---

### TC-API-018: Shift Assignment End

**Component:** Backend API  
**Endpoint:** `POST /api/end-shift/<id>/`  
**Prerequisites:** Active shift assignment  
**Description:** Manually end a shift assignment

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST to end-shift endpoint | Status 200 or 302 redirect |
| 2 | Verify ShiftAssignment `is_active=False`, `ended_at` set | Assignment closed |
| 3 | Verify `guard_supervisor.is_on_shift=False` | Guard marked off shift |

---

### TC-API-019: Dispatcher Organization Scoping

**Component:** Backend API  
**Prerequisites:** Multiple organizations, dispatchers per org  
**Description:** Dispatchers can only see their organization's data

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as Dispatcher for Org A | JWT token received |
| 2 | GET /api/routes/ | Only routes belonging to Org A (or organization=null) returned |
| 3 | GET /api/guards/ | Only guards in Org A returned |
| 4 | POST route for Org B | Should fail with PermissionDenied |
| 5 | Login as Dispatcher for Org B | Can see Org B's routes, not Org A's |

---

### TC-API-020: Admin Full Access

**Component:** Backend API  
**Prerequisites:** Superuser or Admin profile  
**Description:** Admins see all organizations' data

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login as superuser | Can access all organizations |
| 2 | GET /api/routes/ | All routes from all organizations returned |
| 3 | GET /api/guards/ | All guards from all organizations returned |
| 4 | POST route without specifying organization | Route created with null org or default org |

---

### TC-API-021: Incident Report Creation

**Component:** Backend API  
**Endpoint:** `POST /api/incidents/`  
**Prerequisites:** Guard on active shift  
**Description:** Guards can report incidents from the field

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST incident: `{ "category": "security", "title": "Unauthorized Access", "description": "Found door propped open", "lat": 40.7128, "lng": -74.0060 }` | Status 201, incident created |
| 2 | Verify `incident.guard_supervisor` set to reporting guard | Guard linked |
| 3 | Verify `incident.organization` inherited from guard | Org set |
| 4 | GET incidents filtered by `category=security` | Only security incidents returned |
| 5 | GET incidents filtered by `is_resolved=false` | Only unresolved returned |

---

### TC-API-022: Operator Alert with TTS Config

**Component:** Backend API  
**Endpoint:** `POST /api/resend-tts/`  
**Prerequisites:** Active shift assignment with route  
**Description:** Send TTS announcement to guard's device

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST: `{ "assignment_id": "<id>", "message": "All guards proceed to staging area", "play_sound": true, "vibrate": true, "tts_voice": "en-GB-Standard-A", "tts_rate": 0.9 }` | Status 200, OperatorAlert created |
| 2 | Verify `alert.operator=guard`, `alert.tts_voice`, `alert.tts_rate` set | TTS config saved |
| 3 | Verify `alert.priority` default is 'normal' | Default priority set |
| 4 | POST with `priority: "urgent"` | Urgent alert created |

---

### TC-API-023: Checkpoint Validation - NFC without Tag

**Component:** Backend API  
**Prerequisites:** None  
**Description:** Cannot create NFC checkpoint without nfc_tag

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST checkpoint: `{ "name": "Invalid NFC", "checkpoint_type": "nfc", "nfc_tag": null }` | ValidationError: 'NFC tag required for NFC checkpoints' |
| 2 | POST checkpoint: `{ "name": "Invalid GPS", "checkpoint_type": "gps", "lat": null, "lng": null }` | ValidationError: 'GPS coordinates required for GPS checkpoints' |
| 3 | Verify NFC checkpoint auto-clears lat/lng fields | lat/lng set to None for NFC type |
| 4 | Verify GPS checkpoint auto-clears nfc_tag | nfc_tag set to None for GPS type |

---

### TC-API-024: Checkpoint Duplicate Planned Time

**Component:** Backend API  
**Prerequisites:** Route with checkpoints  
**Description:** Cannot have two checkpoints on same route with same planned_time

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create route with checkpoint at 08:00 | Checkpoint created |
| 2 | Attempt to add another checkpoint at 08:00 on same route | ValidationError: 'Another checkpoint in this route already has planned time' |
| 3 | Add checkpoint at 08:01 on same route | Success |

---

### TC-API-025: Guard Supervisor Callsign Validation

**Component:** Backend API  
**Prerequisites:** None  
**Description:** Guard callsign must follow ORG-SEQ format (e.g. TCN-01)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | POST guard with callsign "TCN-01" | Status 201, valid |
| 2 | POST guard with callsign "TCN" (no -NN suffix) | ValidationError: 'Operator ID must be ORG-NN format (e.g. TCN-01)' |
| 3 | POST guard with callsign "AB-01@twocan" (prefix not numeric) | ValidationError: 'Operator ID prefix must be numeric (NN)' |
| 4 | POST guard with null callsign | Allowed (callsign optional until device bound) |

---

## ANDROID APP TEST CASES

---

### TC-AND-001: First Launch - Generate Device ID

**Component:** Android App  
**Prerequisites:** Fresh install  
**Description:** App generates unique device ID on first launch

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Install app, launch | App shows Operator ID field (e.g. TCN-01) |
| 2 | Verify device_id saved to SharedPreferences | Device ID persisted |
| 3 | Kill and relaunch app | Same device_id used (not regenerated) |

---

### TC-AND-002: Guard Login with Callsign

**Component:** Android App  
**Prerequisites:** GuardSupervisor exists with matching callsign  
**Description:** Guard logs in with callsign and PIN

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter operator ID "TCN-01", PIN "1234" | Validation passes (format correct) |
| 2 | Tap Login | POST to register-device endpoint |
| 3 | On success, save device_id, password, callsign to SharedPreferences | Credentials stored |
| 4 | Navigate to Dashboard | Dashboard shows guard_name, callsign, device_id |

---

### TC-AND-003: PIN Lock Screen

**Component:** Android App  
**Prerequisites:** PIN set from login  
**Description:** Dashboard requires PIN to view

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Launch app | PIN overlay appears |
| 2 | Enter wrong PIN | "Invalid PIN" shown, stays on PIN screen |
| 3 | Enter correct PIN | Dashboard visible |
| 4 | Background app for 5+ minutes | PIN screen reappears on return |

---

### TC-AND-004: NFC Scan Detection

**Component:** Android App  
**Prerequisites:** NfcScanService running  
**Description:** NFC tag detected and sent to server

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Tap NFC tag against device | NfcScanService.handleNfcTag() triggered |
| 2 | Extract NDEF text or use UID | nfcValue extracted |
| 3 | POST to /api/scans/ with device_id, password, nfc_value | Scan submitted |
| 4 | Check notification shows "Scan OK" | Success notification displayed |

---

### TC-AND-005: NFC Scan - Offline Buffer

**Component:** Android App  
**Prerequisites:** No network connectivity  
**Description:** Scan stored locally when offline

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Disable network (airplane mode) | - |
| 2 | Scan NFC tag | Scan saved to ScanBuffer Room table with synced=false |
| 3 | Notification shows "Scan Saved" (not "Scan OK") | Offline indication |
| 4 | Re-enable network | SyncManager uploads buffered scans |
| 5 | Verify scan marked as synced=true after sync | Sync confirmed |

---

### TC-AND-006: GPS Collection Running

**Component:** Android App  
**Prerequisites:** Location permissions granted  
**Description:** GPS points collected in background

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start GpsCollector service | Foreground service notification shown |
| 2 | Move to different location | New point stored in gps_points Room table |
| 3 | Check point has lat, lng, accuracy, speed, bearing | Fields populated |
| 4 | Verify battery percentage recorded with each point | battery_pct included |

---

### TC-AND-007: Heartbeat - Periodic

**Component:** Android App  
**Prerequisites:** Dashboard visible  
**Description:** Dashboard sends heartbeat every 15 seconds

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Dashboard visible | Heartbeat sent every 15s |
| 2 | Check network tab for heartbeat POSTs | Requests to /api/heartbeat/ |
| 3 | Verify response parsed for tts_voice, tts_rate, tts_pitch | TTS config applied |
| 4 | If fetch_nfc directive in response | NfcScanService triggers NFC fetch |


---

### TC-AND-008: TTS Readback on Scan

**Component:** Android App  
**Prerequisites:** TTS config received from heartbeat  
**Description:** Scan result announced via Text-to-Speech

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Receive heartbeat with `tts_voice: "en-US", tts_rate: 1.0, tts_pitch: 1.0` | Config stored |
| 2 | Scan NFC tag | TTS announces result: "Gate A, Scan OK" or "Scan Failed" |
| 3 | If route has `readout_text` and checkpoint has `next_announcement_text` | Announced after scan |

---

### TC-AND-009: Battery Optimization

**Component:** Android App  
**Prerequisites:** Low battery  
**Description:** System may kill app on low battery

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Battery drops to 5% | App may be killed by system |
| 2 | On restart (BootReceiver or manual) | NfcScanService restarts as foreground service |
| 3 | Pending scans and GPS points not lost | Offline buffer intact |

---

### TC-AND-010: App Restart on Boot

**Component:** Android App  
**Prerequisites:** App installed and registered  
**Description:** Boot receiver starts services automatically

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Reboot device | BOOT_COMPLETED broadcast received |
| 2 | BootReceiver starts NfcScanService | NFC scanning foreground service running |
| 3 | BootReceiver starts GpsCollector | GPS tracking foreground service running |
| 4 | Services continue without user interaction | Background patrol mode active |

---

## END-TO-END INTEGRATION TEST CASES

---

### TC-E2E-001: Complete Patrol Flow

**Component:** End-to-End  
**Prerequisites:** Organization, Dispatcher, Guard with device  
**Description:** Full patrol from dispatch to completion

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Dispatcher creates route with 3 NFC checkpoints | Route and checkpoints created |
| 2 | Dispatcher assigns guard and deploys route | ShiftAssignment created, is_active=True |
| 3 | Guard logs into Android app | Dashboard shows active mission |
| 4 | Guard scans Checkpoint 1 | Scan recorded, checkpoint marked done |
| 5 | Guard scans Checkpoint 2 | Scan recorded |
| 6 | Guard scans Checkpoint 3 | Final scan recorded |
| 7 | Dispatcher checks mission status | Shows completed=true |
| 8 | Dispatcher ends shift | is_active=False, guard marked off-shift |

---

### TC-E2E-002: Multi-Guard Deployment

**Component:** End-to-End  
**Prerequisites:** Route with 2+ guards assigned  
**Description:** Two guards deployed on same route simultaneously

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Deploy route with 2 assigned guards | 2 ShiftAssignments created |
| 2 | Guard A scans checkpoint | Guard A's scan recorded |
| 3 | Guard B scans same checkpoint (different device) | Guard B's scan recorded separately |
| 4 | Dispatcher views org-stats | Shows 2 active_guards, both scans counted |

---

### TC-E2E-003: Device Swap Mid-Patrol

**Component:** End-to-End  
**Prerequisites:** Guard A active on device  
**Description:** Device reassigned to different guard during active patrol

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Guard A on active patrol, scans checkpoint 1 | Scan recorded |
| 2 | Dispatcher calls swap_operator to reassign to Guard B | CallSign updated, Guard A's assignment ended |
| 3 | Guard B logs into same device | Dashboard shows new assignment |
| 4 | Guard B resumes from checkpoint 2 | Guard B's scans continue from where left off |
| 5 | View mission status | Shows Guard B's hit_count continuing |

---

### TC-E2E-004: GPS Accuracy Filter

**Component:** End-to-End  
**Prerequisites:** GPS checkpoint  
**Description:** GPS accuracy affects scan validity

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create GPS checkpoint at lat/lng with radius=50m | Checkpoint created |
| 2 | Guard within 10m, accuracy=3m, scans | validity_score gets full 0.6 for GPS proximity |
| 3 | Guard within 150m (3x radius), accuracy=10m, scans | validity_score gets 0.3 partial credit |
| 4 | Guard 200m away, scans | validity_score gets 0, reason: "Far from checkpoint" |

---

### TC-E2E-005: Low Battery Scan Penalty

**Component:** End-to-End  
**Prerequisites:** Device with low battery  
**Description:** Low battery reduces scan validity score

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device battery at 20%, scan | -0.1 penalty applied to validity_score |
| 2 | Device battery at 10%, scan | -0.1 penalty applied |
| 3 | Device battery at 50%, scan | No penalty |
| 4 | Verify reason includes "Low battery (X%)" | Reason string includes battery info |

---

### TC-E2E-006: Peer-to-Peer Audit Scan

**Component:** End-to-End  
**Prerequisites:** Route with is_audit=True and peer checkpoint  
**Description:** Two guards exchange peer NFC beams for audit patrol

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Guard A scans peer checkpoint, initiates NFC beam | Scan sent with `raw_nfc` containing peer_handshake |
| 2 | Guard B receives beam and responds | Scan sent with reciprocal peer_handshake |
| 3 | Guard A's scan validated: reciprocal scan found within 30s | Valid peer scan |
| 4 | Guard A's scan without reciprocal | Rejected: 'No reciprocal peer scan found' |

---

### TC-E2E-007: Offline Then Sync

**Component:** End-to-End  
**Prerequisites:** Guard starts patrol with connectivity  
**Description:** Guard completes patrol in dead zone, syncs when back online

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Guard scans checkpoint 1 with connectivity | Scan uploaded immediately |
| 2 | Guard enters dead zone | - |
| 3 | Guard scans checkpoints 2, 3, 4 offline | Scans buffered locally |
| 4 | Guard returns to coverage | SyncManager uploads buffered scans |
| 5 | Verify all 4 scans appear in backend | Complete patrol recorded |
| 6 | Verify timestamps reflect actual scan time, not sync time | Scan times preserved |

---

### TC-E2E-008: Organization Data Isolation

**Component:** End-to-End  
**Prerequisites:** Two organizations with guards/devices  
**Description:** Org A cannot see Org B's data

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create guard in Org A, scan checkpoint in Org A | Scan recorded for Org A |
| 2 | Create guard in Org B | Guard visible in Org B only |
| 3 | Login as Org B dispatcher | Cannot see Org A's guards or routes |
| 4 | Device from Org A attempts to scan checkpoint in Org B | Checkpoint belongs to Org A only, not found |

---

## BOUNDARY/EDGE CASE TEST CASES

---

### TC-EDGE-001: Clock Skew in Scan Timestamps

**Component:** Backend API  
**Prerequisites:** Device clock is incorrect  
**Description:** Offline scans with wrong timestamps

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Scan at 08:00:00 (correct time) | Scan recorded at 08:00:00 server time |
| 2 | Device clock is 1 hour ahead, scan at 09:30:00 (device) | Recorded at 08:30:00 server time |
| 3 | is_on_time calculation uses server time, not device time | Based on server timestamp |

---

### TC-EDGE-002: GPS Correction - Teleportation Rejection

**Component:** Backend API (correct_gps_trail)  
**Prerequisites:** GPS trail with impossible speed between points  
**Description:** GPS points with speed > 30 m/s are corrected

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Upload GPS points where point 1 and 2 are 5km apart in 10 seconds | Speed = 500 m/s (impossible) |
| 2 | Verify corrected=true on the outlier point | Point flagged as corrected |
| 3 | Verify lat/lng adjusted toward plausible location | Interpolated position |
| 4 | Check correctness of smoothing on remaining points | Valid points unchanged |

---

### TC-EDGE-003: Device Registration with Existing Callsign

**Component:** Backend API  
**Prerequisites:** Callsign already bound to another device  
**Description:** Re-registering with same callsign updates binding

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Register device A with operator_id "TCN-01" | Device A authenticated and returned |
| 2 | Register device B with same operator_id "TCN-01" | Same device returned (CallSign binding unchanged) |
| 3 | Device A's callsign field updated? Device A no longer has callsign binding | Old device unbound |

---

### TC-EDGE-004: Route Deploy with Inactive Guard

**Component:** Backend API  
**Prerequisites:** Guard exists but not currently on shift  
**Description:** Guard can be deployed even if is_on_shift=false

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create shift assignment manually (guard.is_on_shift may be false) | Assignment created |
| 2 | Guard scans checkpoint | Scan still works regardless of is_on_shift flag |
| 3 | Verify is_on_shift updated to true when assignment activated | Signal handler updates guard status |

---

### TC-EDGE-005: Concurrent Scans Same Checkpoint

**Component:** Backend API  
**Prerequisites:** Two devices, same checkpoint  
**Description:** Multiple devices can scan same checkpoint

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device A scans TAG-001 | Scan recorded |
| 2 | Device B scans TAG-001 (within 30s) | Device B's scan succeeds if nfc_value differs or cooldown per-device-checkpoint |
| 3 | Device A scans TAG-001 immediately again | Cooldown per device+checkpoint |

---

### TC-EDGE-006: Route with No Checkpoints

**Component:** Backend API  
**Prerequisites:** Route deployed with no checkpoints  
**Description:** Route with 0 checkpoints immediately shows as completed

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Deploy route with no checkpoints | Assignments created |
| 2 | GET mission-status | completed: true, hit_count: 0, total: 0 |

---

### TC-EDGE-007: Checkpoint Time Window Missed

**Component:** Backend API  
**Prerequisites:** Checkpoint with planned_time that has passed  
**Description:** Scanning after window misses deadline

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Checkpoint planned at 08:00, tolerance 15min, dwell 5min | Window: 07:45 - 08:20 |
| 2 | Scan at 08:30 | is_on_time: false |
| 3 | GET mission-status for next checkpoint | is_window_missed: true |

---

## TEST DATA SETUP REQUIREMENTS

Before running tests, these base records must exist:

```
Organizations:
- Org: "Test Organization" (id=1)
- Org: "Second Organization" (id=2)

Users (Django):
- admin: superuser (or Admin profile linking to Org 1)
- dispatcher1: Dispatcher for Org 1 (can_manage_routes=true, can_manage_guards=true)
- dispatcher2: Dispatcher for Org 2

GuardSupervisors:
- guard1: first_name="John", last_name="Doe", role="guard", shift="Day", organization=Org 1
- guard2: first_name="Jane", last_name="Smith", role="supervisor", shift="Night", organization=Org 1
- guard3: first_name="Bob", last_name="Wilson", role="guard", shift="Day", organization=Org 2

Devices:
- device1: device_id="GT-TEST001", device_name="Test Device 1", callsign="TCN-01", organization=Org 1
- device2: device_id="GT-TEST002", device_name="Test Device 2", organization=Org 1

PatrolRoutes:
- route1: "Morning Patrol", organization=Org 1, status="active", enforce_order=true, enforce_time=true
  - checkpoint1: name="Gate", checkpoint_type="nfc", nfc_tag="TAG-GATE", order=1, planned_time=08:00:00
  - checkpoint2: name="Lobby", checkpoint_type="nfc", nfc_tag="TAG-LOBBY", order=2, planned_time=08:30:00
  - checkpoint3: name="Staging", checkpoint_type="gps", lat=40.7128, lng=-74.0060, radius=50, order=3

ShiftAssignments (for E2E tests):
- assignment1: dispatcher=dispatcher1, guard_supervisor=guard1, device=device1, route=route1, is_active=true
```

---

## POSTMAN/INSOMNIA COLLECTION STRUCTURE

```
GuardTour API
├── Auth
│   ├── POST /api/register/ (create user + dispatcher profile)
│   ├── POST /api/login/ (get JWT)
│   └── Cookie set: gt_access_token
│
├── Devices
│   ├── POST /api/register-device/ (device auth, AllowAny)
│   ├── POST /api/heartbeat/ (device auth, AllowAny)
│   ├── POST /api/devices/{id}/fetch_nfc/
│   ├── POST /api/devices/{id}/fetch_gps/
│   └── POST /api/devices/{id}/swap_operator/
│
├── Guards
│   ├── GET /api/guards/
│   ├── POST /api/guards/
│   ├── POST /api/scan-guards/
│   └── GET/PUT/DELETE /api/profiles/{id}/
│
├── Routes (Blueprints)
│   ├── GET /api/routes/
│   ├── POST /api/routes/
│   ├── POST /api/routes/{id}/deploy/
│   └── GET /api/routes/{id}/
│
├── Checkpoints
│   ├── GET /api/checkpoints/
│   └── POST /api/checkpoints/
│
├── Scans
│   ├── POST /api/scans/ (device auth, AllowAny)
│   ├── POST /api/scan-batch/ (device auth, AllowAny)
│   ├── GET /api/scans/ (authenticated)
│   └── GET /api/scans/?guard_id=X&start_date=X&end_date=X
│
├── GPS
│   ├── POST /api/gps-batch/ (device auth, AllowAny)
│   └── GET /api/device-trails/{device_id}/
│
├── Shifts
│   ├── GET /api/shifts/
│   ├── POST /api/shifts/ (supports bulk guard_ids[])
│   ├── GET /api/mission-status/{id}/ (AllowAny)
│   └── POST /api/end-shift/{id}/
│
├── Incidents
│   ├── GET /api/incidents/
│   └── POST /api/incidents/
│
├── Statistics
│   ├── GET /api/org-stats/
│   └── GET /api/admin-stats/
│
└── TTS
    └── POST /api/resend-tts/
```