from django.db import migrations, models
import django.db.models.deletion


def import_customers(apps, schema_editor):
    Customer = apps.get_model('booking', 'Customer')
    Booking = apps.get_model('booking', 'Booking')
    alias = schema_editor.connection.alias
    for booking in Booking.objects.using(alias).order_by('created_at', 'pk').iterator():
        digits = ''.join(character for character in booking.customer_phone if character in '0123456789')
        phone = digits[2:] if len(digits) == 12 and digits.startswith('91') else digits
        if not phone:
            continue
        customer, _ = Customer.objects.using(alias).get_or_create(phone=phone, defaults={'name': booking.customer_name.strip(), 'email': booking.customer_email.strip()})
        customer.name = booking.customer_name.strip()
        if booking.customer_email.strip():
            customer.email = booking.customer_email.strip()
        customer.save(using=alias)
        Booking.objects.using(alias).filter(pk=booking.pk).update(customer_id=customer.pk)


class Migration(migrations.Migration):
    dependencies = [('booking', '0002_booking_return_details')]
    operations = [
        migrations.CreateModel(name='Customer', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=150)),
            ('phone', models.CharField(max_length=15, unique=True)),
            ('email', models.EmailField(blank=True, max_length=254)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ], options={'ordering': ['name', 'pk']}),
        migrations.AddField(model_name='booking', name='customer', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bookings', to='booking.customer')),
        migrations.RunPython(import_customers, migrations.RunPython.noop),
    ]
