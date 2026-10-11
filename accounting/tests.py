from decimal import Decimal
from uuid import uuid4
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from booking.models import Booking
from fleet.models import Vehicle
from maintenance.models import ServiceRecord
from .models import Payment, Expense


class AccountingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='finance', password='test-password')
        self.client = APIClient()
        token = signing.dumps({'id': self.user.pk, 'hash': self.user.get_session_auth_hash()}, salt='zudo-dashboard')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        self.car = Vehicle.objects.create(plate_number='KL01FIN', category='Swift')
        now = timezone.now()
        self.booking = Booking.objects.create(vehicle=self.car, vehicle_plate_number=self.car.plate_number,
            customer_name='Customer', customer_phone='1234567890', start_datetime=now, end_datetime=now + timedelta(days=1),
            pickup_location_id=1, dropoff_location_id=1, rental_amount=900, delivery_amount=100, total_amount=1000, status='confirmed')

    def payment(self, amount, kind='receipt', **extra):
        return self.client.post('/api/accounts/payments/', {'request_id': str(uuid4()), 'booking': self.booking.reference,
            'amount': str(amount), 'kind': kind, 'method': 'upi', **extra}, format='json')

    def summary(self):
        response = self.client.get('/api/accounts/summary/')
        self.assertEqual(response.status_code, 200)
        return {k: Decimal(v) for k, v in response.data.items() if isinstance(v, str)}

    def test_totals_completed_booking_partial_payment_refund_and_expenses(self):
        self.assertEqual(self.payment('600.25').status_code, 201)
        self.assertEqual(self.payment('100.10', 'refund').status_code, 201)
        expense = self.client.post('/api/accounts/expenses/', {'request_id': str(uuid4()), 'amount': '50.15', 'category': 'fuel', 'description': 'Fuel'}, format='json')
        self.assertEqual(expense.status_code, 201, expense.data)
        ServiceRecord.objects.create(car=self.car, service_date=timezone.localdate(), odometer_reading=0, service_center='Workshop', total_cost='200.20')
        totals = self.summary()
        self.assertEqual(totals['revenue'], Decimal('1000'))
        self.assertEqual(totals['received'], Decimal('500.15'))
        self.assertEqual(totals['outstanding'], Decimal('499.85'))
        self.assertEqual(totals['expenses'], Decimal('250.35'))
        self.assertEqual(totals['net_balance'], Decimal('749.65'))
        self.booking.status = 'completed'; self.booking.save()
        self.assertEqual(self.summary(), totals)
        self.booking.status = 'cancelled'; self.booking.save()
        totals = self.summary()
        self.assertEqual(totals['revenue'], 0)
        self.assertEqual(totals['outstanding'], 0)
        self.assertEqual(totals['customer_credit'], Decimal('500.15'))

    def test_validation_refund_limits_and_auth(self):
        for value in ('0', '-1', '1.001', 'NaN'):
            self.assertEqual(self.payment(value).status_code, 400)
        self.assertEqual(self.payment(1, 'refund').status_code, 400)
        self.assertEqual(self.payment(1, date=str(timezone.localdate() + timedelta(days=1))).status_code, 400)
        self.assertEqual(self.payment(1, request_id='bad').status_code, 400)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/accounts/summary/').status_code, 401)
        self.assertEqual(self.payment(1).status_code, 401)
        self.assertEqual(self.client.post('/api/accounts/expenses/', {}).status_code, 401)

    def test_idempotency_and_void_preserve_history(self):
        submission = str(uuid4())
        receipt = self.payment(600, request_id=submission)
        self.assertEqual(receipt.status_code, 201)
        self.assertEqual(self.payment('600.00', request_id=submission).status_code, 200)
        self.assertEqual(self.payment(601, request_id=submission).status_code, 400)
        self.assertEqual(Payment.objects.count(), 1)
        refund = self.payment(100, 'refund')
        url = f"/api/accounts/payments/{receipt.data['id']}/void/"
        self.assertEqual(self.client.post(url, {'reason': 'Correction'}, format='json').status_code, 400)
        refund_url = f"/api/accounts/payments/{refund.data['id']}/void/"
        self.assertEqual(self.client.post(refund_url, {'reason': 'Wrong refund'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {'reason': ''}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'reason': 'Wrong receipt'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {'reason': 'Retry'}, format='json').status_code, 200)
        self.assertEqual(self.summary()['received'], 0)
        self.assertEqual(Payment.objects.count(), 2)
        entry = Payment.objects.get(pk=receipt.data['id'])
        self.assertEqual(entry.void_reason, 'Wrong receipt')
        self.assertEqual(entry.voided_by, self.user)

    def test_pending_deposits_overpayments_and_expense_void(self):
        self.booking.status = 'pending'; self.booking.save()
        self.payment(1200)
        self.assertEqual(self.summary()['customer_credit'], Decimal('1200'))
        self.booking.status = 'confirmed'; self.booking.save()
        self.assertEqual(self.summary()['customer_credit'], Decimal('200'))
        self.assertEqual(self.summary()['outstanding'], 0)
        response = self.client.post('/api/accounts/expenses/', {'request_id': str(uuid4()), 'amount': '50', 'category': 'rent', 'description': 'Office'}, format='json')
        self.assertEqual(response.status_code, 201)
        url = f"/api/accounts/expenses/{response.data['id']}/void/"
        self.assertEqual(self.client.post(url, {'reason': 'Duplicate invoice'}, format='json').status_code, 200)
        self.assertEqual(self.summary()['expenses'], 0)
        self.assertEqual(Expense.objects.count(), 1)
