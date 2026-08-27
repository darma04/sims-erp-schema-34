from django.urls import path
from . import views

app_name = 'reimburse'

urlpatterns = [
    path('', views.ReimburseListView.as_view(), name='list'),
    path('tambah/', views.ReimburseCreateView.as_view(), name='tambah'),
    path('<int:pk>/', views.ReimburseDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ReimburseUpdateView.as_view(), name='edit'),
    path('<int:pk>/action/', views.ReimburseActionView.as_view(), name='action'),
    path('<int:pk>/delete/', views.ReimburseDeleteView.as_view(), name='delete'),
]
