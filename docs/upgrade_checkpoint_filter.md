# Upgrade Plan: Type-Aware Checkpoint Filtering in `manage.py`

Branch: `fix/nav-bar-routing`  
Repo: `https://github.com/johnson254/Guardtour.git`

## Problem

`api/views/partials/manage.py` currently hardcodes the checkpoint queryset to only two types:

```python
qs = MapObject.objects.filter(type__in=['poi', 'geofence'])
```

This was introduced in uncommitted work on `fix/nav-bar-routing` and silently lowers visibility for NFC, GPS, peer, geo, and custom checkpoints across every manage-page partial that calls `_resolve_checkpoints()`. The frontend templates still render all those type-specific chips, groups, and stat blocks, causing a data/UI mismatch.

## Goal

Make checkpoint filtering explicit and opt-in via query parameters, instead of hidden hardcoding. Preserve all existing callers and frontend behavior by default.

## Engineering Rules

- **Frontend stays untouched** during this upgrade. No template, CSS, or JS changes.
- **URL routing stays untouched**. We reuse the existing partial endpoints.
- **Backward compatibility**: when no type filter is supplied, behavior must be the same as before the hardcoded change.

## Proposed Shape

### 1. Refactor `_resolve_checkpoints(user, types=None)`

```python
def _resolve_checkpoints(user, types=None):
    org = _resolve_org(user)
    qs = MapObject.objects.all()
    if org:
        qs = qs.filter(organization=org)
    if types:
        qs = qs.filter(type__in=[t.strip() for t in types.split(',') if t.strip()])
    return qs
```

- `types=None` or empty string → returns all checkpoint types
- `types="poi,geofence"` → filters to exactly those
- Keeps all current callers working without change

### 2. Update `fleet_panel_stats_partial(request)` to accept `?types=...`

```python
types_param = request.GET.get('types', '')
asset_count = MapObject.objects.filter(
    type__in=[t.strip() for t in types_param.split(',') if t.strip()]
).count() if types_param else MapObject.objects.count()
```

- Default remains all types when `?types=` is absent
- Frontend can later pass `?types=poi,geofence` when narrowing is intentional

### 3. Revert prior hardcoding in the same file

Remove the inline `type__in=['poi', 'geofence']` lines that were added during the earlier uncommitted cleanup in both:
- `_resolve_checkpoints`
- `fleet_panel_stats_partial`

### 4. Do not change

- `api/urls.py` routes
- templates in `templates/partials/manage/`
- `static/src/pages/manage.js`
- `guardtour/settings.py` and any frontend files

## Verification

```bash
python3 manage.py check
python3 manage.py runserver
# /manage/ panel stats partial still returns full type counts by default
# Hitting /api/manage/fleet-panel-stats-partial/?types=poi,geofence narrows asset_count only
```

## Commit Message

```
feat(manage): make checkpoint filters opt-in via ?types= query param
```

## Notes for Implementer

This is intended as a minimal backend-only change. Future splits into per-type manage pages or dedicated routes can be done on top of this without touching `_resolve_checkpoints` again. Do not re-introduce hidden hardcoded filters in shared queryset helpers.
