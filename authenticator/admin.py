from django.contrib import admin

from .models import StaffMember

@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'employee_id', 'department', 'status']
    search_fields = ['name', 'email', 'employee_id']
