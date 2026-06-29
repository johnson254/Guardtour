from rest_framework.throttling import SimpleRateThrottle


class DeviceRateThrottle(SimpleRateThrottle):
    """Rate throttle keyed by device_id for device-authenticated endpoints.

    Uses the scopes defined in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']:
    - device_heartbeat: 30/min
    - device_scan: 60/min
    """
    scope = 'device'

    def get_cache_key(self, request, view):
        device_id = (
            request.data.get('device_id') or
            request.GET.get('device_id') or
            self.get_ident(request)
        )
        return self.cache_format % {
            'scope': self.scope,
            'ident': device_id
        }


class DeviceHeartbeatThrottle(DeviceRateThrottle):
    scope = 'device_heartbeat'


class DeviceScanThrottle(DeviceRateThrottle):
    scope = 'device_scan'
