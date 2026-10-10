from rest_framework import serializers
import uuid

from .models import Vehicle, PickupHub


class VehicleSerializer(serializers.ModelSerializer):
    pickup_hub_name = serializers.CharField(source='pickup_hub.name', read_only=True, default='')
    def create(self, validated_data):
        if not validated_data.get('external_id'):
            validated_data['external_id'] = 'ZUDO-' + uuid.uuid4().hex
        return super().create(validated_data)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'external_id', 'plate_number', 'year', 'odometer',
            'category', 'sub_category', 'location_base', 'location_current',
            'vehicle_type', 'booking_type', 'daily_price', 'hourly_rate', 'min_hours_rate',
            'fastag_charge', 'photo_url', 'vehicle_image', 'body_type',
            'fuel_type', 'transmission', 'seats', 'is_active', 'date_added',
            'created_at', 'updated_at',
            'pickup_hub', 'pickup_hub_name',
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

    def validate_pickup_hub(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError('Choose an active pickup hub.')
        return value


class PickupHubSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupHub
        fields = ['id', 'name', 'address', 'city', 'phone', 'is_active']
