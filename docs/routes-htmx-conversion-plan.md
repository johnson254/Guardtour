# Routes Page — Architecture & htmx Conversion Plan

**Date:** 2026-06-30  
**Branch:** `feat/routes-htmx-conversion`  
**Source file:** `static/src/pages/routes.js` (2,052 lines)  
**Template:** `templates/routes.html` (800+ lines)

---

## 1. Current Feature Inventory

### 1.1 Wizard Flow (6 steps, all client-rendered)

| Step | DOM ID | Purpose | Window Export |
|------|--------|---------|---------------|
| 1 | `wizStep1` | Strategy selection (Quick/Flex/Seq/Sched/Audit/Custom) | `wizGo()` |
| 2 | `wizStep2` | Standard config (name, date, shift, time, guards, repeat count) | `wiz2Apply()`, `wiz2SaveDeploy()` |
| Quick | `wizStepQuick` | Fast deploy (name, guards, shift, TTS, points list) | `qApply()`, `qSaveDeploy()`, `qdInlineExecute()` |
| Audit | `wizStepAudit` | Peer audit config (auditor, targets, interval, stay) | `auditApply()`, `auditSaveDeploy()` |
| Quick Deploy | `wizStepQuickDeploy` | Full-screen review with verify + commence | `qdExecute()` |
| Edit Confirm | `wizStepEditConfirm` | Delta review before saving edits | `editExecute()` |

### 1.2 Editor Body

| Feature | Window Export | Description |
|---------|---------------|-------------|
| Duty Cycle selector | `bpHandleShift()`, `bpValidateShiftTime()` | Day/Any/Night radio buttons |
| Blueprint Identity | `bpNameInput()`, `bpAutoGrow()` | Name + mission brief textarea |
| TTS/Alert toolbar | `bpUpdatePreview()`, `bpUpdateAlertTime()` | Announce toggle, repeat interval, alert time |
| Schedule | CalendarComponent integration | Date picker + start time |
| Personnel tags | `bpTagInput()`, `bpPickTagForWrap()`, `bpUntagGuard()` | Callsign autocomplete + tag management |
| Checkpoint list | `bpAddCp()`, `bpRemoveCpAt()`, `bpClearCps()`, `bpRenumber()` | CRUD on `.rs-cp-row` elements |
| Checkpoint config | `bpToggleCpConfig()`, `bpValidateCpTime()` | Per-row radius/dwell/tolerance sliders |
| Asset picker | `bpAssetInput()`, `bpPickAsset()`, `bpPickAssetForRow()` | Map object + checkpoint library |
| Logic type | `bpSetLogic()` | Flexible/Sequential/Scheduled/Audit/Custom |
| Save | `bpSaveRoute()` | Full payload construction + POST/PUT |
| Delete | `bpDeleteRoute()` | Confirm + DELETE |
| Deploy | `rsDeployOpen()`, `rsDeployExecute()` | Deploy overlay + POST to `/api/routes/{id}/deploy/` |
| Preview | `bpUpdatePreview()` | Live preview of mission timeline |

### 1.3 Deploy Flow

```
bpSaveRoute() → rsDeployOpen() → rsDeployExecute() → bpConfirmExecute()
                                                      → bpSaveRoute(skipUI=true)
                                                      → POST /api/routes/{id}/deploy/
```

### 1.4 API Calls (6 total)

| Line | Endpoint | Method | Purpose |
|------|----------|--------|---------|
| 116 | `/api/routes/` | GET | Load all routes |
| 117 | `/api/profiles/` | GET | Load personnel profiles |
| 118 | `/api/map-objects/` | GET | Load map objects |
| 119 | `/api/devices/` | GET | Load devices |
| 985 | `/api/map-objects/` | POST | Save checkpoint to library |
| 1610 | `/api/routes/{id}/deploy/` | POST | Deploy saved route |
| 1970 | `/api/routes/` or `/api/routes/{id}/` | POST/PUT | Save route |
| 1992 | `/api/routes/{id}/` | DELETE | Delete route |

### 1.5 Window Exports (68 total)

