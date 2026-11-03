from django import forms
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib import admin
from rest_framework.exceptions import ValidationError
from .models import Booking, Customer
from .serializer import ManualBookingSerializer
from .booking import create_manual_booking


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']
    search_fields = ['name', 'phone', 'email']
    readonly_fields = ['name', 'phone', 'email', 'created_at', 'updated_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ManualBookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['vehicle', 'customer_name', 'customer_phone', 'customer_email',
                  'start_datetime', 'end_datetime', 'pickup_location_id',
                  'dropoff_location_id', 'rental_amount', 'delivery_amount', 'notes']

    def clean(self):
        data = super().clean()
        required = ['vehicle', 'start_datetime', 'end_datetime', 'pickup_location_id', 'dropoff_location_id', 'rental_amount', 'delivery_amount']
        if any(data.get(key) is None for key in required):
            return data
        start, end = data['start_datetime'], data['end_datetime']
        booking_tz = ZoneInfo(getattr(settings, 'BOOKING_TIME_ZONE', 'Asia/Kolkata'))
        start, end = start.astimezone(booking_tz), end.astimezone(booking_tz)
        payload = {key: data.get(key, '') for key in ['customer_name', 'customer_phone', 'customer_email', 'pickup_location_id', 'dropoff_location_id', 'rental_amount', 'delivery_amount', 'notes']}
        payload.update(cart_vehicle=data['vehicle'].pk,
                       date_from=start.date(), time_from=start.strftime('%H:%M'),
                       date_to=end.date(), time_to=end.strftime('%H:%M'))
        serializer = ManualBookingSerializer(data=payload, context={'manual_booking': True})
        if not serializer.is_valid():
            raise forms.ValidationError(str(serializer.errors))
        self.booking_data = serializer.validated_data
        self.booking_data.update(start_datetime=start, end_datetime=end)
        try:
            create_manual_booking(self.booking_data, validate_only=True, instance=self.instance if self.instance.pk else None)
        except ValidationError as exc:
            raise forms.ValidationError(str(exc.detail))
        return data


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['reference', 'customer_name', 'vehicle_plate_number', 'start_datetime', 'end_datetime', 'status', 'assigned_email', 'total_amount']
    list_filter = ['status']
    search_fields = ['reference', 'customer_name', 'customer_phone', 'vehicle_plate_number']

    def get_form(self, request, obj=None, **kwargs):
        kwargs['form'] = ManualBookingForm
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        return []

    def get_fields(self, request, obj=None):
        return ManualBookingForm.Meta.fields

    def save_model(self, request, obj, form, change):
        booking = create_manual_booking(form.booking_data, instance=obj if change else None)
        obj.__dict__.update(booking.__dict__)

    def has_delete_permission(self, request, obj=None):
        return False
