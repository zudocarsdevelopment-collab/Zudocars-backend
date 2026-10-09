from django.core import signing
from django.contrib.auth import get_user_model
from django.utils.crypto import constant_time_compare
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


class DashboardAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b'bearer':
            raise AuthenticationFailed('Invalid authorization header.')
        try:
            payload = signing.loads(parts[1].decode(), salt='zudo-dashboard', max_age=43200)
            user = get_user_model().objects.get(pk=payload['id'], is_active=True)
            if not constant_time_compare(payload['hash'], user.get_session_auth_hash()):
                raise AuthenticationFailed('Please sign in again.')
        except (signing.BadSignature, ValueError, TypeError, KeyError, UnicodeError, get_user_model().DoesNotExist):
            raise AuthenticationFailed('Your login expired. Please sign in again.')
        return user, None

    def authenticate_header(self, request):
        return 'Bearer'
