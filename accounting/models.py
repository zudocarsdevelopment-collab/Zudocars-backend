from django.conf import settings
from django.db import models
from django.utils import timezone


class Entry(models.Model):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    void_reason = models.CharField(max_length=250, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='%(class)s_voids')

    class Meta:
        abstract = True
        ordering = ['-date', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='%(class)s_positive_amount')]


class Payment(Entry):
    booking = models.ForeignKey('booking.Booking', on_delete=models.PROTECT, related_name='payments')
    kind = models.CharField(max_length=10, choices=[('receipt', 'Receipt'), ('refund', 'Refund')], default='receipt')
    method = models.CharField(max_length=10, choices=[('cash', 'Cash'), ('upi', 'UPI'), ('bank', 'Bank transfer'), ('card', 'Card')])
    request_id = models.UUIDField(unique=True)


class Expense(Entry):
    category = models.CharField(max_length=20, choices=[(x, x.title()) for x in ('fuel', 'salary', 'insurance', 'rent', 'maintenance', 'other')])
    description = models.CharField(max_length=250)
    vehicle = models.ForeignKey('fleet.Vehicle', null=True, blank=True, on_delete=models.PROTECT)
    request_id = models.UUIDField(unique=True)
