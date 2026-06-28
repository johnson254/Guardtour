========================================
Guard Tour Full Project
========================================
1. Extract this folder
2. cd into GuardTour_Full
3. pip install -r requirements.txt
4. python manage.py migrate
5. python manage.py createsuperuser (optional)
6. python manage.py runserver

Access:
- Login page: http://127.0.0.1:8000/
- Dashboard: /dashboard/
- Routes: /routes/
- Dispatch: /dispatch/
- Guards: /guards/
- Reports: /reports/
- Admin panel: /admin_panel/

Default demo accounts (auto-created on first run):
- admin / admin123
- manager / manager123
- guard / guard123

All features from the specification are included:
- Multi-user roles (admin/manager/guard) with separate pages
- Route builder with NFC checkpoints, geo coordinates, planned time, tolerance
- Dispatch with assignment of guards to routes
- Guard management
- Reports with CSV export
- Admin panel to manage users and organizations
- Real-time device status (heartbeat endpoints)
- All data stored in SQLite database