**Critical (used in template onclick):**
`bpSetDirty`, `showOverlay`, `hideOverlay`, `bpShowBuilder`, `wizGo`, `wizBack`, `wizBackToSource`,
`bpPickTagForWrap`, `sweepTargetLookup`, `mgQuickDeploy`, `bpSelectRoute`, `bpCreateNew`, `bpCloseEditor`,
`bpGoDispatch`, `bpHandleShift`, `bpValidateShiftTime`, `bpSetLogic`, `bpRefreshCps`, `bpAddCp`, `bpClearCps`,
`bpRenumber`, `bpToggleCpConfig`, `bpToggleFetchGps`, `bpValidateCpTime`, `regSliderSync`, `regSliderSyncAll`,
`rsToggleProp`, `bpNameInput`, `bpPickAssetForRow`, `bpTagInput`, `bpPickTagForRow`, `bpClearTagField`,
`bpAssetInput`, `bpPickAsset`, `bpLibrarySaveRow`, `bpUntagGuard`, `bpRemoveCpAt`, `wiz2Apply`, `wiz2SaveDeploy`,
`qAddPoint`, `qResetList`, `qHandleShift`, `qApply`, `qSaveDeploy`, `qdShowInlineConfirm`, `qdDismissConfirm`,
`qdInlineUpdateBtn`, `qdInlineExecute`, `bpPopulateQuickDeploy`, `auditAddTarget`, `auditApply`, `auditSaveDeploy`,
`qdUpdateBtn`, `qdExecute`, `editUpdateBtn`, `editExecute`, `showEditConfirm`, `bpConfirmExecute`, `rsDeployOpen`,
`rsDeployCancel`, `rsDeployUpdateBtn`, `rsDeployExecute`, `bpUpdatePreview`, `bpUpdateAlertTime`, `bpSaveRoute`,
`bpDeleteRoute`

---

## 2. Backend Binding Map

### 2.1 Existing Partial Endpoints (in `api/views/partials/routes.py`)

| Endpoint | Function | Status |
|----------|----------|--------|
| `GET /api/routes-list-partial/` | `routes_list_partial` | ✅ Exists, returns card list |
| `GET /api/route-editor-partial/<pk>/` | `route_editor_partial` | ✅ Exists, returns editor HTML |

### 2.2 New Partial Endpoints Needed

| Endpoint | Function | Binds To | Purpose |
|----------|----------|----------|---------|
| `GET /api/routes-wizard-partial/` | `routes_wizard_partial` | `api/views/partials/routes.py` | Return wizard step HTML server-side |
| `GET /api/routes-checkpoint-form-partial/` | `routes_checkpoint_form_partial` | `api/views/partials/routes.py` | Return single checkpoint editor row |
| `GET /api/routes-calendar-partial/` | `routes_calendar_partial` | `api/views/partials/routes.py` | Return calendar grid HTML |
| `POST /api/routes-validate-partial/` | `routes_validate_partial` | `api/views/partials/routes.py` | Validate payload before save, return errors |
| `GET /api/routes-deploy-preview-partial/<pk>/` | `routes_deploy_preview_partial` | `api/views/partials/routes.py` | Return deploy review HTML |

### 2.3 Existing Full Endpoints (stay unchanged)

| Endpoint | Function | Purpose |
|----------|----------|---------|
| `GET /api/routes/` | `PatrolRouteViewSet.list` | List all routes |
| `POST /api/routes/` | `PatrolRouteViewSet.create` | Create route |
| `GET /api/routes/{id}/` | `PatrolRouteViewSet.retrieve` | Get single route |
| `PUT /api/routes/{id}/` | `PatrolRouteViewSet.update` | Update route |
| `DELETE /api/routes/{id}/` | `PatrolRouteViewSet.destroy` | Delete route |
| `POST /api/routes/{id}/deploy/` | `PatrolRouteViewSet.deploy` | Deploy route |

### 2.4 Model Dependencies

