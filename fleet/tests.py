from django.test import TestCase
from types import SimpleNamespace
from unittest.mock import Mock
import requests
from django.test import override_settings
from bs4 import BeautifulSoup
from .services import build_login_payload, validate_login_response, login_to_therentos


class TheRentOSLoginTests(TestCase):
    @override_settings(THERENTOS_EMAIL='test@example.com', THERENTOS_PASSWORD='test-password')
    def test_login_preserves_session_and_uses_fresh_form_token(self):
        session = requests.Session()
        session.cookies.set('old_session', 'stale')
        session.headers['X-CSRF-TOKEN'] = 'old-token'
        session.headers['Authorization'] = 'Bearer old-token'

        def login_page(*args, **kwargs):
            self.assertEqual(session.cookies.get('old_session'), 'stale')
            self.assertEqual(session.headers['X-CSRF-TOKEN'], 'old-token')
            self.assertEqual(session.headers['Authorization'], 'Bearer old-token')
            session.cookies.set('new_session', 'fresh')
            return SimpleNamespace(
                text='<form action="/login"><input name="email" type="email"><input name="password" type="password"><input name="_token" type="hidden" value="new-token"></form>',
                url='https://avs.therentos.com/login', raise_for_status=lambda: None,
            )

        session.get = Mock(side_effect=login_page)
        session.post = Mock(return_value=SimpleNamespace(
            status_code=200, url='https://avs.therentos.com/admin', text='', headers={},
        ))
        login_to_therentos(session)
        self.assertEqual(session.post.call_args.kwargs['data']['_token'], 'new-token')
        self.assertEqual(session.cookies.get('new_session'), 'fresh')

    @override_settings(THERENTOS_EMAIL='test@example.com', THERENTOS_PASSWORD='test-password')
    def test_security_rejection_is_reported_without_credentials_or_retries(self):
        session = Mock()
        session.get.return_value = SimpleNamespace(
            text='<form action="/login"><input type="email" name="email"><input type="password" name="password"><input type="hidden" name="_token" value="csrf"></form>',
            url='https://avs.therentos.com/login', raise_for_status=lambda: None,
        )
        response = Mock(status_code=422, headers={'Content-Type': 'application/json'})
        response.json.return_value = {'success': False, 'errors': {'email': ['Suspicious activity detected for test@example.com, please contact admin']}}
        session.post.return_value = response
        with self.assertRaisesRegex(RuntimeError, 'Suspicious activity detected for \\[redacted\\], please contact admin'):
            login_to_therentos(session)
        session.post.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs['headers'], {'Referer': 'https://avs.therentos.com/login'})
        self.assertEqual(session.post.call_args.kwargs['data']['_token'], 'csrf')

    def test_dashboard_validation_styles_do_not_fail_login(self):
        validate_login_response(SimpleNamespace(
            status_code=200, url='https://avs.therentos.com/admin',
            text='<style>.is-invalid {color:red}</style><script>const invalid = false;</script>',
        ))

    def test_login_redirect_and_login_form_are_rejected(self):
        for url, html, code in (
            ('https://avs.therentos.com/login', '', 200),
            ('https://avs.therentos.com/admin', '<form><input type="password"></form>', 200),
            ('https://avs.therentos.com/admin', '', 403),
        ):
            with self.subTest(url=url, code=code), self.assertRaises(RuntimeError):
                validate_login_response(SimpleNamespace(status_code=code, url=url, text=html))

    def test_august_login_form_fields(self):
        soup = BeautifulSoup('''<form action="/login"><input type="hidden" name="_token" value="csrf">
            <input type="email" name="email"><input type="password" name="password"></form>''', 'html.parser')
        payload, action = build_login_payload(soup, 'test@example.com', 'test-password')
        self.assertEqual(action, 'https://avs.therentos.com/login')
        self.assertEqual(payload, {'_token': 'csrf', 'email': 'test@example.com', 'password': 'test-password'})

    def test_august_login_does_not_force_remember_field(self):
        soup = BeautifulSoup('''<form action="/login">
            <input type="hidden" name="_token" value="fresh-token">
            <input type="email" name="email"><input type="password" name="password">
            <input type="checkbox" name="remember">
            <input type="checkbox" name="unrelated"></form>''', 'html.parser')
        payload, _ = build_login_payload(soup, 'test@example.com', 'test-password')
        self.assertEqual(payload, {
            '_token': 'fresh-token', 'email': 'test@example.com',
            'password': 'test-password',
        })
