# Alpha Fix #1: Organization ID Type Mismatch + Guard Role Handling

## Status
Commit `25db935` is on `main`. Frontend auth works, but `organization_id` is dangerously inconsistent across the auth response.

## Bug Summary
In `api/views/auth.py:login()`:
- **Admin / superuser:** `organization_id` → list of ALL org IDs (e.g. `[1, 2, 3]`)
- **Dispatcher:** `organization_id` → single-item list (e.g. `[1]`)
- **Guard / Supervisor:** `organization_id` → `None` (never assigned)

In `templates/login.html`:
```js
organization_id: d.organization_id ? d.organization_id[0] : null,
```
This crashes silently when `d.organization_id` is `None` because it tries `null[0]`.

In `templates/base_app.html` and nav JS:
- `userData.organization_id` is treated as a scalar (single ID or `null`), not a list

## Scope of Fix
### 1. `api/views/auth.py`
- For **dispatcher:** return scalar `organization_id = dispatcher.organization.id` (not a list)
- For **admin / superuser:** return scalar `organization_id = None` (meaning “global”) OR `organization_id = org.id` of their primary org. Pick one approach and apply it.
- For **guard / supervisor:** add an explicit branch that reads their organization and sets `organization_id` and `organization_name`. Without this, guards log in as `role='guard'` with `organization_id=None` and show “Guest”.

Rule of thumb: `organization_id` should be an integer ID or `null`. Never a list.

### 2. `templates/login.html`
- Change `d.organization_id[0]` → `d.organization_id` (no array indexing)
- The ternary `d.organization_id ? ... : null` is fine because scalar ID truthy works

### 3. `templates/base_template.html` (if needed)
- The nav only renders org display; verify it handles `null` org gracefully (already shows ‘SecOps v2.0’ fallback)

## Verification
- `python manage.py check` must pass
- Do NOT run pytest
- Manual smoke: log in as dispatcher, guard, and admin. Confirm `gt_user.organization_id` is a scalar (number) in browser localStorage

## Constraints
- Do NOT touch committed `.env.example`, `.codebase-memory/`, or untracked prompt files
- Do NOT push or commit
