from decimal import Decimal, ROUND_CEILING
from django.conf import settings
from django.db import transaction
from .models import Booking


def overlapping_bookings(vehicle, start, end):
    # A scheduled return time is an estimate. Release the vehicle only after
    # the operator records its return or cancels the reservation.
    return Booking.objects.filter(vehicle=vehicle, status__in=['pending', 'confirmed'])


def quote(vehicle, start, end):
    hours = (Decimal(str((end - start).total_seconds())) / Decimal('3600')).to_integral_value(rounding=ROUND_CEILING)
    if vehicle.daily_price is not None:
        if vehicle.daily_price <= 0:
            return None
        days = (hours / Decimal('24')).to_integral_value(rounding=ROUND_CEILING)
        rental = (days * vehicle.daily_price).quantize(Decimal('.01'))
    else:
        # Preserve existing quotes until a daily price is entered.
        if vehicle.hourly_rate is None or vehicle.hourly_rate <= 0:
            return None
        rental = max(hours * vehicle.hourly_rate, vehicle.min_hours_rate or Decimal('0')).quantize(Decimal('.01'))
    delivery = Decimal(str(getattr(settings, 'BOOKING_DELIVERY_AMOUNT', '1200.00')))
    return {'hours': int(hours), 'rental': rental, 'delivery': delivery, 'total': rental + delivery}


def booking_result(booking):
    from .serializer import BookingSerializer
    return {
        'success': True, 'booking': BookingSerializer(booking).data,
        'reference': booking.reference, 'estimate_id': booking.pk, 'status': booking.status,
        'customer_name': booking.customer_name,
        'estimate': {
            'total_booking_hours': (booking.end_datetime - booking.start_datetime).total_seconds() / 3600,
            'vehicle': {'subtotal': float(booking.rental_amount)},
            'reposition_charges': [{'name': 'Delivery and return', 'total_estimate': float(booking.delivery_amount), 'tax_amt': 0}],
            'total_final': float(booking.total_amount), 'total_deposit_estimate': 5000,
        },
    }


@transaction.atomic
def create_manual_booking(data, *, validate_only=False, instance=None):
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError
    from fleet.models import Vehicle, PickupHub

    vehicle_ids = [data['cart_vehicle']]
    if instance is not None:
        vehicle_ids.append(Booking.objects.get(pk=instance.pk).vehicle_id)
    vehicles = {row.pk: row for row in Vehicle.objects.select_for_update().filter(pk__in=vehicle_ids).order_by('pk')}
    vehicle = vehicles.get(data['cart_vehicle'])
    if instance is not None:
        instance = Booking.objects.select_for_update().get(pk=instance.pk)
    if vehicle is None:
        raise ValidationError('Select a valid vehicle.')
    start, end = data['start_datetime'], data['end_datetime']
    historical = end <= timezone.now()
    if instance and instance.status == 'completed' and not historical:
        raise ValidationError('A completed booking must have a return date in the past.')
    if instance and instance.return_odometer is not None and instance.vehicle_id != vehicle.pk:
        raise ValidationError('The vehicle cannot be changed after return mileage has been recorded.')
    if vehicle.pickup_hub_id != data['pickup_location_id']:
        raise ValidationError('Select the pickup location belonging to this vehicle.')
    hubs = {hub.pk: hub for hub in PickupHub.objects.filter(pk__in=[data['pickup_location_id'], data['dropoff_location_id']])}
    if data['dropoff_location_id'] not in hubs:
        raise ValidationError('Select a valid return location.')
    conflicts = Booking.objects.filter(vehicle=vehicle).exclude(status='cancelled').filter(start_datetime__lt=end, end_datetime__gt=start)
    active = overlapping_bookings(vehicle, start, end)
    if instance:
        conflicts = conflicts.exclude(pk=instance.pk)
        active = active.exclude(pk=instance.pk)
    schedule_changed = instance is None or (instance.vehicle_id, instance.start_datetime, instance.end_datetime) != (vehicle.pk, start, end)
    if schedule_changed and (not instance or instance.status != 'cancelled') and (conflicts.exists() or (not historical and active.exists())):
        raise ValidationError('This vehicle already has a booking for this period or is awaiting return.')
    if validate_only:
        return None
    if instance:
        for key in ('customer_name', 'customer_phone', 'customer_email', 'pickup_location_id', 'dropoff_location_id', 'notes', 'rental_amount', 'delivery_amount'):
            setattr(instance, key, data[key])
        if instance.vehicle_id != vehicle.pk:
            instance.pickup_odometer = vehicle.odometer if instance.status == 'confirmed' else None
        instance.vehicle = vehicle
        instance.vehicle_plate_number = vehicle.plate_number
        instance.cart_vehicle = {'id': vehicle.pk, 'name': vehicle.category, 'asset_identifier': vehicle.plate_number}
        instance.start_datetime, instance.end_datetime = start, end
        instance.pickup_custom_payload = hubs[data['pickup_location_id']].name
        instance.dropoff_custom_payload = hubs[data['dropoff_location_id']].name
        instance.total_amount = data['rental_amount'] + data['delivery_amount']
        instance.save()
        return instance
    return Booking.objects.create(
        vehicle=vehicle, vehicle_plate_number=vehicle.plate_number,
        cart_vehicle={'id': vehicle.pk, 'name': vehicle.category, 'asset_identifier': vehicle.plate_number},
        start_datetime=start, end_datetime=end, status='completed' if historical else 'confirmed',
        returned_at=end if historical else None,
        pickup_odometer=None if historical else vehicle.odometer,
        rental_amount=data['rental_amount'], delivery_amount=data['delivery_amount'],
        total_amount=data['rental_amount'] + data['delivery_amount'],
        pickup_custom_payload=hubs[data['pickup_location_id']].name,
        dropoff_custom_payload=hubs[data['dropoff_location_id']].name,
        **{key: data[key] for key in ('customer_name', 'customer_phone', 'customer_email', 'pickup_location_id', 'dropoff_location_id', 'notes')},
    )
