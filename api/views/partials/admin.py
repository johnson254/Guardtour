"""Admin partials for htmx — system stats grid."""
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone

from api.models import GuardSupervisor, Organization, Device, ScanRecord


@login_required
def admin_stats_partial(request):
    """Return HTML fragment of admin system stats for htmx."""
    user = request.user
    if not (user.is_superuser or hasattr(user, 'admin_profile')):
        return HttpResponse('<div class="card">Unauthorized</div>', status=403)

    today = timezone.now().date()
    total_users = GuardSupervisor.objects.count()
    total_orgs = Organization.objects.count()
    total_devices = Device.objects.count()
    online_devices = Device.objects.filter(is_online=True).count()
    scans_today = ScanRecord.objects.filter(timestamp__date=today).count()
    total_scans = ScanRecord.objects.count()

    html = (
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;text-align:center;">'
        f'<div class="card" style="padding:15px;"><h4>Users</h4><p style="font-size:1.8em;font-weight:bold;">{total_users}</p></div>'
        f'<div class="card" style="padding:15px;"><h4>Organizations</h4><p style="font-size:1.8em;font-weight:bold;">{total_orgs}</p></div>'
        f'<div class="card" style="padding:15px;"><h4>Devices</h4><p style="font-size:1.8em;font-weight:bold;">{total_devices}</p></div>'
        f'<div class="card" style="padding:15px;"><h4>Online Devices</h4><p style="font-size:1.8em;font-weight:bold;color:#4caf50;">{online_devices}</p></div>'
        f'<div class="card" style="padding:15px;"><h4>Scans Today</h4><p style="font-size:1.8em;font-weight:bold;">{scans_today}</p></div>'
        f'<div class="card" style="padding:15px;"><h4>Total Scans</h4><p style="font-size:1.8em;font-weight:bold;">{total_scans}</p></div>'
        '</div>'
    )
    return HttpResponse(html)
