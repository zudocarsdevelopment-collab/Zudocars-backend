from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['reference', 'customer_name', 'vehicle_plate_number', 'start_datetime', 'end_datetime', 'status', 'assigned_email', 'total_amount']
    list_filter = ['status']
    search_fields = ['reference', 'customer_name', 'customer_phone', 'vehicle_plate_number']
    readonly_fields = [field.name for field in Booking._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
