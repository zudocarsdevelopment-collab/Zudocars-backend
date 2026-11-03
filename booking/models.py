import uuid
from django.db import models
from django.db import transaction


def normalize_customer_phone(value):
    digits = ''.join(character for character in value if character in '0123456789')
    return digits[2:] if len(digits) == 12 and digits.startswith('91') else digits


class Customer(models.Model):
    name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'pk']

    def __str__(self):
        return f'{self.name} · {self.phone}'


def booking_reference():
    return 'ZUDO-' + uuid.uuid4().hex[:12].upper()


class Booking(models.Model):
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    STATUS = [('pending', 'Pending'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled'), ('completed', 'Completed')]
    reference = models.CharField(max_length=20, unique=True, default=booking_reference, editable=False)
    vehicle = models.ForeignKey('fleet.Vehicle', on_delete=models.PROTECT, related_name='bookings')
    vehicle_plate_number = models.CharField(max_length=20)
    cart_vehicle = models.JSONField(default=dict)
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30)
    customer_email = models.EmailField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    pickup_location_id = models.PositiveIntegerField()
    dropoff_location_id = models.PositiveIntegerField()
    pickup_custom_payload = models.CharField(max_length=500, blank=True)
    dropoff_custom_payload = models.CharField(max_length=500, blank=True)
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=10, choices=[('flat', 'Flat amount'), ('percentage', 'Percentage')], default='flat')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1200)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=12, choices=STATUS, default='pending')
    assigned_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    pickup_odometer = models.PositiveIntegerField(null=True, blank=True)
    return_odometer = models.PositiveIntegerField(null=True, blank=True)
    return_notes = models.TextField(blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        contact_fields = ('customer_name', 'customer_phone', 'customer_email')
        previous = type(self).objects.filter(pk=self.pk).values(*contact_fields, 'customer_id').first() if self.pk else None
        update_fields = kwargs.get('update_fields')
        contact_changed = previous is None or any(previous[key] != getattr(self, key) for key in contact_fields if update_fields is None or key in update_fields)
        if contact_changed or not self.customer_id:
            phone = normalize_customer_phone(self.customer_phone)
            if phone:
                customer, _ = Customer.objects.get_or_create(phone=phone, defaults={'name': self.customer_name.strip(), 'email': self.customer_email.strip()})
                customer.name = self.customer_name.strip()
                if self.customer_email.strip():
                    customer.email = self.customer_email.strip()
                customer.save()
                self.customer = customer
                if update_fields is not None:
                    kwargs['update_fields'] = set(update_fields) | {'customer'}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['vehicle', 'start_datetime', 'end_datetime'])]
        constraints = [models.CheckConstraint(condition=models.Q(end_datetime__gt=models.F('start_datetime')), name='booking_positive_duration')]
