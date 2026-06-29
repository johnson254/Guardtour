# Chores Prompt — Maintenance & Cleanup

## Role
You are a scoped subagent. You do not own this repo.
Your job is to clean up existing code, not redesign it.

## Workflow
- No commits. No pushes.
- Report every change you make before committing.
- If a task touches both frontend and backend, STOP and split it.

## Slot A — Backend chores
Focus: `api/`, `guardtour/urls.py`, `guardtour/settings.py`, tests/

### Tasks
1. **Dead middleware cleanup**
   - `api/middleware.py` exists but is not loaded.
   - Decide: delete `api/middleware.py` OR wire it in `guardtour/settings.py`.
   - Do not change other settings.

2. **URL hygiene**
   - Review `guardtour/urls.py` for duplicate or missing routes.
   - `/login/` must resolve to a valid view.
   - Do NOT rename URL names other teams rely on.

3. **Test deprecation cleanup**
   - `tests/test_device_auth.py`, `tests/test_guards.py`, `tests/test_routes.py`, `tests/test_shifts.py`
   - Replace `datetime.utcnow()` with `django.utils.timezone.now()` where safe.
   - Do NOT change test logic.

4. **Docstrings**
   - Add docstrings to all view functions in `api/views/core.py` that are missing them.

### Validation (paste full output)
1. `/home/jay/Desktop/projects/venv/bin/python -m pytest -q`
2. `/home/jay/Desktop/projects/venv/bin/python manage.py check --deploy`
3. `git diff --stat`

## Slot B — Frontend chores
Focus: `templates/`, `static/`, `scripts/`

### Tasks
1. **base_app.html cleanup**
   - Remove duplicate `.spa-content` CSS blocks.
   - Ensure all pages use `base_template.html` inheritance.

2. **scripts/run.sh fix**
   - Fix venv path: use `/home/jay/Desktop/projects/venv` instead of `.venv`.
   - Keep Daphne on 8080 and Vite on 5173.

3. **Stray file cleanup**
   - Remove `templates/components/mapcn-map-route.tsx`
   - Remove `templates/components/mapcn-route-demo.tsx`
   - Remove any `.txt` files in `templates/`

4. **login page**
   - Ensure login works with current JWT response shape (`refresh`, `access`, `role`, `organization_name`).

### Validation (paste full output)
1. `/home/jay/Desktop/projects/venv/bin/python -m pytest -q`
2. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login/`
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/routes/`
4. `git diff --stat`

## Strict refusal rules
- Do NOT touch `api/views/core.py` logic or `guardtour/settings.py` security/db/cors blocks.
- Do NOT rename URL names without explicit approval.
- Do NOT delete migrations.
- Do NOT push.

## Required Review Packet
1. Current state per task
2. Changes made per task
3. Blocked items
4. Validation results (full output)
5. Diff summary
6. Risk tags: [FIX], [CHORE], [BLOCKED]
7. "No unapproved changes."
