from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Location, PickupHub, Vehicle
from .serializers import VehicleSerializer


class FleetLocationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username='fleet-operator', password='test-password')
        token = signing.dumps({'id': user.pk, 'hash': user.get_session_auth_hash()}, salt='zudo-dashboard')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    def test_vehicle_id_generated_for_blank_and_omitted_ids(self):
        ids = []
        for extra in [{}, {'external_id': ''}]:
            response = self.client.post('/api/vehicles/', {'plate_number': 'KL01TEST', 'category': 'Swift', **extra}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(response.data['external_id'].startswith('ZUDO-'))
            ids.append(response.data['external_id'])
        self.assertNotEqual(*ids)
        vehicle = Vehicle.objects.first()
        original = vehicle.external_id
        serializer = VehicleSerializer(vehicle, data={'external_id': ''}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save().external_id, original)

    def test_hub_requires_location_and_inactive_locations_hide_hubs(self):
        location = self.client.post('/api/locations/', {'name': 'Kochi'}, format='json')
        self.assertEqual(location.status_code, 201)
        self.assertEqual(self.client.post('/api/pickup-hubs/', {'name': 'Airport'}, format='json').status_code, 400)
        hub = self.client.post('/api/pickup-hubs/', {'name': 'Airport', 'location': location.data['id']}, format='json')
        self.assertEqual(hub.status_code, 201, hub.data)
        self.assertEqual(hub.data['location_name'], 'Kochi')
        self.assertEqual(self.client.delete(f"/api/locations/{location.data['id']}/").status_code, 409)
        self.client.patch(f"/api/locations/{location.data['id']}/", {'is_active': False}, format='json')
        self.assertEqual(self.client.get('/api/pickup-hubs/').data, [])
        self.assertEqual(len(self.client.get('/api/pickup-hubs/?include_inactive=1').data), 1)
        self.assertEqual(self.client.post('/api/pickup-hubs/', {'name': 'City hub', 'location': location.data['id']}, format='json').status_code, 400)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/locations/', {'name': 'Munnar'}, format='json').status_code, 401)

    def test_vehicle_cannot_be_assigned_to_inactive_location(self):
        location = Location.objects.create(name='Kochi', is_active=False)
        hub = PickupHub.objects.create(name='Airport', location=location)
        serializer = VehicleSerializer(data={'plate_number': 'KL01TEST', 'pickup_hub': hub.pk})
        self.assertFalse(serializer.is_valid())
        self.assertIn('pickup_hub', serializer.errors)
