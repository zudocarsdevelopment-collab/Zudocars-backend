from django.db import models


class ServiceType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ServiceRecord(models.Model):
    car = models.ForeignKey('fleet.Vehicle', on_delete=models.PROTECT, related_name='service_records')
    service_type = models.ForeignKey(ServiceType, null=True, blank=True, on_delete=models.SET_NULL)
    service_date = models.DateField()
    odometer_reading = models.PositiveIntegerField()
    service_center = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    parts_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    invoice = models.FileField(upload_to='service_invoices/', null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    next_service_odometer = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-service_date', '-id']


class MaintenanceSchedule(models.Model):
    STATUS = [(s, s.title()) for s in ('scheduled', 'due', 'overdue', 'completed', 'cancelled')]
    car = models.ForeignKey('fleet.Vehicle', on_delete=models.PROTECT, related_name='maintenance_schedules')
    service_type = models.ForeignKey(ServiceType, null=True, blank=True, on_delete=models.SET_NULL)
    due_date = models.DateField(null=True, blank=True)
    due_odometer = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='scheduled')
    notes = models.TextField(blank=True)
