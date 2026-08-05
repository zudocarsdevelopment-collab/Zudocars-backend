# yourapp/services.py
import json
import time
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from django.conf import settings
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
    form = soup.find('form')
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


def sync_vehicles_from_therentos(asset_type='car', csv_path='assets.csv'):
    """Fetch assets from theRentOS, save CSV snapshot, upsert into Vehicle model.
    Returns a summary dict."""
    if not settings.THERENTOS_EMAIL or not settings.THERENTOS_PASSWORD:
        raise RuntimeError(
            'THERENTOS_EMAIL and THERENTOS_PASSWORD must be set in environment variables'
        )

    session = requests.Session()

    login_page = session.get('https://avs.therentos.com/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    payload, login_action = build_login_payload(
        soup,
        "Ani@avs.com",
        "Ani@avs.com",
    )

    login_resp = session.post(
        login_action,
        data=payload,
        headers={'Referer': 'https://avs.therentos.com/login'},
    )
    if login_resp.status_code != 200 or 'login' in login_resp.url or 'invalid' in login_resp.text.lower():
        raise RuntimeError('Login failed: verify your theRentOS credentials and login form changes')

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