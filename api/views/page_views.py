from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


@login_required
def dashboard_page(request):
    from api.views.reports import organization_stats
    stats_response = organization_stats(request)
    context = stats_response.data if hasattr(stats_response, 'data') else {}
    return render(request, 'dashboard.html', context or {})


@login_required
def map_view_page(request):
    return render(request, 'map_view.html')


@login_required
def routes_page(request):
    return render(request, 'routes.html')


@login_required
def mission_builder_page(request):
    return render(request, 'mission_builder.html')


@login_required
def peer_rules_page(request):
    return render(request, 'peer_rules.html')


@login_required
def dispatch_page(request):
    return render(request, 'dispatch.html')


@login_required
def incidents_page(request):
    return render(request, 'incidents.html')


@login_required
def guards_page(request):
    return render(request, 'guards.html')


@login_required
def manage_page(request):
    return render(request, 'manage.html')


@login_required
def reports_page(request):
    return render(request, 'reports.html')


@login_required
def admin_panel_page(request):
    return render(request, 'admin_panel.html')


def login_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'login.html')


def register_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'register.html')
