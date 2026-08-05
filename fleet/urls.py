from django.urls import path

from .views import VehicleListCreateAPIView, VehicleRetrieveUpdateDestroyAPIView, SyncVehiclesAPIView, SyncStatusAPIView

urlpatterns = [
    path('vehicles/', VehicleListCreateAPIView.as_view(), name='vehicle-list-create'),
    path('vehicles/<int:pk>/', VehicleRetrieveUpdateDestroyAPIView.as_view(), name='vehicle-detail'),
    path('vehicles/sync/', SyncVehiclesAPIView.as_view(), name='sync-vehicles'),
    path('vehicles/sync/<str:task_id>/', SyncStatusAPIView.as_view(), name='sync-status'),
]
