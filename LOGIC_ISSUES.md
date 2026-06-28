# 🛠️ Functional Logic & Business Rule Issues

This document tracks the logic gaps in the GuardTour system. These are not bugs (crashes) or security holes, but failures in business logic that prevent the system from being a professional security tool.

---

## 🔴 Critical: Tour Integrity (Anti-Cheating)

### 1. Sequence Validation

**Issue:** The system currently accepts scans in any order. A guard can scan the last point first and the system marks it as "complete."

**Required Logic:**
- Compare the scanned `checkpoint_id` against the Route sequence.
- If `current_scan_index != last_scan_index + 1`, mark the record as `out_of_sequence = True`.

**Target Files:** `api/scan_service.py`, `api/models.py` (ScanRecord).

### 2. Missed Point Detection

**Issue:** The system records what was scanned, but does not explicitly identify what was skipped.

**Required Logic:**
- Implement a "Route Gap Analysis" function.
- Logic: `Route.checkpoints` MINUS `Shift.scan_records` = `MissedPoints`.
- Trigger a notification to the dispatcher when a point is skipped.

**Target Files:** `api/views.py` (Dispatcher Dashboard), `api/scan_service.py`.

### 3. Emergency Trigger Logic

**Issue:** Emergency routes/tags are defined in the DB but have no unique behavior in the code.

**Required Logic:**
- If `checkpoint.is_emergency == True`, bypass standard sequence validation.
- Immediately trigger a high-priority alert to the dispatcher.
- Change the `ShiftAssignment` status to `EMERGENCY_ACTIVE`.

**Target Files:** `api/scan_service.py`, `api/views.py`.

---

## 🟡 Medium: Operational Quality

### 4. Dwell Time Enforcement

**Issue:** `dwell_time` is defined in the model but not enforced. Guards can "tap and run."

**Required Logic:**
- Calculate `time_delta` between `ScanRecord[n]` and `ScanRecord[n-1]`.
- If `time_delta < checkpoint.dwell_time`, mark as `insufficient_dwell_time = True`.

**Target Files:** `api/scan_service.py`.

### 5. Shift Handover Logic

**Issue:** No mechanism to transfer a partially completed route from one guard to another.

**Required Logic:**
- Create a `transfer_shift(from_guard, to_guard)` method.
- Close the current `ShiftAssignment` and create a new one starting from the last successfully scanned checkpoint.

**Target Files:** `api/views.py`, `api/models.py`.

---

## 🌐 Real-time Architecture (WebSockets)

### 6. Transition from Polling to Event-Driven

**Issue:** Current heartbeat polling is inefficient and creates a delay in TTS delivery and location tracking.

**Required Logic:**
- Implement `GuardConsumer` to handle bi-directional communication.
- **Event Mapping:**
  - `LOCATION_UPDATE` (App → Server): Updates guard position and broadcasts to Dispatcher.
  - `TTS_COMMAND` (Server → App): Instant delivery of TTS messages.
  - `SCAN_EVENT` (App → Server): Real-time scan processing and validation.

**Target Files:** `api/consumers.py` (New), `api/routing.py` (New), `GuardTourNFC/.../SyncManager.kt`.

### 7. Connection State Management

**Issue:** WebSockets are stateful; if a connection drops, the guard is "invisible" to the dispatcher.

**Required Logic:**
- Implement `connect()` and `disconnect()` handlers in `GuardConsumer`.
- Update `Device.is_online` status in the database in real-time.
- Implement an exponential backoff reconnection strategy in the Android app.

### 8. Heartbeat → TTS Delivery (Legacy Fallback)

**Issue:** The server queues TTS messages, but the heartbeat response doesn't deliver them to the app.

**Required Logic:**
- Heartbeat view must check `device.tts_pending`.
- If present, include it in the JSON response and then set `tts_pending = None`.

**Target Files:** `api/views.py` (heartbeat), `GuardTourNFC/app/src/main/java/.../SyncManager.kt`.

---

## ✅ Completion Checklist

- [x] Sequence Validation implemented and tested.
- [x] Missed Point detection alerting the dispatcher.
- [x] Emergency tags triggering immediate alerts.
- [x] Dwell time validation active.
- [x] Shift handover logic functional.
- [x] WebSocket GuardConsumer implemented.
- [x] Real-time Online/Offline status tracking active.
- [x] TTS delivery pipeline closed (WebSocket or Heartbeat fallback).
