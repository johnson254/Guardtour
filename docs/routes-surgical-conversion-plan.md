# Routes Page — Surgical Conversion Plan

**Branch:** `feat/routes-htmx-conversion`  
**Date:** 2026-06-30  
**Principle:** Zero feature loss. Every DOM element preserved. Every onclick handler accounted for.

---

## 1. DOM Audit — What Exists in the Template

### 1.1 Layout Structure (3-column)

```
.rs-shell
├── .rs-panel (rsLibPanel) — LEFT: Blueprint Library
│   ├── .rs-panel-head (search + New button)
│   └── #bpRouteList (htmx-loaded list)
├── .rs-panel.rs-editor — CENTER: Editor
│   ├── #bpOverlay (wizard overlay, hidden by default)
│   │   ├── #wizStep1 (strategy selection)
│   │   ├── #wizStep2 (standard config)
│   │   ├── #wizStepQuick (quick deploy)
│   │   ├── #wizStepAudit (peer audit)
│   │   ├── #wizStepQuickDeploy (full-screen review)
│   │   └── #wizStepEditConfirm (edit delta review)
│   ├── .rs-panel-head (editor header with buttons)
│   ├── .rs-ed-body (editor form)
│   │   ├── Duty Cycle section
│   │   ├── Blueprint Identity section
│   │   ├── Schedule section
│   │   ├── Personnel section
│   │   ├── Checkpoints section (#bpCpList)
│   │   └── Asset picker section
│   └── .rs-ed-footer (Ctrl+S hint + deploy footer button)
└── #rsSidebar — RIGHT: Calendar + Manifest + Deploy Panel
    ├── #rsCalView (calendar component include)
    ├── #rsManifestPanel (personnel + checkpoint summary)
    └── #rsDeployPanel (deploy review panel, hidden by default)
```

### 1.2 All `id=""` Elements in Template (must be preserved)

```
bpOverlay, wizStep1, wizStep2, wizStepQuick, wizStepAudit, 
wizStepQuickDeploy, wizStepEditConfirm,
rsLibPanel, bpRouteSearch, bpRouteList,
bpEdTitle, bpDeployBtn, bpReviewBtn, bpSaveBtn,
bpOverlay (duplicate? no — same as above),
qName, qGuardInput, qGuardTags, qGuardSuggest,
qShiftDay, qShiftAny, qShiftNight,
qTime, qLead, qAlert, qAnnouncementText, qAnnounceToggle,
qPointsList, qPointsEmpty,
qdConfirmStrip, qdConfirmSummary, qdConfirmCps,
qdInlineVerify, qdInlineDeployBtn,
wiz2Name, wiz2Date, wiz2ShiftDay, wiz2ShiftAny, wiz2ShiftNight,
wiz2StartTime, wiz2Alert, wiz2Stay,
wiz2GuardInput, wiz2GuardTags, wiz2GuardSuggest,
wiz2Repeat, wiz2IntervalWrap, wiz2Interval,
auditName, auditShiftDay, auditShiftAny, auditShiftNight,
auditDate, auditStartTime, auditAlert,
auditAuditorInput, auditAuditorTags, auditAuditorSuggest,
auditInterval, auditStay, auditEnforceSeq,
auditTargets,
qdBpName, qdBpStrat, qdShift, qdDate, qdTime,
qdGuardTags, qdSendAlert, qdSendAnnounce, qdLeadTime,
qdCpCount, qdCpList, qdVerify, qdDeployBtn,
editDiffContent, editVerify, editSaveBtn,
bpRouteName, bpMissionBrief, bpCharCount,
bpAnnounceToggle, bpTtsLabel, bpLeadTime, bpRepeatLabel,
bpSendAlert, bpAlertTimeText, bpAlertTimeRow,
bpDate, bpDateQuickLock, bpStartTime, bpIsDaily,
bpShiftDay, bpShiftAny, bpShiftNight,
bpGuardInput, bpGuardTags, bpGuardSuggest,
bpCpList, bpAssetSearch, bpAssetSuggest,
cp-{idx} (dynamically generated),
rsSidebar, rsCalView, rsManifestPanel, rsManifestToggle,
summaryPersonnel, summaryCps,
rsDeployPanel, rsDeployPastDue, rsDeployPastDueDetail,
rsDeployBpName, rsDeployStrat, rsDeployDate, rsDeployTime,
rsShiftDay, rsShiftNight,
rsDeployGuardTags, rsTriggerAlert, rsTriggerAnnounce,
rsTriggerAuto, rsTriggerMiss, rsLeadTime, rsReadoutText,
rsVerify, rsDeployCpCount, rsDeployCpList,
rsDeployBtn, rsDeployBtnText,
bpDeployFooter, bpToasts
```

