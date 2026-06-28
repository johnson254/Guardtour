# HTMX Unification & Conversion Plan

>_dispatch.js (2728L) · routes.js (2057L) · manage.js (3885L) · Total: 8670L_

---

## Phase 1: Unify Duplicated Utilities

Three pages redefine the same helpers locally instead of importing from `static/src/utils/`.

### 1.1 `$` / `$$` DOM helpers

| File | Line | Current |
|------|------|---------|
| `routes.js` | 20–21 | `const $ = id => document.getElementById(id); const $$ = s => document.querySelectorAll(s);` |
| `manage.js` | 19–20 | Same |
| `dispatch.js` | 2 | Already imports from `../utils/dom.js` ✅ |

**Fix:** Replace local definitions in routes.js and manage.js with:
```js
import { $, $$ } from '../utils/dom.js';
```

### 1.2 `api()` fetch wrapper

| File | Line | Current |
|------|------|---------|
| `routes.js` | 26–31 | Local `const api = async (url, opts) => { if (window.apiFetch) ... }` |
| `manage.js` | 23–28 | Same pattern |
| `dispatch.js` | 3 | Already imports from `../utils/api.js` ✅ |

**Fix:** Replace with:
```js
import { api } from '../utils/api.js';
```

### 1.3 `toast()` notification

| File | Line | Class | Container | Duration |
|------|------|-------|-----------|----------|
| `dispatch.js` | 50–56 | `dc-toast` | `$('dcToasts')` | 2800ms |
| `routes.js` | 36–42 | `rs-toast` | `$('bpToasts')` | 2800ms |
| `manage.js` | 34–40 | `mg-toast` | `$('mgToasts')` | 2700ms |

All three are structurally identical — create DOM element, append container, auto-remove.

**Fix:** Make `toast.js` CSS-agnostic by using a `data-toast` attribute, then import it:
```js
import { toast } from '../utils/toast.js';
```
Each page styles `[data-toast]` / `[data-toast="error"]` in their own CSS.

### 1.4 `extractData()` — DRF response unwrapping

| File | Line | Pattern |
|------|------|---------|
| `dispatch.js` | 90–94 | Defined inside `dcLoadAll` |
| `routes.js` | 112–115 | Inlined 4× in `bpLoad()` |
| `manage.js` | 105,241,257,273,564,763,1674 | Inlined 8× |

**Fix:** Add to `utils/api.js`:
```js
export async function extractData(res) {
  if (!res.ok) return [];
  const d = await res.json();
  return Array.isArray(d) ? d : (d.results || []);
}
```
Then replace all inline occurrences.

### 1.5 `loadEntities()` — parallel data loading

Both dispatch and routes load 4–5 entity types on page load using `Promise.all`.

**Fix:** Add to `utils/api.js`:
```js
export async function loadEntities(endpoints) {
  const keys = Object.keys(endpoints);
  const results = await Promise.all(Object.values(endpoints).map(url => api(url)));
  const data = {};
  await Promise.all(results.map(async (res, i) => {
    data[keys[i]] = await extractData(res);
  }));
  return data;
}
```

**Before (dispatch.js:65–71):**
```js
const [aRes, gRes, rRes, dRes, dispRes] = await Promise.all([
    api('/api/shifts/'), api('/api/guards/'), api('/api/routes/'),
    api('/api/devices/'), api('/api/dispatchers/')
]);
// ... then extractData on each ...
```

**After:**
```js
const { shifts: allAssignments, guards: allGuards, routes: allRoutes,
        devices: allDevices, dispatchers: allDispatchers } = await loadEntities({
  shifts: '/api/shifts/', guards: '/api/guards/', routes: '/api/routes/',
  devices: '/api/devices/', dispatchers: '/api/dispatchers/'
});
```

---

## Phase 2: Convert List Rendering to htmx Partials

Every `.map().join('')` loop that builds HTML from JSON can become a server-rendered partial.

### Priority 1 — Simple lists (low effort, high impact)

