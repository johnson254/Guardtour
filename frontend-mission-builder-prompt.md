# Frontend Mission Builder Prompt — HTMX Migration Roles

## Work flow
You are the frontend subagent. You are here to:
1. migrate the Mission Builder to HTMX and
2. add/customise exact behaviour for custom and peer checkpoints.

Manual control rules:
- You should not change backend Python files.
- Do not run project-wide changes beyond the Mission Builder code.
- Report blockers before attempting fixes that need backend support.
- Leave server running or give manual restart instructions.

## Why this matters
Missions are the live chain between dispatch and the device. Custom checkpoints and peer checkpoints are audit-facing flows. The migrated Mission Builder must preserve:
- deploy flow
- live mission selection pane
- checkpoint editor behaviour
- peerflow create / validate behaviour
- render behaviour while offline and reload post-deploy.

## Design idea (target behaviour)

### 1. Target template contract
Only use current Django template primitives:
- `templates/dispatch.html`
- `templates/partials/dispatch/missions.html`
- existing components:
  - `templates/components/mission_detail.html`
  - `templates/components/checkpoint_editor.html`
  - `templates/components/deploy_drawer.html`

New constraint: keep IDs and CSS prefixes as they are. Add new JS modules using `{% vite_asset '...' %}` rather than inline huge scripts still in `dispatch.html`.

Suggested new module files:
- `frontend/src/pages/dispatch.js`
- `frontend/src/features/missions.js`
- `frontend/src/components/checkpoint_editor.js`

The rule: `dispatch.html` must stay as the shell; all page behaviour must come from JS modules.

### 2. Navigation contract
- `base_app.html` controls the left rail via `nav-links` and `#nav-tabs`
- `dispatch.html` has the top rail ` Missions` and the deploy button
- Keep all existing ids

## Custom checkpoint design target

### Form contract
For custom checkpoint create:
- POST `/api/routes/{id}/checkpoints/` or
- POST `/api/checkpoints/` with route set to the active route.

Required fields:
- name
- checkpoint_type = custom
- type-specific logic in backend only
- frontend config: planned_time, dwell_time, time_tolerance, lat/lng optional

### Visual contract
Custom type must appear as:
- Tag badge [CUSTOM] in mission detail
- editor row option custom in checkpoint type selector add this value in JavaScript
- colouredSlate in summary gutter where peer is teal and gps/nfc are default

### Validation contract
- name required
- route required
- If custom requires lat/lng in backend, editor must require lat/lng too.

## Peer checkpoint design target

### Review existing code first
Confirm these exist before editing:
- `api/models.py` has `checkpoint_type='peer'`
- `api/views/core.py` has `_heartbeat_peer_mode`
- `api/checkpoint editor.html` has `'peer'` in TYPE_OPTS

### Visual contract
Peer type must appear as:
- Tag badge `PEER`
- type selector option PEER
- streamEmitterTeal tone in progress gutter
- small helper text under name: Peer checkpoints require device-to-device presence verification

### Create flow contract
- selection route must be set before peer assignment
- if peer is selected but a device is unbound show `Unbind device - Peer needs a target` warning
- if peer checkpoint already has nfc tag populated then show Locked warning

### Read/scan contract offline
- mission status endpoint must keep peer field
- peer mode decisions must work when connection is offline

### missionStatus api contract (frontend expectations)
- GET `/api/mission-status/{assignment}/`
- response fields needed:
  - `assignment_id`
  - `status` one of `active` `completed` `missed` `pending`
  - `next_checkpoint` object with `id`, `name`, `checkpoint_type`, `planned_time`, `time_remaining_seconds`, `dwell_remaining_seconds`
  - `progress` object with `total`, `completed`, `missed`, `progress_percent`

## Migration checklist (Do this first)

### C1. Inventory
Read the current implementation:
- `templates/dispatch.html` especially around line 2221-2375
- `templates/components/mission_detail.html`
- `templates/components/checkpoint_editor.html`
- `templates/components/deploy_drawer.html`
- API endpoints at `templates/dispatch.html` attributes: `hx-get` and `hx-post`

### C2. Extract logic
Extract the following into JS:
- nav active state update
- mission tab switching active upcoming done missed
- deployLauncher open/close
- redeploy config toggle and save
- checkpoint editor config bridge 
- mission detail countdown
- progress bar math and colour classes

Keep render rule: `missions_partial` stays as the fragment supplier via HTMX.

### C3. Keep HTML shape
Do not change the ID contract:
- `#nav-tabs`
- `#dcMissionList`
- `#dcMissionDetail`
- `#dcRightPanel`
- `#cpEditorContainer`
- `#cpCount`
- `#dcDeployDrawer`
- `.dc-mission-grid`

### C4. Custom and peer additions only
Add behaviour ONLY for the new types:
- custom
- peer

Do not change existing gps/nfc logic.

## Steps to migrate

1. Read old inline scripts in dispatch.html
2. Move them into JS modules
3. Replace inline `onclick=".."` actions with `hx-get` and `hx-post` calls or proper `htmx` attributes where server rendered
4. Migrate DeployDrawer to server partial action using HTMX
5. Migrate MissionDetail to HTMX swap on `hx-get`
6. migrate checkpoint editor to htmx enabled POST when apply button clicked with `hx-post` and `hx-target`

## Strict refusal rules
Do not:
- delete existing deploy drawer html
- remove existing gps/nfc logic
- change `templates/base_app.html` structure
- rename `missions-partial` endpoints
- change router path `/api/missions-partial/` or `/dispatch/`
- change existing CSS class prefixes

## Validation (paste full output)
Run from `/home/jay/Desktop/projects/GuardTour_Full` with venv:
1. `/home/jay/Desktop/projects/venv/bin/python -m pytest -q`
2. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dispatch/`
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/routes/`
4. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/reports/`
5. `git diff --stat`
6. `git status --short`
7. start dev server and confirm Missions tab loads, missions rendered, DeployDrawer opens.