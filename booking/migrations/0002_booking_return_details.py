from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('booking', '0001_initial')]
    operations = [
        migrations.AddField(model_name='booking', name='pickup_odometer', field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name='booking', name='return_odometer', field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name='booking', name='return_notes', field=models.TextField(blank=True)),
        migrations.AddField(model_name='booking', name='returned_at', field=models.DateTimeField(null=True, blank=True)),
    ]
