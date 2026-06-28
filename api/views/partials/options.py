"""Alert partials for htmx — dashboard alert polling."""
from rest_framework.decorators import api_view
from django.http import HttpResponse

from api.models import OperatorAlert


@api_view(['GET'])
def alerts_partial(request):
    """Return HTML fragment of pending alerts for htmx polling."""
    user = request.user
    alerts = OperatorAlert.objects.none()

    if user.is_superuser or hasattr(user, 'admin_profile'):
        alerts = OperatorAlert.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        org = user.dispatcher_profile.organization
        if org:
            alerts = OperatorAlert.objects.filter(organization=org)

    pending = alerts.filter(is_read=False).order_by('-created_at')[:5]
    rows = []
    for a in pending:
        rows.append(
            f'<div class="alert-item" style="border-left:3px solid var(--primary)">'
            f'<div class="alert-item-info">'
            f'<strong>{a.title or "Alert"}</strong> for <strong>{a.operator_name or "Unknown"}</strong>'
            f'</div>'
            f'<div class="alert-item-time">{a.created_at.strftime("%H:%M") if a.created_at else ""}</div>'
            f'</div>'
        )
    html = ''.join(rows) if rows else '<p style="color:var(--text-muted);text-align:center">No critical alerts.</p>'
    count = pending.count()
    return HttpResponse(
        f'{html}'
        f'<div hidden data-alert-count="{count}"></div>'
    )
