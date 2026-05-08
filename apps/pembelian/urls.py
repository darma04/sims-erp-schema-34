"""
==========================================================================
 PEMBELIAN URLS - Routing URL untuk modul Pembelian
==========================================================================
 app_name = 'pembelian' → Namespace URL
 Contoh: reverse('pembelian:supplier') → /pembelian/supplier/

 POLA URL:
 /pembelian/supplier/                     → List supplier
 /pembelian/supplier/add/                 → Tambah supplier
 /pembelian/supplier/<pk>/edit/           → Edit supplier
 /pembelian/supplier/<pk>/delete/         → Hapus supplier

 /pembelian/purchase-order/               → List PO
 /pembelian/purchase-order/add/           → Buat PO baru
 /pembelian/purchase-order/<pk>/          → Detail PO
 /pembelian/purchase-order/<pk>/print/    → Cetak PO
 /pembelian/purchase-order/<pk>/edit/     → Edit PO
 /pembelian/purchase-order/<pk>/receive/  → Terima barang
 /pembelian/purchase-order/<pk>/delete/   → Hapus PO
==========================================================================
"""

from django.urls import path
from apps.pembelian import views

app_name = 'pembelian'  # Namespace URL

urlpatterns = [
    # ===== SUPPLIER CRUD =====
    path('supplier/', views.SupplierListView.as_view(), name='supplier'),
    # URL: /pembelian/supplier/add/ — supplier-add
    path('supplier/add/', views.SupplierCreateView.as_view(), name='supplier-add'),
    # URL: /pembelian/supplier/<int:pk>/edit/ — supplier-edit
    path('supplier/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier-edit'),
    # URL: /pembelian/supplier/<int:pk>/delete/ — supplier-delete
    path('supplier/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier-delete'),
    
    # ===== PURCHASE ORDER CRUD =====
    path('purchase-order/', views.PurchaseOrderListView.as_view(), name='purchase-order'),
    # URL: /pembelian/purchase-order/import/ — purchase-order-import
    path('purchase-order/import/', views.PurchaseOrderImportView.as_view(), name='purchase-order-import'),
    # URL: /pembelian/purchase-order/add/ — purchase-order-add
    path('purchase-order/add/', views.PurchaseOrderCreateView.as_view(), name='purchase-order-add'),
    # URL: /pembelian/purchase-order/<int:pk>/ — purchase-order-detail
    path('purchase-order/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    # URL: /pembelian/purchase-order/<int:pk>/print/ — purchase-order-print
    path('purchase-order/<int:pk>/print/', views.PurchaseOrderPrintView.as_view(), name='purchase-order-print'),
    # URL: /pembelian/purchase-order/<int:pk>/edit/ — purchase-order-edit
    path('purchase-order/<int:pk>/edit/', views.PurchaseOrderUpdateView.as_view(), name='purchase-order-edit'),
    # URL: /pembelian/purchase-order/<int:pk>/receive/ — purchase-order-receive
    path('purchase-order/<int:pk>/receive/', views.purchase_order_receive, name='purchase-order-receive'),
    # URL: /pembelian/purchase-order/<int:pk>/delete/ — purchase-order-delete
    path('purchase-order/<int:pk>/delete/', views.PurchaseOrderDeleteView.as_view(), name='purchase-order-delete'),
]
