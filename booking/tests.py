from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIClient
from .models import Booking


class AvailableVehiclesTests(TestCase):
    @patch('booking.views.fetch_available_vehicles')
    def test_json_payload_is_forwarded(self, remote):
        remote.return_value = {'vehicles': [], 'total': 0}
        payload = {
            'date_from': '2026-10-06', 'time_from': '00:00',
            'date_to': '2026-10-06', 'time_to': '01:00',
            'pickup_location_id': 6, 'dropoff_location_id': 6,
            'customer_name': 'Test Customer', 'customer_country_code': '91',
            'customer_phone': '9000000000', 'fuel_type': 'diesel',
        }
        response = APIClient().post('/api/vehicles/available/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        for key, value in payload.items():
            self.assertEqual(remote.call_args.kwargs[key], value)
        self.assertEqual(remote.call_args.kwargs['include_unavailable'], 1)
        self.assertEqual(remote.call_args.kwargs['body_type'], '')

    @patch('booking.views.fetch_available_vehicles')
    def test_missing_required_fields_do_not_contact_avs(self, remote):
        response = APIClient().post('/api/vehicles/available/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        for key in ('date_from', 'date_to', 'pickup_location_id', 'dropoff_location_id'):
            self.assertIn(key, response.data)
        remote.assert_not_called()


class EstimateBookingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            'customer_name': 'Asha', 'customer_phone': '9876543210',
            'date_from': '2026-10-10', 'time_from': '09:00',
            'date_to': '2026-10-11', 'time_to': '09:00',
            'pickup_location_id': 6, 'dropoff_location_id': 6,
            'cart_vehicle': 42,
            'vehicle_snapshot': {'asset_identifier': 'KL07AB1234', 'name': 'Creta'},
            'total_amount': '2500.00',
        }

    @patch('booking.views.create_estimate_booking')
    def test_success_saves_booking_and_lists_it(self, remote):
        remote.return_value = {'success': True, 'estimate_id': 123, 'public_url': 'https://example.com/estimate'}
        response = self.client.post('/api/estimates/create/', self.payload, format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get()
        self.assertEqual(booking.vehicle_plate_number, 'KL07AB1234')
        self.assertEqual(booking.therentos_estimate_id, '123')
        self.assertTrue(booking.therentos_synced)
        self.assertEqual(str(booking.total_amount), '2500.00')
        self.assertEqual(response.data['booking']['reference'], booking.reference)
        self.assertEqual(response.data['public_url'], remote.return_value['public_url'])
        self.assertEqual(self.client.get('/api/bookings/list/').data[0]['reference'], booking.reference)
        self.assertEqual(remote.call_args.args[0]['cart_vehicle'], 42)

    @patch('booking.views.create_estimate_booking')
    def test_remote_failure_rolls_back_booking(self, remote):
        for outcome in (RuntimeError('Unavailable'), {'success': False, 'error': 'Rejected'}):
            remote.side_effect = outcome if isinstance(outcome, Exception) else None
            remote.return_value = outcome
            response = self.client.post('/api/estimates/create/', self.payload, format='json')
            self.assertEqual(response.status_code, 500)
            self.assertFalse(Booking.objects.exists())

    @patch('booking.views.create_estimate_booking')
    def test_invalid_dates_do_not_create_remote_estimate(self, remote):
        self.payload['date_to'] = '2026-10-09'
        response = self.client.post('/api/estimates/create/', self.payload, format='json')
        self.assertEqual(response.status_code, 400)
        remote.assert_not_called()
        self.assertFalse(Booking.objects.exists())