| # | Page | Function | Lines | Lines of HTML | Endpoint |
|---|------|----------|-------|---------------|----------|
| 1 | routes | `bpRenderList()` | 262–275 | ~14 | `GET /api/routes-list-partial/` |
| 2 | dispatch | `dcRenderBpLibrary()` | 295–349 | ~55 | `GET /api/blueprints-partial/` |
| 3 | dispatch | `dcRebuildGuards()` | 159–168 | ~10 | `GET /api/guards-options-partial/` |
| 4 | dispatch | `dcShowBpDeployments()` | 405–420 | ~16 | `GET /api/bp-deployments-partial/` |

### Priority 2 — Medium complexity

| # | Page | Function | Lines | Lines of HTML | Endpoint |
|---|------|----------|-------|---------------|----------|
| 5 | manage | `mgRenderGuards()` | 163–217 | ~55 | `GET /api/manage-guards-partial/` |
| 6 | manage | `mgRenderDevices()` | 811–856 | ~46 | `GET /api/manage-devices-partial/` |
| 7 | manage | `mgRenderCallsigns()` | 542–594 | ~53 | `GET /api/manage-callsigns-partial/` |
| 8 | manage | `mgRenderRouteHealth()` | 1591–1612 | ~22 | `GET /api/manage-routes-partial/` |

### Priority 3 — Complex (large HTML templates, grouped data)

| # | Page | Function | Lines | Lines of HTML | Notes |
|---|------|----------|-------|---------------|-------|
| 9 | dispatch | `dcRenderLsGrid()` | 704–912 | ~210 | Grouped by route, 5 tabs, live data |
| 10 | dispatch | `renderBlueprintCard()` | 796–842 | ~47 | Nested chips per blueprint |
| 11 | dispatch | `dcBpAssignmentCardHTML()` | 527–673 | ~147 | Single assignment card |
| 12 | manage | `mgRenderShiftPairs()` | 324–387 | ~64 | Pair cards with guard info |
| 13 | manage | `mgRenderBlueprintActiveDeployments()` (timeline) | 470–520 | ~51 | Live/queued grouped |
| 14 | manage | `mgRenderActiveDeployments()` | 1619–1638 | ~20 | Deployment cards |
| 15 | manage | `mgRenderLog()` | 1699–1712 | ~14 | Audit log entries |
| 16 | manage | `mgRenderFleetActivity()` | 1464–1478 | ~15 | Activity feed |
| 17 | manage | `mgShowDayDetail()` | 710–753 | ~42 | Calendar day detail |
| 18 | manage | `mgDeviceControls()` | 893–982 | ~90 | Device control dropdown |
| 19 | routes | `bpAddCp()` | 571–693 | ~123 | Checkpoint editor row |
| 20 | routes | `addRegistryRow()` | 3157–3225 | ~69 | Registry checkpoint row |

### Conversion pattern (example: routes list)

**Before:**
```js
function bpRenderList() {
  const filtered = allRoutes.filter(r => r.name.includes(q));
  listEl.innerHTML = filtered.map(r => `
    <div class="rs-r-card" onclick="bpSelectRoute(${r.id})">
      <div class="rs-r-name">${r.name}</div>
      ...
    </div>
  `).join('');
}
```

**After (template):**
```html
<div id="routeList"
     hx-get="/api/routes-list-partial/"
     hx-trigger="load"
     hx-swap="innerHTML"></div>
```

**After (backend):**
```python
@api_view(['GET'])
@login_required
def routes_list_partial(request):
    routes = _resolve_routes_queryset(request.user)
    q = request.GET.get('q', '').lower()
    if q:
        routes = [r for r in routes if q in r.name.lower()]
    html = ''.join(_route_card_html(r) for r in routes)
    return HttpResponse(html)
```

---

## Phase 3: Convert Polling to `hx-trigger="every Ns"`

Replace `setInterval(apiCall, N)` with `hx-trigger"` on the container element.

