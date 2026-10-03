 
import re
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
 
from fleet.models import Vehicle
from .booking import create_estimate_booking
from .models import Booking
 
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

class BookingSerializer(serializers.ModelSerializer):
    """Read serializer: what the API returns."""
 
    class Meta:
        model = Booking
        fields = [
            "id", "reference", "status",
            "customer_name", "customer_phone", "customer_email",
            "vehicle", "vehicle_plate_number",
            "start_datetime", "end_datetime",
            "pickup_location_id", "dropoff_location_id",
            "pickup_custom_payload", "dropoff_custom_payload",
            "total_amount", "currency", "notes",
            "therentos_estimate_id", "therentos_synced", "cart_vehicle",
            "created_at", "updated_at",
        ]
        read_only_fields = fields
 
 
class BookingCreateSerializer(serializers.Serializer):
    """Write serializer: same field names your estimate form already sends."""
 
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.CharField(max_length=30)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
 
    date_from = serializers.DateField()
    time_from = serializers.CharField(default="00:00")
    date_to = serializers.DateField()
    time_to = serializers.CharField(default="23:59")
 
    pickup_location_id = serializers.IntegerField(min_value=1)
    dropoff_location_id = serializers.IntegerField(min_value=1)
    pickup_custom_payload = serializers.CharField(required=False, allow_blank=True, default="")
    dropoff_custom_payload = serializers.CharField(required=False, allow_blank=True, default="")
 
    # The vehicle object picked from the available-vehicles response.
    # Must contain "asset_identifier" (the plate number).
    cart_vehicle = serializers.DictField()
 
    total_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, default=None
    )
    currency = serializers.CharField(max_length=3, default="INR")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
 
    # Also push this booking to theRentOS as an estimate
    sync_to_therentos = serializers.BooleanField(default=False)
 
    def _check_hhmm(self, value, name):
        if not HHMM.match(value):
            raise serializers.ValidationError(f'{name} must be HH:MM, e.g. "14:30"')
        return value
 
    def validate_time_from(self, value):
        return self._check_hhmm(value, "time_from")
 
    def validate_time_to(self, value):
        return self._check_hhmm(value, "time_to")
 
    def validate_cart_vehicle(self, value):
        if not value.get("asset_identifier"):
            raise serializers.ValidationError("cart_vehicle must include 'asset_identifier'.")
        return value
 
    def validate(self, attrs):
        tz = timezone.get_current_timezone()
 
        def combine(d, t):
            naive = datetime.strptime(f"{d.isoformat()} {t}", "%Y-%m-%d %H:%M")
            return timezone.make_aware(naive, tz)
 
        start = combine(attrs["date_from"], attrs["time_from"])
        end = combine(attrs["date_to"], attrs["time_to"])
        if end <= start:
            raise serializers.ValidationError("The end date/time must be after the start date/time.")
 
        attrs["start_datetime"] = start
        attrs["end_datetime"] = end
        return attrs
