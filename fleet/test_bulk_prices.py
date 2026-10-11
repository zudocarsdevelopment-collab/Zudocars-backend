from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Vehicle


class BulkDailyPriceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username='pricing', password='test-password')
        token = signing.dumps({'id': user.pk, 'hash': user.get_session_auth_hash()}, salt='zudo-dashboard')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        self.cars = [Vehicle.objects.create(plate_number=f'KL01PRICE{i}', daily_price=price) for i, price in enumerate(['1000.25', '2000.50', '3000.00'])]

    def update(self, operation='increase', amount='100.00', vehicles=None):
        return self.client.post('/api/vehicles/bulk-daily-price/', {
            'operation': operation, 'amount': amount,
            'vehicles': vehicles if vehicles is not None else [{'id': car.pk, 'daily_price': str(car.daily_price)} for car in self.cars[:2]],
        }, format='json')

    def prices(self):
        return list(Vehicle.objects.order_by('pk').values_list('daily_price', flat=True))

    def test_selected_only_exact_decimal_arithmetic_and_retry_conflict(self):
        response = self.update(amount='100.15')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['updated'], 2)
        self.assertEqual(self.prices(), [Decimal('1100.40'), Decimal('2100.65'), Decimal('3000.00')])
        self.assertEqual(self.update(amount='100.15').status_code, 409)
        self.assertEqual(self.prices()[0], Decimal('1100.40'))

    def test_set_all_including_missing_daily_price_and_decrease(self):
        self.cars[2].daily_price = None; self.cars[2].save()
        rows = [{'id': car.pk, 'daily_price': str(car.daily_price) if car.daily_price is not None else None} for car in self.cars]
        self.assertEqual(self.update('set', '900.25', rows).status_code, 200)
        rows = [{'id': car.pk, 'daily_price': '900.25'} for car in self.cars]
        self.assertEqual(self.update('decrease', '100.10', rows).status_code, 200)
        self.assertEqual(self.prices(), [Decimal('800.15')] * 3)

    def test_failure_is_atomic_for_missing_stale_unpriced_and_negative_results(self):
        original = self.prices()
        rows = [{'id': self.cars[0].pk, 'daily_price': '1000.25'}, {'id': 99999, 'daily_price': '1.00'}]
        self.assertEqual(self.update(vehicles=rows).status_code, 409)
        rows[1] = {'id': self.cars[1].pk, 'daily_price': '1.00'}
        self.assertEqual(self.update(vehicles=rows).status_code, 409)
        self.assertEqual(self.update('decrease', '1500').status_code, 400)
        self.assertEqual(self.update('increase', '99999999.99').status_code, 400)
        self.assertEqual(self.prices(), original)
        self.cars[1].daily_price = None; self.cars[1].save()
        rows[1]['daily_price'] = None
        self.assertEqual(self.update(vehicles=rows).status_code, 400)
        self.assertEqual(self.prices()[0], original[0])

    def test_authentication_and_input_validation(self):
        for amount in ('0', '-1', '1.001', 'NaN'):
            self.assertEqual(self.update(amount=amount).status_code, 400)
        self.assertEqual(self.update(vehicles=[]).status_code, 400)
        row = {'id': self.cars[0].pk, 'daily_price': '1000.25'}
        self.assertEqual(self.update(vehicles=[row, row]).status_code, 400)
        self.assertEqual(self.update(operation='unknown').status_code, 400)
        self.client.credentials()
        self.assertEqual(self.update().status_code, 401)
