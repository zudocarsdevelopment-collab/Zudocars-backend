# Add this to yourapp/services.py — it reuses build_login_payload() and
# clean_number() that already live there.

import csv
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from fleet.services import build_login_payload, clean_number  # use absolute app import


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


def fetch_available_vehicles(
    date_from, time_from, date_to, time_to,
    pickup_location_id, dropoff_location_id,
    vehicle_type='car',
    cooldown_hours=0,
    pre_start_cooldown_hours=0,
    include_unavailable=1,
    pickup_custom_payload='',
    dropoff_custom_payload='',
    csv_path='available_vehicles.csv',
    estimate_page_url='https://avs.therentos.com/admin/estimates/create',
):
    """
    Mirrors what the 'New estimate' screen does when you fill in
    dates/times/locations and it repopulates the vehicle list:
    POSTs to /admin/estimates/available-vehicles and returns pricing +
    availability per vehicle.

    date_from/date_to: 'YYYY-MM-DD'
    time_from/time_to: 'HH:MM' (requests URL-encodes the ':' automatically)
    pickup_location_id/dropoff_location_id: int, from the location dropdowns
    """
    if not settings.THERENTOS_EMAIL or not settings.THERENTOS_PASSWORD:
        raise RuntimeError(
            'THERENTOS_EMAIL and THERENTOS_PASSWORD must be set in environment variables'
        )

    session = requests.Session()

    # --- login (same flow as sync_vehicles_from_therentos, but using
    #     settings instead of hardcoded creds) ---
    login_page = session.get('https://avs.therentos.com/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    payload, login_action = build_login_payload(
        soup, settings.THERENTOS_EMAIL, settings.THERENTOS_PASSWORD,
    )
    login_resp = session.post(
        login_action,
        data=payload,
        headers={'Referer': 'https://avs.therentos.com/login'},
    )
    if login_resp.status_code != 200 or 'login' in login_resp.url or 'invalid' in login_resp.text.lower():
        raise RuntimeError('Login failed: verify your theRentOS credentials and login form changes')

    # --- fresh CSRF token from the estimate-create page ---
    token = get_csrf_token(session, estimate_page_url)

    body = {
        '_token': token,
        'date_from': date_from,
        'time_from': time_from,
        'date_to': date_to,
        'time_to': time_to,
        'cooldown_hours': cooldown_hours,
        'pre_start_cooldown_hours': pre_start_cooldown_hours,
        'vehicle_type': vehicle_type,
        'pickup_location_id': pickup_location_id,
        'dropoff_location_id': dropoff_location_id,
        'pickup_custom_payload': pickup_custom_payload,
        'dropoff_custom_payload': dropoff_custom_payload,
        'include_unavailable': include_unavailable,
    }

    resp = session.post(
        'https://avs.therentos.com/admin/estimates/available-vehicles',
        data=body,
        headers={
            'Referer': estimate_page_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )
    resp.raise_for_status()

    data = resp.json()
    # Endpoint may return a bare list or a wrapped object -- handle both.
    if isinstance(data, list):
        vehicles = data
    else:
        vehicles = data.get('data') or data.get('vehicles') or []

    rows = []
    for v in vehicles:
        breakdown = v.get('rental_breakdown', {}) or {}
        rows.append({
            'id': v.get('id'),
            'name': v.get('name'),
            'business': v.get('business'),
            'business_id': v.get('business_id'),
            'asset_identifier': v.get('asset_identifier'),
            'asset_category_id': v.get('asset_category_id'),
            'sub_category_id': v.get('sub_category_id'),
            'available_stock': v.get('available_stock'),
            'booking_mode': v.get('booking_mode'),
            'min_hrs': v.get('min_hrs'),
            'max_extension_hrs': v.get('max_extension_hrs'),
            'km_limit': v.get('km_limit'),
            'asset_km_per_block': v.get('asset_km_per_block'),
            'journey_km_limit_allowed': v.get('journey_km_limit_allowed'),
            'deposit': clean_number(v.get('deposit')),
            'cost_per_hr': clean_number(v.get('cost_per_hr')),
            'cost_per_hr_incl_tax': clean_number(v.get('cost_per_hr_incl_tax')),
            'cost_per_24_hrs_incl_tax': clean_number(v.get('cost_per_24_hrs_incl_tax')),
            'extension_price_per_hr': clean_number(v.get('extension_price_per_hr')),
            'extension_price_per_hr_incl_tax': clean_number(v.get('extension_price_per_hr_incl_tax')),
            'rental_total_incl_tax': clean_number(v.get('rental_total_incl_tax')),
            'total_journey_incl_tax': clean_number(v.get('total_journey_incl_tax')),
            'billed_hours': breakdown.get('billed_hours'),
            'billed_input_hours': breakdown.get('billed_input_hours'),
            'min_block_hours': breakdown.get('min_block_hours'),
            'billable_blocks': breakdown.get('billable_blocks'),
            'billable_extension_hours': breakdown.get('billable_extension_hours'),
            'normal_hours': breakdown.get('normal_hours'),
            'extension_hours': breakdown.get('extension_hours'),
            'rate_ex_tax': clean_number(breakdown.get('rate_ex_tax')),
            'extension_rate_ex_tax': clean_number(breakdown.get('extension_rate_ex_tax')),
            'amount_ex_tax': clean_number(breakdown.get('amount_ex_tax')),
            'base_amount_ex_tax': clean_number(breakdown.get('base_amount_ex_tax')),
            'extension_amount_ex_tax': clean_number(breakdown.get('extension_amount_ex_tax')),
            'tax_percent': breakdown.get('tax_percent'),
            'tax': clean_number(breakdown.get('tax')),
            'total_incl_tax': clean_number(breakdown.get('total_incl_tax')),
            'image': v.get('image'),
            'business_logo': v.get('business_logo'),
        })

    if rows:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return {
        'total': len(rows),
        'csv_path': csv_path if rows else None,
        'vehicles': rows,
        'query': {
            'date_from': date_from, 'time_from': time_from,
            'date_to': date_to, 'time_to': time_to,
            'pickup_location_id': pickup_location_id,
            'dropoff_location_id': dropoff_location_id,
            'vehicle_type': vehicle_type,
        },
    }