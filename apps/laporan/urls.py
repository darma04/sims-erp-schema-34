"""
==========================================================================
 LAPORAN URLS - Routing URL Modul Laporan
==========================================================================
 Peta URL modul laporan (semua read-only):

 - /laporan/produk/              → Laporan produk + nilai aset
 - /laporan/produk/<id>/         → Detail laporan produk
 - /laporan/stok/                → Laporan stok per gudang
 - /laporan/stok/<id>/           → Detail stok di gudang
 - /laporan/penjualan/           → Laporan penjualan (SO + POS)
 - /laporan/penjualan/<id>/      → Detail Sales Order
 - /laporan/pembelian/           → Laporan pembelian (PO)
 - /laporan/pembelian/<id>/      → Detail Purchase Order
 - /laporan/keuangan/            → Ringkasan keuangan (laba/rugi)

 Didaftarkan di config/urls.py: path('laporan/', include('apps.laporan.urls'))
==========================================================================
"""
from django.urls import path
from . import views

app_name = 'laporan'  # Namespace URL — digunakan: {% url 'laporan:produk' %}

urlpatterns = [
    # ── Laporan Produk ───────────────────────────────────────
    path('produk/', views.LaporanProdukView.as_view(), name='produk'),
    # URL: /laporan/produk/<int:pk>/ — produk-detail
    path('produk/<int:pk>/', views.LaporanProdukDetailView.as_view(), name='produk-detail'),

    # ── Laporan Stok ─────────────────────────────────────────
    path('stok/', views.LaporanStokView.as_view(), name='stok'),
    # URL: /laporan/stok/<int:pk>/ — stok-detail
    path('stok/<int:pk>/', views.LaporanStokDetailView.as_view(), name='stok-detail'),

    # ── Laporan Penjualan ────────────────────────────────────
    path('penjualan/', views.LaporanPenjualanView.as_view(), name='penjualan'),
    # URL: /laporan/penjualan/<int:pk>/ — penjualan-detail
    path('penjualan/<int:pk>/', views.LaporanPenjualanDetailView.as_view(), name='penjualan-detail'),

    # ── Laporan Pembelian ────────────────────────────────────
    path('pembelian/', views.LaporanPembelianView.as_view(), name='pembelian'),
    # URL: /laporan/pembelian/<int:pk>/ — pembelian-detail
    path('pembelian/<int:pk>/', views.LaporanPembelianDetailView.as_view(), name='pembelian-detail'),

    # ── Laporan Keuangan ─────────────────────────────────────
    path('keuangan/', views.LaporanKeuanganView.as_view(), name='keuangan'),

    # ── Laporan Service ──────────────────────────────────────────
    path('service/', views.LaporanServiceView.as_view(), name='service'),

    # ── Laporan Sparepart ────────────────────────────────────────
    path('sparepart/', views.LaporanSparepartView.as_view(), name='sparepart'),

    # ── Laporan Cabang ───────────────────────────────────────────────
    path('cabang/', views.LaporanCabangView.as_view(), name='cabang'),
]
