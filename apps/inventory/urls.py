"""
==========================================================================
 INVENTORY URLS - Routing URL untuk modul Inventory
==========================================================================
 app_name = 'inventory' → Namespace untuk URL reversal
 Contoh: reverse('inventory:gudang') → /inventory/gudang/

 POLA URL:
 /inventory/gudang/            → List gudang
 /inventory/gudang/add/        → Tambah gudang
 /inventory/gudang/<pk>/edit/  → Edit gudang
 /inventory/gudang/<pk>/delete/→ Hapus gudang

 /inventory/stok/              → List stok per produk per gudang

 /inventory/transfer/          → List transfer stok
 /inventory/transfer/add/      → Buat transfer baru
 /inventory/transfer/<pk>/     → Detail transfer
 /inventory/transfer/<pk>/edit/→ Edit transfer
 /inventory/transfer/<pk>/approve/ → Approve transfer
 /inventory/transfer/<pk>/delete/  → Hapus transfer

 /inventory/adjustment/        → List adjustment stok
 /inventory/adjustment/add/    → Buat adjustment baru

 API Endpoints:
 /inventory/api/stok-tersedia/      → JSON: stok tersedia
 /inventory/api/stok-produk-gudang/ → JSON: stok saat ini
 /inventory/api/search-produk/      → JSON: search produk via Select2
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'inventory'  # Namespace URL

urlpatterns = [
    # ===== GUDANG CRUD =====
    path('gudang/', views.GudangListView.as_view(), name='gudang'),
    # URL: /inventory/gudang/add/ — gudang_add
    path('gudang/add/', views.GudangCreateView.as_view(), name='gudang_add'),
    # URL: /inventory/gudang/<int:pk>/edit/ — gudang_edit
    path('gudang/<int:pk>/edit/', views.GudangUpdateView.as_view(), name='gudang_edit'),
    # URL: /inventory/gudang/<int:pk>/delete/ — gudang_delete
    path('gudang/<int:pk>/delete/', views.GudangDeleteView.as_view(), name='gudang_delete'),

    # ===== STOK =====
    path('stok/', views.StokListView.as_view(), name='stok'),

    # ===== TRANSFER STOK CRUD =====
    path('transfer/', views.TransferStokView.as_view(), name='transfer'),
    # URL: /inventory/transfer/add/ — transfer_add
    path('transfer/add/', views.TransferStokCreateView.as_view(), name='transfer_add'),
    # URL: /inventory/transfer/<int:pk>/ — transfer_detail
    path('transfer/<int:pk>/', views.TransferStokDetailView.as_view(), name='transfer_detail'),
    # URL: /inventory/transfer/<int:pk>/edit/ — transfer_edit
    path('transfer/<int:pk>/edit/', views.TransferStokUpdateView.as_view(), name='transfer_edit'),
    # URL: /inventory/transfer/<int:pk>/approve/ — transfer_approve
    path('transfer/<int:pk>/approve/', views.transfer_stok_approve, name='transfer_approve'),
    # URL: /inventory/transfer/<int:pk>/delete/ — transfer_delete
    path('transfer/<int:pk>/delete/', views.TransferStokDeleteView.as_view(), name='transfer_delete'),

    # ===== ADJUSTMENT STOK =====
    path('adjustment/', views.AdjustmentStokView.as_view(), name='adjustment'),
    # URL: /inventory/adjustment/add/ — adjustment_add
    path('adjustment/add/', views.AdjustmentStokCreateView.as_view(), name='adjustment_add'),
    # URL: /inventory/adjustment/<int:pk>/delete/ — adjustment_delete
    path('adjustment/<int:pk>/delete/', views.AdjustmentStokDeleteView.as_view(), name='adjustment_delete'),
    
    # ===== API ENDPOINTS (JSON) =====
    path('api/stok-tersedia/', views.get_stok_tersedia, name='api_stok_tersedia'),
    # URL: /inventory/api/stok-produk-gudang/ — api_stok_produk_gudang
    path('api/stok-produk-gudang/', views.get_stok_produk_gudang, name='api_stok_produk_gudang'),
    # URL: /inventory/api/search-produk/ — api_search_produk
    path('api/search-produk/', views.search_produk, name='api_search_produk'),
]
