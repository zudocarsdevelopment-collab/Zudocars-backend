from django.db import models
from fleet.models import Vehicle
# Create your models here.


class ServiceType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    
class ServiceRecord(models.Model):
    car = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="service_records"
    )

    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.SET_NULL,
        null=True
    )

    service_date = models.DateField()
    odometer_reading = models.PositiveIntegerField()

    service_center = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    parts_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    labor_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    invoice = models.FileField(
        upload_to="service_invoices/", blank=True, null=True
    )

    next_service_date = models.DateField(null=True, blank=True)
    next_service_odometer = models.PositiveIntegerField(
        null=True, blank=True
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MaintenanceSchedule(models.Model):
    car = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="maintenance_schedules"
    )

    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.SET_NULL,
        null=True
    )

    due_date = models.DateField(null=True, blank=True)
    due_odometer = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("scheduled", "Scheduled"),
            ("due", "Due"),
            ("overdue", "Overdue"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="scheduled"
    )

    notes = models.TextField(blank=True)