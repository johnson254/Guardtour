# GuardTour_Full — Session Workflow Summary
**Date:** 2026-06-29  
**Branch:** main (HEAD: 8a6c97a)  
**Dev server:** http://127.0.0.1:8080  
**Stack:** Django + Vite + HTMX + Tailwind + PostgreSQL + Redis

---

## Goal
Deliver a demo-ready app by EOD 2026-06-29 08:00 EAT. Priorities: runtime behavior over tests, in-chat review only, no unfinished pushes, no Ngrok preview without explicit instruction.

---

## What We Did This Session

### 1. Theme unification
- Made `templates/base_template.html` the canonical ops-dark shell for all full-page and HTMX loads.
- Re-skinned `templates/base_app.html` to inherit the same glass-morphism nav, surface tokens, and role builder.
- Re-skinned `templates/login.html` and `templates/register.html` to match the tactical dark ops palette (crimson/teal/amber).
- All template/context-processor changes verified via `python manage.py check` (0 issues). No pytest run was executed (user rule).

### 2. Auth conversion — HTMX POST
- `templates/login.html` now posts via HTMX to `/api/login/` instead of a fetch call.
- `templates/register.html` likewise posts via HTMX to `/api/register/`.
- Backend endpoints and `localStorage.gt_user` payload contract were preserved unchanged.
- `api/views/auth.py` now returns a bounded `next` value in the login JSON response and sets the `gt_access_token` cookie explicitly.

### 3. Redirect loop fix
- **Bug:** A malformed `?next` query could cause infinite encoding (`/?next=/%3Fnext%3D/...`) on every bounce.
- **Fix:** Added `_sanitize_next()` in `api/views/auth.py`. It strips encoded `?next=` prefixes, rejects paths that themselves contain `next=`, and falls back to `/dashboard/`.
- `templates/login.html` now defaults the hidden `next` field to `/dashboard/`, only accepts a clean relative path from URL params, and on success redirects via `data.next.split('?')[0]`.

### 4. Nav restoration
- Restored the dynamic `renderNav()` role-aware HTMX nav pill builder inside `templates/base_app.html`. It wasn’t being called in the simplified shell; dashboards, routes, dispatch, incidents, manage, analytics, and control links are now role-gated again and target `#spa-content`.

### 5. Codebase re-index
- Re-indexed the entire repo in `codebase-memory` for cross-session traceability.
- Result: 2126 nodes, 4877 edges, 126 files; artifact persisted at `.codebase-memory/graph.db.zst`.

---

## Files Changed (uncommitted on main)

| File | Change |
|------|--------|
| `templates/base_template.html` | Canonical ops-dark shell; glass nav, `#spa-content`, HTMX config, `sessionToken`, inline shared JS |
| `templates/base_app.html` | Restored `renderNav()` builder; role-gated spa nav pills |
| `templates/login.html` | HTMX POST form; tactical login card; sanitized redirect on JS and backend |
| `templates/register.html` | HTMX POST form; matching tactical theme |
| `api/views/auth.py` | `_sanitize_next()`; login returns `next` JSON + sets cookie |
| `api/context_processors.py` | Fallback base template for full-page loads set to `base_template.html` |
| `.codebase-memory/graph.db.zst` | Rebuilt repo index artifact |

Backups retained: `templates/base_template.html.bak`, `templates/base_app.html.bak`

---

## Verification Status

- **`python manage.py check`**: passed (0 issues).
- **Browser verification:** pending a hard refresh + localStorage clear.
- **`pytest`:** last run is stale (pre-this-session focus). Baseline: 70 passed, 3 pre-existing `tests/test_scans.py` failures (`test_valid_scan_creates_record`, `test_duplicate_scan_within_30s_rejected`, `test_batch_scan_upload`). These failures are **not** caused by the work in this session; they predate it. No pytest was run because of the user’s explicit block on pytest in this session.

---

## Pre-existing Blockers To Keep In Mind

1. `tests/test_scans.py` still has 3 failures from an earlier state; needs a fresh pytest run to confirm or clear them.
2. Browser/frontend verification of the new login→dashboard HTMX flow still needs a manual refresh and `localStorage` clear.
3. `static/dist` and static asset 404 tracking were not the focus here; no fresh evidence on that.

---

## Operational Notes

- I control git; you run agents and the dev server.
- Do not auto-fix the 3 `test_scans.py` failures unless explicitly asked.
- Template changes in this session are safe to commit; auth backend change is also safe (bounded behavior, no DB changes).
- No API keys, tokens, or credentials were discussed or exposed.
