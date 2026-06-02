from django.urls import path
from . import views

app_name = 'pajak'

urlpatterns = [
    path('', views.FakturPajakListView.as_view(), name='list'),
    path('add/', views.FakturPajakCreateView.as_view(), name='add'),
    path('<int:pk>/edit/', views.FakturPajakUpdateView.as_view(), name='edit'),
    path('setting/', views.SettingPajakView.as_view(), name='setting'),
    path('rekap/', views.RekapPPNView.as_view(), name='rekap'),
    # Settlement PPN
    path('setor/', views.PembayaranPPNListView.as_view(), name='setor_list'),
    path('setor/add/', views.PembayaranPPNCreateView.as_view(), name='setor_add'),
    path('setor/<int:pk>/', views.PembayaranPPNDetailView.as_view(), name='setor_detail'),
]
