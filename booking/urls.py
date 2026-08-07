from django.urls import path
from .views import AvailableVehiclesAPIView,CreateEstimateBookingAPIView
from .zudo_pdf_view import ZudoEstimatePDFAPIView
from django.conf.urls.static import static


urlpatterns = [
    path('vehicles/available/', AvailableVehiclesAPIView.as_view(), name='available-vehicles'),
    path('estimates/create/', CreateEstimateBookingAPIView.as_view(), name='create-estimate'),
    path('estimates/pdf/', ZudoEstimatePDFAPIView.as_view(), name='zudo-estimate-pdf'),  # ADD THIS
]