| # | Page | Line | Interval | What It Polls | Container | Endpoint |
|---|------|------|----------|---------------|-----------|----------|
| 1 | dispatch | 454–461 | 10s | `deployment-checkpoint-live/` | `#dcBpProgressView` | `GET /api/bp-progress-partial/` |
| 2 | manage | 3847 | 60s | Blueprint shifts refresh | `#mgTimeline` | `GET /api/manage-shifts-partial/` |
| 3 | manage | 1105–1129 | 5s | Device GPS status | `#dcGpsStatus_{id}` | `GET /api/devices/{id}/gps-partial/` |
| 4 | manage | 1163–1188 | 5s | Device NFC status | `#dcNfcStatus_{id}` | `GET /api/devices/{id}/nfc-partial/` |
| 5 | manage | 1288–1315 | 3s | TTS ack status | `#dcTtsAck_{id}` | `GET /api/devices/{id}/tts-partial/` |
| 6 | manage | 2827–2849 | 5b | Device scan result | `#cbDeviceScan_{id}` | `GET /api/devices/{id}/scan-partial/` |
| 7 | manage | 2887–2911 | 5s | Device GPS fetch | `#cbDeviceGPS_{id}` | `GET /api/devices/{id}/gps-partial/` |
| 8 | manage | 2968–2995 | 5s | Remote NFC result | `#cbRemoteNFC_{id}` | `GET /api/devices/{id}/nfc-partial/` |
| 9 | manage | 3720–3731 | 1s | Scan countdown | `#cbCountdown` | Remove — use `hx-trigger="every 1s"` on a hidden element |

**Conversion pattern:**

**Before:**
```js
window.__dcBpRefreshTimer = setInterval(() => {
  dcRefreshBpTiming(window.__dcActiveBpId);
}, 10000);
```

**After (template):**
```html
<div id="dcBpProgressView"
     hx-get="/api/bp-progress-partial/"
     hx-trigger="load, every 10s"
     hx-vals='{"bp_id": "${window.__dcActiveBpId}"}'
     hx-swap="innerHTML"></div>
```

---

## Phase 4: Convert Filter/Search to `hx-trigger="input"`

Client-side `.filter()` on arrays → `hx-trigger="input changed delay:200ms"` with server-side filtering.

| # | Page | Line | Element | Current Action | Endpoint |
|---|------|------|---------|---------------|----------|
| 1 | dispatch | 287–288 | `#dcBpSearch` | Client filter of `allRoutes` | `GET /api/blueprints-partial/?q=` |
| 2 | dispatch | search | Mission grid search | Client filter of `allAssignments` | `GET /api/missions-partial/?q=&tab=` |
| 3 | routes | 256–257 | `#bpRouteSearch` | Client filter of `allRoutes` | `GET /api/routes-list-partial/?q=` |
| 4 | manage | 138 | `#guardSearch` | Client filter of `allGuards` | `GET /api/manage-guards-partial/?q=&role=&shift=` |
| 5 | manage | 796 | `#deviceSearch` | Client filter of `allDevices` | `GET /api/manage-devices-partial/?q=` |
| 6 | manage | 3554 | `#regSearch` | Client filter (DOM toggle) | `GET /api/registry-partial/?q=` |

**Conversion pattern:**

**Before:**
```html
<input id="bpRouteSearch" oninput="bpRenderList()">
```
```js
function bpRenderList() {
  const q = $('bpRouteSearch').value.toLowerCase();
  const filtered = allRoutes.filter(r => r.name.toLowerCase().includes(q));
  listEl.innerHTML = filtered.map(...).join('');
}
```

**After:**
```html
<input id="bpRouteSearch" name="q"
       hx-get="/api/routes-list-partial/"
       hx-target="#routeList"
       hx-trigger="input changed delay:200ms"
       hx-swap="innerHTML">
```

---

## Phase 5: Convert Detail Panels to `hx-get`

Click-to-load detail panels become `hx-get` on the trigger element.

| # | Page | Line | Endpoint | Panel | Trigger |
|---|------|------|----------|-------|---------|
| 1 | dispatch | 427 | `/api/mission-detail/{id}/` | Mission detail drawer | Mission card click |
| 2 | dispatch | 685 | `/api/bp-progress-partial/` | Blueprint progress panel | Blueprint card click |
| 3 | routes | 284,365 | `/api/route-editor/{id}/` | Route editor panel | Route card click |
| 4 | manage | many | `/api/guard-form/{id}/` | Guard edit modal | Edit button click |
| 5 | manage | 1961–1979 | Various `/api/{type}-form/{id}/` | Modal forms (7 types) | Modal open buttons |

