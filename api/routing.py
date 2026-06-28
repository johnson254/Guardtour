from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/guard/(?P<device_id>[^/]+)/$', consumers.GuardConsumer.as_asgi()),
    re_path(r'ws/dispatcher/$', consumers.DispatcherConsumer.as_asgi()),
]
