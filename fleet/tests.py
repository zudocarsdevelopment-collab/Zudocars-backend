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

class HubLocationChargeTests(TestCase):
    def setUp(self):
        from .models import Location, PickupHub, Vehicle
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from django.utils import timezone
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        self.client = APIClient()
        self.parent = Location.objects.create(name='Kochi', booking_amount='350.00')
        self.place = PickupHub.objects.create(name='Airport', location=self.parent)
        self.vehicle = Vehicle.objects.create(category='Test car', plate_number='KL-FEE', pickup_hub=self.place, hourly_rate=100, vehicle_type='Car')
        self.user = get_user_model().objects.create_user(username='fee-operator')
        start = (timezone.now() + timedelta(days=3)).astimezone(ZoneInfo('Asia/Kolkata'))
        end = start + timedelta(hours=4)
        self.payload = {'date_from': start.strftime('%Y-%m-%d'), 'time_from': start.strftime('%H:%M'), 'date_to': end.strftime('%Y-%m-%d'), 'time_to': end.strftime('%H:%M'),
                        'pickup_location_id': self.place.pk, 'dropoff_location_id': self.place.pk, 'cart_vehicle': self.vehicle.pk,
                        'customer_name': 'Charge customer', 'customer_phone': '9000000000'}

    def test_hub_default_location_override_zero_and_reset(self):
        from decimal import Decimal
        from .serializers import PickupHubSerializer
        self.assertEqual(self.place.effective_booking_amount, Decimal('350'))
        for value, expected in [('125.50', '125.50'), ('0', '0.00'), (None, '350.00')]:
            serializer = PickupHubSerializer(self.place, data={'booking_amount': value}, partial=True)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()
            self.assertEqual(serializer.data['effective_booking_amount'], expected)

    def test_invalid_charges_rejected_and_auth_required(self):
        from .serializers import PickupHubSerializer, LocationSerializer
        for serializer_class, instance in [(PickupHubSerializer, self.place), (LocationSerializer, self.parent)]:
            for amount in ['-1', 'NaN', '100000000', '1.234']:
                serializer = serializer_class(instance, data={'booking_amount': amount}, partial=True)
                self.assertFalse(serializer.is_valid(), amount)
        self.assertEqual(self.client.patch(f'/api/locations/{self.parent.pk}/', {'booking_amount': '200'}, format='json').status_code, 401)

    def test_quote_and_booking_use_saved_amount_not_client_amount(self):
        response = self.client.post('/api/vehicles/available/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['vehicles'][0]['delivery_amount'], '350.00')
        response = self.client.post('/api/bookings/', {**self.payload, 'delivery_amount': '1'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['booking']['delivery_amount'], '350.00')
        self.assertEqual(response.data['booking']['total_amount'], '750.00')
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(f'/api/locations/{self.parent.pk}/', {'booking_amount': '999'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        from booking.models import Booking
        self.assertEqual(str(Booking.objects.get().delivery_amount), '350.00')

    def test_saved_location_amount_is_editable_and_returned_in_lookup(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(f'/api/pickup-hubs/{self.place.pk}/', {'booking_amount': '175.25'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['effective_booking_amount'], '175.25')
        response = self.client.post('/api/vehicles/available/', self.payload, format='json')
        self.assertEqual(response.data['vehicles'][0]['delivery_amount'], '175.25')

    @override_settings(BOOKING_DELIVERY_AMOUNT='1200.00')
    def test_unset_amounts_keep_standard_charge(self):
        from decimal import Decimal
        self.parent.booking_amount = None
        self.parent.save()
        self.place.refresh_from_db()
        self.assertEqual(self.place.effective_booking_amount, Decimal('1200'))

    def test_manual_booking_uses_default_but_allows_operator_override(self):
        from booking.serializer import ManualBookingSerializer
        for overrides, expected in [({}, '350.00'), ({'delivery_amount': '99.50'}, '99.50'), ({'delivery_amount': '0'}, '0')]:
            serializer = ManualBookingSerializer(data={**self.payload, 'rental_amount': '400', **overrides}, context={'manual_booking': True})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            from decimal import Decimal
            self.assertEqual(serializer.validated_data['delivery_amount'], Decimal(expected))
