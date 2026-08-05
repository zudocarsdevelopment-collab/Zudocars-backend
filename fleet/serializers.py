from rest_framework import serializers

from .models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            'id',
            'external_id',
            'plate_number',
            'year',
            'odometer',
            'category',
            'sub_category',
            'location_base',
            'location_current',
            'vehicle_type',
            'booking_type',
            'hourly_rate',
            'min_hours_rate',
            'fastag_charge',
            'photo_url',
            'vehicle_image',
            'body_type',
            'fuel_type',
            'transmission',
            'seats',
            'date_added',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
