# GuardTour — Oversight Plan: Monday Demo → Production

## 1. Mandate

This document is the single source of truth for:

- Monday demo execution (NFC checkpoints must work)
- Short-term stabilization after demo
- Medium-term feature completion from existing docs
- Long-term production readiness: backend + frontend + deployment + version control

You can hand this to a developer, an AI coding agent, or use it yourself as a runbook.

---

## 2. Current State (as of 2026-06-27)

### 2.1 Backend

Strengths:
- Scan, route, device, shift, TTS, dispatch, heartbeat all modeled and mostly wired.
- Validity scoring exists: `api/scan_service.py` handles GPS proximity, movement plausibility, battery mitigator, 30s cooldown, peer verification.
- Raw NFC payload model support exists (`ScanRecord.raw_nfc` JSONField).
- Multiple active missions supported in heartbeat.
- Offline scan buffering + batch sync implemented.

Active risks (from `BACKLOG.md`, `APP_ISSUES.md`, `LOGIC_ISSUES.md`):
- Android side still missing some heartbeat fields: `route_id`, `verification_key`, `raw_nfc` attachment, GPS on scans.
- TTS pending device-level messages not delivered via heartbeat (`views.py:364-374`).
- Guards can stay "on shift" forever if `end_shift` is never called.
- Some `device_id` vs PK confusion across endpoints.
- No rate limiting on AllowAny device endpoints.
- HCE peer-to-peer NFC work started but not finished in app code.

### 2.2 Frontend

Strengths:
- Vite + htmx + Tailwind architecture is in place.
- `static/src/{main,utils/api,utils/dom,utils/toast}.js` are the unified shared utilities.
- `routes.html` and `dispatch.html` are the approved design templates.
- Pages are modular: `pages/dashboard.js`, `pages/map-view.js`, etc.
- Production builds resolve via Vite manifest; templates use `vite_asset` tags.

Active risks:
- `/map-view/` runtime map tile rendering still being debugged by user.
- Some pages are still stubs (`guards.js`, `incidents.js`, `manage.js`); structured but not feature-complete.
- `base_app.html` still carries inline `showToast` / `apiFetch` / `logout` for backward compatibility; this is acceptable but should be unified later.

### 2.3 Mobile (Android)

Strengths:
- NFC scan service, GPS collector (now `LocationManager`, no Play Services), TTS playback, offline buffering, batch sync, dashboard activity all exist.
- HCE service scaffolded (`PeerHceService.kt`) and registered.

Active risks:
- App ignores several backend heartbeat directives: `fetch_nfc`, `fetch_gps`, `tts_rate`, `tts_pitch`, `play_sound`, `vibrate`, `route_id`.
- Heartbeat callbacks duplicated / not fully processed in some flows.
- NFC hex case handling is fragile.
- `ensureDeviceRegistered()` is currently a no-op.

---

## 3. Monday Demo Scope (HIGHEST PRIORITY)

### 3.1 Success Criteria for Monday Morning

1. A guard can register/login on the Android app using a known device code + numeric password.
2. A route with NFC checkpoints is deployed from the web UI.
3. The guard taps each NFC tag and a scan record appears in the backend.
4. The dispatcher can see scan status on the web UI.
5. If any of the above fails, the fallback demo path is ready (see 3.3).

### 3.2 Demo Hardening Checklist (execute this in order)

Backend:
- [ ] Confirm `/api/scans/` and `/api/scan-batch/` accept and persist scans with `nfc_value`, `route_id`, `lat`, `lng`, `raw_nfc`.
- [ ] Confirm `process_scan` resolves assignment via `route_id` when present; falls back gracefully otherwise.
- [ ] Confirm `ScanRecord` visibility in admin/manage UI.
- [ ] Confirm `DeviceViewSet.device_recent_scans` returns data.
- [ ] Seed 1 org, 1 route, 3 checkpoints (NFC tags), 1 device, 1 guard for demo.

Android:
- [ ] Build fresh debug APK.
- [ ] Confirm register/login path works with seeded credentials.
- [ ] Confirm heartbeat runs and returns active missions.
- [ ] Confirm NFC scan handler:
  - reads tag UID / NDEF
  - sends `nfc_value`, `lat`, `lng`, `raw_nfc`, `route_id`
  - handles success/error toasts
- [ ] Confirm offline buffer + sync path works if demo device will be offline intermittently.

Web UI:
- [ ] Confirm manage.html device panel shows recent scans.
- [ ] Confirm dispatch/routes pages load under authenticated session.
- [ ] Confirm no JS console errors on routes/dispatch/manage pages.

### 3.3 Fallback Demo Path (if NFC fails live)

- Show deployed route + checkpoint list on web UI.
- Show scan logs from backend/admin panel with pre-seeded data.
- Show device management and heartbeat history.
- Show dispatch mission assignment flow.

---

## 4. Post-Demo Sprint (Week 1–2)

### 4.1 Backend (must-fix)

