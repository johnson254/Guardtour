# GuardTour — System Analysis & Next Steps

**Date:** 2026-06-30  
**Branch:** `work/backend`  
**Index:** 2,384 nodes, 5,635 edges

---

## 1. Current State Summary

### What's Solid
- **Scan pipeline** — `ScanPipeline` class with 12 steps, cooldown, sequence, zone verification, dwell, TTS. Well-tested (10+ mission tests pass).
- **Auth** — PBKDF2 password hashing with legacy plaintext migration. Device auth via password + JWT for operators.
- **Multi-tenancy** — `get_user_organization_or_none` centralized in `org_permissions.py` (21 callers).
- **Soft delete** — `is_archived` on Organization and PatrolRoute.
- **Frontend architecture** — All inline JS extracted to 12 Vite ESM modules. htmx partials for guards, routes list, dispatch blueprints/missions, reports table, admin stats, incidents filter.
- **Manage page** — Three-column layout (devices | map/editor | checkpoint groups). Center panel dual-purpose. Operational area of interest with boundary rendering.
- **Migrations** — 75 migrations, clean chain.

### What's Fragile
- **manage.js** — 4,695 lines, 138 `window.*` exports. Largest built asset (170KB). Hard to navigate, risky to edit.
- **dispatch.js** — 2,384 lines, 108 `window.*` exports. Live tracking, deploy overlay, mission detail all still client-rendered.
- **routes.js** — 2,052 lines, 68 `window.*` exports. Wizard flow, calendar, checkpoint editor all client-rendered.
- **CSS bloat** — `manage.css` (1,661 lines), `duty-cycle.css` (2,324 lines), `page-routes.css` (970 lines). Inline styles still dominate.

---

## 2. Critical Issues (Fix Now)

### 2.1 Pre-existing Test Failure
- `test_scan_endpoint_throttles` returns 400 instead of 429. Throttle config or test setup broken. Blocks CI confidence.

### 2.2 `deployment_checkpoint_live` Crash (BACKLOG §10.1)
- `hit_count` NameError — dispatch live-tracking endpoint crashes 100% of the time when assignments have checkpoints. **Operators cannot see live mission progress.** This is the #1 backend bug.

### 2.3 Cross-Org Data Leak (BACKLOG §10.2)
- `resolve_asset` fallback queries `Checkpoint.objects.filter(nfc_tag=nfc_value)` without org filter. Unknown tags from Org A can match Org B's checkpoints. **Multi-tenant isolation broken.**

### 2.4 `manage.js` Maintainability
- 170KB built, 4,695 source lines, 138 global exports. Every edit risks breaking 5+ features. Needs decomposition.

---

## 3. High-Impact Next Steps (Priority Order)

### P0 — Fix Live Tracking Crash
**Why:** Dispatch page's core feature (live mission progress) is completely broken.  
**What:** In `api/views/dispatch.py` `deployment_checkpoint_live`, add `hit_count = len(hit_cp_ids)` before line 2024.  
**Effort:** 5 minutes.  
**Impact:** Restores real-time mission monitoring for operators.

### P1 — Fix Cross-Org Leak
**Why:** Data isolation is a security requirement for multi-tenant SaaS.  
**What:** In `api/services/scan.py` `resolve_asset`, add `organization=device.organization` to the fallback query.  
**Effort:** 5 minutes.  
**Impact:** Prevents scan attribution across org boundaries.

### P2 — Decompose `manage.js`
**Why:** 170KB monolith is the #1 source of regression risk.  
**What:** Split into:
- `manage-fleet.js` — device list, filter, stats, inline detail
- `manage-checkpoints.js` — checkpoint groups, per-group save, inline expand
- `manage-editor.js` — center panel editor (NFC/GPS/device forms, mini-map)
- `manage-map.js` — main map init, area boundary, markers
- `manage.js` — thin orchestrator, tab switching, shared state

**Effort:** 2-3 hours.  
**Impact:** Safer edits, smaller review surface, faster builds.

### P3 — Dispatch Page htmx Conversion
**Why:** 2,384 lines of client-rendered mission tracking. PROGRESS.md lists this as next.  
**What:** Convert remaining client fetches to htmx partials:
- Mission detail panel → `/api/mission-detail-partial/<id>/`
- Live tracking poll → `/api/deployment-checkpoint-live-partial/` (reuses fixed P0)
- Deploy overlay → `/api/deploy-overlay-partial/`