```
PatrolRoute
  ├── organization FK
  ├── assigned_guards M2M → GuardSupervisor
  ├── assigned_devices M2M → Device
  ├── checkpoints M2M → Checkpoint (reverse FK)
  ├── logic_type, enforce_order, enforce_time
  ├── is_audit, is_geofence, is_daily
  ├── scheduled_date, scheduled_start_time
  ├── send_announcement, readout_text, send_start_alert
  └── start_alert_lead_time

Checkpoint (per route)
  ├── route FK → PatrolRoute
  ├── checkpoint_type (nfc/gps/peer/geo/custom)
  ├── nfc_tag, lat, lng, radius, dwell_time, planned_time
  ├── time_tolerance, fetch_location_on_scan
  └── order (sequence index)

MapObject (for checkpoint library)
  ├── organization FK
  ├── geometry (point/polygon)
  └── name, radius, dwell_time, etc.

GuardSupervisor (personnel)
  ├── organization FK
  ├── callsign, first_name, last_name
  └── devices M2M → Device
```

---

## 3. Conversion Strategy

### 3.1 Phase 1 — Wizard Steps (no backend changes needed)

**Current:** All 6 wizard steps are hidden `<div>` elements in `routes.html`. Navigation via `wizGo()` toggles `rs-hidden` class.

**Target:** Each wizard step becomes a server-rendered partial. Navigation uses `hx-get` + `hx-target`.

**Steps:**
1. Move each wizard step HTML into `templates/partials/routes/wizard-step-{1,2,quick,audit,quickdeploy,editconfirm}.html`
2. Each partial extends a common wizard layout (header, back button, form fields)
3. Navigation: `hx-get="/api/routes-wizard-partial/?step=2&strategy=Flexible"` → `hx-target="#bpOverlay"`
4. Strategy selection (step 1) becomes a regular link with query params
5. Form fields in wizard read from URL params via template context

**Backend view:**
```python
@api_view(['GET'])
@login_required
def routes_wizard_partial(request):
    step = request.GET.get('step', '1')
    strategy = request.GET.get('strategy', '')
    ctx = {'step': step, 'strategy': strategy}
    
    if step == '1':
        template = 'partials/routes/wizard-step-1.html'
    elif step == '2':
        template = 'partials/routes/wizard-step-2.html'
        ctx['guards'] = GuardSupervisor.objects.filter(organization=org)
    elif step == 'quick':
        template = 'partials/routes/wizard-step-quick.html'
        ctx['guards'] = GuardSupervisor.objects.filter(organization=org)
    elif step == 'audit':
        template = 'partials/routes/wizard-step-audit.html'
        ctx['guards'] = GuardSupervisor.objects.filter(organization=org)
    elif step == 'quickdeploy':
        template = 'partials/routes/wizard-step-quickdeploy.html'
        ctx['route'] = PatrolRoute.objects.get(pk=request.GET.get('route_id'))
    elif step == 'editconfirm':
        template = 'partials/routes/wizard-step-editconfirm.html'
    
    return HttpResponse(render_to_string(template, ctx, request=request))
```

**Preserved features:**
- All form fields (name, date, shift, time, guards, repeat count)
- Tag input with autocomplete (moves to htmx partial via `hx-get` for suggestions)
- Slider presets (moves to CSS-only or data-attribute-driven)
- Quick Deploy point list (server renders empty state, htmx adds points)
- Audit target list (server renders empty state, htmx adds targets)
- Verify checkbox + deploy button (stays in partial)

### 3.2 Phase 2 — Calendar Component

**Current:** `CalendarComponent` is a JS class defined in `templates/components/calendar_component.html`. Rendered via `CalendarComponent.init()` on boot.

**Target:** Calendar renders server-side. Day click triggers `hx-get` to refresh route list for that date.

**Steps:**
1. Move calendar HTML generation to Django template tag or partial view
2. `CalendarComponent.init()` → `hx-get="/api/routes-calendar-partial/"` on container
3. Day click → `hx-get="/api/routes-list-partial/?date=2026-06-30"` → updates route list

