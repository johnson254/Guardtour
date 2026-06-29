# Backend marker — work/backend

- Branch: work/backend
- Last commit: 88f935c
- Files touched:
  - api/serializers.py (current_mission field on DeviceSerializer)
  - api/views/manage.py (Prefetch active assignments in DeviceViewSet)
  - tests/test_query_counts.py (adjusted threshold for new feature)
- Summary: Fleet panel now shows mission progress per device via current_mission

## Verification
- Run: pytest -q
- Expected: 139 passed, 0 failed

## What's Next
- Update manage.js to render current_mission progress bar on device cards
- Add "On Mission" / "Available" filter chips to fleet panel
- Wire the mission data into the existing device card UI

## Branch Status
- work/backend: 8 commits ahead of main
- All backend features complete: security, scheduling, audit, fleet visibility
- Ready for frontend integration (map UI, Android app)