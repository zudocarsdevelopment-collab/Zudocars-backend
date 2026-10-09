from django.contrib import admin
from .models import ServiceType, ServiceRecord, MaintenanceSchedule

admin.site.register([ServiceType, ServiceRecord, MaintenanceSchedule])
