# Backend marker — work/backend

- Branch: work/backend
- Last commit: 832f12b
- Files touched:
  - api/org_permissions.py (new)
  - api/password.py (new)
  - api/services/mission.py (new)
  - api/throttles.py (new)
  - api/services/scan.py (refactored: ScanPipeline class)
  - api/consumers.py (password hash verify)
  - api/views/__init__.py (canonical imports)
  - api/views/core.py (removed duplicate _deactivate_assignments)
  - api/views/heartbeat.py (removed select_for_update, added throttle)
  - api/views/manage.py (select_related, org helper, password hashing)
  - api/views/scans.py (select_related, password hashing, throttle)
  - guardtour/settings.py (configurable channel layer)
  - guardtour/test_settings.py (throttle rates for tests)
  - tests/test_device_auth.py (fixed broken test)
  - tests/test_fixes.py (new: 34 tests for password, org, pipeline)
  - tests/test_mission.py (new: 13 tests for state machine)
  - tests/test_query_counts.py (new: 5 query regression tests)
  - tests/test_throttles.py (new: 6 rate limit tests)
- Summary: Security hardening (password hashing, rate limiting), query optimization (select_related on all ViewSets with regression tests), ScanPipeline extraction, mission state machine, dead code consolidation

## Verification
- Run: pytest -q
- Expected: 134 passed (up from 106), 0 failed
- Pre-existing test_register_unknown_operator_id fixed (auto-create behavior documented)