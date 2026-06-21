from django.urls import path
from .health_views import health_check

urlpatterns = [
    path('', health_check, name='health-check'),
]
