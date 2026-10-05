# yourapp/services.py
import json
import time
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.conf import settings
from django.core.cache import cache
from .models import Vehicle


def clean_number(val):
    if val is None or val == '':
        return None
    s = str(val).replace(',', '').replace('₹', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def build_login_payload(soup, email, password):
    password_input = soup.find('input', attrs={'type': 'password'})
    form = password_input.find_parent('form') if password_input else None
    if not form:
        raise RuntimeError('Unable to find login form on theRentOS login page')

    payload = {}
    username_key = None
    password_key = None

    for input_tag in form.find_all('input'):
        name = input_tag.get('name')
        if not name:
            continue
        input_type = input_tag.get('type', '').lower()
        value = input_tag.get('value', '')

        # Match the browser login with Remember me enabled. Unrelated unchecked
        # checkboxes must not be submitted.
        if input_type == 'checkbox':
            if name == 'remember' or input_tag.has_attr('checked'):
                payload[name] = input_tag.get('value', 'on')
            continue

        if input_type in ('hidden', 'submit'):
            payload[name] = value
            continue

        lower_name = name.lower()
        if input_type == 'password' or 'pass' in lower_name:
            password_key = name
            continue
        if input_type in ('email',) or 'email' in lower_name or 'user' in lower_name:
            username_key = name
            continue

        if not username_key and input_type in ('text',):
            username_key = name

    if not username_key or not password_key:
        raise RuntimeError('Unable to detect login field names for theRentOS')

    payload[username_key] = email
    payload[password_key] = password
    return payload, urljoin('https://avs.therentos.com/login', form.get('action', ''))


def validate_login_response(response):
    """Inspect authentication state, not incidental words in scripts or CSS."""
    if 'application/json' in getattr(response, 'headers', {}).get('Content-Type', ''):
        try:
            result = response.json()
        except ValueError:
            result = {}
        if isinstance(result, dict) and (response.status_code >= 400 or result.get('success') is False):
            errors = result.get('errors', {})
            messages = []
            if isinstance(errors, dict):
                for values in errors.values():
                    messages.extend(values if isinstance(values, list) else [values])
            detail = '; '.join(str(message) for message in messages) or str(result.get('message', 'Login rejected.'))
            for secret in (settings.THERENTOS_EMAIL, settings.THERENTOS_PASSWORD):
                if secret:
                    detail = detail.replace(secret, '[redacted]')
            raise RuntimeError(f'theRentOS login failed (HTTP {response.status_code}): {detail[:500]}')
    soup = BeautifulSoup(response.text, 'html.parser')
    login_path = urlparse(response.url).path.rstrip('/').lower()
    login_form = soup.select_one('form input[type="password"]')
    if response.status_code != 200 or login_path == '/login' or login_form:
        raise RuntimeError(
            f'theRentOS login failed (HTTP {response.status_code}). '
            'Check configured credentials and whether the login page requires additional verification.'
        )


def login_to_therentos(session):
    """Start a new AVS session and fetch a fresh token for every login."""
    if not settings.THERENTOS_EMAIL or not settings.THERENTOS_PASSWORD:
        raise RuntimeError('THERENTOS_EMAIL and THERENTOS_PASSWORD must be configured.')
    cache.delete('therentos_session_cookies')
    session.cookies.clear()
    for header in ('Cookie', 'Authorization', 'X-CSRF-TOKEN', 'X-XSRF-TOKEN'):
        session.headers.pop(header, None)
    login_url = 'https://avs.therentos.com/login'
    page = session.get(login_url, timeout=20)
    page.raise_for_status()
    payload, action = build_login_payload(
        BeautifulSoup(page.text, 'html.parser'),
        settings.THERENTOS_EMAIL, settings.THERENTOS_PASSWORD,
    )
    response = session.post(action, data=payload, timeout=20, headers={
        'Referer': page.url,
    })
    validate_login_response(response)


def sync_vehicles_from_therentos(asset_type='car', csv_path='assets.csv'):
    """Fetch assets from theRentOS, save CSV snapshot, upsert into Vehicle model.
    Returns a summary dict."""
    if not settings.THERENTOS_EMAIL or not settings.THERENTOS_PASSWORD:
        raise RuntimeError(
            'THERENTOS_EMAIL and THERENTOS_PASSWORD must be set in environment variables'
        )

    session = requests.Session()

    login_to_therentos(session)

    all_assets = []
    page = 1
    while True:
        resp = session.get('https://avs.therentos.com/admin/assets',
                            params={'type': asset_type, 'page': page})
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('tr.js-asset-row')
        if not rows:
            break

        for row in rows:
            specs = {}
            try:
                for item in json.loads(row.get('data-asset-spec-lines', '[]')):
                    if ':' in item:
                        k, v = item.split(':', 1)
                        specs[k.strip()] = v.strip()
            except json.JSONDecodeError:
                pass

            plate = row.select_one('.aid-plate')
            year = row.select_one('.aid-year')
            odo = row.select_one('.odo-val')
            category = row.select_one('.col-cat')
            sub = row.select_one('.col-sub')
            loc_base = row.select_one('.loc-name:not(.loc-name-now)')
            loc_now = row.select_one('.loc-name-now')
            vtype = row.select_one('.col-type .badge')
            booking = row.select_one('.col-book .badge')
            hr_cost = row.select_one('.col-cost .pval')
            min_cost = row.select_one('.col-costmin .pval')
            fastag = row.select_one('.col-fastag .pval')
            added = row.select_one('.col-added')
            img = row.select_one('img.aphoto')

            all_assets.append({
                'id': row['data-asset-url'].rstrip('/').split('/')[-1],
                'plate': plate.text.strip() if plate else '',
                'year': year.text.strip() if year else '',
                'odometer': odo.text.strip() if odo else '',
                'category': category.text.strip() if category else '',
                'sub': sub.text.strip() if sub else '',
                'location_base': loc_base.text.strip() if loc_base else '',
                'location_now': loc_now.text.strip() if loc_now else '',
                'type': vtype.text.strip() if vtype else '',
                'booking': booking.text.strip() if booking else '',
                'hr_cost': hr_cost.contents[0].strip() if hr_cost else '',
                'min_hrs_cost': min_cost.contents[0].strip() if min_cost else '',
                'fastag': fastag.text.strip() if fastag else '',
                'added': added.text.strip() if added else '',
                'photo_url': img['src'] if img else '',
                'body': specs.get('Body', ''),
                'fuel': specs.get('Fuel', ''),
                'transmission': specs.get('Transmission', ''),
                'seats': specs.get('Seats', ''),
            })
        page += 1
        time.sleep(1)

    fieldnames = ['id', 'plate', 'year', 'odometer', 'category', 'sub',
                  'location_base', 'location_now', 'type', 'booking',
                  'hr_cost', 'min_hrs_cost', 'fastag', 'added', 'photo_url',
                  'body', 'fuel', 'transmission', 'seats']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_assets)

    created, updated = 0, 0
    for a in all_assets:
        year_val = clean_number(a['year'])
        seats_val = clean_number(a['seats'])
        obj, was_created = Vehicle.objects.update_or_create(
            external_id=a['id'],
            defaults={
                'plate_number': a['plate'],
                'year': int(year_val) if year_val else None,
                'odometer': int(clean_number(a['odometer']) or 0),
                'category': a['category'],
                'sub_category': a['sub'],
                'location_base': a['location_base'],
                'location_current': a['location_now'],
                'vehicle_type': a['type'],
                'booking_type': a['booking'],
                'hourly_rate': clean_number(a['hr_cost']),
                'min_hours_rate': clean_number(a['min_hrs_cost']),
                'fastag_charge': clean_number(a['fastag']),
                'photo_url': a['photo_url'],
                'body_type': a['body'],
                'fuel_type': a['fuel'],
                'transmission': a['transmission'],
                'seats': int(seats_val) if seats_val else None,
                'date_added': a['added'],
            }
        )
        created += was_created
        updated += (not was_created)

    return {'total': len(all_assets), 'created': created, 'updated': updated, 'csv_path': csv_path}



# In fleet/services.py

def get_csrf_token(session, page_url):
    """Grab a fresh Laravel CSRF token from either a <meta name="csrf-token">
    tag or a hidden `_token` input on the given page."""
    resp = session.get(page_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    meta = soup.find('meta', attrs={'name': 'csrf-token'})
    if meta and meta.get('content'):
        return meta['content']

    token_input = soup.find('input', attrs={'name': '_token'})
    if token_input and token_input.get('value'):
        return token_input['value']

    raise RuntimeError(f'Unable to find CSRF token on {page_url}')
