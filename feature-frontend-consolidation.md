# Feature Prompt — Frontend Consolidation + Glass Design System (Frontend Slot 1 Only)

## Role
You are a scoped frontend subagent. You do not own this repo.
This is a single commit: consolidate templates, extract shared CSS, unify nav, refactor manage page, and bring every page to at least 70% visual/functional parity with the dispatch duty-cycle panel.

**Slot 1 only.** You may touch:
- `templates/` (all `.html` files)
- `static/` (CSS, JS, assets)

**You may NOT touch:**
- `api/` (any Python file)
- `guardtour/` (settings, urls)
- Android app (`GuardTourNFC/`)
- `.env`, `requirements.txt`, migrations
- Git commands, server processes, pytest

**Failure mode to avoid:** breaking any page so badly it 500s or returns blank. Every page must render HTTP 200 with content visible.

---

## Phase 0 — Index first
Run this before editing anything:
```bash
find templates -type f -name "*.html" | sort
find static -type f \( -name "*.css" -o -name "*.js" \) | sort
grep -rn "id=\"navMenu\"\|id=\"nav-links\"" templates/ static/
grep -rn "htmx\|hx-get\|hx-post\|hx-swap" templates/ static/ | head -40
grep -rn "base.html\|base_app.html\|base_template.html" templates/*.html
```

Record the output. You will use it to verify nothing broke.

---

## Phase 1 — Nav unification (blocking everything else)
**Problem:** Nav contract is split. `base_app.html` uses `id="navMenu"`. `base_template.html` uses `id="nav-links"`. `dispatch.html` is the only page that works because it has its own nav JS. All other pages are broken or partial.

**Actions:**
1. Read `templates/base_template.html` nav block and its inline `<script>` at the bottom.
2. Read `templates/base_app.html` nav block.
3. Read `templates/base.html` nav block (if any).
4. Choose **one** canonical ID: use `id="navMenu"` everywhere (matching dispatch).
5. In `base_template.html`:
   - Update the `<nav>` container to use `id="navMenu"`.
   - Update the nav JS to read `document.getElementById('navMenu')`.
   - Ensure nav links are populated from a Django context variable `nav_links` (list of `{label, url, icon, active}`).
6. Remove all competing nav JS from `base_app.html` and `base.html`.
7. Ensure `dispatch.html` nav continues to work — it already uses `navMenu`, so this should be a no-op once the base is fixed.

**Validation:** grep `id="navMenu"` across all templates; exactly one definition per page, no `id="nav-links"` remains.

---

## Phase 2 — Kill base.html
**Actions:**
1. Confirm zero pages `{% extends "base.html" %}`.
2. Delete `templates/base.html`.
3. Delete any inline CSS or JS that only existed in `base.html`.

**Validation:** `find templates -name "base.html"` returns nothing.

---

## Phase 3 — HTMX unconditional load
**Problem:** If htmx is loaded only when `DEBUG=True`, `hx-get`/`hx-post` silently fail in production.

**Actions:**
1. Read `templates/base_template.html` `<head>` block.
2. Find the htmx script tag. If it is inside `{% if debug %}` or any conditional, move it outside so it always loads.
3. Preferred CDN: `https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js`.
4. Add `htmx.config.globalViewTransitions = true` if supported.
5. Ensure `base_template.html` is the single source of htmx loading — no page loads its own copy.

**Validation:** View source of any page, confirm htmx script is present in `<head>` with no conditional wrapper.

---

## Phase 4 — CSS extraction: duty-cycle design system
**Source of truth:** `templates/dispatch.html` inline `<style>` block contains the glass design system. Extract it.

**Actions:**
1. Create `static/css/duty-cycle.css`.
2. Copy these class families from `dispatch.html` `<style>` into the new file, in this order:
   - `.dc-shell` (layout grid)
   - `.dc-panel`, `.dc-panel-head`, `.dc-panel-title`
   - `.dc-card` (glass card)
   - `.dc-ls-*` (left sidebar: stats, tabs, cards, bp grid)
   - `.dc-bp-*` (blueprint cards)
   - `.dc-pv-*` (preview/summary)
   - `.dc-guard-*`, `.dc-shift-*`, `.dc-toggle`, `.dc-fi`
   - `.dc-route-info`, `.dc-avail-*`, `.dc-redeploy-*`
   - `.dc-deploy-btn`, `.dc-command`, `.dc-cmd-*`
   - Color tokens: `.shift-day`, `.shift-night`, `.shift-flex`, `.status-scheduled`, `.status-active`
3. In `base_template.html` `<head>`, add `<link rel="stylesheet" href="{% static 'css/duty-cycle.css' %}">`.
4. In `dispatch.html`, delete the inline `<style>` block entirely. Replace with `<link>` (already in base) plus a tiny `<style>` block (<100 lines) for page-specific overrides only.
5. In `map_view.html`, replace its 600-line bespoke sidebar CSS with `.dc-shell` / `.dc-panel` classes. Keep Leaflet-specific overrides only.
6. In `manage.html`, replace old `.mg-*` card styles with `.dc-panel` / `.dc-card` glass system.

**Validation:**
- `dispatch.html` renders and looks identical (visual spot-check against original).
- `map_view.html` sidebar uses `.tm-sidebar` with `.dc-panel` children.
- `manage.html` cards use `.dc-panel` / `.dc-card`.
- No template contains >150 lines of inline `<style>`.

---

## Phase 5 — Manage page rewrite
**Problem:** Dead code, old tab system, non-glass cards, unused CSS classes.

