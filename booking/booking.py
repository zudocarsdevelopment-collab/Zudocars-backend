import requests
from bs4 import BeautifulSoup
from django.conf import settings
from fleet.services import get_csrf_token, login_to_therentos

def create_estimate_booking(payload_data):
    """
    Logs into theRentOS, grabs a CSRF token, and creates a new booking estimate.
    `payload_data` is expected to be a dictionary matching the API parameters.
    """
    if not settings.THERENTOS_EMAIL or not settings.THERENTOS_PASSWORD:
        raise RuntimeError('THERENTOS_EMAIL and THERENTOS_PASSWORD must be configured.')

    session = requests.Session()

    # 1. Login flow
    login_to_therentos(session)

    # 2. Get fresh CSRF token
    estimate_page_url = 'https://avs.therentos.com/admin/estimates/'
    token = get_csrf_token(session, estimate_page_url)

    # 3. Construct payload
    post_payload = {
        '_token': token,
        'send_whatsapp': payload_data.get('send_whatsapp', 0),
        'customer_name': payload_data.get('customer_name'),
        'customer_country_code': payload_data.get('customer_country_code', '91'),
        'customer_phone': payload_data.get('customer_phone'),
        'estimate_priority': payload_data.get('estimate_priority', 'medium'),
        'booking_source': payload_data.get('booking_source', ''),
        'date_from': payload_data.get('date_from'),
        'time_from': payload_data.get('time_from'),
        'date_to': payload_data.get('date_to'),
        'time_to': payload_data.get('time_to'),
        'cooldown_hours': payload_data.get('cooldown_hours', 0.15),
        'pre_start_cooldown_hours': payload_data.get('pre_start_cooldown_hours', 0.15),
        'vehicle_type': payload_data.get('vehicle_type', 'car'),
        'pickup_location_id': payload_data.get('pickup_location_id'),
        'dropoff_location_id': payload_data.get('dropoff_location_id'),
        'pickup_custom_payload': payload_data.get('pickup_custom_payload', ''),
        'dropoff_custom_payload': payload_data.get('dropoff_custom_payload', ''),
        'coupon': payload_data.get('coupon', ''),
        'cart_vehicle': payload_data.get('cart_vehicle'),
        'cart_services': payload_data.get('cart_services', '[]'),
        'cart_km_packages': payload_data.get('cart_km_packages', '[]'),
        'selected_km_deduction_id': payload_data.get('selected_km_deduction_id', ''),
        'selected_price_deduction_id': payload_data.get('selected_price_deduction_id', ''),
        'selected_pricing_label': payload_data.get('selected_pricing_label', ''),
        'reposition_to_pickup_incl': payload_data.get('reposition_to_pickup_incl', 0),
        'reposition_return_incl': payload_data.get('reposition_return_incl', 0),
    }

    # 4. Dispatch request
    response = session.post(
        'https://avs.therentos.com/admin/estimates',
        data=post_payload,
        headers={
            'Referer': estimate_page_url,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        }
    )
    response.raise_for_status()
    return response.json()
