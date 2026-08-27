from django.urls import path
from . import views

app_name = 'approval_center'

urlpatterns = [
    path('', views.ApprovalCenterView.as_view(), name='index'),
]
