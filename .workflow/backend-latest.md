# Backend marker — work/backend

- Branch: work/backend
- Last commit: a36a8e7
- Files touched:
  - api/models.py (scheduled_date field on Checkpoint)
  - api/migrations/0073_add_scheduled_date_to_checkpoint.py (new migration)
  - api/serializers.py (scheduled_date in CheckpointSerializer)
  - api/services/scan.py (get_mission_status filters by scheduled_date)
  - api/urls.py (schedule + scheduled-checkpoints + peer-audit endpoints)
  - api/views/scans.py (schedule_checkpoints, scheduled_checkpoints endpoints)
  - api/views/dispatch.py (my_mission returns scheduled checkpoints, peer_audit_report)
  - api/views/__init__.py (new endpoint exports)
  - api/consumers.py (WebSocket peer scan → ScanRecord creation)
- Summary: Scheduled checkpoints (future days per hour), peer scan WebSocket
  wiring, peer audit report, my_mission password hash fix

## Verification
- Run: pytest -q
- Expected: 135 passed, 0 failed

## What's Next (Vertical Slice: Map UI + Android App)
1. Build trail rendering in map-view.js (consumes my_mission API)
2. Wire progress pill in routes.js (completed/total/% from mission_status)
3. Android app consumes my_mission endpoint (shows current mission + checkpoints)
4. ETA/next checkpoint derived from mission_status.scheduled_date + planned_time
5. Frontend date picker for scheduling checkpoints (uses schedule_checkpoints endpoint)