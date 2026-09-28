# yourapp/models.py  (add this next to your other models)

import uuid

from django.db import models

from fleet.models import Vehicle


def generate_booking_reference():
    return f"BK-{uuid.uuid4().hex[:8].upper()}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    reference = models.CharField(
        max_length=20, unique=True, default=generate_booking_reference, editable=False
    )

    # Customer
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30)
    customer_email = models.EmailField(blank=True)

    # Vehicle (FK is optional; the plate is kept as a snapshot so the record
    # stays meaningful even if the vehicle is later edited or deleted)
    vehicle = models.ForeignKey(
        Vehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    vehicle_plate_number = models.CharField(max_length=30, blank=True, db_index=True)

    # Rental window
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField(db_index=True)

    # theRentOS location ids
    pickup_location_id = models.PositiveIntegerField()
    dropoff_location_id = models.PositiveIntegerField()
    pickup_custom_payload = models.CharField(max_length=255, blank=True)
    dropoff_custom_payload = models.CharField(max_length=255, blank=True)

    # Pricing
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)

    # theRentOS sync data
    therentos_estimate_id = models.CharField(max_length=64, blank=True)
    therentos_synced = models.BooleanField(default=False)
    cart_vehicle = models.JSONField(default=dict, blank=True)
    therentos_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vehicle_plate_number", "start_datetime", "end_datetime"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.customer_name} ({self.vehicle_plate_number or 'no vehicle'})"