from rest_framework import serializers
from django.utils import timezone
from .models import Payment, Expense, accounting_date
from booking.models import Booking


class EntrySerializer(serializers.ModelSerializer):
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Enter an amount greater than zero.')
        return value

    def validate_date(self, value):
        if value > accounting_date():
            raise serializers.ValidationError('Recorded transactions cannot have a future date.')
        return value

    class Meta:
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'voided_at', 'voided_by', 'void_reason']


class PaymentSerializer(EntrySerializer):
    booking = serializers.SlugRelatedField(slug_field='reference', queryset=Booking.objects.all())

    class Meta(EntrySerializer.Meta):
        model = Payment


class ExpenseSerializer(EntrySerializer):
    class Meta(EntrySerializer.Meta):
        model = Expense
