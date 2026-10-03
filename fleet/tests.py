from django.test import TestCase
from types import SimpleNamespace
from unittest.mock import Mock
from django.test import override_settings
from bs4 import BeautifulSoup
from .services import build_login_payload, validate_login_response, login_to_therentos


class TheRentOSLoginTests(TestCase):
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

    def test_selects_login_form_instead_of_first_form(self):
        soup = BeautifulSoup('''<form action="/search"><input name="query"></form>
            <form action="/login"><input type="hidden" name="_token" value="csrf">
            <input type="email" name="email"><input type="password" name="password"></form>''', 'html.parser')
        payload, action = build_login_payload(soup, 'test@example.com', 'test-password')
        self.assertEqual(action, 'https://avs.therentos.com/login')
        self.assertEqual(payload, {'_token': 'csrf', 'email': 'test@example.com', 'password': 'test-password'})
