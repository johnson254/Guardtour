# Frontend Work Prompt — Slot 1 Sequential

## Role
You are a subagent in a controlled review workflow. You are NOT the primary owner of this codebase.

Your job is to continue existing frontend work and fix specific, scoped issues. You must NOT:
- Revert, undo, or roll back any existing code
- Rebrand, restructure, or refactor the app architecture
- Change backend, settings, or Python files
- Commit or push anything

## Branch
Use `work/frontend` in `/home/jay/Desktop/projects/GuardTour_Full`.
Leave all changes uncommitted. This repo uses a protected review flow: you edit, a human reviews the diff, then decides merge/fix/drop.

## Hard Scope Guard
You MAY edit:
  - templates/**/*.html (do NOT delete or rename `templates/base_template.html`)
  - static/**/*

You MUST NOT edit:
  - api/**/*
  - guardtour/settings.py
  - guardtour/urls.py
  - Any Python files
  - .env, .env.example, scripts/*

If a fix requires touching forbidden paths, STOP and list it as "blocked — needs human decision".

## Concrete Tasks

### 1. Fix nav container mismatch
- `templates/base_app.html` contains both `<div class="nav" id="navMenu">` and `<div class="nav-tabs" id="nav-tabs">`.
- JS at the bottom of `base_app.html` targets `#nav-tabs`.
- Keep ONE id. Preferred: `id="nav-tabs"` with class `nav-tabs`.
- Remove the duplicate `id="navMenu"` if still present.
- Update any page templates that reference `#navMenu` in inline JS.

### 2. Remove duplicate SPA transition CSS
- `templates/base_app.html` has `.spa-content` / `.spa-transition-overlay` / `.spa-spinner` defined TWICE.
- Keep the second/better version and delete the first duplicate block.
- Ensure `@keyframes spa-spin` and `@keyframes spaPageIn` remain exactly once.

### 3. Clean template extends chain
- All page templates extend `{% extends base_template %}`.
- The context processor resolves `base_template` to `bare_base.html` for HTMX partials and `base_app.html` for full pages.
- Verify each page still has:
  - `{% extends base_template %}`
  - optional `{% block extra_head %}`
  - `{% block content %}`
  - optional `{% block page_js %}` with `{% load static %}` and `{% load vite %}`
- Do NOT add `{% load htmx_base %}` anywhere.

### 4. Preserve HTMX CDN delivery
- `base_app.html` already loads htmx from CDN.
- Do NOT remove or relocate this script.
- Keep `shared-globals.js` load order after htmx.

### 5. Remove rogue non-HTML files from templates/
Delete if present:
  - templates/components/mapcn-map-route.tsx
  - templates/components/mapcn-route-demo.tsx
  - templates/components/mapcn-map-route.txt

### 6. No visual regression for nav
- Keep the flat `.nav` / `.nav-tabs` pill design.
- Do NOT reintroduce glass tabs or `.nav-tab` classes unless they already exist cleanly.

## Validation Steps (run in order, paste full output)
Run from `/home/jay/Desktop/projects/GuardTour_Full` using the venv interpreter.

1. `pytest -q`
2. `python manage.py check --deploy`
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dashboard/`
4. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/map-view/`
5. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/`
6. `git diff --stat`
7. `git status --short`

## Output Format
Return a review packet:

1. Files modified
2. Tasks completed / skipped (with reason)
3. Validation results (full output)
4. Diff summary (high level)
5. Risk tags per change: [FIX], [CHORE], [FEATURE]
6. Statement: "No Python, settings, or API code was modified."

Then STOP. Do not commit. Do not push.
