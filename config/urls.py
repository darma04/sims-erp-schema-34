"""
==========================================================================
 CONFIG URLS - Routing URL Master (Root URL Configuration)
==========================================================================
 File routing utama yang mendaftarkan SEMUA modul ke URL:

 Modul ERP:
 - /                   → Dashboard
 - /produk/            → Produk, Kategori, Satuan
 - /inventory/         → Transfer Stok, Adjustment, Gudang
 - /pembelian/         → Supplier, Purchase Order
 - /penjualan/         → Customer, Sales Order
 - /pos/               → Point of Sale
 - /biaya/             → Transaksi Biaya
 - /laporan/           → Laporan (Produk, Stok, Penjualan, dll)
 - /hr/                → HR Management
 - /automation/        → Notifikasi Telegram

 Modul Sistem:
 - /admin/             → Django Admin
 - /users/             → User Management
 - /access/            → Permission & Role Management
 - /activity-log/      → Activity Log
 - /pengaturan/        → Pengaturan Perusahaan
 - /api/search/        → Global Search API

 Fitur:
 - global_search_api()  → Pencarian global di semua model
 - debug_perms_view()   → Debug endpoint (development only)
 - Custom error handlers (404, 403, 400, 500)
==========================================================================
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.core.cache_views import refresh_cache_view
from web_project.views import custom_error_404, custom_error_403, custom_error_400, custom_error_500


@login_required
def global_search_api(request):
    """API pencarian global — mencari di semua model utama sistem."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    try:
        # 1. Produk
        from apps.produk.models import Produk
        produk_qs = Produk.objects.filter(
            Q(nama__icontains=query) | Q(sku__icontains=query)
        )[:5]
        for p in produk_qs:
            results.append({
                'title': p.nama,
                'subtitle': f'SKU: {p.sku}' if p.sku else 'Produk',
                'icon': 'ri-shopping-bag-line',
                'category': 'Produk',
                'url': '/produk/',
            })

        # 2. Kategori
        from apps.produk.models import Kategori
        kategori_qs = Kategori.objects.filter(nama__icontains=query)[:3]
        for k in kategori_qs:
            results.append({
                'title': k.nama,
                'subtitle': 'Kategori Produk',
                'icon': 'ri-folder-line',
                'category': 'Kategori',
                'url': '/produk/kategori/',
            })

        # 3. Customer
        from apps.penjualan.models import Customer
        customer_qs = Customer.objects.filter(
            Q(nama__icontains=query) | Q(telepon__icontains=query) | Q(email__icontains=query)
        )[:5]
        for c in customer_qs:
            results.append({
                'title': c.nama,
                'subtitle': c.telepon or c.email or 'Customer',
                'icon': 'ri-user-heart-line',
                'category': 'Customer',
                'url': '/penjualan/customer/',
            })

        # 4. Supplier
        from apps.pembelian.models import Supplier
        supplier_qs = Supplier.objects.filter(
            Q(nama__icontains=query) | Q(telepon__icontains=query) | Q(email__icontains=query)
        )[:5]
        for s in supplier_qs:
            results.append({
                'title': s.nama,
                'subtitle': s.telepon or s.email or 'Supplier',
                'icon': 'ri-truck-line',
                'category': 'Supplier',
                'url': '/pembelian/supplier/',
            })

        # 5. Gudang
        from apps.inventory.models import Gudang
        gudang_qs = Gudang.objects.filter(
            Q(nama__icontains=query) | Q(alamat__icontains=query)
        )[:3]
        for g in gudang_qs:
            results.append({
                'title': g.nama,
                'subtitle': g.alamat or 'Gudang',
                'icon': 'ri-home-4-line',
                'category': 'Gudang',
                'url': '/inventory/gudang/',
            })

        # 6. User
        from django.contrib.auth.models import User
        user_qs = User.objects.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
        )[:3]
        for u in user_qs:
            full_name = u.get_full_name() or u.username
            results.append({
                'title': full_name,
                'subtitle': f'@{u.username}',
                'icon': 'ri-user-line',
                'category': 'User',
                'url': '/users/',
            })

        # 7. Karyawan
        from apps.hr.models import Karyawan
        karyawan_qs = Karyawan.objects.filter(
            Q(nama__icontains=query) | Q(nik__icontains=query) | Q(email__icontains=query)
        )[:3]
        for k in karyawan_qs:
            results.append({
                'title': k.nama,
                'subtitle': f'NIK: {k.nik}' if hasattr(k, 'nik') and k.nik else 'Karyawan',
                'icon': 'ri-team-line',
                'category': 'Karyawan',
                'url': '/hr/karyawan/',
            })

        # 8. Transaksi POS
        from apps.pos.models import POSTransaction
        pos_qs = POSTransaction.objects.filter(
            Q(nomor_transaksi__icontains=query) | Q(nama_customer__icontains=query)
        )[:3]
        for t in pos_qs:
            results.append({
                'title': t.nomor_transaksi,
                'subtitle': t.nama_customer or 'Transaksi POS',
                'icon': 'ri-shopping-cart-2-line',
                'category': 'Transaksi POS',
                'url': f'/pos/invoice/{t.pk}/',
            })

        # 9. Sales Order
        from apps.penjualan.models import SalesOrder
        so_qs = SalesOrder.objects.filter(
            Q(nomor_so__icontains=query)
        )[:3]
        for so in so_qs:
            results.append({
                'title': so.nomor_so,
                'subtitle': 'Sales Order',
                'icon': 'ri-file-list-3-line',
                'category': 'Sales Order',
                'url': '/penjualan/sales-order/',
            })

        # 10. Purchase Order
        from apps.pembelian.models import PurchaseOrder
        po_qs = PurchaseOrder.objects.filter(
            Q(nomor_po__icontains=query)
        )[:3]
        for po in po_qs:
            results.append({
                'title': po.nomor_po,
                'subtitle': 'Purchase Order',
                'icon': 'ri-file-list-2-line',
                'category': 'Purchase Order',
                'url': '/pembelian/purchase-order/',
            })

        # 11. Order Service
        from apps.service_center.models import OrderService as SC_OrderService
        sc_qs = SC_OrderService.objects.filter(
            Q(nomor_service__icontains=query) | Q(pelanggan__nama__icontains=query) |
            Q(merek__icontains=query) | Q(model_tipe__icontains=query)
        )[:5]
        for sc in sc_qs:
            results.append({
                'title': sc.nomor_service,
                'subtitle': f'{sc.pelanggan.nama} - {sc.merek} {sc.model_tipe or ""}',
                'icon': 'ri-tools-line',
                'category': 'Order Service',
                'url': f'/service/order/{sc.pk}/',
            })

        # 12. Pelanggan Service
        from apps.service_center.models import Pelanggan as SC_Pelanggan
        sc_plg = SC_Pelanggan.objects.filter(
            Q(nama__icontains=query) | Q(telepon__icontains=query) | Q(kode__icontains=query)
        )[:3]
        for p in sc_plg:
            results.append({
                'title': p.nama,
                'subtitle': f'{p.kode} - {p.telepon}',
                'icon': 'ri-user-heart-line',
                'category': 'Pelanggan Service',
                'url': '/service/pelanggan/',
            })

    except Exception:
        pass  # Jika model tidak ada, skip

    return JsonResponse({'results': results[:20]})




