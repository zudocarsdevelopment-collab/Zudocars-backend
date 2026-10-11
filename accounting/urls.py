from django.urls import path
from .views import SummaryAPI, EntryAPI, PaymentAPI, VoidAPI, PaymentVoidAPI

urlpatterns = [
    path('accounts/summary/', SummaryAPI.as_view()),
    path('accounts/payments/', PaymentAPI.as_view()),
    path('accounts/expenses/', EntryAPI.as_view()),
    path('accounts/payments/<int:pk>/void/', PaymentVoidAPI.as_view()),
    path('accounts/expenses/<int:pk>/void/', VoidAPI.as_view()),
]
