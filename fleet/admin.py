from django.contrib import admin
from .models import Vehicle,PickupHub

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    exclude = ('hourly_rate', 'min_hours_rate')
    list_display = ('plate_number', 'category', 'daily_price', 'is_active')
# Register your models here.
admin.site.register(PickupHub)
