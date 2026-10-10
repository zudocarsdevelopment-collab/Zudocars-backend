from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from fleet.models import Vehicle, PickupHub
from .models import Booking


class LocalBookingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hub = PickupHub.objects.create(name='Test hub')
        self.vehicle = Vehicle.objects.create(pickup_hub=self.hub, external_id='local-test', plate_number='KL01TEST', category='Test Car', vehicle_type='Car', hourly_rate=100, min_hours_rate=300)
        start = timezone.localtime(timezone.now() + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=4)
        self.payload = {
            'customer_name': 'Test Customer', 'customer_phone': '9000000000',
            'date_from': start.strftime('%Y-%m-%d'), 'time_from': start.strftime('%H:%M'),
            'date_to': end.strftime('%Y-%m-%d'), 'time_to': end.strftime('%H:%M'),
            'pickup_location_id': self.hub.pk, 'dropoff_location_id': self.hub.pk, 'cart_vehicle': self.vehicle.pk,
            'total_amount': '1.00',
        }
        self.user = get_user_model().objects.create_user(username='operator', email='operator@example.com', password='local-test-password')

    def sign_in(self):
        response = self.client.post('/api/login/', {'email': self.user.email, 'password': 'local-test-password'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['token'])

    def create_booking(self):
        response = self.client.post('/api/bookings/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['reference']

    @patch('requests.sessions.Session.request', side_effect=AssertionError('No external requests allowed'))
    def test_booking_is_local_and_server_prices_override_client(self, network):
        reference = self.create_booking()
        booking = Booking.objects.get(reference=reference)
        self.assertEqual(booking.rental_amount, Decimal('400.00'))
        self.assertEqual(booking.total_amount, Decimal('1600.00'))
        self.assertEqual(booking.status, 'pending')
        network.assert_not_called()

    def test_overlap_blocks_booking_and_availability(self):
        self.create_booking()
        response = self.client.post('/api/bookings/', self.payload, format='json')
        self.assertEqual(response.status_code, 409)
        available = self.client.post('/api/vehicles/available/', self.payload, format='json')
        self.assertEqual(available.data['vehicles'], [])
        self.assertEqual(Booking.objects.count(), 1)

    def test_daily_price_is_used_for_availability_and_booking(self):
        self.vehicle.daily_price = Decimal('1800.00')
        self.vehicle.save()
        available = self.client.post('/api/vehicles/available/', self.payload, format='json')
        self.assertEqual(available.status_code, 200)
        self.assertEqual(available.data['vehicles'][0]['daily_price'], '1800.00')
        self.assertEqual(available.data['vehicles'][0]['total_incl_tax'], '1800.00')
        reference = self.create_booking()
        self.assertEqual(Booking.objects.get(reference=reference).rental_amount, Decimal('1800.00'))

    def test_daily_price_charges_each_started_day(self):
        from .booking import quote
        start = timezone.now()
        self.vehicle.daily_price = Decimal('1800.00')
        for duration, expected in [(timedelta(hours=4), '1800.00'),
                                   (timedelta(hours=24), '1800.00'),
                                   (timedelta(hours=24, seconds=1), '3600.00'),
                                   (timedelta(hours=48), '3600.00')]:
            with self.subTest(duration=duration):
                self.assertEqual(quote(self.vehicle, start, start + duration)['rental'], Decimal(expected))

    def test_invalid_daily_price_is_rejected(self):
        from fleet.serializers import VehicleSerializer
        for value in ['0.00', '-1.00']:
            serializer = VehicleSerializer(self.vehicle, data={'daily_price': value}, partial=True)
            self.assertFalse(serializer.is_valid())
            self.assertIn('daily_price', serializer.errors)

    def test_adjacent_windows_are_allowed(self):
        self.create_booking()
        self.payload['time_from'] = '13:00'
        self.payload['time_to'] = '14:00'
        self.create_booking()
        self.assertEqual(Booking.objects.count(), 2)

    def test_management_requires_authentication(self):
        reference = self.create_booking()
        self.assertEqual(self.client.get('/api/bookings/list/').status_code, 401)
        self.assertEqual(self.client.patch(f'/api/bookings/{reference}/', {'status': 'confirmed'}, format='json').status_code, 401)

    def test_operator_can_confirm_assign_cancel_and_release_vehicle(self):
        reference = self.create_booking()
        self.sign_in()
        response = self.client.patch(f'/api/bookings/{reference}/', {'status': 'confirmed', 'assigned_email': 'staff@example.com', 'notes': 'Call at pickup'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['assigned_email'], 'staff@example.com')
        self.assertEqual(len(self.client.get('/api/bookings/list/').data), 1)
        self.assertEqual(self.client.patch(f'/api/bookings/{reference}/', {'status': 'cancelled'}, format='json').status_code, 200)
        response = self.client.post('/api/vehicles/available/', self.payload, format='json')
        self.assertEqual(response.data['total'], 1)
        self.create_booking()

    def test_complete_and_terminal_status_cannot_reopen(self):
        reference = self.create_booking()
        self.sign_in()
        for state in ('confirmed', 'completed'):
            payload = {'status': state}
            if state == 'completed':
                payload['return_odometer'] = 100
            self.assertEqual(self.client.patch(f'/api/bookings/{reference}/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'/api/bookings/{reference}/', {'status': 'confirmed'}, format='json').status_code, 400)

    def test_return_updates_mileage_and_maintenance_atomically(self):
        from maintenance.models import MaintenanceSchedule
        from maintenance.intervals import CHECKUP, SERVICE
        self.vehicle.odometer = 4900
        self.vehicle.save()
        reference = self.create_booking()
        self.sign_in()
        url = f'/api/bookings/{reference}/'
        self.assertEqual(self.client.patch(url, {'status': 'confirmed'}, format='json').status_code, 200)
        for payload in [{'status': 'completed'}, {'status': 'completed', 'return_odometer': 4800}]:
            self.assertEqual(self.client.patch(url, payload, format='json').status_code, 400)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer, 4900)
        self.assertEqual(Booking.objects.get(reference=reference).status, 'confirmed')
        response = self.client.patch(url, {'status': 'completed', 'return_odometer': 5100, 'return_notes': 'Fuel full'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['pickup_odometer'], 4900)
        self.assertEqual(response.data['return_odometer'], 5100)
        self.assertEqual(response.data['return_notes'], 'Fuel full')
        self.assertIsNotNone(response.data['returned_at'])
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer, 5100)
        self.assertEqual(MaintenanceSchedule.objects.get(car=self.vehicle, service_type__name=CHECKUP).status, 'overdue')
        self.assertEqual(MaintenanceSchedule.objects.get(car=self.vehicle, service_type__name=SERVICE).due_odometer, 10000)
        self.assertEqual(self.client.patch(url, {'status': 'completed'}, format='json').status_code, 200)
        self.assertEqual(MaintenanceSchedule.objects.filter(car=self.vehicle).count(), 2)
        self.assertEqual(self.client.patch(url, {'return_odometer': 6000}, format='json').status_code, 400)

    def test_return_details_require_confirmed_trip(self):
        reference = self.create_booking()
        self.sign_in()
        self.assertEqual(self.client.patch(f'/api/bookings/{reference}/', {'return_odometer': 100}, format='json').status_code, 400)

    def test_invalid_dates_phone_and_unpriced_vehicle_are_rejected(self):
        for changes in ({'time_to': '08:00'}, {'time_from': '25:00'}, {'customer_phone': 'bad'}):
            response = self.client.post('/api/bookings/', {**self.payload, **changes}, format='json')
            self.assertEqual(response.status_code, 400)
        self.vehicle.hourly_rate = None
        self.vehicle.save()
        self.assertEqual(self.client.post('/api/bookings/', self.payload, format='json').status_code, 400)
        self.assertFalse(Booking.objects.exists())

    def test_pdf_uses_saved_booking(self):
        reference = self.create_booking()
        with TemporaryDirectory(dir=settings.BASE_DIR) as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post('/api/estimates/pdf/', {'booking_reference': reference}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            from pathlib import Path
            pdf = next(Path(directory).rglob('*.pdf'))
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
            from pypdf import PdfReader
            text = '\n'.join(page.extract_text() for page in PdfReader(pdf).pages)
            self.assertIn(reference, text)
            self.assertIn('1,600', text)
            self.assertIn('Refundable security deposit', text)
            self.assertIn('5,000.00', text)
            self.assertIn('6,600.00', text)
            self.assertEqual(Booking.objects.get(reference=reference).total_amount, Decimal('1600.00'))

    def test_generated_pdf_url_serves_pdf_without_nginx_media_access(self):
        from urllib.parse import urlsplit
        reference = self.create_booking()
        with TemporaryDirectory(dir=settings.BASE_DIR) as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post('/api/estimates/pdf/', {'booking_reference': reference}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            path = urlsplit(response.data['pdf_url']).path
            self.assertTrue(path.startswith('/api/estimates/pdf/'))
            download = self.client.get(path)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download['Content-Type'], 'application/pdf')
            self.assertTrue(download['Content-Disposition'].startswith('inline;'))
            self.assertTrue(b''.join(download.streaming_content).startswith(b'%PDF'))
            self.assertEqual(self.client.get('/api/estimates/pdf/settings.py/').status_code, 404)
            self.assertEqual(self.client.get('/api/estimates/pdf/zudo-booking-ZUDO-000000000000-00000000.pdf/').status_code, 404)

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid-token')
        self.assertEqual(self.client.get('/api/bookings/list/').status_code, 401)

    def test_pickup_hub_filters_available_vehicles_and_rejects_wrong_hub(self):
        other = PickupHub.objects.create(name='Other hub')
        payload = {**self.payload, 'pickup_location_id': other.pk}
        response = self.client.post('/api/vehicles/available/', payload, format='json')
        self.assertEqual(response.data['vehicles'], [])
        self.assertEqual(self.client.post('/api/bookings/', payload, format='json').status_code, 400)
        response = self.client.post('/api/bookings/', {**self.payload, 'pickup_custom_payload': 'Forged name'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['booking']['pickup_custom_payload'], self.hub.name)