1. Close TTS device delivery gap: heartbeat must read `device.tts_pending` and return it; clear after delivery.
2. Fix guard `is_on_shift` lifecycle: reset on assignment end / swap / deactivate.
3. Make `generate_operator_id` collision-safe: use max existing sequence, not count.
4. Decide and standardize `device_id` lookup: string `device_id` vs PK. Document which endpoints use which.
5. Add basic rate limiting or at least request logging on AllowAny device endpoints.
6. Add admin endpoint for active logins / online devices.

### 4.2 Android (must-fix)

1. Attach `lat`, `lng` to every scan.
2. Send `route_id` in scans and offline batch.
3. Send `raw_nfc` payload in scans.
4. Send `verification_key` for peer NFC flows.
5. Process heartbeat directives: `fetch_nfc`, `fetch_gps`, `tts_rate`, `tts_pitch`, `play_sound`, `vibrate`, `route_id`.
6. Finish HCE peer flow if that is in demo scope; otherwise defer to backlog.

### 4.3 Frontend (stabilize)

1. Finish map-view runtime tile rendering bug.
2. Convert `guards.js`, `incidents.js`, `manage.js` from stubs to feature-complete modules reusing shared utils.
3. Replace remaining inline `<style>` blocks with Tailwind or centralized CSS where practical.
4. Remove dead inline IIFEs/empty handlers from templates.

---

## 5. Medium-Term Features (Backlog)

From existing docs, execute in this priority order:

1. **NFC default-app confirmation** (`APP_ISSUES.md §7`) — Android-only, no backend change.
2. **NFC scan dump viewer in manage UI** (`APP_ISSUES.md §4`) — table + JSON expander for `raw_nfc`.
3. **TTS profiles** (`APP_ISSUES.md §2.1`) — backend model + route FK + heartbeat merge + Android voice selection.
4. **TTS status in web UI** (`APP_ISSUES.md §2.3`) — pending/acked/history in manage device panel.
5. **TTS test endpoint + panel** (`APP_ISSUES.md §5`) — POST test TTS from web.
6. **Active logins panel** (`APP_ISSUES.md §7`) — list active devices + swap operator + force re-login.
7. **Route validation UX** (`TODO.md`) — block save/deploy when past-due times, improve checkpoint chips, auto-fill point names.
8. **Body sensors + telemetry** — only if Android team re-engages; otherwise leave as backend-ready fields.

---

## 6. Production Readiness (Long-Term)

### 6.1 Backend

- [ ] Move from `AllowAny` device auth to tokenized device auth or at least IP/rate-limited flow.
- [ ] Add request idempotency keys for scan endpoints.
- [ ] Add structured logging and metrics: heartbeat rate, scan success rate, TTS delivery lag.
- [ ] Add database indexes for high-traffic filters: `device_id`, `route_id`, `timestamp`, `organization`.
- [ ] Add health-check endpoint and readiness probe for containerized deployment.
- [ ] Document deployment runbook: migrations, env vars, static build, media/static serving, backup/restore.

### 6.2 Frontend

- [ ] Split page bundles by route in Vite so unused page code is not shipped.
- [ ] Add CSP/nonce handling for inline scripts if required by your security baseline.
- [ ] Add integration tests for critical flows: login, route deploy, scan create, device TTS status.
- [ ] Add visual regression baseline for `routes.html` and `dispatch.html` since they are approved designs.

### 6.3 Android

- [ ] Replace any remaining hardcoded URLs with configurable base URL / settings screen.
- [ ] Add proper error parsing so users see server messages instead of "Connection failed".
- [ ] Implement exponential backoff reconnect for WebSocket if WebSocket path is used.
- [ ] Add ProGuard/R8 rules and sign release builds for distribution.

### 6.4 DevOps / Deployment / Version Control

- [ ] Remote repo: decide Git host (GitHub/GitLab/Bitbucket) and branch model (`main` protected, feature branches).
- [ ] CI pipeline: lint + backend tests + frontend build on every PR.
- [ ] CD pipeline: build backend container, run migrations, deploy; build frontend, upload static assets.
- [ ] Environment separation: `dev`, `staging`, `prod` with separate DB and secrets.
- [ ] Secrets management: do not store credentials in repo; use env vars or secret manager.
- [ ] Database migration strategy: migrations versioned, tested in CI, rollback plan documented.
- [ ] Backup strategy: automated DB backups, retention policy, test restore quarterly.

---

## 7. How to Use This Document

- For Monday: use section 3 only.
- For the next 2 weeks: use sections 4.1–4.3.
- For roadmap grooming: section 5.
- For production launch: section 6.
- If scope changes, update this doc first, then execute.

---

## 8. Source Docs This Plan Is Based On

- `PROGRESS.md`
- `BACKLOG.md`
- `APP_ISSUES.md`
- `LOGIC_ISSUES.md`
- `TODO.md`
- `static/ARCHITECTURE_PLAN.md`
- `GUARDTOUR_DOCS.md`
- `DESIGN.md`

If any of these are updated, this plan should be re-synced.
