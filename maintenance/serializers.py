from rest_framework import serializers
from .models import ServiceType, ServiceRecord, MaintenanceSchedule


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
        return attrs

    def create(self, validated_data):
        validated_data['total_cost'] = validated_data.get('parts_cost', 0) + validated_data.get('labor_cost', 0)
        return super().create(validated_data)

    def update(self, instance, validated_data):
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
        return attrs
