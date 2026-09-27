from django.contrib import admin

from .models import  ServiceType, MaintenanceSchedule, ServiceRecord
# Register your models here.
admin.site.register(ServiceType)
admin.site.register(MaintenanceSchedule)    
admin.site.register(ServiceRecord)