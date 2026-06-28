from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

class JwtTokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle JWT token from cookie for server-rendered pages (runs before Auth middleware)
        token = request.COOKIES.get('gt_access_token') or request.session.get('access_token')
        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                try:
                    user = User.objects.get(id=user_id)
                    # Set user directly on request so AuthMiddleware can use it
                    setattr(request, 'user', user)
                except User.DoesNotExist:
                    pass
                request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'
            except (InvalidToken, TokenError):
                pass
        
        return self.get_response(request)
