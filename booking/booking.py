from decimal import Decimal, ROUND_CEILING
from django.conf import settings
from .models import Booking


def overlapping_bookings(vehicle, start, end):
    return Booking.objects.filter(vehicle=vehicle, status__in=['pending', 'confirmed'],
                                  start_datetime__lt=end, end_datetime__gt=start)


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
            'total_final': float(booking.total_amount), 'total_deposit_estimate': 0,
        },
    }
