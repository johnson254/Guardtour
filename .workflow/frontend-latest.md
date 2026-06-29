# Frontend Work Log
Last updated: 2026-06-29
Focus: bright glass morphism UI, higher-contrast panels, crimson/teal/amber/indigo/violet palette

## Workflow
- Verify template edits with `python3 manage.py check`.
- Keep pug/HTML/CSS/JS-only unless explicitly asked for backend work.
- Do not auto-restart the dev server.
- No CI/CD pipeline runs here; smoke/preview is manual.
- Demo deadline is 2026-06-29 08:00 EAT.

## Active constraints
- Avoid dark/non-glass panels; brighter, higher-contrast glass is preferred.
- Preserve existing backend contracts: `/api/login/`, `/api/register/`, `gt_user` in localStorage.
- Keep code organized: views live in dedicated modules (e.g. `api/views/page_views.py`) if changed.
- Review new UI changes for layout/overlap/color issues before calling them done.

## Known frontend blockers
- White background on routes/dashboard needs a targeted CSS fix.
- Pre-existing backend tests in `tests/test_scans.py` have 3 failures (F..F..F); they predate frontend work.
- Map route focus flow is only partially implemented; route selection and map focus need alignment.

## Completed/committed
- Login/register reskinned to tactical dark ops style.
- `base_app.html` restoration fixed the full-page fallback `TemplateDoesNotExist`.