**Conversion pattern:**

**Before (routes.js:361):**
```js
window.bpSelectRoute = async function(id) {
  const res = await api('/api/routes/' + id + '/');
  const r = await res.json();
  $('bpRouteName').value = r.name;
  $('bpDate').value = r.scheduled_date;
  // ... 15 more field assignments ...
};
```

**After (template):**
```html
<div hx-get="/api/route-editor-partial/{id}/"
     hx-target="#routeEditor"
     hx-swap="innerHTML"
     hx-trigger="click from:.rs-r-card"></div>
```

---

## Phase 6: Convert CRUD Actions to `hx-post/put/delete`

| # | Page | Line | Method | Endpoint | Trigger | After Success |
|---|------|------|--------|----------|---------|---------------|
| 1 | routes | 1625 | POST | `/api/routes/{id}/deploy/` | Deploy button | Re-render list, close panel |
| 2 | routes | 1885 | POST/PUT | `/api/routes/{id}/` | Save button | Re-render list, close editor |
| 3 | routes | 2007 | DELETE | `/api/routes/{id}/` | Delete button | Re-render list |
| 4 | dispatch | 2611 | POST | `/api/shifts/` | Create assignment | Re-render mission grid |
| 5 | manage | 449–456 | POST | `/api/assign-guard-to-blueprint-shift/` | Assign guard | Re-render timeline |
| 6 | manage | 1047 | POST/PUT | `/api/devices/{id}/` | Save device | Re-render device grid |
| 7 | manage | 1346 | POST | `/api/devices/{id}/swap_operator/` | Swap operator | Re-render device grid |
| 8 | manage | 2199–2208 | PUT/POST | `/api/profiles/{id}/` | Save guard | Re-render guard list |
| 9 | manage | 3804 | POST | `/api/map-objects/bulk_create/` | Bulk save | Re-render asset list |

**Conversion pattern:**

**Before:**
```js
window.bpDeleteRoute = async function(event, id) {
  event.stopPropagation();
  if (!confirm('Delete route?')) return;
  const res = await api(`/api/routes/${id}/`, { method: 'DELETE' });
  if (res.ok) { allRoutes = allRoutes.filter(r => r.id !== id); bpRenderList(); }
};
```

**After:**
```html
<button class="rs-r-del"
        hx-delete="/api/routes/{{r.id}}/"
        hx-confirm="Delete route?"
        hx-target="#routeList"
        hx-swap="innerHTML"
        hx-on::after-request="if(event.detail.successful) this.closest('.rs-r-card').remove()">
  <i class="fas fa-trash-alt"></i>
</button>
```

---

## New Endpoints Required

| Endpoint | Method | Purpose | Serves |
|----------|--------|---------|--------|
| `/api/routes-list-partial/` | GET | Route card grid | routes.html |
| `/api/route-editor-partial/<id>/` | GET | Pre-filled editor form | routes.html |
| `/api/blueprints-partial/` | GET | Blueprint card grid | dispatch.html |
| `/api/missions-partial/` | GET | Mission list (grouped) | dispatch.html |
| `/api/mission-detail-partial/<id>/` | GET | Mission detail panel | dispatch.html |
| `/api/bp-progress-partial/` | GET | Blueprint progress panel | dispatch.html |
| `/api/bp-deployments-partial/` | GET | Deployment cards per BP | dispatch.html |
| `/api/manage-guards-partial/` | GET | Personnel card grid | manage.html |
| `/api/manage-devices-partial/` | GET | Device card grid | manage.html |
| `/api/manage-callsigns-partial/` | GET | Callsigns table | manage.html |
| `/api/manage-routes-partial/` | GET | Route health list | manage.html |
| `/api/manage-shifts-partial/` | GET | Timeline (live/queued) | manage.html |
| `/api/manage-assets-partial/` | GET | Asset/checkpoint list | manage.html |
| `/api/manage-log-partial/` | GET | Audit log entries | manage.html |
| `/api/devices-partial/` | GET | Device list for guards page | guards.html |
| `/api/devices/<id>/gps-partial/` | GET | GPS status snippet | manage.html |
| `/api/devices/<id>/nfc-partial/` | GET | NFC status snippet | manage.html |
| `/api/devices/<id>/tts-partial/` | GET | TTS ack snippet | manage.html |
| `/api/devices/<id>/scan-partial/` | GET | Scan result snippet | manage.html |

