from django.urls import path
from .views import AvailableVehiclesAPIView,CreateEstimateBookingAPIView

urlpatterns = [
    path('vehicles/available/', AvailableVehiclesAPIView.as_view(), name='available-vehicles'),
    path('estimates/create', CreateEstimateBookingAPIView.as_view(), name='create-estimate'),
]
 