"""
==========================================================================
 HUTANG URLS
==========================================================================
"""
from django.urls import path
from . import views

app_name = 'hutang'

urlpatterns = [
    path('', views.HutangListView.as_view(), name='list'),
    path('add/', views.HutangCreateView.as_view(), name='add'),
    path('<int:pk>/', views.HutangDetailView.as_view(), name='detail'),
    path('<int:pk>/bayar/', views.PembayaranHutangCreateView.as_view(), name='bayar'),
    path('aging/', views.AgingReportView.as_view(), name='aging'),
]
