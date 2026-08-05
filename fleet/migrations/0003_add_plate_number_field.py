from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0002_db_sync_vehicle_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='plate_number',
            field=models.CharField(default='', max_length=20, db_index=True),
            preserve_default=False,
        ),
    ]
