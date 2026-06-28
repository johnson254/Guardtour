# Migration Progress: GuardTour Frontend Unification

## Overview
Status: **Phase 2 Complete, Phase 3 (htmx) In Progress — Simple Pages Done**

Architecture in place. All inline JS extracted into Vite ES modules. htmx conversion underway — server-rendered HTML partials for data fetching, replacing `api()` + client-side render.

## Completed Work
- [x] **Infrastructure:** Vite + Tailwind config, Django integration via `vite_asset` template tag.
- [x] **Foundation:** Shared ESM modules (`dom.js`, `api.js`, `toast.js`, `ws-client.js`).
- [x] **Dashboard:** Extracted dashboard JS into `pages/dashboard.js`, converted alert polling to htmx.
- [x] **Map View:** Created `pages/map-view.js` (~20KB) with initMap, draw tools, guard markers, history tracks, blueprint overlays, feed render.
- [x] **Dispatch:** Extracted 2734-line inline script into `pages/dispatch.js` module (75KB built). Template 5058→2324 lines.
- [x] **Manage:** Extracted 3881-line inline script into `pages/manage.js` module (140KB built). Template 5250→1372 lines.
- [x] **Routes:** Extracted 2059-line inline script into `pages/routes.js` module (75KB built). Template 3910→1853 lines.
- [x] **Incidents:** Extracted 186-line inline script into `pages/incidents.js` module (4.7KB built). Template 364→180 lines.
- [x] **Guards:** Reconstructed and extracted into `pages/guards.js` module (3.4KB built). Template 184→38 lines.
- [x] **Login/Register/Reports/Admin:** Extracted 4 remaining inline scripts into Vite modules. Login 63→31, register 64→36, reports 229→56, admin 375→62 lines. Built 17 modules total.
- [x] **Build Fixes:** Fixed `shared-globals.js` import paths; added `asset_type='css'` to `vite_asset` tag; removed debug dev server dependency.
- [x] **Backend Fix:** Added `bulk` action to `CheckpointViewSet` for `POST /api/checkpoints/bulk/`
- [x] **Frontend Fix:** Fixed field name mapping in `map-view.js` `tmSaveCheckpoints` (→ `route`, `nfc_tag`, `checkpoint_type`, `next_announcement_text`) and removed MapObject-only fields from `tmSaveObject`
- [x] **Window export audit:** Verified all onclick handlers across manage/dispatch/routes/incidents/guards/map-view templates have matching `window.*` exports. Fixed 2 missing: `cbClearStaged`, `mgLoadLog`.

## Phase 3 — htmx Conversion
- [x] **Reports page (full conversion):** Added `/api/scans-table-partial/` endpoint returning HTML fragment. Filter form uses `hx-get` with `hx-target`, auto-refresh via `hx-trigger="every 300s"`. Removed 80 lines of fetch+render JS. Reports module shrunk 4.7KB→2.0KB.
- [x] **Admin stats (partial conversion):** Added `/api/admin-stats-partial/` endpoint. Stats card uses `hx-trigger="load, every 120s"`. Removed stats fetch from JS. Admin module shrunk 8.5KB→7.3KB.
- [x] **Guards page (full conversion):** Added `/api/guards-partial/`, `/api/guard-form-partial/<pk>/` endpoints. Personnel grid, create/edit form, and delete all use htmx. Form fields swap in via `hx-swap="innerHTML"`. Guards module shrunk 3.4KB→0.32KB. Fixed `name`→`first_name`/`last_name` field mapping bug.
- [x] **Reports filter dropdowns:** Added `/api/reports-guards-options-partial/` and `/api/reports-routes-options-partial/` endpoints. Guard and route `<select>` elements populated via htmx on load. Removed fetch calls from reports.js.
- [x] **Incidents guard filter:** Added `/api/incidents-guards-options-partial/` endpoint. Guard dropdown populated via hidden htmx trigger on load. Removed `populateGuards()` fetch from incidents.js.
- [x] **Routes list (htmx):** Added `/api/routes-list-partial/` endpoint + `templates/partials/routes/list.html`. Route card list rendered server-side. Search input uses `hx-trigger="input changed delay:200ms"`. Removed `bpRenderList()` fetch from routes.js.
- [x] **Dispatch blueprints (htmx):** Added `/api/blueprints-partial/` endpoint + `templates/partials/dispatch/blueprints.html`. Blueprint card grid rendered server-side. Search input uses `hx-trigger`. Removed `dcFilterBlueprints()` + `dcRenderBpLibrary()` fetch.
- [x] **Dispatch missions (htmx):** Added `/api/missions-partial/` endpoint + `templates/partials/dispatch/missions.html`. Mission grid grouped by route rendered server-side. Tab buttons use `hx-get` with `tab` param. Removed `dcRenderLsGrid()` fetch.
- [x] **Backend views split:** `api/views.py` (3111L) → `api/views/core.py` + `api/views/partials/` package. Partials organized by domain: `guards.py`, `reports.py`, `admin.py`, `incidents.py`, `options.py`, `routes.py`, `dispatch.py`. All re-exported from `api/views/__init__.py` for backward compatibility.
- [x] **Manage/Fleet & Asset Registry full redesign:** Three-column layout — devices (240px left sidebar) | Leaflet dark map (center, flexes) | checkpoint builder (300px right). Click-to-pick coordinates on map, checkpoint markers rendered. Register Device + Register Checkpoint buttons in header. htmx device list. Glass checkpoint panel with trigger button expanding 4 type buttons. Blueprint Identity `.rs-fi` inputs in checkpoint rows. DESIGN.md updated with input standards.

## Remaining Inline Scripts
- `base_app.html` (~135 lines for auth/nav/token infra — stays inline)

## Remaining JS fetch/api() Calls (deferred — complex pages)
- `dispatch.js` (~15 remaining calls) — calendar, live tracking, deploy overlay, mission detail panel. Blueprint library + mission grid now use htmx.
- `manage.js` (~50+ calls) — device control, fleet map, blueprint shifts, audit log. Needs dedicated htmx conversion session.
- `map-view.js` — Leaflet map interactions (stays as JS, not htmx-convertible)
- `login.js` / `register.js` — auth (stays as fetch)
- `routes.js` (~10 remaining calls) — route editor form, checkpoint editor, deploy panel, wizard flow. Route list now uses htmx.

## Next Steps
1. **Dispatch page htmx conversion:** Mission list, live tracking poll, deploy overlay. Requires new partial endpoints for shift assignments and deployment-checkpoint-live.
2. **Manage page htmx conversion:** Fleet device list, blueprint shift board, audit log. Largest remaining effort.
3. **Tailwind:** Replace inline CSS with utility classes template-by-template.
4. **Cleanup:** Delete dead code, empty IIFEs, unused inline `<style>` blocks.

## Critical Notes
- All JS is modular ESM via Vite production build. No dev server dependency.
- Tailwind JIT produces ~5KB CSS per page, only used classes emitted.
- htmx handles data fetching; no SPA rebuild.
- Dispatch module preserves `window.*` exports for `onclick` handlers in template.
- Vite config: `base: '/static/dist/'`, `root: '.'` (static/ dir), `outDir: dist`
- Refer to `static/ARCHITECTURE_PLAN.md` for full roadmap.
- htmx partial views follow the `alerts_partial` pattern: `@login_required`, `HttpResponse(html)`.