**Backend view:**
```python
@api_view(['GET'])
@login_required
def routes_calendar_partial(request):
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    org = get_user_organization_or_none(request.user)
    
    # Get routes active in this month for this org
    routes = PatrolRoute.objects.filter(
        organization=org,
        scheduled_date__year=year,
        scheduled_date__month=month,
    )
    
    cal = calendar.Calendar()
    days = cal.monthdayscalendar(year, month)
    
    return HttpResponse(render_to_string('partials/routes/calendar.html', {
        'year': year, 'month': month, 'days': days,
        'routes_by_day': {r.scheduled_date.day: r for r in routes},
    }, request=request))
```

### 3.3 Phase 3 — Checkpoint Row Editor

**Current:** Each `.rs-cp-row` is constructed in JS via `bpAddCp()`. Contains name, type, lat/lng, tag/target inputs, sliders, config toggle.

**Target:** Checkpoint row rendered server-side. Add button triggers `hx-get` to fetch new row template.

**Steps:**
1. Create `templates/partials/routes/checkpoint-row.html`
2. `bpAddCp(data)` → `hx-get="/api/routes-checkpoint-form-partial/?type=nfc"` → `hx-target="#bpCpList"` (append)
3. Each row's type-specific fields rendered conditionally in template
4. Slider sync moved to `input` event listener in routes.js (preserved, ~5 lines)
5. Time validation preserved as `oninput` attribute in template

**Backend view:**
```python
@api_view(['GET'])
@login_required
def routes_checkpoint_form_partial(request):
    cp_type = request.GET.get('type', 'nfc')
    order = int(request.GET.get('order', 0))
    ctx = {'type': cp_type, 'order': order}
    
    if cp_type == 'nfc':
        ctx['map_objects'] = MapObject.objects.filter(
            organization=get_user_organization_or_none(request.user),
            object_type='poi'
        )
    elif cp_type == 'gps':
        pass  # No extra context needed
    elif cp_type == 'peer':
        ctx['guards'] = GuardSupervisor.objects.filter(
            organization=get_user_organization_or_none(request.user)
        )
    
    return HttpResponse(render_to_string('partials/routes/checkpoint-row.html', ctx, request=request))
```

### 3.4 Phase 4 — Deploy Preview

**Current:** `rsDeployOpen()` builds a full-screen overlay client-side, reads all form values, renders checkpoint list with planned times, shows verify checkbox.

**Target:** Deploy preview rendered server-side after save. Save returns route ID, then `hx-get` fetches deploy preview.

**Steps:**
1. `bpSaveRoute()` still exists but simplified — only constructs payload + POSTs
2. On success → `hx-get="/api/routes-deploy-preview-partial/{id}/"` → shows overlay
3. Deploy overlay partial renders: route summary, checkpoint list with planned times, verify checkbox, commence button
4. Commence button triggers `hx-post="/api/routes/{id}/deploy/"`

**Backend view:**
```python
@api_view(['GET'])
@login_required
def routes_deploy_preview_partial(request, pk):
    route = get_object_or_404(PatrolRoute, pk=pk, organization=get_user_organization_or_none(request.user))
    checkpoints = route.checkpoints.order_by('order')
    planned_times = _compute_planned_times(route, checkpoints)
    
    return HttpResponse(render_to_string('partials/routes/deploy-preview.html', {
        'route': route,
        'checkpoints': zip(checkpoints, planned_times),
    }, request=request))
```

---

## 4. What Stays in routes.js

After conversion, routes.js shrinks from 2,052 lines to ~300 lines:

### Preserved (client-only logic):
- `bpSaveRoute()` — payload construction + POST/PUT (complex, 130 lines)
- `bpDeleteRoute()` — confirm + DELETE (10 lines)
- `bpLoad()` — initial data fetch (routes, profiles, map-objects, devices)
- `bpSelectRoute()` — load route into editor
- `bpCreateNew()` / `bpCloseEditor()` — editor state management
- `bpSetDirty()` / dirty tracking
- `bpUpdatePreview()` — live timeline preview (reads DOM, updates preview panel)
- `bpValidatePastDueBlocking()` — client-side time validation
- `bpHandleShift()` / `bpValidateShiftTime()` — shift logic
- `bpSetLogic()` — logic type state
- `bpUpdateAlertTime()` — alert time display
- Tag input handlers (`bpTagInput`, `bpPickTagForWrap`, `bpUntagGuard`) — autocomplete
- Slider sync (`regSliderSync`, `regSliderSyncAll`) — UI feedback
- Asset picker (`bpAssetInput`, `bpPickAsset`) — map object selection
- Keyboard shortcut (Ctrl+S → save)
- `bpBoot()` — initialization

