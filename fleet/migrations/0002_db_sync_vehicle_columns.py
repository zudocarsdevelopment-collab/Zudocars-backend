from django.db import migrations


def rename_vehicle_columns(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        return

    cursor = schema_editor.connection.cursor()

    def has_column(table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def add_column_sql(table, column_sql):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")

    table = 'fleet_vehicle'

    rename_pairs = [
        ('identifier', 'external_id'),
        ('model_year', 'year'),
        ('photo', 'photo_url'),
        ('location', 'location_current'),
        ('minimum_charge', 'min_hours_rate'),
        ('fastag_balance', 'fastag_charge'),
        ('added_on', 'date_added'),
    ]

    for old, new in rename_pairs:
        if has_column(table, old) and not has_column(table, new):
            cursor.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")

    if not has_column(table, 'location_base'):
        add_column_sql(table, "location_base varchar(100) NOT NULL DEFAULT ''")
    if not has_column(table, 'vehicle_image'):
        add_column_sql(table, "vehicle_image varchar(100)")
    if not has_column(table, 'body_type'):
        add_column_sql(table, "body_type varchar(50) NOT NULL DEFAULT ''")
    if not has_column(table, 'fuel_type'):
        add_column_sql(table, "fuel_type varchar(50) NOT NULL DEFAULT ''")
    if not has_column(table, 'transmission'):
        add_column_sql(table, "transmission varchar(50) NOT NULL DEFAULT ''")
    if not has_column(table, 'seats'):
        add_column_sql(table, "seats integer")
    if not has_column(table, 'created_at'):
        add_column_sql(table, "created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP")


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(rename_vehicle_columns, reverse_code=migrations.RunPython.noop),
    ]
