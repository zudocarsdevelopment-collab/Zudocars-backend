from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import LoginView

urlpatterns = [
    path('login/', csrf_exempt(LoginView.as_view()), name='login'),
]