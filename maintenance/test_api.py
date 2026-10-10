from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from rest_framework.test import APIClient
from fleet.models import Vehicle


class OperationsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username='operator', password='test-password')
        token = signing.dumps({'id': user.pk, 'hash': user.get_session_auth_hash()}, salt='zudo-dashboard')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        self.car = Vehicle.objects.create(external_id='local', plate_number='KL01TEST', vehicle_type='Car')

    def test_service_and_schedule_persist_and_update(self):
        response = self.client.post('/api/service-types/', {'name': 'Oil change'}, format='json')
        self.assertEqual(response.status_code, 201)
        kind = response.data['id']
        payload = {'car': self.car.pk, 'service_type': kind, 'service_date': '2026-10-09', 'odometer_reading': 1000, 'service_center': 'Workshop', 'parts_cost': '100', 'labor_cost': '50', 'total_cost': '1'}
        record = self.client.post('/api/services/', payload, format='json')
        self.assertEqual(record.status_code, 201, record.data)
        self.assertEqual(record.data['total_cost'], '150.00')
        updated = self.client.patch(f"/api/services/{record.data['id']}/", {'parts_cost': '200'}, format='json')
        self.assertEqual(updated.data['total_cost'], '250.00')
        schedule = self.client.post('/api/schedules/', {'car': self.car.pk, 'service_type': kind, 'due_date': '2026-11-09'}, format='json')
        self.assertEqual(schedule.status_code, 201)
        update = self.client.patch(f"/api/schedules/{schedule.data['id']}/", {'status': 'completed'}, format='json')
        self.assertEqual(update.data['status'], 'completed')
        self.assertEqual(len(self.client.get('/api/services/', {'car_id': self.car.pk}).data), 1)

    def test_staff_create_update_duplicate_and_delete(self):
        member = {'name': 'Test Staff', 'email': 'staff@example.com', 'employeeId': 'EMP-1', 'department': 'Operations'}
        response = self.client.post('/api/staff/', member, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.post('/api/staff/', member, format='json').status_code, 400)
        pk = response.data['id']
        update = self.client.patch(f'/api/staff/{pk}/', {'status': 'Approved', 'phone': '9000000000'}, format='json')
        self.assertEqual(update.data['status'], 'Approved')
        self.assertEqual(len(self.client.get('/api/staff/').data), 1)
        self.assertEqual(self.client.delete(f'/api/staff/{pk}/').status_code, 204)
        self.assertEqual(self.client.get('/api/staff/').data, [])

    def test_validation_and_authentication(self):
        response = self.client.post('/api/services/', {'car': self.car.pk, 'service_date': '2026-10-09', 'odometer_reading': 0, 'service_center': 'Workshop', 'parts_cost': '-1'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/schedules/', {'car': self.car.pk}, format='json').status_code, 400)
        self.client.credentials()
        for url in ['/api/staff/', '/api/services/', '/api/schedules/', '/api/service-types/']:
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_mileage_reminders_and_completed_work_reset_intervals(self):
        from .models import ServiceType, MaintenanceSchedule
        from .intervals import CHECKUP, SERVICE
        self.car.odometer = 10000
        self.car.save()
        for _ in range(2):
            response = self.client.get('/api/schedules/')
            self.assertEqual(response.status_code, 200)
        self.assertEqual(MaintenanceSchedule.objects.filter(car=self.car).count(), 2)
        checkup = MaintenanceSchedule.objects.get(car=self.car, service_type__name=CHECKUP)
        self.assertEqual(checkup.status, 'overdue')
        self.assertEqual(self.client.patch(f'/api/schedules/{checkup.pk}/', {'status': 'completed'}, format='json').status_code, 400)
        payload = {'car': self.car.pk, 'service_type': ServiceType.objects.get(name=SERVICE).pk,
                   'service_date': '2026-10-09', 'odometer_reading': 10000,
                   'service_center': 'Workshop', 'parts_cost': '200', 'labor_cost': '100'}
        result = self.client.post('/api/services/', payload, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['total_cost'], '300.00')
        checkup.refresh_from_db()
        self.assertEqual(checkup.status, 'completed')
        active = MaintenanceSchedule.objects.filter(car=self.car).exclude(status__in=['completed', 'cancelled'])
        self.assertEqual(active.get(service_type__name=CHECKUP).due_odometer, 15000)
        self.assertEqual(active.get(service_type__name=SERVICE).due_odometer, 20000)
        self.car.odometer = 15000
        self.car.save()
        self.client.get('/api/schedules/')
        self.assertEqual(active.get(service_type__name=CHECKUP).status, 'due')
        payload['service_type'] = ServiceType.objects.get(name=CHECKUP).pk
        payload['odometer_reading'] = 15000
        self.assertEqual(self.client.post('/api/services/', payload, format='json').status_code, 201)
        self.assertEqual(active.get(service_type__name=CHECKUP).due_odometer, 20000)
        self.assertEqual(active.get(service_type__name=SERVICE).due_odometer, 20000)
