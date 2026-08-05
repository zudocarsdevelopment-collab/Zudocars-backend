# yourapp/models.py
from django.db import models


class Vehicle(models.Model):
    external_id = models.CharField(
        max_length=50, unique=True,
        help_text="theRentOS asset ID, used to avoid duplicates on re-sync"
    )
    plate_number = models.CharField(max_length=20, db_index=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    odometer = models.PositiveIntegerField(default=0)

    category = models.CharField(max_length=100, blank=True)
    sub_category = models.CharField(max_length=100, blank=True)

    location_base = models.CharField(max_length=100, blank=True)
    location_current = models.CharField(max_length=100, blank=True)

    vehicle_type = models.CharField(max_length=50, blank=True)   # e.g. "Car"
    booking_type = models.CharField(max_length=50, blank=True)   # e.g. "Hourly (Min)"

    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_hours_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fastag_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    photo_url = models.URLField(max_length=500, blank=True)
    vehicle_image=models.ImageField(upload_to='vehicle_images/', null=True, blank=True)
    body_type = models.CharField(max_length=50, blank=True)
    fuel_type = models.CharField(max_length=50, blank=True)
    transmission = models.CharField(max_length=50, blank=True)
    seats = models.PositiveSmallIntegerField(null=True, blank=True)

    date_added = models.CharField(max_length=50, blank=True)  # or DateField if you parse it

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.plate_number} ({self.category})"