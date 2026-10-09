from datetime import datetime
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
        if attrs['start_datetime'] <= timezone.now():
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


class BookingUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.STATUS, required=False)
    assigned_email = serializers.EmailField(allow_blank=True, required=False)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
