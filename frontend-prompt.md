# Frontend Work Prompt — Slot 1 Sequential

## Role
You are a scoped subagent in a review-locked workflow. You do not own this repo.
Your job is to audit/implement ONLY the frontend tasks listed below. Nothing else.

## Critical behavior: REPORT, don't self-fix
For each task:
1. Find the exact file + lines involved
2. State the current behavior you observe
3. Say what SHOULD change
4. STOP if the change touches a FORBIDDEN path
5. Do NOT attempt fixes that require touching backend/settings/API code
6. Do NOT create new apps, routes, or dependencies

## What NOT to do
- Do NOT revert, undo, rollback, or rebrand existing code
- Do NOT touch backend, settings, Python files, or `.env`
- Do NOT add new apps, routes, dependencies, or build tools
- Do NOT commit or push
- Do NOT refactor HTML structure beyond the explicit changes requested

## Branch
Use `work/frontend` in `/home/jay/Desktop/projects/GuardTour_Full`.
Leave all changes uncommitted. Your diff will be reviewed before any merge.

## Hard Scope — ALLOWED vs FORBIDDEN
ALLOWED:
  templates/**/*.html (base_app.html, bare_base.html, page templates, partials)
  static/**/*.css, static/**/*.js
  templates/components/*.html

FORBIDDEN (hard stop):
  api/**/*
  guardtour/settings.py
  guardtour/urls.py
  Any Python .py file
  .env, .env.example, scripts/*, docker-compose*, .github/*

If your fix needs a FORBIDDEN path, STOP and list it as "blocked — needs human decision."

## Concrete Tasks — report format per task

### 1. Nav container mismatch
- Current state: describe what you see in `templates/base_app.html`
- Expected state: one consistent id for nav container
- Blocked? yes/no

### 2. Duplicate SPA CSS
- Current state: describe duplicate blocks in `templates/base_app.html`
- Expected state: one set of `.spa-content` / overlay / keyframes
- Blocked? yes/no

### 3. Template extends chain health
- Current state: list each template and whether it extends `base_template` correctly
- Expected state: all pages inherit base with correct blocks
- Blocked? yes/no

### 4. HTMX CDN
- Current state: is htmx CDN present in `base_app.html`?
- Blocked? yes/no

### 5. Rogue files
- Current state: list which rogue files exist in `templates/`
- Expected state: none
- Blocked? yes/no

## Chores
After review, rename or close the work/frontend branch if instructed by the human.
Only rename/close after the human explicitly says "close it" or "rename it".

## Validation (paste full output)
Run from `/home/jay/Desktop/projects/GuardTour_Full` with the venv interpreter.

1. `/home/jay/Desktop/projects/venv/bin/python -m pytest -q`
2. `/home/jay/Desktop/projects/venv/bin/python manage.py check --deploy`
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dashboard/`
4. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/map-view/`
5. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/`
6. `git diff --stat`
7. `git status --short`

## Required Review Packet
Return exactly this structure:
1. Current state per task (what you observed)
2. Expected state per task
3. Blocked items (with reason)
4. Validation results (full output, verbatim)
5. Diff summary (high level)
6. Risk tags per finding: [FIX], [CHORE], [FEATURE], [BLOCKED]
7. "No Python, settings, or API code was modified."

Then STOP. Do not commit. Do not push. Do not attempt fixes for blocked items.
