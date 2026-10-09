from django.db import transaction, OperationalError
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError
from fleet.models import Vehicle, PickupHub
from fleet.serializers import VehicleSerializer
from authenticator.authentication import DashboardAuthentication
from .models import Booking
from .serializer import AvailabilitySerializer, BookingCreateSerializer, BookingSerializer, BookingUpdateSerializer
from .booking import overlapping_bookings, quote, booking_result


class AvailableVehiclesAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return self.lookup(request.query_params, request)

    def post(self, request):
        return self.lookup(request.data, request)

    def lookup(self, payload, request):
        serializer = AvailabilitySerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        start, end = data['start_datetime'], data['end_datetime']
        blocked = set(Booking.objects.filter(status__in=['pending', 'confirmed'], start_datetime__lt=end, end_datetime__gt=start).values_list('vehicle_id', flat=True))
        rows = []
        for vehicle in Vehicle.objects.filter(is_active=True, pickup_hub_id=data['pickup_location_id'], pickup_hub__is_active=True, vehicle_type__iexact=data['vehicle_type']):
            pricing = quote(vehicle, start, end)
            available = vehicle.pk not in blocked and pricing is not None
            if not available and not data['include_unavailable']:
                continue
            row = dict(VehicleSerializer(vehicle, context={'request': request}).data)
            row.update(name=vehicle.category, asset_identifier=vehicle.plate_number,
                       available_stock=int(available), total_incl_tax=str(pricing['rental']) if pricing else None,
                       delivery_amount=str(pricing['delivery']) if pricing else None,
                       total_amount=str(pricing['total']) if pricing else None)
            rows.append(row)
        return Response({'vehicles': rows, 'total': len(rows)})


class CreateEstimateBookingAPIView(APIView):
    permission_classes = [AllowAny]

    def handle_exception(self, exc):
        if isinstance(exc, OperationalError) and 'locked' in str(exc).lower():
            return Response({'error': 'Another reservation is being processed. Please retry.'}, status=409)
        return super().handle_exception(exc)

    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            vehicle = get_object_or_404(Vehicle.objects.select_for_update(), pk=data['cart_vehicle'], is_active=True)
            if vehicle.pickup_hub_id != data['pickup_location_id']:
                raise ValidationError('This vehicle belongs to a different pickup hub.')
            if not PickupHub.objects.filter(pk=data['pickup_location_id'], is_active=True).exists():
                raise ValidationError('The pickup hub is unavailable.')
            dropoff = get_object_or_404(PickupHub, pk=data['dropoff_location_id'], is_active=True)
            data['pickup_custom_payload'] = vehicle.pickup_hub.name
            data['dropoff_custom_payload'] = dropoff.name
            start, end = data['start_datetime'], data['end_datetime']
            if overlapping_bookings(vehicle, start, end).exists():
                return Response({'error': 'This vehicle is already reserved for the selected dates.'}, status=409)
            pricing = quote(vehicle, start, end)
            if pricing is None:
                raise ValidationError('This vehicle has no valid rental rate. Please contact our team.')
            booking = Booking.objects.create(
                vehicle=vehicle, vehicle_plate_number=vehicle.plate_number,
                cart_vehicle={'id': vehicle.pk, 'name': vehicle.category, 'asset_identifier': vehicle.plate_number},
                start_datetime=start, end_datetime=end,
                rental_amount=pricing['rental'], delivery_amount=pricing['delivery'], total_amount=pricing['total'],
                **{key: data[key] for key in ('customer_name', 'customer_phone', 'customer_email',
                    'pickup_location_id', 'dropoff_location_id', 'pickup_custom_payload', 'dropoff_custom_payload', 'notes')},
            )
        return Response(booking_result(booking), status=201)


class BookingListAPIView(APIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(BookingSerializer(Booking.objects.all(), many=True).data)


class BookingDetailAPIView(BookingListAPIView):
    def get(self, request, reference):
        return Response(BookingSerializer(get_object_or_404(Booking, reference=reference)).data)

    def patch(self, request, reference):
        serializer = BookingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            initial = get_object_or_404(Booking, reference=reference)
            Vehicle.objects.select_for_update().get(pk=initial.vehicle_id)
            booking = Booking.objects.select_for_update().get(pk=initial.pk)
            transitions = {'pending': {'confirmed', 'cancelled'}, 'confirmed': {'completed', 'cancelled'}, 'completed': set(), 'cancelled': set()}
            target = data.get('status', booking.status)
            if target != booking.status and target not in transitions[booking.status]:
                raise ValidationError('This booking status change is not allowed.')
            for key, value in data.items():
                setattr(booking, key, value)
            booking.save()
        return Response(BookingSerializer(booking).data)
