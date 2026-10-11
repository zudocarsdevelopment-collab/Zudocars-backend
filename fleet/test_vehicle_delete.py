from django.test import TestCase
from rest_framework.test import APIClient
from .models import Vehicle
from maintenance.models import MaintenanceSchedule, ServiceRecord
from accounting.models import Expense
from django.contrib.auth import get_user_model
from django.utils import timezone


class VehicleDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.car = Vehicle.objects.create(plate_number='KL01DELETE')

    def test_vehicle_without_history_can_be_deleted(self):
        self.assertEqual(self.client.delete(f'/api/vehicles/{self.car.pk}/').status_code, 204)
        self.assertFalse(Vehicle.objects.filter(pk=self.car.pk).exists())

    def test_schedules_return_clear_json_conflict_and_disable_retains_history(self):
        schedule = MaintenanceSchedule.objects.create(car=self.car, due_odometer=1000)
        response = self.client.delete(f'/api/vehicles/{self.car.pk}/')
        self.assertEqual(response.status_code, 409)
        self.assertIn('Disable', response.data['error'])
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertTrue(Vehicle.objects.filter(pk=self.car.pk).exists())
        self.assertEqual(self.client.patch(f'/api/vehicles/{self.car.pk}/', {'is_active': False}, format='json').status_code, 200)
        self.assertTrue(MaintenanceSchedule.objects.filter(pk=schedule.pk).exists())

    def test_service_and_expense_history_are_protected(self):
        record = ServiceRecord.objects.create(car=self.car, service_date=timezone.localdate(), odometer_reading=0, service_center='Workshop')
        self.assertEqual(self.client.delete(f'/api/vehicles/{self.car.pk}/').status_code, 409)
        record.delete()
        from uuid import uuid4
        user = get_user_model().objects.create_user(username='finance')
        Expense.objects.create(vehicle=self.car, amount=100, description='Fuel', category='fuel', created_by=user, request_id=uuid4())
        self.assertEqual(self.client.delete(f'/api/vehicles/{self.car.pk}/').status_code, 409)
