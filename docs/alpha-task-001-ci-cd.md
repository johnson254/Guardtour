# Alpha Task: CI/CD Pipeline for GuardTour_Full

## Objective
Build a production-grade CI/CD pipeline that runs on every push to `main` and on pull requests.

## Why
User explicitly requires CI/CD before deployment (see USER.md: "Production mode; CI/CD required").

## Current State
- Repo: `/home/jay/Desktop/projects/GuardTour_Full` (branch `main`, HEAD `1f97532`)
- Remote: `https://github.com/johnson254/Guardtour.git`
- Stack: Django + DRF backend, Vite + HTMX + Tailwind frontend, PostgreSQL+PostGIS target
- Existing codebase indexed: 2049 nodes, 5266 edges, 126 files
- Tests: pytest present (70/73 green, 3 pre-existing test_scans.py failures)

## Requirements

### 1. GitHub Actions Workflow
Create `.github/workflows/ci.yml` with these jobs:

**lint** (runs on PR)
- Black + isort check on `api/`, `guardtour/`
- ESLint or `npm run lint` on `static/` (if configured)
- `python manage.py check` for Django syntax

**test** (runs on PR)
- `pytest` with `--tb=short -q`
- Fail on warnings count change? No. Just exit code.
- Cache `venv` and pip dependencies

**build-frontend** (runs on PR + push to main)
- Install Node deps in `static/`
- Run `npm run build` (or equivalent Vite build)
- Verify `static/dist/` manifest exists
- Upload `static/dist/` as artifact

**security-scan** (runs on PR + push to main)
- `pip-audit` or `safety check` on `requirements.txt`
- Fail if high/critical vulnerabilities found

### 2. Deployment Gate (staging trigger, not prod auto-deploy)
- All 3 jobs (`lint`, `test`, `build-frontend`) must pass before merge
- Auto-merge to `main` is **NOT** required. User merges manually.
- Tag `v*` pushes to `main` trigger a deploy notification job that:
  1. Builds Docker image (if Dockerfile exists, else skip)
  2. Prints deployment checklist (migrations, env vars, restart command)

### 3. Caching Strategy
- Pip cache: `~/.cache/pip`
- Node cache: `~/.npm` or `~/.yarn`
- Django test DB: SQLite in memory is fine for CI (`:memory:`)

### 4. Secrets / Env
Do NOT hardcode secrets. Reference these in README for user to set in GitHub:
- `DJANGO_SECRET_KEY`
- `DATABASE_URL` (optional for CI; SQLite memory is default)
- `DEBUG=False` for staging checks

## Acceptance Criteria
1. `.github/workflows/ci.yml` exists and is valid YAML
2. `python manage.py check` result is referenced or gated
3. `pytest` runs and reports pass/fail (don't fix the 3 pre-existing test_scans.py failures unless trivial)
4. Frontend build step completes and emits `static/dist/` (or fails clearly)
5. README.md section "CI/CD" explains how to set repo secrets

## Constraints
- Do NOT push or commit without user approval
- Do NOT run migrations or touch production database
- Do NOT modify Dockerfile unless user requests it
- Keep changes minimal; pipeline should be fast (<8 min total)

## Estimated Scope
~150-250 lines of YAML + README update. Self-contained.
