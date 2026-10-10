from django.db import transaction
from django.db.models import Max
from fleet.models import Vehicle
from .models import ServiceType, ServiceRecord, MaintenanceSchedule

CHECKUP = 'Checkup (5,000 km)'
SERVICE = 'Full service (10,000 km)'


def sync_vehicle_maintenance(vehicle):
    """Keep one active mileage reminder per interval; caller locks the vehicle."""
    for name, interval, completed_types in (
        (CHECKUP, 5000, [CHECKUP, SERVICE]),
        (SERVICE, 10000, [SERVICE]),
    ):
        kind, _ = ServiceType.objects.get_or_create(name=name)
        last = ServiceRecord.objects.filter(car=vehicle, service_type__name__in=completed_types).aggregate(
            reading=Max('odometer_reading'))['reading'] or 0
        due = last + interval
        status = 'overdue' if vehicle.odometer > due else 'due' if vehicle.odometer == due else 'scheduled'
        active = MaintenanceSchedule.objects.filter(car=vehicle, service_type=kind).exclude(status__in=['completed', 'cancelled'])
        schedule = active.order_by('pk').first()
        if schedule:
            active.exclude(pk=schedule.pk).update(status='cancelled')
            schedule.due_odometer = due
            schedule.status = status
            schedule.save(update_fields=['due_odometer', 'status'])
        else:
            MaintenanceSchedule.objects.create(car=vehicle, service_type=kind, due_odometer=due, status=status,
                                               notes=f'Every {interval:,} km. Log completed maintenance to reset the interval.')


def refresh_mileage_schedules():
    for pk in Vehicle.objects.values_list('pk', flat=True).iterator():
        with transaction.atomic():
            sync_vehicle_maintenance(Vehicle.objects.select_for_update().get(pk=pk))


def complete_mileage_maintenance(record, vehicle):
    name = record.service_type.name if record.service_type else ''
    types = [CHECKUP, SERVICE] if name == SERVICE else [CHECKUP] if name == CHECKUP else []
    if types:
        MaintenanceSchedule.objects.filter(car=vehicle, service_type__name__in=types,
                                           due_odometer__lte=record.odometer_reading).exclude(
            status__in=['completed', 'cancelled']).update(status='completed')
    vehicle.odometer = max(vehicle.odometer, record.odometer_reading)
    vehicle.save(update_fields=['odometer', 'updated_at'])
    sync_vehicle_maintenance(vehicle)
