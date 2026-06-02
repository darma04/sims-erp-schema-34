"""
==========================================================================
 BIAYA URLS - Routing URL untuk modul Biaya (Expense)
==========================================================================
 app_name = 'biaya' → Namespace URL

 /biaya/kategori/                  → Daftar kategori biaya
 /biaya/kategori/add/              → Tambah kategori
 /biaya/kategori/<pk>/edit/        → Edit kategori
 /biaya/kategori/<pk>/delete/      → Hapus kategori

 /biaya/transaksi/                 → Daftar transaksi biaya
 /biaya/transaksi/add/             → Catat pengeluaran baru
 /biaya/transaksi/<pk>/            → Detail transaksi + audit trail
 /biaya/transaksi/<pk>/edit/       → Edit transaksi
 /biaya/transaksi/<pk>/delete/     → Hapus transaksi
 /biaya/transaksi/<pk>/print/      → Cetak bukti pengeluaran
 /biaya/transaksi/<pk>/approve/    → Setujui transaksi biaya
 /biaya/transaksi/<pk>/reject/     → Tolak transaksi biaya
 /biaya/transaksi/<pk>/cancel/     → Batalkan transaksi biaya
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'biaya'  # Namespace URL

urlpatterns = [
    # ===== KATEGORI BIAYA CRUD =====
    path('kategori/', views.KategoriBiayaListView.as_view(), name='kategori'),
    # URL: /biaya/kategori/add/ — kategori_add
    path('kategori/add/', views.KategoriBiayaCreateView.as_view(), name='kategori_add'),
    # URL: /biaya/kategori/<int:pk>/edit/ — kategori_edit
    path('kategori/<int:pk>/edit/', views.KategoriBiayaUpdateView.as_view(), name='kategori_edit'),
    # URL: /biaya/kategori/<int:pk>/delete/ — kategori_delete
    path('kategori/<int:pk>/delete/', views.KategoriBiayaDeleteView.as_view(), name='kategori_delete'),
    
    # ===== TRANSAKSI BIAYA CRUD + PRINT =====
    path('transaksi/', views.TransaksiBiayaListView.as_view(), name='transaksi'),
    # URL: /biaya/transaksi/add/ — transaksi_add
    path('transaksi/add/', views.TransaksiBiayaCreateView.as_view(), name='transaksi_add'),
    # URL: /biaya/transaksi/<int:pk>/ — transaksi_detail
    path('transaksi/<int:pk>/', views.TransaksiBiayaDetailView.as_view(), name='transaksi_detail'),
    # URL: /biaya/transaksi/<int:pk>/edit/ — transaksi_edit
    path('transaksi/<int:pk>/edit/', views.TransaksiBiayaUpdateView.as_view(), name='transaksi_edit'),
    # URL: /biaya/transaksi/<int:pk>/delete/ — transaksi_delete
    path('transaksi/<int:pk>/delete/', views.TransaksiBiayaDeleteView.as_view(), name='transaksi_delete'),
    # URL: /biaya/transaksi/<int:pk>/print/ — transaksi_print
    path('transaksi/<int:pk>/print/', views.TransaksiBiayaPrintView.as_view(), name='transaksi_print'),
    
    # ===== WORKFLOW APPROVE / REJECT / CANCEL =====
    # URL: /biaya/transaksi/<int:pk>/approve/ — transaksi_approve
    path('transaksi/<int:pk>/approve/', views.TransaksiBiayaApproveView.as_view(), name='transaksi_approve'),
    # URL: /biaya/transaksi/<int:pk>/reject/ — transaksi_reject
    path('transaksi/<int:pk>/reject/', views.TransaksiBiayaRejectView.as_view(), name='transaksi_reject'),
    # URL: /biaya/transaksi/<int:pk>/cancel/ — transaksi_cancel
    path('transaksi/<int:pk>/cancel/', views.cancel_transaksi_biaya, name='transaksi_cancel'),
]