**Effort:** 3-4 hours.  
**Impact:** Shrinks dispatch.js by ~800 lines. Consistent with guards/routes pattern.

### P4 — Routes Page htmx Conversion
**Why:** 2,052 lines with wizard flow, calendar, checkpoint editor all client-rendered.  
**What:** Convert:
- Checkpoint editor form → `/api/checkpoint-form-partial/`
- Calendar view → `/api/calendar-partial/`
- Wizard steps → server-rendered partials with `hx-get` navigation

**Effort:** 3-4 hours.  
**Impact:** Shrinks routes.js by ~600 lines. Wizard becomes testable server-side.

### P5 — Fix Throttle Test
**Why:** Pre-existing failure masks real regressions.  
**What:** Investigate why `test_scan_endpoint_throttles` returns 400. Likely: throttle key function or test client not hitting the right rate.  
**Effort:** 30 minutes.  
**Impact:** Restores test suite integrity.

---

## 4. Medium-Term Improvements

### 4.1 CSS Consolidation
- `duty-cycle.css` (2,324 lines) likely has dead rules from pre-refactor era.
- `manage.css` (1,661 lines) has editor/group styles that could move to component classes.
- Audit with PurgeCSS or manual review. Target: <800 lines per page CSS.

### 4.2 Dashboard Enhancement
- Currently thin: alert polling + scan timer + sound/vibrate.
- Add: live mission progress widget (reuses fixed P0 endpoint), recent scan feed, guard status summary.
- Backend already has `organization_stats` — just needs frontend rendering.

### 4.3 Reports Backend
- `exportCSV` is a stub (`alert('CSV Export Feature...')`).
- Implement real CSV export using `csv` module in a new `reports_csv` view.
- PDF export works but could use server-side generation for consistency.

### 4.4 Incidents Page
- Charts use random data (`Math.random()` in `renderCharts`).
- Backend has `organization_stats` with real data — wire it through.
- Heatmap grid is placeholder — replace with actual scan density data.

### 4.5 TTS Status in Device Detail (BACKLOG §2.3, §5)
- Backend already tracks `tts_pending`, `tts_acked`, `tts_pending_at`.
- Add to device detail panel in manage page: status indicator + history.
- Low effort, high operator value.

---

## 5. Long-Term / Strategic

### 5.1 Android Parity
- BACKLOG §1-14 documents 14 Android ↔ backend mismatches.
- Most critical: `route_id` not sent in scans (§1.2), `verification_key` missing (§1.3).
- These are Android-side fixes but affect data quality for the entire system.

### 5.2 Body Sensors (BACKLOG §6)
- Backend stores `raw_nfc.sensors` but never reads it in scoring.
- Android never registers `SensorEventListener`.
- Implement both sides for anti-cheat improvement.

### 5.3 Peer-to-Peer HCE (BACKLOG §8)
- Full design exists. `PeerHceService.kt` + server role assignment via heartbeat.
- High complexity but enables hands-free audit routes.

### 5.4 TTS Profiles (BACKLOG §2.1)
- New model `TtsProfile` with org scope.
- Route gets optional FK. Heartbeat merges profile + route overrides.
- Nice-to-have for voice customization.

---

## 6. Architecture Health Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Total source lines (JS+CSS+Python) | ~22,000 | — |
| Largest JS module | 4,695 (manage.js) | <1,500 |
| Largest built asset | 170KB (manage) | <80KB |
| `window.*` exports | 314 total | <100 |
| htmx-converted pages | 4 (guards, routes-list, dispatch-bp/missions, reports) | All data-fetch pages |
| Client-only pages | 3 (manage, dispatch, routes) | 0 |
| Test pass rate | 9/10 (1 throttle failure) | 10/10 |
| Migrations | 75 | — |
| API endpoints | ~48 | — |

---

## 7. Recommended Immediate Action

1. **Fix `hit_count` NameError** in `deployment_checkpoint_live` — 5 min, unblocks dispatch.
2. **Fix org leak** in `resolve_asset` — 5 min, security.
3. **Start `manage.js` decomposition** — extract map module first (least coupled).
4. **Fix throttle test** — restore CI confidence.

Total: ~3 hours for critical fixes, then iterative htmx conversion of dispatch/routes.
