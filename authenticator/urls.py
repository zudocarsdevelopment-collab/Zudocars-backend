from django.urls import path
from .views import LoginAPIView
from .staff import StaffListAPI, StaffDetailAPI

urlpatterns = [
    path('staff/', StaffListAPI.as_view()),
    path('staff/<int:pk>/', StaffDetailAPI.as_view()),
    path("login/", LoginAPIView.as_view(), name="login"),
]
