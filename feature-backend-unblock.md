# Backend Unblock Slot

## Scope
Fix only the 3 hard runtime blockers that prevent `python manage.py runserver` from starting. Do not refactor, clean, or touch anything outside these paths.

## Blocker 1 — guardtour/urls.py custom error handlers
File: `guardtour/urls.py`
Issue:
  handler404 = 'api.views.core.custom_404'
  handler500 = 'api.views.core.custom_500'
`custom_404` and `custom_500` are no longer in `api/views/core.py`. They now live in `api/views/__init__.py` as `api.views.custom_404` and `api.views.custom_500`.
Change only the dotted paths; leave all other URL patterns untouched.

## Blocker 2 — api/services/scan.py syntax error
File: `api/services/scan.py`
Issue: line ~195 uses `||` instead of Python's `or`.
Change ONLY that operator. Do not reformat, rename vars, or extract functions.

## Blocker 3 — dotenv import will crash after requirements install
File: `guardtour/settings.py`
Issue: `from dotenv import load_dotenv` is present but `python-dotenv` is not installed.
Two acceptable fixes; pick one:
  A) Add `python-dotenv` to `requirements.txt`
  B) Remove the `dotenv` import and the `load_dotenv()` call from settings and keep using a plain SECRET_KEY default. For deployment, add an env-key check manually later.
Do not change anything else in settings.py.

## Hard constraints
- Touching only:
  - `guardtour/urls.py`
  - `api/services/scan.py`
  - `guardtour/settings.py`
  - `requirements.txt` only if choosing fix A
- Do not edit `api/views/core.py`, templates, frontend, or other services.
- Do not run migrations or modify models.

## Verification
After your edits run:
  python manage.py check
Expected outcome:
  System check identified no issues (or only harmless warnings).

## Deliverable
- Commit message: fix(backend): unblock dev server startup (handlers, scan syntax, settings import)
- Report the exact diff lines you changed and the output of `python manage.py check`.
