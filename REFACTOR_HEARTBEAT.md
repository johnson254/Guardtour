# Heartbeat Refactor

## Why

The `heartbeat` function in `api/views.py:316-529` had a McCabe complexity of **38** across **214 lines**, handling **9 distinct responsibilities** in a single function. This made it difficult to reason about, test, and maintain.

## What Changed

The function was decomposed into focused helper functions, each with a single responsibility:

| # | Responsibility | Extracted To | Lines |
|---|---------------|-------------|-------|
| 1 | Device auth + validation | `_heartbeat_auth` | 12 |
| 2 | Device state update (battery, GPS, last_seen) | `_heartbeat_update_device` | 22 |
| 3 | NFC/GPS fetch directives | `_heartbeat_fetch_directives` | 14 |
| 4 | Operator identity attachment | `_heartbeat_operator_identity` | 6 |
| 5 | Active missions attachment | `_heartbeat_active_missions` | 19 |
| 6 | Lead-time repeating reminder | `_heartbeat_lead_time_reminder` | 42 |
| 7 | Geofence entry TTS | `_heartbeat_geofence_tts` | 37 |
| 8 | Pending TTS delivery | `_heartbeat_deliver_pending_tts` | 15 |
| 9 | TTS ack processing | `_heartbeat_process_tts_ack` | 13 |

## Result

- `heartbeat` function reduced from **214 lines / complexity 38** → **22 lines / complexity 1**
- Each helper is independently testable
- The `_heartbeat_` prefix groups them logically for readability

## Logic Preserved

- All auth, state update, fetch directive, operator identity, mission, reminder, geofence, pending TTS, and TTS ack logic is **identical**
- No behavior changed — only extraction
