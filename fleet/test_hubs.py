from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework.test import APIClient
from .models import Vehicle, PickupHub


class PickupHubTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username='operator', password='test-password')
        token = signing.dumps({'id': user.pk, 'hash': user.get_session_auth_hash()}, salt='zudo-dashboard')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    def test_hub_crud_and_vehicle_connection(self):
        hub = self.client.post('/api/pickup-hubs/', {'name': 'Airport hub', 'city': 'Kochi'}, format='json')
        self.assertEqual(hub.status_code, 201)
        car = Vehicle.objects.create(external_id='local-car', plate_number='KL01TEST')
        response = self.client.patch(f'/api/vehicles/{car.pk}/', {'pickup_hub': hub.data['id']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pickup_hub_name'], 'Airport hub')
        self.assertEqual(self.client.delete(f"/api/pickup-hubs/{hub.data['id']}/").status_code, 409)
        response = self.client.patch(f"/api/pickup-hubs/{hub.data['id']}/", {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/pickup-hubs/').data, [])

    def test_public_reads_but_no_public_writes(self):
        hub = PickupHub.objects.create(name='Station hub')
        self.client.credentials()
        self.assertEqual(len(self.client.get('/api/pickup-hubs/').data), 1)
        self.assertEqual(self.client.post('/api/pickup-hubs/', {'name': 'Unauthorized'}, format='json').status_code, 401)
        self.assertEqual(self.client.patch(f'/api/pickup-hubs/{hub.pk}/', {'name': 'Changed'}, format='json').status_code, 401)
