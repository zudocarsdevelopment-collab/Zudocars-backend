"""Run once: python manage.py shell < tools/check_original_login.py.

Tests the August 5 login flow only. Does not create estimates, bookings, or PDFs.
"""
import ast
import subprocess
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings


def check_original_login():
    source = subprocess.run(
        ['git', 'show', '86c246f:fleet/services.py'],
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
        print('Original commit: 86c246f (2026-08-05)')
        print('Submitted field names:', ', '.join(sorted(payload)))
        print('HTTP status:', response.status_code)
        print('Final path:', urlparse(response.url).path)
        print('Redirect statuses:', [item.status_code for item in response.history])
        print('Login form still present:', login_form_present)
        print('Original code would reject:', original_rejected)
        if login_form_present or urlparse(response.url).path.rstrip('/') == '/login':
            print('Result: original login request also returned to login.')
        elif response.status_code == 200:
            print('Result: original request reached a page without a login form; verify authenticated access next.')
        else:
            print('Result: original request failed. HTTP status shown above.')


check_original_login()
