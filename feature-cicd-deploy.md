# Feature Prompt — CI/CD Pipeline + Deploy Prep (Slot 2 Backend)

## Role
You are a scoped backend subagent. You do not own this repo.
Sequential workflow: frontend Slot 1 is assumed complete. This slot must not touch templates/static.

## Goal
Design and implement a CI/CD pipeline that builds, validates, and packages the Django backend plus Vite/HTMX frontend for deployment readiness — without actually deploying. Deliver a working pipeline definition and deployment artifacts.

## Reviewed Design Docs to Honor
- `APP_ISSUES.md` — mobile API design/intent, known backend quirks, device auth model
- `DESIGN.md` — visual design system not relevant here
- `backend-audit-prompt.md` — prior scale fixes that must not regress
- `LOGIC_ISSUES.md` and `OVERSEER_PLAN.md` — business rules around missions, shifts, operators

## Constraints
- No commits, no pushes.
- No changes to templates, HTMX, or frontend code beyond buildArtifacts.
- All CI changes must live under `.github/workflows/` (or agreed infra path).
- Do NOT create or modify `.env` content. `.env.example` may be updated if a new required env var is introduced.
- All env/secrets must be declared as GitHub Actions secrets, not checked in.
- Output must include: workflow YAML, deployment docs, and a checklist of what CI will prevent from shipping.

## Deliverables

## A. Assessment
1. Audit existing backend build paths:
   - Django ASGI/WSGI entry points
   - Static/Vite asset build and collectstatic behavior
   - Database migration workflow
2. Identify blockers to production deploy:
   - Missing env vars
   - Hardcoded URLs / DEBUG=True risk
   - Unbounded `.all()` views + no pagination risk
   - Missing SECRET_KEY and allowed hosts validation
3. Propose the simplest production runner for this stack:
   - Docker Compose local/dev
   - GitHub Actions CI for backend tests + lint + build
   - Optional: simple VPS deploy via SSH or Docker image push

## B. Pipeline Implementation

### B1. Tests & Lint Job
- Backend lint: `ruff` or `flake8` for Python
- Backend type check: optional `mypy --ignore-missing-imports`
- Backend unit tests: `/home/jay/Desktop/projects/venv/bin/python -m pytest -q` (respect existing 54/54 baseline)
- Frontend check: if `static/package.json` has a build script, verify `npm run build` and `npm run lint` succeed
- Cache steps to prevent workflow thrashing

### B2. Build Job
- Build Vite assets
- Run `python manage.py collectstatic --noinput`
- Verify `DEBUG=False` still boots the app
- Create a Docker image (or tarball artifact) for Django + static + media

### B3. Security & Env Check
- Scan for hardcoded secrets: regex for `ngrok`, `password =`, `token =`, `SECRET_KEY =`
- Verify `.env.example` matches `.env` keys used in settings
- Assert no `.env` file is committed in workflow on protected branches

### C. Deployment Documentation
Write a `DEPLOY.md` at project root with:
- Container runtime prerequisites (Docker / Docker Compose)
- Env var table with purpose + security note
- Database migration procedure before first run
- Static asset collection procedure
- Rollback procedure
- Log rotation / access notes for 50-org scale
- ngrok deprecation checklist (remove hardcoded tunnel URL)

## Validation Requirements
1. CI must not require network secrets to validate locally.
2. CI must report Python requirements mismatch with `requirements.txt`.
3. CI must validate settings layer for required `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, database URL, and DEBUG default.
4. For local dev, provide a `Makefile` target:
   - `make check` — lint + tests + secret scan
   - `make build` — build frontend + collectstatic + test run
   - `make docker-build` — build container image

## OUTPUT FORMAT
Return in this order:
1. DIFF SUMMARY — files to add/modify (no diffs, only paths + purpose)
2. CI YAML — inline complete content for `.github/workflows/backend.yml` and `frontend.yml` if needed
3. DEPLOY.md content — markdown block
4. Makefile content — if added
5. RISK ASSESSMENT — breaking changes to current dev loop
6. VALIDATION — how you verified each step

Remember: no commits. The assistant will review your output and decide when to commit.