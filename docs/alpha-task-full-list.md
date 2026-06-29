# Alpha Task List: GuardTour_Full Production Hardening

## Current State
- Branch `main`, commit `4e0f0c8`
- Frontend auth verified/normalized
- Constraint: guard login does NOT exist yet; guard record is a DB placeholder only
- Constraint: no automated pytest until user says so
- Constraint: Alpha must not push/commit

---

## Your Rules
- NO questions — work through blockers yourself
- NO pytest
- NO push/commit
- If verification is needed, build/run a quick standalone smoke, don’t run the test suite
- Work order: A1 → A2 → B1 → B2 → B3 → D1 → D2
- Guard pathway: do NOT invent guard login; leave guard profile as-is

---

## A1. DeviceSerializer Duplicate Meta
**File:** `api/serializers.py`
**Fix:** Merge duplicate `Meta`; mark TTS/read-only fields explicitly read-only

## A2. OperatorAlert FK Crash
**File:** `api/models.py`
**Fix:** Allow null operator; add `device_info` property without crashing

## B1. Global Loader 404
**File:** `templates/base_app.html`
**Fix:** Find the missing asset reference on `/dashboard/` and make it 200

## B2. Dashboard Countdown Sound
**File:** `static/src/pages/dashboard.js`
**Fix:** Make alert sound/vibrate skip gracefully if asset/path is missing

## B3. Role Badge Consistency
**File:** `templates/base_template.html`
**Fix:** Role badge must render cleanly for legacy role strings

## D1. Missing Serializer Definitions
**Files:** `api/serializers.py`, `api/views/scans.py`
**Fix:** Add `ScanSerializer` stubs if missing; ensure views import them

## D2. PostgreSQL Config Smoke
**Files:** `guardtour/settings.py`, `.env.example`
**Fix:** Ensure env-driven DB config is readable and connection test is documented/sketchable

---

## CI/CD Recommendation
Do NOT build pipeline yet. Build a local `scripts/smoke.sh` manually and run it after changes.
