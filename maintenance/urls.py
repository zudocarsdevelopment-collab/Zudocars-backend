from django.urls import path
from .views import ServiceTypeAPIView, ServiceTypeDetailAPIView, ServiceRecordAPIView, ServiceRecordDetailAPIView, MaintenanceScheduleAPIView, MaintenanceScheduleDetailAPIView

urlpatterns = [
    path('service-types/', ServiceTypeAPIView.as_view()),
    path('service-types/<int:pk>/', ServiceTypeDetailAPIView.as_view()),
    path('services/', ServiceRecordAPIView.as_view()),
    path('services/<int:pk>/', ServiceRecordDetailAPIView.as_view()),
    path('schedules/', MaintenanceScheduleAPIView.as_view()),
    path('schedules/<int:pk>/', MaintenanceScheduleDetailAPIView.as_view()),
]
