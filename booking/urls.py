from django.urls import path
from .views import AvailableVehiclesAPIView, CreateEstimateBookingAPIView, BookingListAPIView, BookingDetailAPIView
from .zudo_pdf_view import ZudoEstimatePDFAPIView
from django.conf.urls.static import static


urlpatterns = [
    path('bookings/', CreateEstimateBookingAPIView.as_view(), name='create-booking'),
    path('bookings/list/', BookingListAPIView.as_view(), name='booking-list'),
    path('bookings/<str:reference>/', BookingDetailAPIView.as_view(), name='booking-detail'),
    path('vehicles/available/', AvailableVehiclesAPIView.as_view(), name='available-vehicles'),
    path('estimates/create/', CreateEstimateBookingAPIView.as_view(), name='create-estimate'),
    path('estimates/pdf/', ZudoEstimatePDFAPIView.as_view(), name='zudo-estimate-pdf'),  # ADD THIS
]
