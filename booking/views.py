# yourapp/views.py (or a new yourapp/api/views.py)
#
# Requires: pip install djangorestframework
# and 'rest_framework' added to INSTALLED_APPS in settings.py.

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers

from .Services_available_vehicles import fetch_available_vehicles
from .booking import create_estimate_booking

class AvailableVehiclesRequestSerializer(serializers.Serializer):
    """Validates the query params coming from the estimate-builder UI
    (dates, times, locations) before we hit theRentOS."""

    date_from = serializers.DateField()
    time_from = serializers.CharField(default='00:00')
    date_to = serializers.DateField()
    time_to = serializers.CharField(default='23:59')

    pickup_location_id = serializers.IntegerField()
    dropoff_location_id = serializers.IntegerField()

    vehicle_type = serializers.CharField(default='car')
    cooldown_hours = serializers.IntegerField(default=0, min_value=0)
    pre_start_cooldown_hours = serializers.IntegerField(default=0, min_value=0)
    include_unavailable = serializers.IntegerField(default=1)

    pickup_custom_payload = serializers.CharField(required=False, allow_blank=True, default='')
    dropoff_custom_payload = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_time_from(self, value):
        return self._validate_hhmm(value, 'time_from')

    def validate_time_to(self, value):
        return self._validate_hhmm(value, 'time_to')

    @staticmethod
    def _validate_hhmm(value, field_name):
        import re
        if not re.match(r'^\d{2}:\d{2}$', value):
            raise serializers.ValidationError(f'{field_name} must be in HH:MM format, e.g. "14:30"')
        return value

    def validate(self, attrs):
        if attrs['date_to'] < attrs['date_from']:
            raise serializers.ValidationError('date_to cannot be before date_from')
        return attrs


class AvailableVehiclesAPIView(APIView):
    """
    GET /api/vehicles/available/?date_from=2026-08-04&time_from=00:00
        &date_to=2026-08-04&time_to=02:30&pickup_location_id=6&dropoff_location_id=6

    Proxies the theRentOS 'New estimate' vehicle-availability lookup and
    returns pricing + availability per vehicle for the given window.
    """

    def get(self, request):
        return self._handle(request.query_params)

    def post(self, request):
        """Same lookup, but accepting a JSON body instead of query params
        (handy if the frontend wants to POST the whole estimate form)."""
        return self._handle(request.data)

    def _handle(self, raw_data):
        serializer = AvailableVehiclesRequestSerializer(data=raw_data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = fetch_available_vehicles(
                date_from=data['date_from'].isoformat(),
                time_from=data['time_from'],
                date_to=data['date_to'].isoformat(),
                time_to=data['time_to'],
                pickup_location_id=data['pickup_location_id'],
                dropoff_location_id=data['dropoff_location_id'],
                vehicle_type=data['vehicle_type'],
                cooldown_hours=data['cooldown_hours'],
                pre_start_cooldown_hours=data['pre_start_cooldown_hours'],
                include_unavailable=data['include_unavailable'],
                pickup_custom_payload=data['pickup_custom_payload'],
                dropoff_custom_payload=data['dropoff_custom_payload'],
                csv_path=f"available_vehicles_{data['date_from']}.csv",
            )
        except RuntimeError as e:
            # login failed / missing creds / CSRF token not found etc.
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response(
                {'error': f'Unexpected error contacting theRentOS: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result, status=status.HTTP_200_OK)
# Create your views here.



class CreateEstimateBookingAPIView(APIView):
    """
    API endpoint to create a vehicle booking estimate via theRentOS.
    """
    def post(self, request, *args, **kwargs):
        # Mandatory payload validation
        required_fields = [
            'customer_name', 'customer_phone', 'date_from', 
            'time_from', 'date_to', 'time_to', 
            'pickup_location_id', 'dropoff_location_id', 'cart_vehicle'
        ]
        
        missing_fields = [field for field in required_fields if field not in request.data]
        if missing_fields:
            return Response(
                {
                    'success': False, 
                    'error': f"Missing required fields: {', '.join(missing_fields)}"
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = create_estimate_booking(request.data)
            return Response(result, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
