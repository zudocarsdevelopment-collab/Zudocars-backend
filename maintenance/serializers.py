from rest_framework import serializers
from .models import ServiceType, ServiceRecord, MaintenanceSchedule
from django.db import transaction
from django.utils import timezone
from fleet.models import Vehicle
from .intervals import CHECKUP, SERVICE, complete_mileage_maintenance


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = '__all__'


class ServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = '__all__'
        read_only_fields = ['total_cost', 'created_at']

    def validate(self, attrs):
        for name in ('parts_cost', 'labor_cost'):
            if attrs.get(name, 0) < 0:
                raise serializers.ValidationError({name: 'Cost cannot be negative.'})
        if attrs.get('service_date', getattr(self.instance, 'service_date', None)) > timezone.localdate():
            raise serializers.ValidationError({'service_date': 'Completed maintenance cannot have a future date.'})
        return attrs

    def create(self, validated_data):
        validated_data['total_cost'] = validated_data.get('parts_cost', 0) + validated_data.get('labor_cost', 0)
        with transaction.atomic():
            vehicle = Vehicle.objects.select_for_update().get(pk=validated_data['car'].pk)
            record = super().create(validated_data)
            complete_mileage_maintenance(record, vehicle)
            return record

    def update(self, instance, validated_data):
        for field in ('car', 'service_type', 'odometer_reading', 'service_date'):
            if field in validated_data and validated_data[field] != getattr(instance, field):
                raise serializers.ValidationError({field: 'Maintenance mileage history cannot be changed. Log a new record instead.'})
        validated_data['total_cost'] = validated_data.get('parts_cost', instance.parts_cost) + validated_data.get('labor_cost', instance.labor_cost)
        return super().update(instance, validated_data)


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'

    def validate(self, attrs):
        due_date = attrs.get('due_date', getattr(self.instance, 'due_date', None))
        due_odometer = attrs.get('due_odometer', getattr(self.instance, 'due_odometer', None))
        if due_date is None and due_odometer is None:
            raise serializers.ValidationError('Set a due date or due odometer.')
        if self.instance and self.instance.service_type and self.instance.service_type.name in [CHECKUP, SERVICE]:
            raise serializers.ValidationError('Mileage reminders update automatically. Log a completed checkup or full service in Service History.')
        return attrs