### Removed (moved to server):
- All wizard step HTML rendering
- Calendar rendering
- Checkpoint row HTML construction
- Deploy overlay HTML construction
- Wizard navigation (`wizGo`, `wizBack`)
- Point list management (`qAddPoint`, `qResetList`, `auditAddTarget`)
- Inline confirm strip management

---

## 5. Org-Scoped Queryset Pattern

All new partials use the existing `_resolve_route_queryset()` pattern from `api/views/partials/routes.py`:

```python
def _resolve_checkpoint_queryset(user):
    """Return checkpoints visible to this user's org."""
    org = get_user_organization_or_none(user)
    if not org:
        return Checkpoint.objects.none()
    return Checkpoint.objects.filter(organization=org)

def _resolve_guard_queryset(user):
    """Return guards visible to this user's org."""
    org = get_user_organization_or_none(user)
    if not org:
        return GuardSupervisor.objects.none()
    return GuardSupervisor.objects.filter(organization=org)

def _resolve_mapobject_queryset(user):
    """Return map objects visible to this user's org."""
    org = get_user_organization_or_none(user)
    if not org:
        return MapObject.objects.none()
    return MapObject.objects.filter(organization=org)
```

---

## 6. URL Registration

New URLs in `api/urls.py`:

```python
path('routes-wizard-partial/', views.routes_wizard_partial, name='routes_wizard_partial'),
path('routes-checkpoint-form-partial/', views.routes_checkpoint_form_partial, name='routes_checkpoint_form_partial'),
path('routes-calendar-partial/', views.routes_calendar_partial, name='routes_calendar_partial'),
path('routes-deploy-preview-partial/<int:pk>/', views.routes_deploy_preview_partial, name='routes_deploy_preview_partial'),
path('routes-validate-partial/', views.routes_validate_partial, name='routes_validate_partial'),
```

---

## 7. Migration Checklist

- [ ] Create `templates/partials/routes/wizard-step-1.html` through `wizard-step-editconfirm.html`
- [ ] Create `templates/partials/routes/checkpoint-row.html`
- [ ] Create `templates/partials/routes/calendar.html`
- [ ] Create `templates/partials/routes/deploy-preview.html`
- [ ] Add 5 new views to `api/views/partials/routes.py`
- [ ] Add 5 new URL patterns to `api/urls.py`
- [ ] Update `routes.html` to use `hx-get` for wizard navigation
- [ ] Update `routes.html` to use `hx-get` for checkpoint add
- [ ] Update `routes.html` to use `hx-get` for calendar
- [ ] Update `routes.html` to use `hx-get` for deploy preview
- [ ] Simplify `routes.js` — remove wizard HTML, calendar JS, checkpoint HTML construction
- [ ] Test: create route via wizard → save → deploy
- [ ] Test: edit existing route → save → review changes
- [ ] Test: quick deploy flow end-to-end
- [ ] Test: peer audit flow end-to-end
- [ ] Test: checkpoint add/remove/reorder
- [ ] Test: tag input autocomplete
- [ ] Test: slider presets
- [ ] Test: shift validation
- [ ] Test: past-due time blocking
- [ ] Test: Ctrl+S keyboard shortcut
- [ ] Test: delete route

---

## 8. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Feature loss during conversion | Full inventory above; test checklist covers all flows |
| Tag autocomplete breaks | Keep `bpTagInput()` in routes.js; use `hx-get` for suggestions endpoint |
| Slider sync breaks | Keep `regSliderSync()` in routes.js; trigger via `oninput` in template |
| Deploy flow breaks | `bpSaveRoute()` stays in JS; only the preview overlay moves to server |
| Calendar loses route indicators | Server renders route dots based on `scheduled_date` query |
| Wizard state lost on navigation | Use URL query params + template context; no client state needed |
| Org isolation | All new views use `get_user_organization_or_none()` |
