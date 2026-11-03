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
        reference = self.create_booking()
        self.payload['time_from'] = '13:00'
        self.payload['time_to'] = '14:00'
        self.assertEqual(self.client.post('/api/bookings/', self.payload, format='json').status_code, 409)
        self.sign_in()
        self.client.patch(f'/api/bookings/{reference}/', {'status': 'confirmed'}, format='json')
        self.client.patch(f'/api/bookings/{reference}/', {'status': 'completed', 'return_odometer': 100}, format='json')
        self.create_booking()
        self.assertEqual(Booking.objects.count(), 2)

    def test_reserved_vehicle_shows_expected_return_and_blocks_later_dates(self):
        reference = self.create_booking()
        self.payload['time_from'] = '14:00'
        self.payload['time_to'] = '15:00'
        response = self.client.post('/api/vehicles/available/', {**self.payload, 'include_unavailable': True}, format='json')
        self.assertEqual(response.status_code, 200)
        row = response.data['vehicles'][0]
        self.assertEqual(row['available_stock'], 0)
        self.assertEqual(row['unavailable_reason'], 'awaiting_return')
        self.assertEqual(row['expected_return_at'], Booking.objects.get(reference=reference).end_datetime)
        self.assertEqual(self.client.post('/api/bookings/', self.payload, format='json').status_code, 409)

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

