# Feature Prompt — Custom & Peer Checkpoints

## Role
You are a scoped subagent. You do not own this repo.
Your job is to implement the custom and peer checkpoint features.

## Workflow
- No commits. No pushes.
- Report blockers before attempting fixes that need backend support.
- Leave server running or give manual restart instructions.

## Goal
Add new checkpoint type support in the frontend to match backend model `api/models.py`:
- `custom` — operator-defined checkpoints with optional lat/lng
- `peer` — HCE device-to-device presence verification

## Prerequisites (report only)
Before changing anything, confirm these exist:
- `api/models.py`: `checkpoint_type` includes `('custom', 'Custom')` and `('peer', 'Peer')`
- `api/views/core.py`: `_heartbeat_peer_mode(device, active_assignments)` exists
- `templates/components/checkpoint_editor.html`: `TYPE_OPTS` includes `peer`

If any are missing, STOP and report them as [BLOCKED].

## Frontend changes required

### 1. Checkpoint editor type selector
- Add `custom` and `peer` to type options in:
  - `templates/components/checkpoint_editor.html`
  - `frontend/src/components/checkpoint_editor.js`

### 2. Custom checkpoint fields
- name (required)
- planned_time, dwell_time, time_tolerance
- lat/lng optional
- Visual badge: `[CUSTOM]`

### 3. Peer checkpoint fields
- name (required)
- peer_target_device_id (auto-filled from HCE session)
- Verification key display
- Visual badge: `PEER`
- Helper text: "Device-to-device presence required"
- Coloured border: teal

### 4. Mission detail updates
- Show `[CUSTOM]` and `PEER` badges next to checkpoint names
- Show `peer_session_key` if present

### 5. Deploy flow
- Validate peer checkpoints have a device bound before deploy
- Show `Unbind device - Peer needs a target` if missing

### 6. Offline/reload
- mission-status/summary must preserve custom/peer fields on reload

## Backend contract (NO CHANGES unless explicitly directed)
Current endpoints to use as-is:
- `POST /api/routes/{id}/checkpoints/`
- `GET /api/mission-status/{assignment}/`
- `GET /api/heartbeat/` (device heartbeat with peer mode)
- `POST /api/peer/scan/` (HCE verification)

Allowed backend changes ONLY if frontend cannot proceed:
1. Add `custom` to `CHECKPOINT_TYPES` in `api/models.py`
2. Add custom checkpoint validation in `Checkpoint.clean()`
3. Confirm `peer` checkpoint emits `peer_mode` in heartbeat

## Strict refusal rules
- Do NOT remove or rename existing GPS/NFC checkpoint behaviour.
- Do NOT change `templates/base_app.html` structure.
- Do NOT rename `missions-partial` endpoints.
- Do NOT change router paths.
- Do NOT delete migrations.

## Validation (paste full output)
Run from `/home/jay/Desktop/projects/GuardTour_Full` with venv:
1. `/home/jay/Desktop/projects/venv/bin/python -m pytest -q`
2. `/home/jay/Desktop/projects/venv/bin/python manage.py check --deploy`
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dispatch/`
4. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/routes/`
5. `git diff --stat`
6. `git status --short`

## Required Review Packet
1. Prerequisite check (which exist, which missing)
2. Changes made by file
3. Blocked items
4. Validation results (full output, verbatim)
5. Diff summary (high level)
6. Risk tags per finding: [FIX], [FEATURE], [BLOCKED]
7. "No backend changes beyond optional contract items listed above."
