from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('booking', '0003_customer_records')]

    operations = [
        migrations.AddField(model_name='booking', name='discount_type', field=models.CharField(choices=[('flat', 'Flat amount'), ('percentage', 'Percentage')], default='flat', max_length=10)),
        migrations.AddField(model_name='booking', name='discount_value', field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name='booking', name='discount_amount', field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
    ]
