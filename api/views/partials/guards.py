"""Guard partials for htmx — personnel grid and edit form."""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from api.models import GuardSupervisor, Organization


def _resolve_guard_queryset(user):
    """Return the queryset of GuardSupervisor objects visible to this user."""
    if user.is_superuser or hasattr(user, 'admin_profile'):
        return GuardSupervisor.objects.all()
    elif hasattr(user, 'dispatcher_profile'):
        dispatcher = user.dispatcher_profile
        if not dispatcher.organization:
            default_org = Organization.objects.first()
            if default_org:
                dispatcher.organization = default_org
                dispatcher.save(update_fields=['organization'])
        if dispatcher.organization:
            return GuardSupervisor.objects.filter(organization=dispatcher.organization)
    elif hasattr(user, 'guardsupervisor') and user.guardsupervisor.organization:
        return GuardSupervisor.objects.filter(organization=user.guardsupervisor.organization)
    return GuardSupervisor.objects.none()


def _guard_card_html(g):
    """Render a single guard card as HTML."""
    status_color = 'rgba(0, 230, 118, 0.1)' if g.is_on_shift else 'rgba(255,255,255,0.05)'
    status_text_color = 'var(--accent-green)' if g.is_on_shift else 'var(--text-muted)'
    status_label = 'On Mission' if g.is_on_shift else 'Off Duty'
    name = f"{g.first_name or ''} {g.last_name or ''}".strip() or 'Unknown'
    callsign = g.callsign or 'NOT ASSIGNED'
    shift = g.shift or 'Day'
    return (
        f'<div class="person-card">'
        f'<span class="status-pill" style="background:{status_color};color:{status_text_color}">'
        f'{status_label}</span>'
        f'<div style="font-weight:800;font-size:1rem;color:white;margin-bottom:5px;">{name}</div>'
        f'<div style="font-size:0.7rem;color:var(--primary-light);margin-bottom:15px;">ID: {callsign}</div>'
        f'<div class="label-mini">Deployment Pattern</div>'
        f'<div style="font-size:0.8rem;color:var(--text-muted);">{shift} Shift</div>'
        f'<div style="display:flex;gap:10px;margin-top:20px;">'
        f'<button class="action-btn" style="flex:1;font-size:0.7rem;padding:8px;" '
        f'  hx-get="/api/guard-form-partial/{g.id}/" hx-target="#guardFormFields" '
        f'  hx-swap="innerHTML"'
        f'  hx-on::after-request="document.getElementById(\'guardForm\').style.display=\'block\';'
        f'document.getElementById(\'guardFormTitle\').innerText=\'Edit Guard\'">'
        f'Edit Profile</button>'
        f'<button class="action-btn btn-secondary" style="padding:8px 12px;" '
        f'  hx-delete="/api/profiles/{g.id}/" hx-confirm="Delete this guard?" '
        f'  hx-on::after-request="if(event.detail.successful) htmx.ajax(\'GET\',\'/api/guards-partial/\','
        f'  {target:\'#guardsList\',swap:\'innerHTML\'})">'
        f'<i class="fas fa-trash"></i></button>'
        f'</div></div>'
    )


def _guard_form_fields_html(g):
    """Render pre-filled form fields for editing."""
    return {
        'first_name': g.first_name or '',
        'last_name': g.last_name or '',
        'callsign': g.callsign or '',
        'shift': g.shift or 'Day',
    }


@api_view(['GET'])
@login_required
def guards_partial(request):
    """Return HTML fragment of personnel grid for htmx."""
    queryset = _resolve_guard_queryset(request.user)
    guards = queryset.order_by('-is_on_shift', 'last_name', 'first_name')
    cards = ''.join(_guard_card_html(g) for g in guards)
    return HttpResponse(cards)


@api_view(['GET'])
@login_required
def guard_form_partial(request, pk):
    """Return HTML fragment of edit form pre-filled for a guard, or empty for new."""
    if pk == 'new':
        data = {'first_name': '', 'last_name': '', 'callsign': '', 'shift': 'Day'}
        guard_id = ''
    else:
        try:
            g = GuardSupervisor.objects.get(pk=int(pk))
        except (GuardSupervisor.DoesNotExist, ValueError):
            return HttpResponse('<p style="color:var(--danger)">Guard not found</p>')
        data = _guard_form_fields_html(g)
        guard_id = g.id

    return HttpResponse(
        f'<input type="hidden" name="guardId" value="{guard_id}">'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;">'
        f'<div><label>First Name</label>'
        f'<input type="text" name="first_name" value="{data["first_name"]}" required></div>'
        f'<div><label>Last Name</label>'
        f'<input type="text" name="last_name" value="{data["last_name"]}"></div>'
        f'</div>'
        f'<input type="text" name="callsign" value="{data["callsign"]}" placeholder="Operator ID (e.g. TCN-01)">'
        f'<select name="shift">'
        f'<option {"selected" if data["shift"]=="Day" else ""}>Day</option>'
        f'<option {"selected" if data["shift"]=="Night" else ""}>Night</option>'
        f'<option {"selected" if data["shift"]=="Flex" else ""}>Flex</option>'
        f'</select>'
    )
