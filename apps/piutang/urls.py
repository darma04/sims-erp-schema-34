"""
==========================================================================
 PIUTANG URLS
==========================================================================
"""
from django.urls import path
from . import views

app_name = 'piutang'

urlpatterns = [
    path('', views.PiutangListView.as_view(), name='list'),
    path('add/', views.PiutangCreateView.as_view(), name='add'),
    path('<int:pk>/', views.PiutangDetailView.as_view(), name='detail'),
    path('<int:pk>/bayar/', views.PembayaranPiutangCreateView.as_view(), name='bayar'),
    path('<int:pk>/hapuskan/', views.PiutangHapuskanView.as_view(), name='hapuskan'),
    path('aging/', views.AgingReportView.as_view(), name='aging'),
]