### 1.3 All `onclick=""` Handlers in Template

```
hideOverlay() — wizStep1 close button
wizGo('quick') — Quick Deploy hero
wizGo(2,'Flexible') — Flexible chip
wizGo(2,'Sequential') — Sequential chip
wizGo(2,'Scheduled') — Scheduled chip
wizGo('audit') — Audit chip
wizGo(2,'Custom') — Custom chip
wizBack(1) — wizStep2 back button
wiz2Apply() — Apply to Editor
wiz2SaveDeploy() — Save & Deploy
qAddPoint('nfc') — Add NFC point
qAddPoint('gps') — Add GPS point
qAddPoint('peer') — Add Peer point
qAddPoint('custom') — Add Custom point
qApply() — Apply to Editor (quick)
qSaveDeploy() — Deploy Now (quick)
qdDismissConfirm() — Cancel confirm
qdInlineExecute() — COMMENCE (inline)
auditAddTarget() — Add target guard
auditApply() — Apply to Editor (audit)
auditSaveDeploy() — Save & Deploy (audit)
qdExecute() — COMMENCE DEPLOYMENT
editExecute() — SAVE CHANGES
rsDeployCancel() — Back (deploy panel)
rsDeployExecute() — COMMENCE MISSION
bpCreateNew() — New Blueprint
rsDeployOpen() — Deploy button
showEditConfirm() — Review button
bpSaveRoute() — Save button
bpCloseEditor() — Discard button
bpGoDispatch() — Go to Dispatch
bpHandleShift() — shift radio change
bpSetDirty() — various inputs
rsToggleProp(event,this) — checkpoint setting chips
```

---

## 2. Dead Code Audit

### 2.1 Unused Functions in routes.js

| Function | Evidence | Action |
|----------|----------|--------|
| `setDispatch(show)` | Only toggles `bpDeployBtn`/`bpReviewBtn` visibility. But these buttons are always `rs-hidden` in template and never unhidden by current code paths. | **KEEP** — used by `bpSelectRoute()` and `bpCreateNew()` which are core flows |
| `bpGoDispatch()` | Redirects to `/dispatch/`. No button calls it currently. | **KEEP** — may be wired later, harmless |
| `mgQuickDeploy(routeId)` | Named "mg" (manage prefix). Not called from routes template. Likely dead. | **REMOVE** |
| `rsToggleProp(e, chip)` | Called from checkpoint setting chips in template. | **KEEP** |
| `refreshRouteList()` | Called from `bpLoad()` and `bpDeleteRoute()`. | **KEEP** |

### 2.2 Unused State Variables

| Variable | Usage | Action |
|----------|-------|--------|
| `calDate` | Set but never read (calendar is CalendarComponent) | **REMOVE** |
| `selCalDay` | Set but never read | **REMOVE** |
| `wizSourceId` | Set to 'wizStep1', used by `wizBackToSource()` which is never called | **REMOVE** |
| `shiftMode` | Set to '', never read meaningfully | **REMOVE** |
| `assignedGuardIds` | Populated but only used for validation in `bpSaveRoute()` | **KEEP** |

