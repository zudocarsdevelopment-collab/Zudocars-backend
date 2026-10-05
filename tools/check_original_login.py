"""Run once: python manage.py shell < tools/check_original_login.py.

Tests the August 23 login flow only. Does not create estimates, bookings, or PDFs.
"""
import ast
import subprocess
import shutil
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings


def check_original_login():
    source = subprocess.run(
        [shutil.which('git') or 'git', 'show', '9de6fae:fleet/services.py'],
        check=True, capture_output=True, text=True,
    ).stdout
    tree = ast.parse(source)
    original_function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == 'build_login_payload'
    )
    namespace = {'urljoin': urljoin}
    exec(compile(ast.Module(body=[original_function], type_ignores=[]), '<August login>', 'exec'), namespace)
    email, password = settings.THERENTOS_EMAIL, settings.THERENTOS_PASSWORD
    if not email or not password:
        print('Missing configured credentials. No login attempted.')
        return
    with requests.Session() as session:
        page = session.get('https://avs.therentos.com/login', timeout=20)
        page.raise_for_status()
        payload, action = namespace['build_login_payload'](
            BeautifulSoup(page.text, 'html.parser'), email, password,
        )
        response = session.post(
            action, data=payload,
            headers={'Referer': 'https://avs.therentos.com/login'}, timeout=20,
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        original_rejected = (
            response.status_code != 200 or 'login' in response.url
            or 'invalid' in response.text.lower()
        )
        login_form_present = bool(soup.select_one('form input[type="password"]'))
        print('Original commit: 9de6fae (2026-08-23)')
        print('Submitted field names:', ', '.join(sorted(payload)))
        print('HTTP status:', response.status_code)
        print('Final path:', urlparse(response.url).path)
        print('Redirect statuses:', [item.status_code for item in response.history])
        print('Login form still present:', login_form_present)
        print('Original code would reject:', original_rejected)
        # Report provider feedback without exposing credentials, tokens or cookies.
        messages = []
        for element in soup.select('.alert, .invalid-feedback, [role="alert"], .error-message'):
            message = element.get_text(' ', strip=True)
            if message and message not in messages:
                messages.append(message)
        if 'application/json' in response.headers.get('Content-Type', ''):
            try:
                result = response.json()
                if isinstance(result, dict):
                    messages.append(str(result.get('errors') or result.get('message') or ''))
            except ValueError:
                pass
        for message in messages:
            for secret in (email, password):
                message = message.replace(secret, '[redacted]')
            print('AVS feedback:', message[:500])
        if login_form_present or urlparse(response.url).path.rstrip('/') == '/login':
            print('Result: original login request also returned to login.')
        elif response.status_code == 200:
            protected = session.get('https://avs.therentos.com/admin/estimates/create', timeout=20)
            protected_soup = BeautifulSoup(protected.text, 'html.parser')
            authenticated = (
                protected.status_code == 200
                and urlparse(protected.url).path.rstrip('/') != '/login'
                and not protected_soup.select_one('form input[type="password"]')
            )
            print('Protected estimate page accessible:', authenticated)
            print('Result:', 'Authenticated access confirmed.' if authenticated else 'Protected page rejected the session.')
        else:
            print('Result: original request failed. HTTP status shown above.')


check_original_login()
