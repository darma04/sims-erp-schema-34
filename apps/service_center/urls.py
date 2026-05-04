"""
==========================================================================
 SERVICE CENTER URLS - Routing URL Service Center
==========================================================================
 Semua URL di-prefix dengan /service/ di config/urls.py
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'service_center'

urlpatterns = [
    # ===== DASHBOARD =====
    path('', views.ServiceDashboardView.as_view(), name='dashboard'),

    # ===== PELANGGAN =====
    path('pelanggan/', views.PelangganListView.as_view(), name='pelanggan_list'),
    path('pelanggan/tambah/', views.PelangganCreateView.as_view(), name='pelanggan_create'),
    path('pelanggan/<int:pk>/edit/', views.PelangganUpdateView.as_view(), name='pelanggan_update'),
    path('pelanggan/<int:pk>/delete/', views.pelanggan_delete, name='pelanggan_delete'),

    # ===== PERANGKAT =====
    path('perangkat/', views.PerangkatListView.as_view(), name='perangkat_list'),
    path('perangkat/tambah/', views.PerangkatCreateView.as_view(), name='perangkat_create'),
    path('perangkat/<int:pk>/edit/', views.PerangkatUpdateView.as_view(), name='perangkat_update'),
    path('perangkat/<int:pk>/delete/', views.perangkat_delete, name='perangkat_delete'),

    # ===== KATEGORI SERVICE =====
    path('kategori/', views.KategoriServiceListView.as_view(), name='kategori_list'),
    path('kategori/tambah/', views.KategoriServiceCreateView.as_view(), name='kategori_create'),
    path('kategori/<int:pk>/edit/', views.KategoriServiceUpdateView.as_view(), name='kategori_update'),
    path('kategori/<int:pk>/delete/', views.kategori_delete, name='kategori_delete'),

    # ===== JENIS SERVICE =====
    path('jenis/', views.JenisServiceListView.as_view(), name='jenis_list'),
    path('jenis/tambah/', views.JenisServiceCreateView.as_view(), name='jenis_create'),
    path('jenis/<int:pk>/edit/', views.JenisServiceUpdateView.as_view(), name='jenis_update'),
    path('jenis/<int:pk>/delete/', views.jenis_delete, name='jenis_delete'),

    # ===== ORDER SERVICE =====
    path('order/', views.OrderServiceListView.as_view(), name='order_list'),
    path('order/terima/', views.OrderServiceCreateView.as_view(), name='order_create'),
    path('order/<int:pk>/', views.OrderServiceDetailView.as_view(), name='order_detail'),
    path('order/<int:pk>/edit/', views.OrderServiceUpdateView.as_view(), name='order_update'),
    path('order/<int:pk>/delete/', views.order_delete, name='order_delete'),
    path('order/<int:pk>/update-status/', views.update_status, name='update_status'),
    path('order/<int:pk>/update-pembayaran/', views.update_pembayaran, name='update_pembayaran'),
    path('order/<int:pk>/update-items/', views.update_items, name='update_items'),
    path('order/<int:pk>/cetak-nota/', views.CetakNotaServiceView.as_view(), name='cetak_nota'),
    path('order/<int:pk>/cetak-bukti-bayar/', views.CetakBuktiPembayaranView.as_view(), name='cetak_bukti_bayar'),

    # ===== LAPORAN =====
    path('laporan/', views.LaporanServiceView.as_view(), name='laporan'),

    # ===== SPAREPART API =====
    path('order/<int:pk>/tambah-sparepart/', views.tambah_sparepart, name='tambah_sparepart'),
    path('order/<int:pk>/hapus-sparepart/<int:sparepart_id>/', views.hapus_sparepart, name='hapus_sparepart'),
    path('order/<int:pk>/edit-sparepart/<int:sparepart_id>/', views.edit_sparepart, name='edit_sparepart'),
    path('api/search-sparepart/', views.api_search_sparepart, name='api_search_sparepart'),

    # ===== CEK STATUS PUBLIK (TANPA LOGIN) =====
    path('cek-status/', views.CekStatusPublikView.as_view(), name='cek_status'),
    path('api/cek-status/', views.cek_status_api, name='cek_status_api'),
]