### 2.3 Template Elements Never Referenced in JS

| Element | Purpose | Action |
|---------|---------|--------|
| `bpDateQuickLock` | "TODAY ONLY" overlay on date field | **KEEP** — visual only |
| `bpAlertTimeRow` | Hidden alert info row | **KEEP** — toggled by `bpUpdateAlertTime()` |
| `rsManifestToggle` | Hide/show manifest panel | **KEEP** — inline onclick |
| `bpDeployFooter` | "Go to Dispatch" in editor footer | **KEEP** — wired via `setDispatch()` |
| `rsTriggerAuto`, `rsTriggerMiss` | Deploy panel checkboxes | **KEEP** — read by `rsDeployExecute()` |
| `rsReadoutText` | Deploy panel textarea | **KEEP** — read by `rsDeployExecute()` |

---

## 3. Conversion Strategy — Phase by Phase

### Phase 0: Cleanup (safe, no behavior change)

**Remove dead code:**
- `mgQuickDeploy()` function (lines ~265-340)
- `calDate`, `selCalDay`, `wizSourceId`, `shiftMode` variables
- `wizBackToSource()` function (unused)

**Estimated savings:** ~80 lines

### Phase 1: Wizard Navigation via htmx

**Current behavior:** `wizGo()` hides all steps, shows target step. `wizBack()` shows step 1.

**New behavior:** Each wizard step is a full htmx swap. Navigation links use `hx-get` to fetch step partial.

**Critical preservation:**
- All form field `id=""` attributes MUST be unique across steps (they already are: `wiz2Name` vs `qName` vs `auditName`)
- Tag suggestion dropdowns (`wiz2GuardSuggest`, `qGuardSuggest`, `auditAuditorSuggest`) must still work
- Shift pill radio buttons must still trigger `bpHandleShift()` / `qHandleShift()`

**Implementation:**
1. Extract each wizard step `<div>` into `templates/partials/routes/wizard/{step-name}.html`
2. Each partial includes its own `onclick` handlers (they reference global functions that still exist)
3. Navigation buttons become `<a hx-get="..." hx-target="#bpOverlay" hx-swap="innerHTML">`
4. `showOverlay()` / `hideOverlay()` still work — they toggle the overlay container visibility
5. Inside overlay, htmx swaps the step content

**Key insight:** We don't need to move form logic to server. We just need to:
- Make each step a separate partial file
- Load step 1 on page boot (replaces the 6 hidden divs)
- Swap steps via htmx navigation

**This means:** The wizard HTML stays identical. We just split it into files and load via htmx.

### Phase 2: Checkpoint Row via htmx

**Current behavior:** `bpAddCp(data)` constructs a `.rs-cp-row` DOM element from scratch in JS.

**New behavior:** `bpAddCp()` fetches a pre-rendered row via htmx, then populates data.

**Critical preservation:**
- All `id="cp-*"` attributes must be unique per row
- Slider sync (`regSliderSync`) must still work on new rows
- Drag-and-drop reorder must still work
- Time validation (`bpValidateCpTime`) must still work
- Toggle fetch GPS (`bpToggleFetchGps`) must still work

**Implementation:**
1. Create `templates/partials/routes/checkpoint-row.html` — a single row template
2. Template uses `{{ type }}`, `{{ order }}`, `{{ idx }}` for dynamic values
3. `bpAddCp(data)` becomes:
   ```js
   async function bpAddCp(data = {}) {
     const type = data.type || 'nfc';
     const idx = document.querySelectorAll('#bpCpList .rs-cp-row').length;
     const res = await fetch(`/api/routes-checkpoint-form-partial/?type=${type}&order=${idx}`);
     const html = await res.text();
     const div = document.createElement('div');
     div.innerHTML = html;
     const row = div.firstElementChild;
     // Populate data into row inputs
     if (data.name) row.querySelector('.bp-cp-name').value = data.name;
     // ... etc
     $('bpCpList').appendChild(row);
     bpRenumber();
   }
   ```