class ManualBookingTests(LocalBookingTests):
    def test_percentage_discount_saved_and_edited(self):
        self.sign_in()
        payload = {**self.old_payload(), 'discount_type': 'percentage', 'discount_value': '10'}
        response = self.client.post('/api/bookings/list/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['discount_amount'], '150.00')
        self.assertEqual(response.data['total_amount'], '1550.00')
        reference = response.data['reference']
        response = self.client.put(f'/api/bookings/{reference}/', {**payload, 'discount_type': 'flat', 'discount_value': '250.25'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['discount_amount'], '250.25')
        self.assertEqual(response.data['total_amount'], '1449.75')
        saved = Booking.objects.get(reference=reference)
        self.assertEqual(saved.discount_value, Decimal('250.25'))

    def test_invalid_discounts_rejected(self):
        self.sign_in()
        for kind, value in [('percentage', '100.01'), ('flat', '1500.01'), ('flat', '-1'), ('other', '10')]:
            with self.subTest(kind=kind, value=value):
                response = self.client.post('/api/bookings/list/', {**self.old_payload(), 'discount_type': kind, 'discount_value': value}, format='json')
                self.assertEqual(response.status_code, 400, response.data)

    def test_full_discount_keeps_location_charge(self):
        self.sign_in()
        response = self.client.post('/api/bookings/list/', {**self.old_payload(), 'discount_type': 'percentage', 'discount_value': '100'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_amount'], '200.00')

    def old_payload(self):
        start = timezone.localtime(timezone.now() - timedelta(days=10))
        end = start + timedelta(days=1)
        return {**self.payload, 'date_from': start.strftime('%Y-%m-%d'), 'time_from': start.strftime('%H:%M'),
                'date_to': end.strftime('%Y-%m-%d'), 'time_to': end.strftime('%H:%M'),
                'rental_amount': '1500.00', 'delivery_amount': '200.00'}

    def test_manual_auth_and_public_date_restriction(self):
        payload = self.old_payload()
        self.assertEqual(self.client.post('/api/bookings/list/', payload, format='json').status_code, 401)
        self.assertEqual(self.client.post('/api/bookings/', payload, format='json').status_code, 400)

    def test_old_booking_completed_without_changing_fleet(self):
        self.create_booking()
        self.sign_in()
        response = self.client.post('/api/bookings/list/', self.old_payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['total_amount'], '1700.00')
        self.assertIsNotNone(response.data['returned_at'])
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer, 0)

    def test_manual_overlap_and_invalid_duration(self):
        self.sign_in()
        payload = self.old_payload()
        self.assertEqual(self.client.post('/api/bookings/list/', payload, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/bookings/list/', payload, format='json').status_code, 400)
        payload.update(date_to=payload['date_from'], time_to=payload['time_from'])
        self.assertEqual(self.client.post('/api/bookings/list/', payload, format='json').status_code, 400)

    def test_manual_future_confirmed(self):
        self.sign_in()
        response = self.client.post('/api/bookings/list/', {**self.payload, 'rental_amount': '500', 'delivery_amount': '0'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'confirmed')

    def test_admin_add(self):
        from django.urls import reverse
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse('admin:booking_booking_add')
        self.assertEqual(self.client.get(url).status_code, 200)
        start = timezone.localtime(timezone.now() - timedelta(days=10))
        end = start + timedelta(days=1)
        response = self.client.post(url, {'vehicle': self.vehicle.pk, 'customer_name': 'Old customer', 'customer_phone': '9000000000',
            'start_datetime_0': start.strftime('%Y-%m-%d'), 'start_datetime_1': start.strftime('%H:%M:%S'),
            'end_datetime_0': end.strftime('%Y-%m-%d'), 'end_datetime_1': end.strftime('%H:%M:%S'),
            'pickup_location_id': self.hub.pk, 'dropoff_location_id': self.hub.pk,
            'rental_amount': '1500', 'delivery_amount': '200', '_save': 'Save'})
        self.assertEqual(response.status_code, 302, getattr(response, 'context_data', None))
        self.assertEqual(Booking.objects.get().status, 'completed')

class BookingEditTests(LocalBookingTests):
    def edit_payload(self):
        return {**self.payload, 'customer_name': 'Corrected customer', 'customer_phone': '9111111111',
                'rental_amount': '1800.00', 'delivery_amount': '100.00', 'notes': 'Corrected notes'}

    def test_edit_requires_authentication(self):
        reference = self.create_booking()
        response = self.client.put(f'/api/bookings/{reference}/', self.edit_payload(), format='json')
        self.assertEqual(response.status_code, 401)

    def test_edit_existing_without_self_conflict_preserves_reference_and_status(self):
        reference = self.create_booking()
        self.sign_in()
        response = self.client.put(f'/api/bookings/{reference}/', self.edit_payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['reference'], reference)
        self.assertEqual(response.data['customer_name'], 'Corrected customer')
        self.assertEqual(response.data['customer_phone'], '9111111111')
        self.assertEqual(response.data['notes'], 'Corrected notes')
        self.assertEqual(response.data['total_amount'], '1900.00')
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(Booking.objects.count(), 1)

    def test_edit_rejects_conflict_and_rolls_back(self):
        reference = self.create_booking()
        other = Vehicle.objects.create(pickup_hub=self.hub, external_id='edit-test', plate_number='KL02TEST', category='Other car', vehicle_type='Car', hourly_rate=100)
        Booking.objects.create(vehicle=other, vehicle_plate_number=other.plate_number, customer_name='Other customer', customer_phone='9000000000',
            start_datetime=Booking.objects.get(reference=reference).start_datetime, end_datetime=Booking.objects.get(reference=reference).end_datetime,
            pickup_location_id=self.hub.pk, dropoff_location_id=self.hub.pk, rental_amount=100, delivery_amount=0, total_amount=100)
        self.sign_in()
        response = self.client.put(f'/api/bookings/{reference}/', {**self.edit_payload(), 'cart_vehicle': other.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        booking = Booking.objects.get(reference=reference)
        self.assertEqual(booking.vehicle_id, self.vehicle.pk)
        self.assertEqual(booking.customer_name, 'Test Customer')

    def test_edit_rejects_invalid_dates_and_negative_charges(self):
        reference = self.create_booking()
        self.sign_in()
        for changes in [{'date_to': self.payload['date_from'], 'time_to': self.payload['time_from']}, {'rental_amount': '-1'}]:
            response = self.client.put(f'/api/bookings/{reference}/', {**self.edit_payload(), **changes}, format='json')
            self.assertEqual(response.status_code, 400)

    def test_admin_edit(self):
        from django.urls import reverse
        reference = self.create_booking()
        booking = Booking.objects.get(reference=reference)
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse('admin:booking_booking_change', args=[booking.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        start, end = timezone.localtime(booking.start_datetime), timezone.localtime(booking.end_datetime)
        response = self.client.post(url, {'vehicle': self.vehicle.pk, 'customer_name': 'Fixed by admin', 'customer_phone': '9000000000',
            'start_datetime_0': start.strftime('%Y-%m-%d'), 'start_datetime_1': start.strftime('%H:%M:%S'),
            'end_datetime_0': end.strftime('%Y-%m-%d'), 'end_datetime_1': end.strftime('%H:%M:%S'),
            'pickup_location_id': self.hub.pk, 'dropoff_location_id': self.hub.pk,
            'rental_amount': '900', 'delivery_amount': '0', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.customer_name, 'Fixed by admin')
        self.assertEqual(booking.total_amount, Decimal('900'))
        self.assertEqual(booking.reference, reference)
        self.assertEqual(booking.status, 'pending')

    def test_edit_completed_preserves_return_records_and_vehicle_mileage(self):
        reference = self.create_booking()
        booking = Booking.objects.get(reference=reference)
        booking.start_datetime -= timedelta(days=10)
        booking.end_datetime -= timedelta(days=10)
        booking.status = 'completed'
        booking.return_odometer = 900
        booking.returned_at = booking.end_datetime
        booking.assigned_email = 'driver@example.com'
        booking.save()
        self.vehicle.odometer = 1200
        self.vehicle.save()
        self.sign_in()
        from zoneinfo import ZoneInfo
        start = booking.start_datetime.astimezone(ZoneInfo('Asia/Kolkata'))
        end = booking.end_datetime.astimezone(ZoneInfo('Asia/Kolkata'))
        payload = {**self.edit_payload(), 'date_from': start.strftime('%Y-%m-%d'), 'time_from': start.strftime('%H:%M'),
                   'date_to': end.strftime('%Y-%m-%d'), 'time_to': end.strftime('%H:%M')}
        response = self.client.put(f'/api/bookings/{reference}/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['return_odometer'], 900)
        self.assertEqual(response.data['assigned_email'], 'driver@example.com')
        self.assertEqual(response.data['status'], 'completed')
        booking.refresh_from_db()
        self.assertEqual(booking.returned_at, end)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer, 1200)
        response = self.client.put(f'/api/bookings/{reference}/', self.edit_payload(), format='json')
        self.assertEqual(response.status_code, 400)

class CustomerRecordTests(LocalBookingTests):
    def test_booking_saves_customer_and_search_by_name_or_mobile(self):
        from .models import Customer
        self.payload.update(customer_name='Varun Kumar', customer_email='varun@example.com')
        reference = self.create_booking()
        customer = Customer.objects.get()
        self.assertEqual(customer.name, 'Varun Kumar')
        self.assertEqual(customer.email, 'varun@example.com')
        self.assertEqual(Booking.objects.get(reference=reference).customer_id, customer.pk)
        self.sign_in()
        for query in ['va', 'VA', '9000']:
            response = self.client.get('/api/customers/', {'q': query})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data[0]['name'], 'Varun Kumar')
            self.assertEqual(response.data[0]['phone'], '9000000000')
            self.assertEqual(response.data[0]['email'], 'varun@example.com')

    def test_customer_search_requires_login_and_two_characters(self):
        self.create_booking()
        self.assertEqual(self.client.get('/api/customers/', {'q': 'te'}).status_code, 401)
        self.sign_in()
        self.assertEqual(self.client.get('/api/customers/', {'q': 't'}).data, [])
        self.assertEqual(self.client.get('/api/customers/', {'q': 'missing'}).data, [])

    def test_same_mobile_reuses_customer_and_same_name_different_mobile_is_separate(self):
        from .models import Customer
        reference = self.create_booking()
        booking = Booking.objects.get(reference=reference)
        booking.customer_phone = '+919000000000'
        booking.customer_email = 'customer@example.com'
        booking.save()
        self.assertEqual(Customer.objects.count(), 1)
        booking.customer_phone = '9111111111'
        booking.save()
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(booking.customer.phone, '9111111111')

    def test_status_update_does_not_overwrite_newer_customer_details(self):
        from .models import Customer
        reference = self.create_booking()
        customer = Customer.objects.get()
        customer.name = 'Updated customer name'
        customer.save()
        self.sign_in()
        response = self.client.patch(f'/api/bookings/{reference}/', {'status': 'confirmed'}, format='json')
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.name, 'Updated customer name')

    def test_manual_save_and_edit_sync_customer(self):
        from .models import Customer
        self.sign_in()
        payload = {**self.payload, 'rental_amount': '500', 'delivery_amount': '0', 'customer_name': 'Varun'}
        response = self.client.post('/api/bookings/list/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        reference = response.data['reference']
        response = self.client.put(f'/api/bookings/{reference}/', {**payload, 'customer_name': 'Varun Kumar', 'customer_email': 'varun@example.com'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Customer.objects.get().name, 'Varun Kumar')
        self.assertEqual(Customer.objects.get().email, 'varun@example.com')

    def test_backfill_imports_existing_bookings_and_preserves_history(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from .models import Customer
        reference = self.create_booking()
        booking = Booking.objects.get(reference=reference)
        Customer.objects.all().delete()
        self.assertIsNone(Booking.objects.get(pk=booking.pk).customer_id)
        from types import SimpleNamespace
        import_module('booking.migrations.0003_customer_records').import_customers(apps, SimpleNamespace(connection=connection))
        booking.refresh_from_db()
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(booking.customer.name, 'Test Customer')
        self.assertEqual(booking.customer_name, 'Test Customer')
