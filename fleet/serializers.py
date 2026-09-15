from rest_framework import serializers

from .models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            'id', 'external_id', 'plate_number', 'year', 'odometer',
            'category', 'sub_category', 'location_base', 'location_current',
            'vehicle_type', 'booking_type', 'hourly_rate', 'min_hours_rate',
            'fastag_charge', 'photo_url', 'vehicle_image', 'body_type',
            'fuel_type', 'transmission', 'seats', 'is_active', 'date_added',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'external_id': {'required': False},  # auto-filled on manual add, see view
        }

    def validate_external_id(self, value):
        qs = Vehicle.objects.filter(external_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A vehicle with this external_id already exists."
            )
        return value