from django.db import migrations


def ensure_plate_number(apps, schema_editor):
    Vehicle = apps.get_model('fleet', 'Vehicle')
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name for column in schema_editor.connection.introspection.get_table_description(
                cursor, Vehicle._meta.db_table
            )
        }
    if 'plate_number' not in columns:
        field = Vehicle._meta.get_field('plate_number').clone()
        field.set_attributes_from_name('plate_number')
        field.model = Vehicle
        field.default = ''
        schema_editor.add_field(Vehicle, field)


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0002_db_sync_vehicle_columns'),
    ]

    operations = [
        # The current initial migration already includes this field. Repair
        # older databases only; do not add it twice on a fresh installation.
        migrations.RunPython(ensure_plate_number, reverse_code=migrations.RunPython.noop),
    ]
