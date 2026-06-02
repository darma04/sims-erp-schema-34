"""
==========================================================================
 POS URLS - Routing URL untuk modul POS/Kasir
==========================================================================
 app_name = 'pos' → Namespace URL

 /pos/                              → Halaman utama POS (kasir)
 /pos/api/create-transaction/       → API: buat transaksi (POST)
 /pos/api/check-stock/<produk_id>/  → API: cek stok produk
 /pos/api/search-products/          → API: search produk
 /pos/api/get-stocks-by-gudang/     → API: stok per gudang
 /pos/invoice/                      → Daftar invoice
 /pos/invoice/<pk>/                 → Detail invoice
 /pos/invoice/<pk>/print/           → Cetak struk
 /pos/invoice/<pk>/delete/          → Hapus invoice
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'pos'  # Namespace URL

urlpatterns = [
    # ===== HALAMAN UTAMA POS =====
    path('', views.POSIndexView.as_view(), name='index'),
    
    # ===== API ENDPOINTS (dipanggil via AJAX) =====
    path('api/create-transaction/', views.create_transaction, name='api_create_transaction'),
    # URL: /pos/api/check-stock/<int:produk_id>/ — api_check_stock
    path('api/check-stock/<int:produk_id>/', views.check_stock, name='api_check_stock'),
    # URL: /pos/api/search-products/ — api_search_products
    path('api/search-products/', views.search_products, name='api_search_products'),
    # URL: /pos/api/get-stocks-by-gudang/ — api_get_stocks_by_gudang
    path('api/get-stocks-by-gudang/', views.get_stocks_by_gudang, name='api_get_stocks_by_gudang'),
    # URL: /pos/api/lookup-barcode/ — api_lookup_barcode (scanner barcode kamera)
    path('api/lookup-barcode/', views.lookup_barcode, name='api_lookup_barcode'),
    
    # ===== INVOICE CRUD =====
    path('invoice/', views.InvoiceListView.as_view(), name='invoice_list'),
    # URL: /pos/invoice/<int:pk>/ — invoice_detail
    path('invoice/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    # URL: /pos/invoice/<int:pk>/print/ — invoice_print
    path('invoice/<int:pk>/print/', views.InvoicePrintView.as_view(), name='invoice_print'),
    # URL: /pos/invoice/<int:pk>/delete/ — invoice_delete
    path('invoice/<int:pk>/delete/', views.InvoiceDeleteView.as_view(), name='invoice_delete'),
    # URL: /pos/invoice/<int:pk>/cancel/ — invoice_cancel (POST AJAX)
    path('invoice/<int:pk>/cancel/', views.cancel_pos_transaction, name='invoice_cancel'),
]