**Actions:**
1. Read `templates/manage.html` fully.
2. Identify dead code: CSS classes with no matching HTML, JS functions never called, panels that are `display:none` with no toggle.
3. Remove dead CSS and dead JS. If a panel is truly dead (no backend endpoint, no nav link), delete the entire panel HTML+CSS+JS.
4. Rewrite remaining panels to use `.dc-shell` where appropriate and `.dc-panel` / `.dc-card` everywhere.
5. Ensure tab switching uses HTMX or vanilla JS that actually works. No orphaned tab buttons.
6. Typography: same as dispatch — compact labels, uppercase micro-headers, glass cards, no top borders.

**Validation:** Open manage page. Every visible panel renders. No console errors. Tab switches work.

---

## Phase 6 — State-aware UI hooks (future-proofing)
**Actions:**
1. In `dispatch.html`, inside the duty-cycle panel where device state is shown, add:
   ```html
   <div class="dc-panel" data-device-state="{{ device_state|default:'unknown' }}">
       <div class="dc-panel-head">
           <span class="dc-panel-title">Device State</span>
       </div>
       <div class="dc-panel-body" id="dcDeviceState">
           <!-- HTMX will populate this when backend sends state data -->
           <div class="dc-ls-empty">Loading state…</div>
       </div>
   </div>
   ```
2. In `map_view.html` sidebar, add `data-zone-event` placeholders on the map panel.
3. These are inert placeholders. Backend will wire `hx-get` to them later. They must not break the page now.

**Validation:** Pages render with placeholder text visible. No JS errors.

---

## Phase 7 — Cross-page glass consistency
Apply these rules to every remaining page (`dashboard.html`, `guards.html`, `routes.html`, `reports.html`, `incidents.html`, `admin_panel.html`, `login.html`, `register.html`):

1. All cards/pannels must use `.dc-panel` / `.dc-card` classes.
2. Backgrounds must be glass gradients: `rgba(22,22,34,0.82)` to `rgba(16,16,26,0.92)`.
3. No solid `background: #fff` or `background: #000` blocks.
4. Border radius minimum `14px`, preferred `18px`–`24px`.
5. No top borders (`border-top`, `border-top-color`, `outline-top`).
6. Text hierarchy: white headlines, `rgba(255,255,255,0.7)` body, `rgba(255,255,255,0.35)` labels.
7. Interactive elements: glass hover states, no flat button fills unless they are primary actions.

**Rebuttal:** If a page (e.g., `login.html`) is intentionally a full-screen auth form and doesn't need glass cards, document it as a known exception in a comment. Don't force glass where it breaks usability (e.g., low-contrast text on transparent backgrounds for forms).

**Validation:** View source of every page. No raw `#fff`/`#000` backgrounds on cards. All interactive containers have `backdrop-filter: blur(...)` or glass gradient.

---

## Test / validation gate
Before you report done, run these checks and include the output in your report:

```bash
# 1. All templates exist and have content > 0 bytes
find templates -name "*.html" -size +0c | sort

# 2. No page extends base.html
grep -rn "extends base.html" templates/

# 3. Nav id is unified
grep -rn 'id="navMenu"' templates/ | head
grep -rn 'id="nav-links"' templates/ || echo "clean"

# 4. HTMX is unconditional in base_template
grep -A2 -B2 "htmx" templates/base_template.html

# 5. dispatch.html has no inline <style> block
grep -c "<style>" templates/dispatch.html || echo "0"

# 6. manage.html has no dead mg-duty-* if replaced
grep -c "mg-duty-grid\|mg-duty-card" templates/manage.html || echo "0"

# 7. All pages are valid HTML-ish (no unclosed tags at first 5 lines)
head -3 templates/*.html
```

**Pass criteria:**
- Check 1: all 12 pages listed
- Check 2: empty output
- Check 3: `navMenu` present, `nav-links` absent
- Check 4: htmx line present without `{% if`
- Check 5: `0` inline styles in dispatch
- Check 6: `0` dead duty classes
- Check 7: all pages start with `{% extends base_template %}` or `<!DOCTYPE` on line 1

**Do NOT run pytest.** Django/Python tests are backend work. This is frontend only.

---

## Reporting protocol
1. After Phase 0, report: "Indexed. Found N templates, M CSS files. Issues: [list]."
2. After Phase 1-3, report: "Nav unified. base.html deleted. HTMX unconditional."
3. After Phase 4-5, report: "CSS extracted to duty-cycle.css. Manage rewritten. Dispatch inline styles removed. Map view uses `.dc-shell`."
4. After Phase 6-7, report: "State hooks added. All pages glass-ified. Validation: [paste gate output]."
5. If any page breaks during refactor, stop, report the broken page and exact error, and await instructions before continuing.

**Do not self-fix blocked items.** Report first.

---

## Design reference (from dispatch.html duty cycle)
- No top borders on any panel.
- Glass morphism only: `background: linear-gradient(155deg, rgba(18,18,30,0.75) 0%, rgba(10,10,20,0.9) 60%, rgba(14,14,24,0.82) 100%); backdrop-filter: blur(20px);`
- Rounded corners: `border-radius: 16px`–`24px`.
- Micro-typography: uppercase labels `letter-spacing: 0.6px`, `font-size: 0.62rem`, `color: rgba(255,255,255,0.35)`.
- Interactive: hover lifts, subtle borders `rgba(255,255,255,0.06)`, primary accent `#d32f2f` / `var(--primary)`.
- Dense but not cramped: gap `8px`–`12px`, padding `10px`–`14px`.

Make it world-class. Every pixel matters.