4. All existing event listeners (drag, slider, time validate) are re-attached after insertion

### Phase 3: Deploy Panel via htmx

**Current behavior:** `rsDeployOpen()` populates `rsDeployPanel` from form values, shows it.

**New behavior:** `rsDeployOpen()` fetches pre-rendered deploy panel with route data.

**Implementation:**
1. `rsDeployOpen()` first saves the route (if dirty), gets route ID
2. Then `hx-get="/api/routes-deploy-preview/{id}/"` → swaps `rsDeployPanel` content
3. Deploy button triggers `hx-post="/api/routes/{id}/deploy/"`

### Phase 4: Calendar (already server-rendered)

**Current:** Calendar is already included via `{% include "components/calendar_component.html" %}`.

**Issue:** `CalendarComponent` is a JS class that renders client-side. The include provides the container + JS.

**Decision:** Leave as-is for now. Calendar is not a priority for htmx conversion.

---

## 4. Backend Endpoints

### 4.1 New Views in `api/views/partials/routes.py`

```python
@api_view(['GET'])
@login_required
def routes_wizard_partial(request):
    """Return a wizard step HTML fragment."""
    step = request.GET.get('step', '1')
    strategy = request.GET.get('strategy', '')
    org = get_user_organization_or_none(request.user)
    
    ctx = {'step': step, 'strategy': strategy}
    
    if step == '2':
        ctx['guards'] = _resolve_guard_queryset(request.user)
    elif step == 'quick':
        ctx['guards'] = _resolve_guard_queryset(request.user)
    elif step == 'audit':
        ctx['guards'] = _resolve_guard_queryset(request.user)
    
    template_map = {
        '1': 'partials/routes/wizard/step-1.html',
        '2': 'partials/routes/wizard/step-2.html',
        'quick': 'partials/routes/wizard/step-quick.html',
        'audit': 'partials/routes/wizard/step-audit.html',
        'quickdeploy': 'partials/routes/wizard/step-quickdeploy.html',
        'editconfirm': 'partials/routes/wizard/step-editconfirm.html',
    }
    
    return HttpResponse(render_to_string(template_map.get(step, template_map['1']), ctx, request=request))


@api_view(['GET'])
@login_required
def routes_checkpoint_form_partial(request):
    """Return a single checkpoint row HTML fragment."""
    cp_type = request.GET.get('type', 'nfc')
    order = int(request.GET.get('order', 0))
    org = get_user_organization_or_none(request.user)
    
    ctx = {'type': cp_type, 'order': order, 'idx': order}
    
    if cp_type == 'nfc':
        ctx['map_objects'] = MapObject.objects.filter(organization=org, object_type='poi')
    elif cp_type == 'peer':
        ctx['guards'] = _resolve_guard_queryset(request.user)
    
    return HttpResponse(render_to_string('partials/routes/checkpoint-row.html', ctx, request=request))


@api_view(['GET'])
@login_required
def routes_deploy_preview_partial(request, pk):
    """Return deploy preview panel HTML."""
    route = get_object_or_404(PatrolRoute, pk=pk, organization=get_user_organization_or_none(request.user))
    checkpoints = route.checkpoints.order_by('order')
    
    return HttpResponse(render_to_string('partials/routes/deploy-preview.html', {
        'route': route,
        'checkpoints': checkpoints,
    }, request=request))
```

### 4.2 New URL Patterns

```python
path('routes-wizard-partial/', views.routes_wizard_partial, name='routes_wizard_partial'),
path('routes-checkpoint-form-partial/', views.routes_checkpoint_form_partial, name='routes_checkpoint_form_partial'),
path('routes-deploy-preview-partial/<int:pk>/', views.routes_deploy_preview_partial, name='routes_deploy_preview_partial'),
```

### 4.3 Helper Functions

