"""
Custom JWT authentication that reads token from httpOnly cookie.
Falls back to Authorization header for device/API clients.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings


class CookieJWTAuthentication(JWTAuthentication):
    """Authenticate via JWT stored in httpOnly cookie or Authorization header."""

    def authenticate(self, request):
        # Try cookie first
        token = request.COOKIES.get('gt_access_token')
        if token:
            try:
                validated_token = self.get_validated_token(token)
                user = self.get_user(validated_token)
                return (user, validated_token)
            except Exception:
                pass

        # Fall back to Authorization header (for device API calls)
        return super().authenticate(request)
