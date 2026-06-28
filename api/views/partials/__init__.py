"""
HTML partial views for htmx endpoints.
Each view returns an HttpResponse containing HTML fragments.
"""
from .guards import guards_partial, guard_form_partial
from .reports import scans_table_partial, reports_guards_options_partial, reports_routes_options_partial
from .admin import admin_stats_partial
from .incidents import incidents_partial, incidents_guards_options_partial
from .options import alerts_partial
from .routes import routes_list_partial, route_editor_partial
from .dispatch import blueprints_partial, missions_partial
from .manage import devices_list_partial, checkpoints_list_partial

__all__ = [
    'guards_partial', 'guard_form_partial',
    'scans_table_partial', 'reports_guards_options_partial', 'reports_routes_options_partial',
    'admin_stats_partial',
    'incidents_partial', 'incidents_guards_options_partial',
    'alerts_partial',
    'routes_list_partial', 'route_editor_partial',
    'blueprints_partial', 'missions_partial',
    'devices_list_partial', 'checkpoints_list_partial',
]
