from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authenticator.authentication import DashboardAuthentication
from .models import Vehicle
from .serializers import VehicleSerializer


class PriceSelectionSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    daily_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, min_value=Decimal('0.01'))


class BulkPriceSerializer(serializers.Serializer):
    vehicles = PriceSelectionSerializer(many=True, allow_empty=False, max_length=10000)
    operation = serializers.ChoiceField(choices=['increase', 'decrease', 'set'])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))

    def validate_vehicles(self, value):
        ids = [row['id'] for row in value]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError('Select each vehicle only once.')
        return value


class BulkDailyPriceAPI(APIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BulkPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        expected = {row['id']: row['daily_price'] for row in data['vehicles']}
        with transaction.atomic():
            vehicles = list(Vehicle.objects.select_for_update().filter(pk__in=expected).order_by('pk'))
            if len(vehicles) != len(expected):
                return Response({'error': 'One or more selected vehicles no longer exist. Refresh Fleet and select again.'}, status=409)
            for vehicle in vehicles:
                if vehicle.daily_price != expected[vehicle.pk]:
                    return Response({'error': f'{vehicle.plate_number}: daily price has changed. Refresh Fleet before applying this update.'}, status=409)
                if data['operation'] != 'set' and vehicle.daily_price is None:
                    raise serializers.ValidationError(f'{vehicle.plate_number} has no daily price. Use Set price first.')
                if data['operation'] == 'set':
                    price = data['amount']
                elif data['operation'] == 'increase':
                    price = vehicle.daily_price + data['amount']
                else:
                    price = vehicle.daily_price - data['amount']
                if not Decimal('0.01') <= price <= Decimal('99999999.99'):
                    raise serializers.ValidationError(f'{vehicle.plate_number}: resulting daily price must be between ₹0.01 and ₹99,999,999.99. No prices were changed.')
                vehicle.daily_price = price
                vehicle.updated_at = timezone.now()
            Vehicle.objects.bulk_update(vehicles, ['daily_price', 'updated_at'])
        return Response({'updated': len(vehicles), 'vehicles': VehicleSerializer(vehicles, many=True, context={'request': request}).data})
