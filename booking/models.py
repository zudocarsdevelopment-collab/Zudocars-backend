import uuid
from django.db import models


def booking_reference():
    return 'ZUDO-' + uuid.uuid4().hex[:12].upper()


class Booking(models.Model):
    STATUS = [('pending', 'Pending'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled'), ('completed', 'Completed')]
    reference = models.CharField(max_length=20, unique=True, default=booking_reference, editable=False)
    vehicle = models.ForeignKey('fleet.Vehicle', on_delete=models.PROTECT, related_name='bookings')
    vehicle_plate_number = models.CharField(max_length=20)
    cart_vehicle = models.JSONField(default=dict)
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30)
    customer_email = models.EmailField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    pickup_location_id = models.PositiveIntegerField()
    dropoff_location_id = models.PositiveIntegerField()
    pickup_custom_payload = models.CharField(max_length=500, blank=True)
    dropoff_custom_payload = models.CharField(max_length=500, blank=True)
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1200)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=12, choices=STATUS, default='pending')
    assigned_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['vehicle', 'start_datetime', 'end_datetime'])]
        constraints = [models.CheckConstraint(condition=models.Q(end_datetime__gt=models.F('start_datetime')), name='booking_positive_duration')]
