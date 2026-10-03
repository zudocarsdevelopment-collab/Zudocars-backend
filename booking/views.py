# yourapp/views.py (or a new yourapp/api/views.py)
#
# Requires: pip install djangorestframework
# and 'rest_framework' added to INSTALLED_APPS in settings.py.

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from django.db import transaction
from .models import Booking
from .Services_available_vehicles import fetch_available_vehicles
from .booking import create_estimate_booking
from fleet.models import Vehicle
from .Services import (
    fetch_estimates,
    TheRentOSAuthError,
    TheRentOSFetchError,
)
from .serializer import BookingSerializer, BookingCreateSerializer

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
    Also enriches each vehicle with fuel_type/transmission from the local
    fleet.models.Vehicle table, matched by plate number.
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
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            return Response(
                {'error': f'Unexpected error contacting theRentOS: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            result = self._enrich_with_local_specs(result)
        except Exception as e:
            # Don't fail the whole lookup just because local enrichment failed
            print(f"Local vehicle spec enrichment failed: {e}")

        return Response(result, status=status.HTTP_200_OK)

    def _enrich_with_local_specs(self, result):
        items = self._extract_list(result)

        plate_numbers = [item.get('asset_identifier') for item in items if item.get('asset_identifier')]
        local_vehicles = Vehicle.objects.filter(plate_number__in=plate_numbers)
        specs_by_plate = {
            v.plate_number: {'fuel_type': v.fuel_type, 'transmission': v.transmission}
            for v in local_vehicles
        }

        for item in items:
            specs = specs_by_plate.get(item.get('asset_identifier'))
            item['fuel_type'] = specs['fuel_type'] if specs else None
            item['transmission'] = specs['transmission'] if specs else None

        return result

    @staticmethod
    def _extract_list(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('data', 'vehicles', 'cart', 'results'):
                if isinstance(data.get(key), list):
                    return data[key]
        return []


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

        # Keep the remote vehicle ID intact, but validate a local vehicle snapshot.
        local_payload = dict(request.data)
        cart = local_payload.get('cart_vehicle')
        if not isinstance(cart, dict):
            vehicle = Vehicle.objects.filter(external_id=str(cart)).first()
            snapshot = local_payload.get('vehicle_snapshot', {})
            local_payload['cart_vehicle'] = {
                'id': cart,
                'asset_identifier': vehicle.plate_number if vehicle else snapshot.get('asset_identifier', ''),
                'name': vehicle.category if vehicle else snapshot.get('name', ''),
            }
        serializer = BookingCreateSerializer(data=local_payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plate = data['cart_vehicle']['asset_identifier']

        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    **{key: data[key] for key in (
                        'customer_name', 'customer_phone', 'customer_email',
                        'start_datetime', 'end_datetime', 'pickup_location_id',
                        'dropoff_location_id', 'pickup_custom_payload',
                        'dropoff_custom_payload', 'total_amount', 'currency', 'notes',
                        'cart_vehicle',
                    )},
                    vehicle=Vehicle.objects.filter(plate_number=plate).first(),
                    vehicle_plate_number=plate,
                )
                result = create_estimate_booking(request.data)
                if not isinstance(result, dict) or result.get('success') is False:
                    raise RuntimeError(result.get('error', 'Estimate creation failed.') if isinstance(result, dict) else 'Invalid estimate response.')
                booking.therentos_response = result
                booking.therentos_estimate_id = BookingCreateAPIView._extract_remote_id(result)
                booking.therentos_synced = True
                booking.save(update_fields=['therentos_response', 'therentos_estimate_id', 'therentos_synced', 'updated_at'])
            return Response({**result, 'success': True, 'booking': BookingSerializer(booking).data}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class TheRentOSEstimatesAPIView(APIView):
    """
    GET /api/therentos/estimates/?page=1&search=Zudo&status=&estimate_priority=
 
    Wraps theRentOS's server-rendered Estimates page and returns it as
    JSON, so your React dashboard can render it with a normal table
    component instead of an iframe.
    """
 
    # permission_classes = [IsAdminUser]  # enable once real auth is wired up
 
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        search = request.query_params.get("search", "")
        status_filter = request.query_params.get("status", "")
        priority = request.query_params.get("estimate_priority", "")
        force_refresh = request.query_params.get("refresh") == "1"
 
        try:
            data = fetch_estimates(
                page=page,
                search=search,
                status=status_filter,
                priority=priority,
                force_refresh=force_refresh,
            )
        except TheRentOSAuthError as exc:
            return Response(
                {"error": f"theRentOS authentication failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except TheRentOSFetchError as exc:
            return Response(
                {"error": f"theRentOS fetch failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
 
        return Response(data, status=status.HTTP_200_OK)
 

class BookingCreateAPIView(APIView):
    """
    POST /api/bookings/
 
    {
      "customer_name": "Asha K",
      "customer_phone": "9876543210",
      "date_from": "2026-08-04", "time_from": "09:00",
      "date_to": "2026-08-06",   "time_to": "18:00",
      "pickup_location_id": 6, "dropoff_location_id": 6,
      "cart_vehicle": {"asset_identifier": "KA01AB1234", ...},
      "total_amount": "7500.00",
      "sync_to_therentos": false
    }
 
    Saves the booking locally. If sync_to_therentos is true, it is also
    created in theRentOS; if that call fails, nothing is saved locally.
    """
 
    # permission_classes = [IsAuthenticated]
 
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
 
        plate = data["cart_vehicle"]["asset_identifier"]
 
        try:
            with transaction.atomic():
                # Lock rows for this plate so two requests can't double-book it
                clashes = (
                    Booking.objects.select_for_update()
                    .filter(
                        vehicle_plate_number=plate,
                        start_datetime__lt=data["end_datetime"],
                        end_datetime__gt=data["start_datetime"],
                    )
                    .exclude(status=Booking.Status.CANCELLED)
                )
                if clashes.exists():
                    return Response(
                        {"success": False,
                         "error": f"Vehicle {plate} is already booked for an overlapping period."},
                        status=status.HTTP_409_CONFLICT,
                    )
 
                booking = Booking.objects.create(
                    customer_name=data["customer_name"],
                    customer_phone=data["customer_phone"],
                    customer_email=data["customer_email"],
                    vehicle=Vehicle.objects.filter(plate_number=plate).first(),
                    vehicle_plate_number=plate,
                    start_datetime=data["start_datetime"],
                    end_datetime=data["end_datetime"],
                    pickup_location_id=data["pickup_location_id"],
                    dropoff_location_id=data["dropoff_location_id"],
                    pickup_custom_payload=data["pickup_custom_payload"],
                    dropoff_custom_payload=data["dropoff_custom_payload"],
                    total_amount=data["total_amount"],
                    currency=data["currency"],
                    notes=data["notes"],
                    cart_vehicle=data["cart_vehicle"],
                )
 
                if data["sync_to_therentos"]:
                    # Raises on failure -> whole transaction rolls back
                    remote = create_estimate_booking(request.data)
                    booking.therentos_response = remote if isinstance(remote, dict) else {"result": remote}
                    booking.therentos_estimate_id = self._extract_remote_id(remote)
                    booking.therentos_synced = True
                    booking.save(update_fields=[
                        "therentos_response", "therentos_estimate_id",
                        "therentos_synced", "updated_at",
                    ])
 
        except Exception as e:
            return Response(
                {"success": False, "error": f"Could not create booking: {e}"},
                status=status.HTTP_502_BAD_GATEWAY if data["sync_to_therentos"]
                else status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
 
        return Response(
            {"success": True, "booking": BookingSerializer(booking).data},
            status=status.HTTP_201_CREATED,
        )
 
    @staticmethod
    def _extract_remote_id(remote):
        """Best-effort: adjust the keys to match what create_estimate_booking returns."""
        if isinstance(remote, dict):
            for key in ("estimate_id", "id", "booking_id"):
                if remote.get(key):
                    return str(remote[key])
            inner = remote.get("data")
            if isinstance(inner, dict):
                for key in ("estimate_id", "id", "booking_id"):
                    if inner.get(key):
                        return str(inner[key])
        return ""
 
 
class BookingListAPIView(APIView):
    """GET /api/bookings/?status=confirmed&plate=KA01AB1234"""
 
    def get(self, request):
        qs = Booking.objects.all()
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("plate"):
            qs = qs.filter(vehicle_plate_number=request.query_params["plate"])
        return Response(BookingSerializer(qs[:200], many=True).data)
 
 
class BookingDetailAPIView(APIView):
    """GET /api/bookings/<reference>/"""
 
    def get(self, request, reference):
        try:
            booking = Booking.objects.get(reference=reference)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingSerializer(booking).data)
