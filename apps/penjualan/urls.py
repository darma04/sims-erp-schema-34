"""
==========================================================================
 PENJUALAN URLS - Routing URL untuk modul Penjualan
==========================================================================
 app_name = 'penjualan' → Namespace URL

 URL POLA:
 ┌─────────────────────────────────────────────────────────────────┐
 │ CUSTOMER CRUD                                                  │
 │ /penjualan/customer/              → Daftar customer            │
 │ /penjualan/customer/add/          → Tambah customer            │
 │ /penjualan/customer/<pk>/edit/    → Edit customer              │
 │ /penjualan/customer/<pk>/delete/  → Hapus customer             │
 ├─────────────────────────────────────────────────────────────────┤
 │ SALES ORDER CRUD + CONFIRM                                     │
 │ /penjualan/sales-order/               → Daftar SO              │
 │ /penjualan/sales-order/add/           → Buat SO                │
 │ /penjualan/sales-order/<pk>/          → Detail SO              │
 │ /penjualan/sales-order/<pk>/print/    → Cetak SO               │
 │ /penjualan/sales-order/<pk>/edit/     → Edit SO                │
 │ /penjualan/sales-order/<pk>/confirm/  → Konfirmasi SO          │
 │ /penjualan/sales-order/<pk>/delete/   → Hapus SO               │
 ├─────────────────────────────────────────────────────────────────┤
 │ TRANSAKSI POS (model dari apps.pos, URL di penjualan)          │
 │ /penjualan/transaksi/               → Daftar transaksi POS     │
 │ /penjualan/transaksi/<pk>/          → Detail transaksi         │
 │ /penjualan/transaksi/<pk>/print/    → Cetak struk              │
 │ /penjualan/transaksi/<pk>/delete/   → Hapus transaksi          │
 └─────────────────────────────────────────────────────────────────┘
==========================================================================
"""

from django.urls import path
from apps.penjualan import views

app_name = 'penjualan'  # Namespace URL

urlpatterns = [
    # ===== CUSTOMER CRUD =====
    path('customer/', views.CustomerListView.as_view(), name='customer'),
    # URL: /penjualan/customer/add/ — customer-add
    path('customer/add/', views.CustomerCreateView.as_view(), name='customer-add'),
    # URL: /penjualan/customer/<int:pk>/edit/ — customer-edit
    path('customer/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer-edit'),
    # URL: /penjualan/customer/<int:pk>/delete/ — customer-delete
    path('customer/<int:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer-delete'),
    
    # ===== SALES ORDER CRUD + CONFIRM =====
    path('sales-order/', views.SalesOrderListView.as_view(), name='sales-order'),
    # URL: /penjualan/sales-order/add/ — sales-order-add
    path('sales-order/add/', views.SalesOrderCreateView.as_view(), name='sales-order-add'),
    # URL: /penjualan/sales-order/<int:pk>/ — sales-order-detail
    path('sales-order/<int:pk>/', views.SalesOrderDetailView.as_view(), name='sales-order-detail'),
    # URL: /penjualan/sales-order/<int:pk>/print/ — sales-order-print
    path('sales-order/<int:pk>/print/', views.SalesOrderPrintView.as_view(), name='sales-order-print'),
    # URL: /penjualan/sales-order/<int:pk>/edit/ — sales-order-edit
    path('sales-order/<int:pk>/edit/', views.SalesOrderUpdateView.as_view(), name='sales-order-edit'),
    # URL: /penjualan/sales-order/<int:pk>/confirm/ — sales-order-confirm
    path('sales-order/<int:pk>/confirm/', views.sales_order_confirm, name='sales-order-confirm'),
    # URL: /penjualan/sales-order/<int:pk>/delete/ — sales-order-delete
    path('sales-order/<int:pk>/delete/', views.SalesOrderDeleteView.as_view(), name='sales-order-delete'),
    # URL: /penjualan/sales-order/<int:pk>/cancel/ — sales-order-cancel (POST AJAX)
    path('sales-order/<int:pk>/cancel/', views.cancel_sales_order, name='sales-order-cancel'),
    
    # ===== TRANSAKSI POS (model dari apps.pos) =====
    path('transaksi/', views.TransactionListView.as_view(), name='transaksi'),
    # URL: /penjualan/transaksi/<int:pk>/ — transaksi-detail
    path('transaksi/<int:pk>/', views.TransactionDetailView.as_view(), name='transaksi-detail'),
    # URL: /penjualan/transaksi/<int:pk>/print/ — transaksi-print
    path('transaksi/<int:pk>/print/', views.TransactionPrintView.as_view(), name='transaksi-print'),
    # URL: /penjualan/transaksi/<int:pk>/delete/ — transaksi-delete
    path('transaksi/<int:pk>/delete/', views.TransactionDeleteView.as_view(), name='transaksi-delete'),
]
