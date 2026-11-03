from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'


class AvailabilitySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    time_from = serializers.TimeField(input_formats=['%H:%M'])
    date_to = serializers.DateField()
    time_to = serializers.TimeField(input_formats=['%H:%M'])
    pickup_location_id = serializers.IntegerField(min_value=1)
    dropoff_location_id = serializers.IntegerField(min_value=1)
    vehicle_type = serializers.CharField(default='car')
    include_unavailable = serializers.BooleanField(default=False)

    def validate(self, attrs):
        tz = ZoneInfo(getattr(settings, 'BOOKING_TIME_ZONE', 'Asia/Kolkata'))
        attrs['start_datetime'] = timezone.make_aware(datetime.combine(attrs['date_from'], attrs['time_from']), tz)
        attrs['end_datetime'] = timezone.make_aware(datetime.combine(attrs['date_to'], attrs['time_to']), tz)
        if attrs['end_datetime'] <= attrs['start_datetime']:
            raise serializers.ValidationError('Return time must be after pickup time.')
        if not self.context.get('manual_booking') and attrs['start_datetime'] <= timezone.now():
            raise serializers.ValidationError('Pickup time must be in the future.')
        return attrs


class BookingCreateSerializer(AvailabilitySerializer):
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.RegexField(r'^\+?[0-9]{10,15}$')
    customer_email = serializers.EmailField(required=False, allow_blank=True, default='')
    cart_vehicle = serializers.IntegerField(min_value=1)
    pickup_custom_payload = serializers.CharField(max_length=500, allow_blank=True, default='')
    dropoff_custom_payload = serializers.CharField(max_length=500, allow_blank=True, default='')
    notes = serializers.CharField(max_length=5000, allow_blank=True, default='')


class ManualBookingSerializer(BookingCreateSerializer):
    discount_type = serializers.ChoiceField(choices=['flat', 'percentage'], default='flat')
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=Decimal('0'))
    time_from = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    time_to = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    rental_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    delivery_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if 'delivery_amount' not in attrs:
            from fleet.models import Vehicle
            vehicle = Vehicle.objects.select_related('pickup_hub__location').filter(pk=attrs['cart_vehicle']).first()
            if vehicle is None:
                raise serializers.ValidationError({'cart_vehicle': 'Select a valid vehicle.'})
            from django.conf import settings
            attrs['delivery_amount'] = vehicle.pickup_hub.effective_booking_amount if vehicle.pickup_hub_id else Decimal(str(getattr(settings, 'BOOKING_DELIVERY_AMOUNT', '1200.00')))
        value = attrs['discount_value']
        if attrs['discount_type'] == 'percentage' and value > 100:
            raise serializers.ValidationError({'discount_value': 'Percentage must be between 0 and 100.'})
        discount = (attrs['rental_amount'] * value / Decimal('100') if attrs['discount_type'] == 'percentage' else value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if discount > attrs['rental_amount']:
            raise serializers.ValidationError({'discount_value': 'Discount cannot exceed the rental amount.'})
        attrs['discount_amount'] = discount
        if attrs['rental_amount'] - discount + attrs['delivery_amount'] > Decimal('99999999.99'):
            raise serializers.ValidationError('Total amount must not exceed 99,999,999.99.')
        return attrs


class BookingUpdateSerializer(serializers.Serializer):
    return_odometer = serializers.IntegerField(min_value=0, required=False)
    return_notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    status = serializers.ChoiceField(choices=Booking.STATUS, required=False)
    assigned_email = serializers.EmailField(allow_blank=True, required=False)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)


class ManualAvailabilitySerializer(AvailabilitySerializer):
    time_from = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    time_to = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    pickup_location_id = serializers.IntegerField(required=False)
    dropoff_location_id = serializers.IntegerField(required=False)
    exclude_reference = serializers.CharField(required=False, allow_blank=True, default='', max_length=20)
