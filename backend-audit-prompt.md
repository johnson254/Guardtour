# Backend Audit & Fix Prompt — Scalability & Logic (Slot 2 Only)

## Role
You are a scoped backend subagent. You do not own this repo.
Sequential workflow: this runs AFTER frontend Slot 1 is complete.

## MANDATORY FIRST STEP — Index the repo
Before changing anything, run this exact command from `/home/jay/Desktop/projects/GuardTour_Full`:

```bash
python3 -m pip install -q mcp-codebase-memory
mcp_codebase_memory_index_repository --repo-path /home/jay/Desktop/projects/GuardTour_Full --mode full --target-projects '["*"]'
```

If indexing fails, STOP and report `[BLOCKED]` with the error. Do not proceed without a fresh index.

## Baseline test (run and paste output)
```bash
/home/jay/Desktop/projects/venv/bin/python -m pytest -q
```

## Your deliverables (in this order)

### 1. Indexed assessment
After indexing, scan the codebase and report:

**A. Query efficiency audit**
- List every `Manager.objects.all()` or `Manager.objects.filter(...).all()` that lacks `.select_related(...)` or `.prefetch_related(...)` inside `api/views/core.py`, `api/views/partials/*`, and `api/serializers.py`.
- Flag every `.all()` inside a Python loop or list comprehension that could become N+1 at scale.

**B. Loop/instance creation audit**
- List every `get_or_create`, `update_or_create`, and `save()` call that lacks `transaction.atomic()` or unique=True on the lookup fields.
- Flag repeated `.save(update_fields=[...])` calls on the same model instance within one request/function.
- Flag any place where multiple model objects are created sequentially without rollback safety.

**C. Permission audit**
- List ViewSets or function views that return `Manager.objects.all()` without org-scoping.
- List views where role/permission logic is duplicated instead of centralized.

**D. Data integrity audit**
- Flag any ForeignKey or CharField that should be `unique=True` but isn’t (e.g. `device_id`).
- Flag any `clean()` or validation that only considers a subset of states (`is_active=True` misses `cancelled`, `handover`, etc.).

**E. Scalability audit**
- Flag unbounded querysets in list/retrieve views (no pagination limit visible).
- Flag any unauthenticated or unthrottled endpoints (`AllowAny` + write paths).

For each finding, give:
- File path + line range
- Risk level: [CRITICAL], [HIGH], [MEDIUM], [LOW]
- One-line plain explanation
- Suggested fix direction (not necessarily exact code)

### 2. Prioritized fix plan
Rank every finding as:
- **Fix now** — blocks demo or causes data loss/crashes
- **Fix after demo** — scalability / hygiene
- **Ignore** — not worth the risk

### 3. Implemented fixes
Only after presenting the assessment and getting direction, fix the items tagged **Fix now**.
For each fix:
- One-line change description
- Paste the diff snippet
- Re-run `pytest -q` and paste output

## Scope guard (STRICT)
- You MAY touch: `api/`, `guardtour/settings.py` (only MIDDLEWARE/INSTALLED_APPS/ROOT_URLCONF), `guardtour/urls.py`, tests/
- You MAY NOT touch: `templates/`, `static/`, `frontend/`, any `.env` files
- You MAY NOT add new dependencies without flagging [BLOCKED] + reason
- You MAY NOT change URL names unless flagged as bug
- You MAY NOT delete migrations

## TDD discipline
For every fix that changes runtime behavior:
1. Write or update the test to assert the fixed behavior
2. Run it — see it fail (or pass if the test already existed)
3. Apply the minimal fix
4. Re-run — confirm pass
5. Do NOT write speculative tests for items marked “Ignore”

## Validation (paste full output for each)
```bash
/home/jay/Desktop/projects/venv/bin/python -m pytest -q
/home/jay/Desktop/projects/venv/bin/python manage.py check --deploy
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dispatch/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/routes/
git diff --stat
git status --short
```

## Required Review Packet (paste verbatim)
1. Indexed assessment (A–E above)
2. Prioritized fix plan table
3. Implementation log (file + diff + test result per fix)
4. Validation output (verbatim)
5. Remaining risks / post-demo backlog
6. Branch status
7. “No unapproved changes.”

## Strict refusal rules
- Do NOT push, merge, or close the branch
- Do NOT change `guardtour/settings.py` database, security, CORS, or INSTALLED_APPS unless flagged [CRITICAL]
- Do NOT delete migrations or models without explicit approval
- Do NOT touch frontend templates or static assets
- Do NOT run project-wide search-replace
