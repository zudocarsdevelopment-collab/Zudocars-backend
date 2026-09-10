from django.urls import path, re_path
from .views import AvailableVehiclesAPIView,CreateEstimateBookingAPIView
from .zudo_pdf_view import ZudoEstimatePDFAPIView
from django.conf.urls.static import static
from django.conf import settings
from django.views.static import serve
urlpatterns = [
    path('vehicles/available/', AvailableVehiclesAPIView.as_view(), name='available-vehicles'),
    path('estimates/create/', CreateEstimateBookingAPIView.as_view(), name='create-estimate'),
    path('estimates/pdf/', ZudoEstimatePDFAPIView.as_view(), name='zudo-estimate-pdf'),

    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]