# Frontend Audit Prompt — Templates, HTMX, JS, CSS (Slot 1 Only)

## Role
You are a scoped frontend subagent. You do not own this repo.
Sequential workflow: this runs BEFORE any backend work.

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

**A. Template inheritance audit**
- List every template that extends `base.html`, `base_template.html`, `bare_base.html`, or any other parent.
- Flag any template that does NOT extend a shared parent.
- Flag duplicate `{% load static %}`, `{% load vite %}`, `{% load htmx_base %}` blocks that could be moved to the parent.
- Flag any `{% block %}` that is declared in a child but never rendered by the parent.

**B. HTMX loading audit**
- Find every `<script src="...htmx...">` reference.
- Flag any conditional loading (`{% if debug %}`, `{% if not debug %}`, env-gated) that would break HTMX in production.
- List every `hx-get`, `hx-post`, `hx-trigger`, `hx-target`, `hx-swap` attribute in templates and confirm the target endpoint exists in `guardtour/urls.py` or `api/urls.py`.

**C. Inline CSS/JS audit**
- List every `<style>` block in templates (count lines).
- List every inline `onclick`, `ondblclick`, `onchange`, `onsubmit` in templates.
- List every `<script>` block that is not `type="module"` and not loaded via `{% vite_asset %}`.
- Flag any `<script>` that accesses `document.getElementById`, `document.querySelector`, or `localStorage` outside of a module or `DOMContentLoaded` guard.

**D. ID/contract consistency audit**
- List every `id="..."` in `base.html`, `base_template.html`, `bare_base.html`.
- List every `id="..."` in child templates and components.
- Flag IDs that exist in the parent JS but are missing from the HTML, or vice versa.
- Flag IDs that differ between `base.html` and `base_template.html` for the same element (e.g. `navMenu` vs `nav-links`).

**E. localStorage/auth audit**
- List every `localStorage.getItem`, `localStorage.setItem`, `localStorage.removeItem`, `localStorage.clear` in templates and static JS.
- Flag any page that reads `gt_user` without checking for `token` existence.
- Flag any page that writes to `gt_user` without validating required fields (`role`, `organization_id`, `organization_name`).
- Flag any missing `storage` event listener for cross-tab logout sync.

**F. Nav/role/org rendering audit**
- List how each page renders role, org name, and logout button.
- Flag any page that hardcodes role names, org names, or nav links instead of reading from `gt_user` / backend.
- Flag any page where the logout button does not clear `gt_user`.

**G. Vite/manifest safety audit**
- List every `{% vite_asset %}` call.
- Flag any fallback or `onerror` handling for missing manifest in production.
- Flag any page where `{% vite_asset %}` is called but the referenced JS module does not exist in `frontend/src/`.

**H. Accessibility & i18n audit**
- List every `<button type="button">` without `type` attribute.
- List every interactive element without `aria-label` or visible label.
- Flag any hardcoded English strings in templates that should be translatable.

**I. Orphan/dead file audit**
- List any template, partial, or component file that is not referenced by any parent or URL resolver.
- List any `.tsx`, `.ts`, `.js`, `.css` file in `templates/components/`, `static/`, or `frontend/src/` that is not imported anywhere.

For each finding, give:
- File path + line range
- Risk level: [CRITICAL], [HIGH], [MEDIUM], [LOW]
- One-line plain explanation
- Suggested fix direction (not necessarily exact code)

### 2. Prioritized fix plan
Rank every finding as:
- **Fix now** — blocks demo or causes runtime breakage for 50 dispatchers
- **Fix after demo** — scalability / hygiene
- **Ignore** — not worth the risk or already acceptable

### 3. Implemented fixes
Only after presenting the assessment and getting direction, fix the items tagged **Fix now**.
For each fix:
- One-line change description
- Paste the diff snippet
- Run validation and paste output

## Scope guard (STRICT)
- You MAY touch: `templates/`, `static/`, `frontend/src/` (if it exists), `templates/components/`
- You MAY NOT touch: `api/`, `guardtour/settings.py`, `guardtour/urls.py`, `.env`, `requirements*.txt`, `Pipfile`, `pyproject.toml`
- You MAY NOT add new npm packages without flagging [BLOCKED] + reason
- You MAY NOT rename URL names unless flagged as bug
- You MAY NOT delete migrations or Python model files
- You MAY NOT change backend views, serializers, or middleware

## TDD discipline
For every fix that changes runtime behavior:
1. Describe the expected behavior change in plain language
2. Apply the minimal fix
3. Validate with curl or browser observation (since frontend tests are limited):
   - `/home/jay/Desktop/projects/venv/bin/python manage.py runserver 8080`
   - `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/<page>/`
4. Confirm the page loads and key DOM elements are present
5. Do NOT write speculative fixes for items marked "Ignore"

## Validation (paste full output for each)
```bash
/home/jay/Desktop/projects/venv/bin/python -m pytest -q
/home/jay/Desktop/projects/venv/bin/python manage.py check --deploy
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/login/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dashboard/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/dispatch/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/routes/
git diff --stat
git status --short
```

## Required Review Packet (paste verbatim)
1. Indexed assessment (A–I above)
2. Prioritized fix plan table
3. Implementation log (file + diff + validation per fix)
4. Validation output (verbatim)
5. Remaining risks / post-demo backlog
6. Branch status
7. "No unapproved changes."

## Strict refusal rules
- Do NOT push, merge, or close the branch
- Do NOT change backend Python files
- Do NOT change `guardtour/settings.py` unless flagged [CRITICAL]
- Do NOT delete migrations or models
- Do NOT run project-wide search-replace on templates without explicit approval per file
- Do NOT start the dev server unless validation requires it; if you do, stop it before reporting
- Do NOT attempt to fix items tagged "Ignore"
- Do NOT self-fix blocked items — report them as [BLOCKED] and wait for direction