```python
def _resolve_guard_queryset(user):
    org = get_user_organization_or_none(user)
    if not org:
        return GuardSupervisor.objects.none()
    return GuardSupervisor.objects.filter(organization=org)
```

---

## 5. Template Partial Files to Create

```
templates/partials/routes/
├── wizard/
│   ├── step-1.html       (strategy selection)
│   ├── step-2.html       (standard config)
│   ├── step-quick.html   (quick deploy)
│   ├── step-audit.html   (peer audit)
│   ├── step-quickdeploy.html (full-screen review)
│   └── step-editconfirm.html (edit delta)
├── checkpoint-row.html   (single checkpoint editor row)
└── deploy-preview.html   (deploy review panel content)
```

---

## 6. What Stays in routes.js (preserved functions)

### Core (never touch):
- `bpSaveRoute()` — payload construction + API call
- `bpDeleteRoute()` — delete with confirm
- `bpLoad()` — initial data fetch
- `bpSelectRoute()` — load route into editor
- `bpCreateNew()` / `bpCloseEditor()` — editor state
- `bpUpdatePreview()` — live timeline preview
- `bpValidatePastDueBlocking()` — time validation
- `bpHandleShift()` / `bpValidateShiftTime()` — shift logic
- `bpSetLogic()` — logic type state
- `bpUpdateAlertTime()` — alert time display
- `refreshRouteList()` — htmx list refresh
- `bpBoot()` — initialization
- `toast()` — user feedback
- `bpAutoGrow()` — textarea auto-resize
- `bpSetDirty()` — dirty tracking
- `showOverlay()` / `hideOverlay()` — overlay visibility
- `setDispatch()` — deploy button visibility

### Modified (adapted for htmx):
- `bpAddCp()` — now fetches partial then populates
- `wizGo()` — now triggers htmx fetch instead of DOM toggle
- `wizBack()` — now triggers htmx fetch
- `rsDeployOpen()` — now fetches deploy preview partial
- `auditAddTarget()` — now fetches partial for new target row
- `qAddPoint()` — now fetches partial for new point card
- `bpPopulateQuickDeploy()` — may become server-rendered

### Removed (dead code):
- `mgQuickDeploy()` — not called from routes
- `wizBackToSource()` — not called
- `calDate`, `selCalDay`, `wizSourceId`, `shiftMode` — unused state

---

## 7. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Tag autocomplete breaks after htmx swap | `populateTagSuggest()` called after every swap via `htmx:afterSwap` listener |
| Slider sync breaks on dynamically-added rows | Use event delegation on `#bpCpList` instead of per-row listeners |
| Drag-and-drop breaks on new rows | Re-attach drag handlers after htmx swap |
| Time validation breaks | Keep `oninput` attribute in template; doesn't need re-attachment |
| Wizard state lost on navigation | Each step reads from shared form fields (bpRouteName, etc.) which persist in the editor |
| Deploy panel loses data | Deploy preview is server-rendited from saved route ID |
| `bpSaveRoute()` breaks | Not modified — only the UI around it changes |
| Ctrl+S shortcut breaks | Not modified — `keydown` listener stays in routes.js |
| Overlay close button breaks | `hideOverlay()` stays in routes.js |

---

## 8. Implementation Order

1. **Phase 0:** Remove dead code (safe, test immediately)
2. **Phase 1:** Create wizard partials + backend view + URL
3. **Phase 1b:** Update `wizGo()` to use htmx
4. **Phase 1c:** Test all wizard flows
5. **Phase 2:** Create checkpoint-row partial + backend view + URL
6. **Phase 2b:** Update `bpAddCp()` to use htmx
7. **Phase 2c:** Test checkpoint CRUD
8. **Phase 3:** Create deploy-preview partial + backend view + URL
9. **Phase 3b:** Update `rsDeployOpen()` to use htmx
10. **Phase 3c:** Test deploy flow
11. **Final:** Full regression test of all routes flows

Each phase is independently testable. If any phase breaks, revert just that phase.