urlpatterns = [
    #path("admin/", admin.site.urls),
    
    # Test Error Routes (untuk testing error handlers)
    path("test-error/404/", lambda request: custom_error_404(request, Exception("Test 404"))),
    path("test-error/403/", lambda request: custom_error_403(request, Exception("Test 403"))),
    path("test-error/400/", lambda request: custom_error_400(request, Exception("Test 400"))),
    path("test-error/500/", lambda request: custom_error_500(request)),
    
    # Global Search API — endpoint pencarian global untuk semua modul
    path("api/search/", global_search_api, name='global_search'),
    path("core/cache/refresh/", refresh_cache_view, name='core_refresh_cache'),
    
    # Tenant Provisioning API — Internal endpoint untuk CLS
    path("api/internal/", include("apps.tenants.api_urls")),

    # License Activation URLs
    path("", include("apps.core.license_urls")),

    # Auth URLs
    path("", include("auth.urls")),
    
    # ERP Module URLs
    path("", include("apps.dashboard.urls")),
    path("users/", include("apps.user_management.urls")),
    path("produk/", include("apps.produk.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("pembelian/", include("apps.pembelian.urls")),
    path("penjualan/", include("apps.penjualan.urls")),
    path("pos/", include("apps.pos.urls")),
    path("biaya/", include("apps.biaya.urls")),
    path("laporan/", include("apps.laporan.urls")),
    path("activity-log/", include("apps.activity_log.urls")),
    path("pengaturan/", include("apps.pengaturan.urls")),
    path("access/", include("apps.permission_management.urls")),  # Changed to /access/
    path("hr/", include("apps.hr.urls")),  # HR Management
    path("automation/", include("apps.automation.urls")),  # Automasi Telegram
    path("ai/", include("apps.ai_assistant.urls")),  # AI Chat Assistant
    path("fraud/", include("apps.fraud_detection.urls")),  # Fraud Detection
    path("piutang/", include("apps.piutang.urls")),  # Piutang (Accounts Receivable)
    path("akuntansi/", include("apps.akuntansi.urls")),  # Akuntansi (Core Accounting)
    path("kas-bank/", include("apps.kas_bank.urls")),  # Kas & Bank (Treasury)
    path("hutang/", include("apps.hutang.urls")),  # Hutang (Accounts Payable)
    path("aset/", include("apps.aset.urls")),  # Aset Tetap (Fixed Assets)
    path("pajak/", include("apps.pajak.urls")),  # Pajak (Tax Engine)
    path("service/", include("apps.service_center.urls")),  # Service Center Elektronik
    
    # Original URLs
    path("", include("apps.pages.urls")),
]

# Media files — dilayani di semua environment (development & production)
# WhiteNoise hanya menangani static files, bukan media files.
# Agar foto/upload berfungsi di production, Django harus tetap melayani media.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Error Handlers
handler404 = custom_error_404
handler403 = custom_error_403
handler400 = custom_error_400
handler500 = custom_error_500
