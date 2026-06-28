# TODO: Live checkpoint type + time/dwell remaining on Dispatch

- [x] Step 1: Add backend endpoint to compute per active ShiftAssignment the live status of the next checkpoint (type, time remaining, dwell remaining, present/absent) using ScanRecord timestamps.

- [x] Step 2: Add serializer/DTO (or inline response) for that endpoint.

- [ ] [Implemented] Step 3: Update `templates/dispatch.html` UI to render next objective detail (type, time remaining, dwell remaining, presence) and refresh via existing auto-refresh.
- [ ] Step 4: Quick sanity test: ensure mission cards render for routes with/without planned_time and with dwell_time.

