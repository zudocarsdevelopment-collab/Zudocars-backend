from django.db import migrations


def connect_existing_hubs(apps, schema_editor):
    Vehicle = apps.get_model('fleet', 'Vehicle')
    Hub = apps.get_model('fleet', 'PickupHub')
    database = schema_editor.connection.alias
    for vehicle in Vehicle.objects.using(database).filter(pickup_hub__isnull=True).exclude(location_base='').iterator():
        name = vehicle.location_base.strip()
        if name:
            hub, _ = Hub.objects.using(database).get_or_create(name=name)
            vehicle.pickup_hub_id = hub.pk
            vehicle.save(using=database, update_fields=['pickup_hub'])


class Migration(migrations.Migration):
    dependencies = [('fleet', '0007_pickuphub_vehicle_pickup_hub')]
    operations = [migrations.RunPython(connect_existing_hubs, migrations.RunPython.noop)]
