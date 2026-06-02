"""
==========================================================================
 PENGATURAN URLS - Routing URL untuk modul Pengaturan (Settings)
==========================================================================
 app_name = 'pengaturan' → Namespace URL

 /pengaturan/profil/                → Edit profil user
 /pengaturan/perusahaan/            → Pengaturan perusahaan + sistem

 /pengaturan/pembayaran/...         → Metode pembayaran CRUD + toggle
 /pengaturan/template-cetak/...     → Template cetak CRUD

 /pengaturan/manajemen-data/        → Statistik DB + riwayat backup
 /pengaturan/manajemen-data/backup/ → Export DB ke JSON
 /pengaturan/manajemen-data/restore/→ Import DB dari JSON
 /pengaturan/manajemen-data/reset/  → ⚠ Hapus semua transaksi
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'pengaturan'  # Namespace URL

urlpatterns = [
    # URL: /pengaturan/profil/ — profil
    path('profil/', views.ProfilView.as_view(), name='profil'),
    # URL: /pengaturan/perusahaan/ — perusahaan
    path('perusahaan/', views.PerusahaanView.as_view(), name='perusahaan'),
    
    # Metode Pembayaran
    path('pembayaran/', views.MetodePembayaranListView.as_view(), name='metode_pembayaran_list'),
    path('pembayaran/seed/', views.SeedMetodePembayaranView.as_view(), name='metode_pembayaran_seed'),
    # URL: /pengaturan/pembayaran/tambah/ — metode_pembayaran_create
    path('pembayaran/tambah/', views.MetodePembayaranCreateView.as_view(), name='metode_pembayaran_create'),
    # URL: /pengaturan/pembayaran/<int:pk>/ — metode_pembayaran_detail
    path('pembayaran/<int:pk>/', views.MetodePembayaranDetailView.as_view(), name='metode_pembayaran_detail'),
    # URL: /pengaturan/pembayaran/<int:pk>/edit/ — metode_pembayaran_update
    path('pembayaran/<int:pk>/edit/', views.MetodePembayaranUpdateView.as_view(), name='metode_pembayaran_update'),
    # URL: /pengaturan/pembayaran/<int:pk>/hapus/ — metode_pembayaran_delete
    path('pembayaran/<int:pk>/hapus/', views.MetodePembayaranDeleteView.as_view(), name='metode_pembayaran_delete'),
    # URL: /pengaturan/pembayaran/<int:pk>/toggle/ — metode_pembayaran_toggle
    path('pembayaran/<int:pk>/toggle/', views.toggle_metode_pembayaran, name='metode_pembayaran_toggle'),
    
    # Template Cetak
    path('template-cetak/', views.TemplateCetakListView.as_view(), name='template_cetak_list'),
    # URL: /pengaturan/template-cetak/tambah/ — template_cetak_create
    path('template-cetak/tambah/', views.TemplateCetakCreateView.as_view(), name='template_cetak_create'),
    # URL: /pengaturan/template-cetak/<int:pk>/edit/ — template_cetak_update
    path('template-cetak/<int:pk>/edit/', views.TemplateCetakUpdateView.as_view(), name='template_cetak_update'),
    # URL: /pengaturan/template-cetak/<int:pk>/hapus/ — template_cetak_delete
    path('template-cetak/<int:pk>/hapus/', views.TemplateCetakDeleteView.as_view(), name='template_cetak_delete'),
    
    # Manajemen Data
    path('manajemen-data/', views.ManajemenDataView.as_view(), name='manajemen_data'),
    # URL: /pengaturan/manajemen-data/backup/ — backup_data
    path('manajemen-data/backup/', views.backup_data, name='backup_data'),
    # URL: /pengaturan/manajemen-data/restore/ — restore_data
    path('manajemen-data/restore/', views.restore_data, name='restore_data'),
    # URL: /pengaturan/manajemen-data/reset/ — reset_data
    path('manajemen-data/reset/', views.reset_data, name='reset_data'),
    # URL: /pengaturan/manajemen-data/riwayat/<int:pk>/hapus/ — hapus_riwayat_backup
    path('manajemen-data/riwayat/<int:pk>/hapus/', views.hapus_riwayat_backup, name='hapus_riwayat_backup'),
    # URL: /pengaturan/manajemen-data/bersihkan-log-aktivitas/ — bersihkan_log_aktivitas
    path('manajemen-data/bersihkan-log-aktivitas/', views.bersihkan_log_aktivitas, name='bersihkan_log_aktivitas'),
    # URL: /pengaturan/manajemen-data/bersihkan-log-notifikasi/ — bersihkan_log_notifikasi
    path('manajemen-data/bersihkan-log-notifikasi/', views.bersihkan_log_notifikasi, name='bersihkan_log_notifikasi'),
]
