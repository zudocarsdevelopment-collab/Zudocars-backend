from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('fleet', '0007_pickuphub_vehicle_pickup_hub')]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='daily_price',
            field=models.DecimalField(
                verbose_name='Daily price', max_digits=10, decimal_places=2,
                null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))],
                help_text='Rental price per 24 hours. Each started rental day is charged in full.',
            ),
        ),
    ]