---

## Internal Helpers to Extract

### `_route_card_html(r)` — routes.html card
Used by: `routes-list-partial`, `blueprints-partial` (shared card style)

### `_guard_card_html(g)` — guard card with status  
Already exists in `guards_partial`. Reuse for `manage-guards-partial`.

### `_device_card_html(d)` — device card with online/battery
Used by: `manage-devices-partial`

### `_mission_card_html(a, live_data)` — mission card
Used by: `missions-partial`, `bp-progress-partial`

### `_assignment_card_html(a)` — single assignment card
Used by: `mission-detail-partial`, `bp-deployments-partial`, `manage-shifts-partial`

### `_resolve_guard_queryset(user)` — org-scoped guard query
Already added in Phase 3 guards migration. Use everywhere.

### `_resolve_routes_queryset(user)` — org-scoped route query
New. Used by routes-list, manage-routes, blueprints-partial.

---

## Risk Notes

1. **`cbToggleProp` bug (audit #17/31):** Function signature `function(el)` but called as `cbToggleProp(event, this)`. Must fix before htmx conversion of manage.js.

2. **`cbCloseScan` undefined (audit #1):** Called in `cbAcceptScan` but never defined. Must add before any scan window htmx work.

3. **`dcRenderLsGrid` syntax error (audit #29):** Trailing comma at line 746: `} else if (currentFilter === 'paused'), {` — breaks entire dispatch.js parse. Must fix first.

4. **Global state coupling:** dispatch.js uses `allAssignments`, `allRoutes`, etc. across functions. htmx partials must either render entirely server-side or the JS must drop these globals and use DOM state.

5. **Window exports:** dispatch.js has 20+ `window.*` exports used by onclick handlers. These can stay for htmx triggers (`hx-on:click="..."`) or be replaced by `hx-get` directly on elements.

6. **Calendar component:** `CalendarComponent.init()` and `CalendarComponent.render()` are complex date-grid builders that must remain in JS. htmx partials should render around them, not replace them.

---

## Execution Order

```
Phase 1: Unify imports (mechanical, zero behavior risk)
  → Fix imports in routes.js, manage.js (1.1–1.3)
  → Add extractData + loadEntities to api.js (1.4–1.5)
  → Replace Promise.all + manual extract with loadEntities

Phase 2: Fix critical bugs (must do before Phase 3)
  → Fix cbToggleProp signature
  → Add cbCloseScan function
  → Fix dcRenderLsGrid trailing comma

Phase 3: Convert simplest lists first (builds confidence)
  → bpRenderList (routes)
  → dcRenderBpLibrary (dispatch)
  → mgRenderGuards (manage)

Phase 4: Convert filters (depends on Phase 3 endpoints)
  → bpRouteSearch
  → dcBpSearch
  → guardSearch, deviceSearch

Phase 5: Convert polling (standalone, low risk)
  → BP progress refresh (10s)
  → Shift refresh (60s)
  → Device GPS/NFC/TTS polls (5s)

Phase 6: Convert detail panels (depends on data endpoints)
  → Route editor panel
  → Mission detail panel
  → Guard edit modal

Phase 7: Convert CRUD actions (last — needs all partials working)
  → Delete buttons
  → Save/submit forms
  → Deploy actions
```

---

## Progress Tracking

- [ ] Phase 1: Unify duplicated utilities
- [ ] Phase 2: Fix critical bugs (cbToggleProp, cbCloseScan, dcRenderLsGrid)
- [ ] Phase 3: Convert list rendering loops to htmx partials
- [ ] Phase 4: Convert filter/search inputs to htmx
- [ ] Phase 5: Convert polling intervals to hx-trigger
- [ ] Phase 6: Convert detail panels to hx-get
- [ ] Phase 7: Convert CRUD actions to hx-post/put/delete
