# Backend marker — work/backend

- Branch: work/backend
- Last commit: 2637656
- Files touched:
  - api/services/scan.py (wired mission state machine, removed dual-write)
  - api/services/mission.py (documented complete_mission bypass rationale)
  - api/scan_service.py (DELETED — dead backward-compat shim)
  - api/services/fallback.py (DELETED — apply_sensor_fallback never called)
  - guardtour/settings.py (pagination + CORS gate)
  - tests/test_scan_service.py (imports from canonical location)
  - tests/test_zone_verification.py (imports from canonical location)
- Summary: Phase 1 cleanup — wired mission state machine into scan pipeline,
  removed 2 dead code files, added pagination (50/page), gated CORS behind DEBUG

## Verification
- Run: pytest -q
- Expected: 135 passed, 0 failed

## What's Next (Phase 2)
- Database indexes on hot query paths (ScanRecord device+route+timestamp, ShiftAssignment device+is_active)
- API versioning (/api/v1/) before Android app ships
- GuardSupervisor migration squash (73 migrations → ~5 logical chunks)
- Split scan.py (934 lines) into pipeline.py + queries.py