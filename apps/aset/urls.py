from django.urls import path
from . import views

app_name = 'aset'

urlpatterns = [
    path('', views.AsetListView.as_view(), name='list'),
    path('add/', views.AsetCreateView.as_view(), name='add'),
    path('<int:pk>/', views.AsetDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.AsetUpdateView.as_view(), name='edit'),
    path('<int:pk>/susutkan/', views.ProsessPenyusutanView.as_view(), name='susutkan'),
    path('<int:pk>/disposal/', views.DisposalCreateView.as_view(), name='disposal'),
    path('penyusutan/', views.PenyusutanDashboardView.as_view(), name='penyusutan'),
    path('penyusutan/massal/', views.ProsessPenyusutanMassalView.as_view(), name='penyusutan_massal'),
]
