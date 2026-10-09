from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from zudobackend import settings_local

@override_settings(
    CSRF_COOKIE_DOMAIN=settings_local.CSRF_COOKIE_DOMAIN,
    SESSION_COOKIE_DOMAIN=settings_local.SESSION_COOKIE_DOMAIN,
    CSRF_COOKIE_SECURE=settings_local.CSRF_COOKIE_SECURE,
    SESSION_COOKIE_SECURE=settings_local.SESSION_COOKIE_SECURE,
    CSRF_COOKIE_SAMESITE=settings_local.CSRF_COOKIE_SAMESITE,
    SESSION_COOKIE_SAMESITE=settings_local.SESSION_COOKIE_SAMESITE,
    CSRF_TRUSTED_ORIGINS=settings_local.CSRF_TRUSTED_ORIGINS,
)
class LocalAdminLoginTests(TestCase):
    def test_local_admin_login_sets_usable_cookies_and_requires_csrf(self):
        get_user_model().objects.create_superuser(
            username='localadmin', email='admin@example.com', password='test-admin-password'
        )
        client = Client(enforce_csrf_checks=True)
        response = client.get('/admin/login/', HTTP_HOST='localhost:8000')
        cookie = response.cookies['csrftoken']
        self.assertFalse(cookie['secure'])
        self.assertEqual(cookie['domain'], '')
        payload = {'username': 'localadmin', 'password': 'test-admin-password', 'next': '/admin/'}
        self.assertEqual(client.post('/admin/login/', payload, HTTP_HOST='localhost:8000').status_code, 403)
        payload['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        response = client.post('/admin/login/', payload, HTTP_HOST='localhost:8000', HTTP_ORIGIN='http://localhost:8000')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')
        self.assertFalse(response.cookies['sessionid']['secure'])
        self.assertEqual(response.cookies['sessionid']['domain'], '')
