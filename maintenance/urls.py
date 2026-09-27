from django.urls import path

from .views import (
    ServiceTypeAPIView,
    ServiceRecordAPIView,
    ServiceRecordDetailAPIView,
    MaintenanceScheduleAPIView,
    MaintenanceScheduleDetailAPIView,
)

urlpatterns = [
    # Service types
    path(
        "service-types/",
        ServiceTypeAPIView.as_view(),
        name="service-types"
    ),

    # Service records
    path(
        "services/",
        ServiceRecordAPIView.as_view(),
        name="service-list-create"
    ),

    path(
        "services/<int:pk>/",
        ServiceRecordDetailAPIView.as_view(),
        name="service-detail"
    ),

    # Maintenance schedules
    path(
        "schedules/",
        MaintenanceScheduleAPIView.as_view(),
        name="schedule-list-create"
    ),

    path(
        "schedules/<int:pk>/",
        MaintenanceScheduleDetailAPIView.as_view(),
        name="schedule-detail"
    ),
]