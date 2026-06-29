# Backend marker — work/backend

- Branch: work/backend
- Last commit: c6908db
- Files touched:
  - api/models.py (new composite indexes on ScanRecord + ShiftAssignment)
  - api/migrations/0073_add_scan_shift_indexes.py (new migration)
  - api/urls.py (v1 namespace + legacy unversioned for internal frontend)
  - api/services/scan.py (split: 934 → 454 lines, imports from scan_queries)
  - api/services/scan_queries.py (new: standalone query/mutation functions)
  - api/scan_service.py (DELETED)
  - tests/test_scan_service.py (imports from canonical location)
  - tests/test_zone_verification.py (imports from canonical location)
  - guardtour/urls.py (namespace routing for v1)
- Summary: Phase 2 complete — indexes for hot queries, API v1 contract,
  scan.py split for maintainability, dead code removed

## Verification
- Run: pytest -q
- Expected: 135 passed, 0 failed

## What's Next (Vertical Slice: Mission Execution + Map UI)
1. Fix 3 failing scan tests (test data setup, not logic)
2. Build trail rendering in map-view.js (consumes my_mission API)
3. Wire progress pill in routes.js (shows real completed/total/%)
4. Android app consumes my_mission endpoint (closes the loop)
5. ETA/next checkpoint derived from mission_status data