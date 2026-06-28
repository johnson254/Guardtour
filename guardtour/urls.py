from django.contrib import admin
from django.http import HttpResponsePermanentRedirect
from django.urls import path, include
from api import views as api_views

handler404 = 'api.views.custom_404'
handler500 = 'api.views.custom_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),

    # Authentication Page Views
    path('', api_views.login_page, name='login'),
    path('login/', api_views.login_page, name='login_page'),
    path('register/', api_views.register_page, name='register'),

    # Operational Hub Page Views
    path('dashboard/', api_views.dashboard_page, name='operations_hub'),
    path('dispatch/', api_views.dispatch_page, name='dispatch'),
    path('incidents/', api_views.incidents_page, name='incidents'),
    path('manage/', api_views.manage_page, name='manage'),
    path('analytics/', api_views.reports_page, name='analytics'),
    path('map-view/', api_views.map_view_page, name='intelligence_map'),
    path('control/', api_views.admin_panel_page, name='secops_control'),
    path('routes/', api_views.routes_page, name='routes'),
    path('logout/', api_views.logout_view, name='logout'),
    path('intelligence_map/', lambda r: HttpResponsePermanentRedirect('/map-view/')),
]