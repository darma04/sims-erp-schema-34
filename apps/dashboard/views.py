"""
==========================================================================
 DASHBOARD VIEWS - View utama Dashboard ERP (1015 baris)
==========================================================================
 Satu class DashboardView (TemplateView) dengan get_context_data() raksasa
 yang mengumpulkan data dari SELURUH modul untuk ditampilkan di dashboard.

 DATA YANG DIKUMPULKAN:
 1. Sales Overview: total penjualan (SO + POS), revenue, growth bulan ini
 2. Produk: total produk, stok rendah, stok kosong, produk terlaris
 3. Keuangan: pendapatan, pengeluaran (PO + biaya), profit margin
 4. Customer & Supplier: statistik jumlah + baru
 5. Grafik: data penjualan harian (7 hari), penjualan bulanan (6 bulan)
 6. HR Stats: karyawan aktif, absensi hari ini, penggajian
 7. Inventory: transfer stok, adjustment, nilai stok total
 8. Payment Methods: statistik per metode pembayaran (build_card_data)
 9. Quick Stats: transaksi hari ini, pending, produk terlaris

 FITUR KHUSUS:
 - Filter tanggal dari GET params (start_date, end_date)
 - build_card_data(): helper nested function untuk metode pembayaran
 - fmt(): helper format angka ke format singkat (K, Jt, M)
 - Semua query dibungkus try/except agar dashboard tidak crash
==========================================================================
"""

import logging
logger = logging.getLogger(__name__)

# ==========================================================================
# PANDUAN DJANGO UNTUK DEVELOPER PEMULA (baca ini sebelum mempelajari views)
# ==========================================================================
#
# APA ITU CLASS-BASED VIEW (CBV)?
# - CBV = class Python yang menangani HTTP request dan return response
# - Django menyediakan CBV bawaan: ListView, CreateView, UpdateView, DeleteView
# - Setiap CBV punya "lifecycle" (siklus hidup) yang bisa di-customize
#
# SIKLUS HIDUP CBV (urutan method yang dipanggil):
# 1. as_view()     → Entry point, dipanggil oleh URL router
# 2. dispatch()    → Tentukan method (GET/POST) → panggil get() atau post()
# 3. get()/post()  → Handle request, kumpulkan data
# 4. get_queryset()→ Ambil data dari database (bisa di-filter/optimasi)
# 5. get_context_data() → Siapkan data untuk template (variabel {{ }})
# 6. render()      → Gabungkan template + context → HTML response
#
# METHOD PENTING YANG SERING DI-OVERRIDE:
# - get_queryset()     → Optimasi query (prefetch_related, select_related)
# - get_context_data() → Tambah variabel ke template (self.context)
# - form_valid()       → Proses setelah form divalidasi (sebelum save)
# - get_success_url()  → URL redirect setelah operasi berhasil
#
# DECORATOR YANG SERING DIGUNAKAN:
# @login_required       → User HARUS login, jika tidak → redirect ke /login/
# @permission_required  → User harus punya permission tertentu (RBAC)
# @require_http_methods → Batasi method yang diterima (GET, POST, dll)
# @never_cache          → Response tidak boleh di-cache oleh browser
#
# POLA UMUM VIEW DI PROYEK INI:
# class MyListView(SubModulePermissionMixin, ListView):
#     module_name = 'nama_modul'          # Untuk pengecekan RBAC
#     sub_module_name = 'nama_sub_modul'  # Sub-modul yang diakses
#     model = MyModel                      # Model database yang dipakai
#     template_name = 'modul/page.html'    # File HTML template
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context = TemplateLayout.init(self, context)  # WAJIB: setup layout
#         context['data_tambahan'] = ...    # Tambah data custom
#         return context
# ==========================================================================


# Import dari framework Django
from django.shortcuts import render
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import TemplateView
# Import dari framework Django
from django.utils.decorators import method_decorator
from web_project import TemplateLayout
# Import dari framework Django
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
# Import dari framework Django
from django.db.models.functions import Coalesce
from apps.core.mixins import ReadPermissionMixin, TenantScopedResponseCacheMixin
from datetime import datetime, timedelta
from decimal import Decimal
import logging  # Modul logging standar Python — pengganti print() untuk production

# Inisialisasi logger untuk modul Dashboard


@method_decorator(login_required, name='dispatch')
class DashboardView(TenantScopedResponseCacheMixin, ReadPermissionMixin, TemplateView):
    """
    View utama DASHBOARD ERP — mengumpulkan data dari SELURUH modul.

    Dashboard menampilkan ringkasan bisnis:
    - Sales overview (penjualan SO + POS, revenue, growth)
    - Statistik produk (total, stok rendah, terlaris)
    - Keuangan (pendapatan, pengeluaran, profit margin)
    - Grafik penjualan harian & bulanan (Chart.js)
    - HR stats (karyawan, absensi, penggajian)
    - Inventory (transfer, adjustment, nilai stok)

    Semua query dibungkus try/except agar dashboard tidak crash
    ketika salah satu modul bermasalah.

    Template: dashboard/index.html
    URL: / (halaman utama setelah login)
    """
    template_name = 'dashboard/index.html'
    permission_module = 'dashboard'
    cache_timeout = 60
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        
        try:
            # Import dari modul internal proyek
            from apps.produk.models import Produk, Stok, Kategori
            # Import dari modul internal proyek
            from apps.penjualan.models import SalesOrder, SalesOrderItem, Customer
            # Import dari framework Django
            from django.contrib.auth.models import User
            # Import dari framework Django
            from django.utils import timezone
            
            today = timezone.now().date()
            month_start = today.replace(day=1)
            last_month_start = (month_start - timedelta(days=1)).replace(day=1)
            
            # --- FILTER WAKTU dari GET params ---
            start_date_str = self.request.GET.get('start_date', '')
            end_date_str = self.request.GET.get('end_date', '')
            filter_start = None
            filter_end = None
            has_date_filter = False
            
            if start_date_str:
                try:
                    filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    has_date_filter = True
                except ValueError:
                    pass
            if end_date_str:
                try:
                    filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    has_date_filter = True
                except ValueError:
                    pass
            
            context['filter_start_date'] = start_date_str
            context['filter_end_date'] = end_date_str
            context['has_date_filter'] = has_date_filter
            context['is_dashboard'] = True  # Flag agar navbar menampilkan icon filter
            
            # --- 1. SALES OVERVIEW - Real Data ---
            from apps.pos.models import POSTransaction
            
            # Bangun filter tanggal sebagai dictionary kwargs
            # so_date_filter → untuk Sales Order, pos_date_filter → untuk POS
            so_date_filter = {}
            pos_date_filter = {}
            if filter_start:
                so_date_filter['tanggal__date__gte'] = filter_start
                pos_date_filter['tanggal__date__gte'] = filter_start
            if filter_end:
                so_date_filter['tanggal__date__lte'] = filter_end
                pos_date_filter['tanggal__date__lte'] = filter_end
            
            total_sales_so = SalesOrder.objects.exclude(status='cancelled').filter(**so_date_filter).count()
            total_sales_pos = POSTransaction.objects.exclude(status='cancelled').filter(**pos_date_filter).count()

            # Service Center order count & revenue (untuk Ringkasan Penjualan)
            try:
                from apps.service_center.models import OrderService as SC_OrderOverview
                sc_overview_filter = {}
                if filter_start:
                    sc_overview_filter['tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    sc_overview_filter['tanggal_masuk__date__lte'] = filter_end
                total_sales_sc = SC_OrderOverview.objects.exclude(status='dibatalkan').filter(**sc_overview_filter).count()
                revenue_sc = SC_OrderOverview.objects.filter(
                    status_bayar='lunas', **sc_overview_filter
                ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
            except Exception:
                total_sales_sc = 0
                revenue_sc = 0

            total_sales = total_sales_so + total_sales_pos + total_sales_sc
            
            revenue_so = SalesOrder.objects.filter(
                status__in=['confirmed', 'delivered', 'completed'],
                **so_date_filter
            ).aggregate(total=Sum('total_harga'))['total'] or 0
            
            revenue_pos = POSTransaction.objects.filter(
                status='paid',
                **pos_date_filter
            ).aggregate(total=Sum('total_harga'))['total'] or 0
            
            total_revenue = revenue_so + revenue_pos + revenue_sc
            
            # Hitung pertumbuhan pendapatan dibanding bulan lalu (SO + POS + SC)
            this_month_revenue_so = SalesOrder.objects.filter(
                tanggal__date__gte=month_start,
                status__in=['confirmed', 'delivered', 'completed']
            ).aggregate(total=Sum('total_harga'))['total'] or 0
            
            this_month_revenue_pos = POSTransaction.objects.filter(
                tanggal__date__gte=month_start,
                status='paid'
            ).aggregate(total=Sum('total_harga'))['total'] or 0

            # SC revenue bulan ini
            try:
                this_month_revenue_sc = SC_OrderOverview.objects.filter(
                    tanggal_masuk__date__gte=month_start,
                    status_bayar='lunas'
                ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
            except Exception:
                this_month_revenue_sc = 0
            
            this_month_revenue = this_month_revenue_so + this_month_revenue_pos + this_month_revenue_sc
            
            last_month_revenue_so = SalesOrder.objects.filter(
                tanggal__date__gte=last_month_start,
                tanggal__date__lt=month_start,
                status__in=['confirmed', 'delivered', 'completed']
            ).aggregate(total=Sum('total_harga'))['total'] or 0
            
            last_month_revenue_pos = POSTransaction.objects.filter(
                tanggal__date__gte=last_month_start,
                tanggal__date__lt=month_start,
                status='paid'
            ).aggregate(total=Sum('total_harga'))['total'] or 0

            # SC revenue bulan lalu
            try:
                last_month_revenue_sc = SC_OrderOverview.objects.filter(
                    tanggal_masuk__date__gte=last_month_start,
                    tanggal_masuk__date__lt=month_start,
                    status_bayar='lunas'
                ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
            except Exception:
                last_month_revenue_sc = 0
            
            last_month_revenue = last_month_revenue_so + last_month_revenue_pos + last_month_revenue_sc
            
            if last_month_revenue > 0:
                growth_percentage = ((this_month_revenue - last_month_revenue) / last_month_revenue) * 100
            else:
                growth_percentage = 100 if this_month_revenue > 0 else 0
            
            # Customer baru tahun ini — dari model Customer di modul Penjualan
            new_customers = Customer.objects.filter(
                dibuat_pada__year=timezone.now().year
            ).count()
            
            # Total produk aktif dan total stok keseluruhan
            total_produk = Produk.objects.filter(aktif=True).count()
            total_stok = Stok.objects.aggregate(total=Sum('jumlah'))['total'] or 0
            
            # ===== Hitung Total Keseluruhan Aset, Total Harga Beli, Total Harga Jual, Estimasi Keuntungan =====
            # CATATAN: Total Aset TIDAK dipengaruhi filter tanggal — bersifat kumulatif historis.
            # Total Aset = harga_beli × semua qty yang pernah masuk (stok + terjual + adjustment).
            # Ini menjadi patokan untuk deteksi kecurangan/selisih.
            total_keseluruhan_aset = Decimal('0')
            total_harga_beli_ready = Decimal('0')
            total_harga_jual_ready = Decimal('0')
            estimasi_keuntungan = Decimal('0')
            
            try:
                # Import dari modul internal proyek
                from apps.penjualan.models import SalesOrderItem
                # Import dari modul internal proyek
                from apps.pos.models import POSTransactionItem
                from apps.inventory.models import AdjustmentStok
                
                # Qty terjual per produk dari SO — TANPA filter tanggal (kumulatif)
                so_sold_by_produk = {}
                for item in SalesOrderItem.objects.filter(
                    sales_order__status__in=['confirmed', 'delivered', 'completed']
                ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                    so_sold_by_produk[item['produk_id']] = item['total_qty']
                
                # Qty terjual per produk dari POS — TANPA filter tanggal (kumulatif)
                pos_sold_by_produk = {}
                for item in POSTransactionItem.objects.filter(
                    transaction__status='paid'
                ).values('produk_id').annotate(total_qty=Sum('jumlah_konversi')):
                    pos_sold_by_produk[item['produk_id']] = item['total_qty']
                
                # Qty adjustment per produk — TANPA filter tanggal (kumulatif historis)
                # Adjustment 'out' mengurangi qty yang pernah masuk (misal: barang rusak/hilang)
                adj_out_by_produk = {}
                for item in AdjustmentStok.objects.filter(
                    tipe='out'
                ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                    adj_out_by_produk[item['produk_id']] = item['total_qty']

                # Qty sparepart terpakai dari Service Center — kumulatif historis
                sc_used_by_produk = {}
                try:
                    from apps.service_center.models import PenggunaanSparepart as SC_SP_Asset
                    for item in SC_SP_Asset.objects.values('produk_id').annotate(
                        total_qty=Sum('jumlah')
                    ):
                        if item['produk_id']:
                            sc_used_by_produk[item['produk_id']] = item['total_qty']
                except Exception as e:
                    logger.warning("Error tidak terduga: %s", e)
                
                # Hitung per produk
                for produk in Produk.objects.prefetch_related('stok_set').all():
                    stok_saat_ini = sum(s.jumlah for s in produk.stok_set.all())
                    qty_sold_so = so_sold_by_produk.get(produk.pk, Decimal('0'))
                    qty_sold_pos = pos_sold_by_produk.get(produk.pk, Decimal('0'))
                    qty_adj_out = adj_out_by_produk.get(produk.pk, Decimal('0'))
                    qty_sc_used = sc_used_by_produk.get(produk.pk, Decimal('0'))
                    # Total Aset = harga_beli × (stok saat ini + terjual + yg keluar via adjustment + service)
                    qty_total_pernah_masuk = stok_saat_ini + qty_sold_so + qty_sold_pos + qty_adj_out + qty_sc_used
                    
                    # Total Keseluruhan Aset = harga_beli × total stok pernah masuk
                    total_keseluruhan_aset += produk.harga_beli * qty_total_pernah_masuk
                    
                    # Hanya produk ready (stok > 0)
                    if stok_saat_ini > 0:
                        total_harga_beli_ready += produk.harga_beli * stok_saat_ini
                        total_harga_jual_ready += produk.harga_jual * stok_saat_ini
                
                estimasi_keuntungan = total_harga_jual_ready - total_harga_beli_ready
            except Exception as asset_err:
                # Catat error perhitungan aset ke log — tidak menghentikan proses
                logger.error("Error menghitung total aset: %s", asset_err, exc_info=True)
            
            context['sales_overview'] = {
                'total_sales': total_sales,
                'revenue': total_revenue,
                'growth': round(growth_percentage, 1),
                'new_customers': new_customers,
                'products': total_produk,
                'stock': int(total_stok),
                'total_keseluruhan_aset': total_keseluruhan_aset,
                'total_harga_beli': total_harga_beli_ready,
                'total_harga_jual': total_harga_jual_ready,
                'estimasi_keuntungan': estimasi_keuntungan,
            }
            
            # --- 2. SALES SLIDER - Real Data ---
            # Slider 1: Transaksi POS + Top Product dari POS
            # Slider 2: Sales Order + Top Product dari SO
            # Slider 3: Produk dengan stock terbanyak
            
            weekly_sales_data = []
            
            # ===== SLIDER 1: Transaksi POS =====
            try:
                # Import dari modul internal proyek
                from apps.pos.models import POSTransactionItem
                
                # POS queries — with optional date filter
                pos_qs = POSTransaction.objects.filter(status='paid', **pos_date_filter)
                total_pos_count = pos_qs.count()
                total_pos_revenue = pos_qs.aggregate(total=Sum('total_harga'))['total'] or 0
                
                # Top products dari POS
                pos_item_filter = {'transaction__status': 'paid'}
                if filter_start:
                    pos_item_filter['transaction__tanggal__date__gte'] = filter_start
                if filter_end:
                    pos_item_filter['transaction__tanggal__date__lte'] = filter_end
                
                top_pos_items = POSTransactionItem.objects.filter(
                    **pos_item_filter
                ).values('produk__id', 'produk__nama', 'produk__gambar').annotate(
                    total_qty=Sum('jumlah'),
                    total_revenue=Sum('subtotal')
                ).order_by('-total_qty')[:4]
                
                pos_items_list = []
                top_pos_product = None
                
                for item in top_pos_items:
                    pos_items_list.append({
                        'name': item['produk__nama'],
                        'count': int(item['total_qty'])
                    })
                    if top_pos_product is None and item['produk__id']:
                        produk_obj = Produk.objects.filter(pk=item['produk__id']).first()
                        if produk_obj:
                            top_pos_product = produk_obj
                
                # Format revenue
                if total_pos_revenue < 1000000:
                    earning_str = f'Rp {total_pos_revenue/1000:.1f}k'
                else:
                    earning_str = f'Rp {total_pos_revenue/1000000:.1f}jt'
                
                # Pastikan selalu 4 item (pad dengan placeholder jika kurang)
                while len(pos_items_list) < 4:
                    pos_items_list.append({'name': 'Belum ada data', 'count': 0})
                
                weekly_sales_data.append({
                    'category': 'Transaksi POS',
                    'items': pos_items_list[:4],
                    'earning': earning_str,
                    'growth': total_pos_count,
                    'product_image': top_pos_product.gambar if top_pos_product and top_pos_product.gambar else None
                })
                
            except Exception as e:
                weekly_sales_data.append({
                    'category': 'Transaksi POS',
                    'items': [
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                    ],
                    'earning': 'Rp 0',
                    'growth': 0,
                    'product_image': None
                })
            
            # ===== SLIDER 2: Sales Order =====
            try:
                # SO queries — with optional date filter
                so_qs = SalesOrder.objects.filter(
                    status__in=['confirmed', 'delivered', 'completed'],
                    **so_date_filter
                )
                total_so = so_qs.count()
                total_so_revenue = so_qs.aggregate(total=Sum('total_harga'))['total'] or 0
                
                # Top products dari Sales Order
                so_item_filter = {'sales_order__status__in': ['confirmed', 'delivered', 'completed']}
                if filter_start:
                    so_item_filter['sales_order__tanggal__date__gte'] = filter_start
                if filter_end:
                    so_item_filter['sales_order__tanggal__date__lte'] = filter_end
                
                top_so_items = SalesOrderItem.objects.filter(
                    **so_item_filter
                ).values('produk__id', 'produk__nama', 'produk__gambar').annotate(
                    total_qty=Sum('jumlah'),
                    total_revenue=Sum('subtotal')
                ).order_by('-total_qty')[:4]
                
                so_items_list = []
                top_so_product = None
                
                for item in top_so_items:
                    so_items_list.append({
                        'name': item['produk__nama'],
                        'count': int(item['total_qty'])
                    })
                    if top_so_product is None and item['produk__id']:
                        produk_obj = Produk.objects.filter(pk=item['produk__id']).first()
                        if produk_obj:
                            top_so_product = produk_obj
                
                # Format revenue
                if total_so_revenue < 1000000:
                    earning_str = f'Rp {total_so_revenue/1000:.1f}k'
                else:
                    earning_str = f'Rp {total_so_revenue/1000000:.1f}jt'
                
                # Pastikan selalu 4 item (pad dengan placeholder jika kurang)
                while len(so_items_list) < 4:
                    so_items_list.append({'name': 'Belum ada data', 'count': 0})
                
                weekly_sales_data.append({
                    'category': 'Sales Order',
                    'items': so_items_list[:4],
                    'earning': earning_str,
                    'growth': total_so,
                    'product_image': top_so_product.gambar if top_so_product and top_so_product.gambar else None
                })
                
            except Exception as e:
                weekly_sales_data.append({
                    'category': 'Sales Order',
                    'items': [
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                    ],
                    'earning': 'Rp 0',
                    'growth': 0,
                    'product_image': None
                })
            
            # ===== SLIDER 3: Produk dengan Stock Terbanyak =====
            try:
                # Gunakan Coalesce agar nilai None menjadi 0 (aman untuk perhitungan)
                # Menampilkan semua produk termasuk non-aktif
                # Coalesce dan Decimal sudah di-import di bagian atas file
                
                highest_stock_products = Produk.objects.annotate(
                    total_stock=Coalesce(Sum('stok_set__jumlah'), Decimal('0'))
                ).order_by('-total_stock')[:4]
                
                stock_items_list = []
                highest_stock_product = None
                total_stock_value = 0
                
                for produk in highest_stock_products:
                    # Coalesce menjamin tidak None, tapi tetap aman dikonversi ke float
                    stock_count = produk.total_stock
                    
                    stock_items_list.append({
                        'name': produk.nama,
                        'count': int(stock_count)
                    })
                    
                    # Ambil gambar produk dengan stok tertinggi (item pertama)
                    if highest_stock_product is None:
                        highest_stock_product = produk
                    
                    # Hitung total nilai stok (stok × harga jual)
                    total_stock_value += float(stock_count) * float(produk.harga_jual or 0)
                
                # Format nilai ke format singkat
                if total_stock_value < 1000000:
                    value_str = f'Rp {total_stock_value/1000:.1f}k'
                else:
                    value_str = f'Rp {total_stock_value/1000000:.1f}jt'
                
                # Pastikan selalu 4 item (pad dengan placeholder jika kurang)
                while len(stock_items_list) < 4:
                    stock_items_list.append({'name': 'Belum ada data', 'count': 0})
                
                weekly_sales_data.append({
                    'category': 'Produk Stock Terbanyak',
                    'items': stock_items_list[:4],
                    'earning': value_str,
                    'growth': 8,
                    'product_image': highest_stock_product.gambar if highest_stock_product and highest_stock_product.gambar else None
                })
                
            except Exception as e:
                weekly_sales_data.append({
                    'category': 'Produk Stock Terbanyak',
                    'items': [
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                    ],
                    'earning': 'Rp 0',
                    'growth': 0,
                    'product_image': None
                })

            
            # ===== SLIDER 4: Sparepart Terbanyak Digunakan =====
            try:
                from apps.service_center.models import PenggunaanSparepart as SC_SP_Slider

                # Filter tanggal opsional
                sp_slider_filter = {}
                if filter_start:
                    sp_slider_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    sp_slider_filter['order_service__tanggal_masuk__date__lte'] = filter_end

                # Total harga sparepart
                total_sp_cost = SC_SP_Slider.objects.filter(
                    **sp_slider_filter
                ).annotate(
                    _sub=ExpressionWrapper(
                        F('jumlah') * F('harga_satuan'),
                        output_field=DecimalField()
                    )
                ).aggregate(total=Sum('_sub'))['total'] or 0

                total_sp_usage_count = SC_SP_Slider.objects.filter(**sp_slider_filter).count()

                # Top sparepart berdasarkan jumlah penggunaan
                top_sp_items = SC_SP_Slider.objects.filter(
                    **sp_slider_filter
                ).values('produk__id', 'produk__nama', 'produk__gambar').annotate(
                    total_qty=Sum('jumlah'),
                    total_cost=Sum(ExpressionWrapper(
                        F('jumlah') * F('harga_satuan'),
                        output_field=DecimalField()
                    ))
                ).order_by('-total_qty')[:4]

                sp_items_list = []
                top_sp_product = None
                for item in top_sp_items:
                    sp_items_list.append({
                        'name': item['produk__nama'][:30],
                        'count': int(item['total_qty'])
                    })
                    if top_sp_product is None and item['produk__id']:
                        sp_obj = Produk.objects.filter(pk=item['produk__id']).first()
                        if sp_obj:
                            top_sp_product = sp_obj

                # Format biaya
                if total_sp_cost < 1000000:
                    sp_earning_str = f'Rp {total_sp_cost/1000:.1f}k'
                else:
                    sp_earning_str = f'Rp {total_sp_cost/1000000:.1f}jt'

                while len(sp_items_list) < 4:
                    sp_items_list.append({'name': 'Belum ada data', 'count': 0})

                weekly_sales_data.append({
                    'category': 'Sparepart Terbanyak',
                    'items': sp_items_list[:4],
                    'earning': sp_earning_str,
                    'growth': total_sp_usage_count,
                    'product_image': top_sp_product.gambar if top_sp_product and top_sp_product.gambar else None
                })

            except Exception as e:
                weekly_sales_data.append({
                    'category': 'Sparepart Terbanyak',
                    'items': [
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                        {'name': 'Belum ada data', 'count': 0},
                    ],
                    'earning': 'Rp 0',
                    'growth': 0,
                    'product_image': None
                })

            # === SERVICE CENTER OVERVIEW ===
            try:
                from apps.service_center.models import OrderService as SC_OrderDash
                from apps.service_center.models import Pelanggan as SC_PelangganDash

                sc_dash_filter = {}
                if filter_start:
                    sc_dash_filter['tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    sc_dash_filter['tanggal_masuk__date__lte'] = filter_end

                sc_aktif = SC_OrderDash.objects.filter(
                    status__in=['diterima', 'diagnosa', 'menunggu_konfirmasi', 'dikerjakan'],
                    **sc_dash_filter
                ).count()
                sc_selesai = SC_OrderDash.objects.filter(
                    status__in=['selesai', 'diambil'],
                    **sc_dash_filter
                ).count()
                sc_pending_bayar = SC_OrderDash.objects.filter(
                    status_bayar__in=['belum_bayar', 'dp'],
                    status__in=['selesai'],
                    **sc_dash_filter
                ).count()
                sc_revenue_total = SC_OrderDash.objects.filter(
                    status_bayar='lunas',
                    **sc_dash_filter
                ).aggregate(total=Sum('biaya_akhir'))['total'] or 0

                # Pemasukan Sparepart = total harga jual sparepart dari order LUNAS
                from apps.service_center.models import PenggunaanSparepart as SC_Sparepart
                sp_filter = {}
                if filter_start:
                    sp_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    sp_filter['order_service__tanggal_masuk__date__lte'] = filter_end

                sc_pemasukan_sparepart = SC_Sparepart.objects.filter(
                    order_service__status_bayar='lunas',
                    **sp_filter
                ).annotate(
                    _subtotal=ExpressionWrapper(
                        F('jumlah') * F('harga_satuan'),
                        output_field=DecimalField()
                    )
                ).aggregate(total=Sum('_subtotal'))['total'] or 0

                # Pemasukan Layanan = total biaya ItemService dari order LUNAS (tanpa sparepart)
                from apps.service_center.models import ItemService as SC_ItemService
                item_filter = {}
                if filter_start:
                    item_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    item_filter['order_service__tanggal_masuk__date__lte'] = filter_end

                sc_pemasukan_layanan = SC_ItemService.objects.filter(
                    order_service__status_bayar='lunas',
                    **item_filter
                ).aggregate(total=Sum('biaya'))['total'] or 0

                # Total order (exclude cancelled)
                sc_total_orders = SC_OrderDash.objects.exclude(
                    status='dibatalkan'
                ).filter(**sc_dash_filter).count()

                # Total sparepart usage count
                sc_total_sparepart = SC_Sparepart.objects.filter(
                    **sp_filter
                ).count()

                context['service_overview'] = {
                    'total_revenue': sc_revenue_total,
                    'pemasukan_layanan': sc_pemasukan_layanan,
                    'pemasukan_sparepart': sc_pemasukan_sparepart,
                    'total_sparepart': sc_total_sparepart,
                    'total_orders': sc_total_orders,
                    'order_selesai': sc_selesai,
                    'total_pelanggan': SC_PelangganDash.objects.filter(aktif=True).count(),
                }
            except Exception:
                context['service_overview'] = {
                    'total_revenue': 0, 'pemasukan_layanan': 0, 'pemasukan_sparepart': 0,
                    'total_sparepart': 0, 'total_orders': 0, 'order_selesai': 0, 'total_pelanggan': 0,
                }

            context['weekly_sales_data'] = weekly_sales_data
            
            # --- 3. TOP PRODUCTS TABLE - Real Data (Sales Order + POS) ---
            from apps.pos.models import POSTransactionItem
            from collections import defaultdict
            
            # Dictionary untuk menggabungkan data penjualan dari SO + POS
            # Key = produk_id, Value = {total_qty, total_revenue, produk_data}
            product_sales = defaultdict(lambda: {'total_qty': 0, 'total_revenue': 0, 'produk_data': None})
            
            # Ambil data penjualan dari SalesOrderItem (dengan filter tanggal)
            so_top_filter = {'sales_order__status__in': ['confirmed', 'delivered', 'completed']}
            if filter_start:
                so_top_filter['sales_order__tanggal__date__gte'] = filter_start
            if filter_end:
                so_top_filter['sales_order__tanggal__date__lte'] = filter_end
            
            so_items = SalesOrderItem.objects.filter(
                **so_top_filter
            ).values(
                'produk__id',
                'produk__nama',
                'produk__sku',
                'produk__harga_jual',
                'produk__harga_beli',
                'produk__gambar'
            ).annotate(
                total_qty=Sum('jumlah'),
                total_revenue=Sum('subtotal')
            )
            
            for item in so_items:
                pid = item['produk__id']
                product_sales[pid]['total_qty'] += float(item['total_qty'] or 0)
                product_sales[pid]['total_revenue'] += float(item['total_revenue'] or 0)
                product_sales[pid]['produk_data'] = item
            
            # Ambil data penjualan dari POSTransactionItem (dengan filter tanggal)
            pos_top_filter = {'transaction__status': 'paid'}
            if filter_start:
                pos_top_filter['transaction__tanggal__date__gte'] = filter_start
            if filter_end:
                pos_top_filter['transaction__tanggal__date__lte'] = filter_end
            
            pos_items = POSTransactionItem.objects.filter(
                **pos_top_filter
            ).values(
                'produk__id',
                'produk__nama',
                'produk__sku',
                'produk__harga_jual',
                'produk__harga_beli',
                'produk__gambar'
            ).annotate(
                total_qty=Sum('jumlah'),
                total_revenue=Sum('subtotal')
            )
            
            for item in pos_items:
                pid = item['produk__id']
                product_sales[pid]['total_qty'] += float(item['total_qty'] or 0)
                product_sales[pid]['total_revenue'] += float(item['total_revenue'] or 0)
                if not product_sales[pid]['produk_data']:
                    product_sales[pid]['produk_data'] = item
            
            # Urutkan berdasarkan total revenue terbesar, ambil 5 teratas
            sorted_products = sorted(
                product_sales.items(),
                key=lambda x: x[1]['total_revenue'],
                reverse=True
            )[:5]
            
            top_products_list = []
            for pid, data in sorted_products:
                item = data['produk_data']
                if not item:
                    continue
                
                # Ambil objek produk asli untuk penanganan gambar yang benar
                produk_obj = Produk.objects.filter(pk=pid).first()
                    
                # Ambil status stok saat ini untuk menentukan label status
                total_stock = Stok.objects.filter(
                    produk__id=pid
                ).aggregate(total=Sum('jumlah'))['total'] or 0
                
                if total_stock > 10:
                    status = 'In Stock'
                    status_class = 'success'
                elif total_stock > 0:
                    status = 'Low Stock'
                    status_class = 'warning'
                else:
                    status = 'Out of Stock'
                    status_class = 'danger'
                
                # Hitung keuntungan (profit)
                revenue = data['total_revenue']
                cost = float(item['produk__harga_beli'] or 0) * data['total_qty']
                profit = revenue - cost
                profit_percentage = (profit / revenue * 100) if revenue > 0 else 0
                
                top_products_list.append({
                    'id': pid,
                    'name': item['produk__nama'],
                    'sku': item['produk__sku'],
                    'image': produk_obj.gambar if produk_obj and produk_obj.gambar else None,
                    'status': status,
                    'status_class': status_class,
                    'revenue': revenue,
                    'profit': profit,
                    'profit_percentage': round(profit_percentage, 1),
                    'qty_sold': int(data['total_qty'])
                })
            
            context['top_products'] = top_products_list
            
            # --- 4. ACTIVITY TIMELINE - Real Data from Activity Log ---
            try:
                # Import dari modul internal proyek
                from apps.activity_log.models import UserActivity
                recent_activities = UserActivity.objects.all().order_by('-timestamp')[:5]
                
                activity_timeline = []
                for activity in recent_activities:
                    # Hitung selisih waktu untuk tampilan "X hari/jam/menit lalu"
                    time_diff = timezone.now() - activity.timestamp
                    if time_diff.days > 0:
                        time_ago = f"{time_diff.days} hari lalu"
                    elif time_diff.seconds // 3600 > 0:
                        time_ago = f"{time_diff.seconds // 3600} jam lalu"
                    else:
                        time_ago = f"{time_diff.seconds // 60} menit lalu"
                    
                    # Tentukan warna badge berdasarkan jenis aksi
                    color_map = {
                        'create': 'success',
                        'update': 'info',
                        'delete': 'danger',
                        'view': 'primary',
                        'login': 'success',
                        'logout': 'warning',
                    }
                    color = color_map.get(activity.action, 'primary')
                    
                    # Format judul aktivitas
                    title = f"{activity.get_action_display()}"
                    if activity.model_name:
                        title += f" {activity.model_name}"
                    if activity.object_repr:
                        title += f": {activity.object_repr}"
                    
                    activity_timeline.append({
                        'title': title,
                        'time': time_ago,
                        'color': color,
                        'desc': activity.description or f"User {activity.user.username if activity.user else 'Unknown'} melakukan {activity.get_action_display()}",
                    })
                
                if activity_timeline:
                    context['activity_timeline'] = activity_timeline
                else:
                    raise Exception("No activities")
                    
            except Exception as e:
                # Catat error loading aktivitas — gunakan fallback data dummy
                logger.error("Error loading activities: %s", e, exc_info=True)
                # Fallback ke data dummy jika gagal load aktivitas
                context['activity_timeline'] = [
                    {
                        'title': 'Belum ada aktivitas',
                        'time': 'Baru saja',
                        'color': 'secondary',
                        'desc': 'Mulai gunakan sistem untuk melihat aktivitas',
                    }
                ]
            
            # --- 5. MARKETING & SALES METRICS - REPLACED WITH PAYMENT METHOD STATS ---
            try:
                # Import dari modul internal proyek
                from apps.pos.models import MetodePembayaran
                
                # Ambil semua metode pembayaran beserta total revenue
                # DIPERBAIKI QA-D1: Tambahkan filter tanggal agar konsisten saat filter aktif
                pos_revenue_q = Q(postransaction__status='paid')
                if filter_start:
                    pos_revenue_q &= Q(postransaction__tanggal__date__gte=filter_start)
                if filter_end:
                    pos_revenue_q &= Q(postransaction__tanggal__date__lte=filter_end)
                
                payment_methods = MetodePembayaran.objects.annotate(
                    revenue=Coalesce(Sum('postransaction__total_harga', filter=pos_revenue_q), Decimal('0')),
                    trx_count=Count('postransaction', filter=pos_revenue_q)
                ).order_by('-revenue')
                
                # Hitung total revenue seluruh metode untuk persentase share
                total_revenue_all = sum(pm.revenue for pm in payment_methods) or Decimal('1')
                
                marketing_sales_data = []
                
                if payment_methods.exists():
                    # Fungsi helper untuk membangun data kartu statistik pembayaran
                    def build_card_data(method, title):
                        # Hitung statistik tambahan (saldo, pendapatan, pengeluaran)
                        """Membuat data kartu dashboard dari parameter yang diberikan."""
                        saldo = method.saldo
                        pendapatan = method.revenue
                        # Pengeluaran needs to be calculated (PO + Biaya)
                        try:
                            pengeluaran = method.total_pengeluaran
                        except Exception:
                            pengeluaran = 0
                            
                        trx_total = method.trx_count
                        
                        # Hitung persentase share dari total revenue
                        share_percent = round((pendapatan / total_revenue_all) * 100, 1)
                        
                        # Format mata uang ke singkat (Rp Xk / Rp Xjt)
                        def fmt(val): 
                            """Format angka ke Rupiah penuh (contoh: Rp 550,000)."""
                            try:
                                val = float(val)
                                return f'Rp {val:,.0f}'
                            except (ValueError, TypeError):
                                return f'Rp 0'
                        
                        # Statistik metode pembayaran — menggunakan label singkat dan bersih
                        # Label dibuat minimalis agar tampilan ringkas tanpa menghilangkan konteks
                        
                        stats = [
                            {'label': 'Saldo', 'value': fmt(saldo)},
                            {'label': 'Pendapatan', 'value': fmt(pendapatan)},
                            {'label': 'Pengeluaran', 'value': fmt(pengeluaran)},
                            {'label': 'Transaksi', 'value': str(trx_total)},
                        ]
                        
                        # URLs
                        detail_url = f"/pengaturan/pembayaran/{method.pk}/" # Hardcoded based on standard URL pattern or use reverse
                        # We can use 'pengaturan:metode_pembayaran_detail' but need reverse inside view or pass ID
                        # Let's construct data so template can generate URL or pass ID
                        
                        return {
                            'title': title,
                            'total': method.nama,
                            'growth': share_percent, # Percentage share
                            'stats': stats,
                            'product_image': method.gambar if method.gambar else None,
                            'id': method.pk # Pass ID for URL generation in template
                        }

                    # === 1. Metode Pembayaran Tertinggi ===
                    marketing_sales_data.append(build_card_data(payment_methods.first(), 'Metode Pembayaran Tertinggi'))
                    
                    # === 2. Metode Pembayaran Terrendah ===
                    low_method = payment_methods.last()
                    marketing_sales_data.append(build_card_data(low_method, 'Metode Pembayaran Terrendah'))
                    
                else:
                    # Fallback jika belum ada metode pembayaran
                    marketing_sales_data = [
                        {'title': 'Metode Pembayaran Tertinggi', 'total': 'Belum ada data', 'growth': 0, 'stats': [], 'id': None},
                        {'title': 'Metode Pembayaran Terrendah', 'total': 'Belum ada data', 'growth': 0, 'stats': [], 'id': None}
                    ]
                    
            except Exception as e:
                # Catat error perhitungan statistik pembayaran
                logger.error("Error menghitung statistik pembayaran: %s", e, exc_info=True)
                marketing_sales_data = []
            
            context['marketing_sales_data'] = marketing_sales_data
            
            # --- 6. CHARTS DATA ---
            
            # Sales Chart Data — "Penjualan Bulan Ini"
            # Show daily sales for the current month (day 1 to today)
            sales_data = []
            sales_labels = []
            chart_start = month_start
            chart_end_date = today
            # Jika filter tanggal aktif, gunakan rentang filter sebagai gantinya
            if filter_start and filter_end:
                chart_start = filter_start
                chart_end_date = filter_end
            
            num_days = (chart_end_date - chart_start).days + 1
            for i in range(num_days):
                date = chart_start + timedelta(days=i)
                total_so = SalesOrder.objects.filter(
                    tanggal__date=date,
                    status__in=['confirmed', 'delivered', 'completed']
                ).aggregate(total=Sum('total_harga'))['total'] or 0
                total_pos_day = POSTransaction.objects.filter(
                    tanggal__date=date,
                    status='paid'
                ).aggregate(total=Sum('total_harga'))['total'] or 0
                # Service Center: revenue dari order lunas pada tanggal ini
                total_sc_day = 0
                try:
                    from apps.service_center.models import OrderService as SC_DayChart
                    total_sc_day = SC_DayChart.objects.filter(
                        tanggal_masuk__date=date,
                        status_bayar='lunas'
                    ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
                except Exception as e:
                    logger.warning("Error tidak terduga: %s", e)
                sales_data.append(float(total_so) + float(total_pos_day) + float(total_sc_day))
                sales_labels.append(date.day)
            context['sales_chart_data'] = sales_data
            context['sales_chart_labels'] = sales_labels
            
            # Default data chart — akan di-override dengan data riil jika tersedia
            context['live_visitors_data'] = [0]  # Default: keuntungan per cabang
            context['visits_by_day_data'] = [0]  # Default: biaya per kategori
            context['cabang_names'] = ['Belum ada']
            context['biaya_labels'] = ['Belum ada']
            
            # --- 7. USER TABLE - Real Data with Roles ---
            latest_users = User.objects.all().order_by('-date_joined')[:7]
            users_list = []
            
            for user in latest_users:
                # Tentukan role user
                if user.is_superuser:
                    role = 'Admin'
                    role_icon = 'ri-vip-crown-line'
                    role_color = 'danger'
                elif user.is_staff:
                    role = 'Editor'
                    role_icon = 'ri-edit-box-line'
                    role_color = 'info'
                else:
                    role = 'Subscriber'
                    role_icon = 'ri-user-line'
                    role_color = 'success'
                
                # Tentukan status user
                if user.is_active:
                    if user.last_login and (timezone.now() - user.last_login).days < 7:
                        status = 'Active'
                        status_class = 'success'
                    else:
                        status = 'Pending'
                        status_class = 'warning'
                else:
                    status = 'Inactive'
                    status_class = 'secondary'
                
                users_list.append({
                    'id': user.id,  # PENTING: diperlukan untuk URL reverse di template
                    'username': user.username,
                    'email': user.email,
                    'role': role,
                    'role_icon': role_icon,
                    'role_color': role_color,
                    'status': status,
                    'status_class': status_class,
                    'is_superuser': user.is_superuser,  # For delete action condition
                })
            
            context['latest_users'] = users_list
            
            # Sales This Month
            context['sales_this_month'] = this_month_revenue
            
            # Statistik tambahan
            context['total_customers'] = Customer.objects.filter(aktif=True).count()
            context['total_produk'] = total_produk
            context['total_sales'] = total_sales
            context['total_revenue'] = total_revenue

            # --- NEW: ERP Dashboard Cards Data ---
            # --- ERP Dashboard Cards Data ---
            
            # Initialize with safe defaults FIRST — memastikan chart & card 
            # selalu punya data meskipun terjadi error di blok try berikutnya
            context['cabang_profit_data'] = []
            context['sales_cabang_labels'] = []
            context['sales_cabang_series'] = []
            
            try:
                # Import dari modul internal proyek
                from apps.produk.models import Gudang
                # Import dari modul internal proyek
                from apps.pembelian.models import PurchaseOrder
                # Import dari modul internal proyek
                from apps.biaya.models import TransaksiBiaya  # DIPERBAIKI: sebelumnya Biaya
                

                
                # 1. Cabang/Gudang data + Karyawan
                total_gudang = Gudang.objects.filter(aktif=True).count()
                from django.contrib.auth import get_user_model
                UserModel = get_user_model()
                total_karyawan = UserModel.objects.filter(is_active=True).count()
                
                total_all = total_gudang + total_produk + total_karyawan
                gudang_ratio_percent = round((total_gudang / total_all * 100)) if total_all > 0 else 0
                karyawan_ratio_percent = round((total_karyawan / total_all * 100)) if total_all > 0 else 0
                produk_ratio_percent = 100 - gudang_ratio_percent - karyawan_ratio_percent
                
                context['cabang_data'] = {
                    'total_gudang': total_gudang,
                    'total_produk': total_produk,
                    'total_karyawan': total_karyawan,
                    'gudang_percent': gudang_ratio_percent,
                    'produk_percent': produk_ratio_percent,
                    'karyawan_percent': karyawan_ratio_percent,
                }

                
                # 2. Profit/Keuntungan calculation
                # Keuntungan = (harga_jual - harga_beli) * jumlah terjual dari SO + POS
                
                # Keuntungan dari Sales Order
                from apps.penjualan.models import SalesOrderItem
                profit_so_filter = {'sales_order__status__in': ['confirmed', 'delivered', 'completed']}
                if filter_start:
                    profit_so_filter['sales_order__tanggal__date__gte'] = filter_start
                if filter_end:
                    profit_so_filter['sales_order__tanggal__date__lte'] = filter_end
                
                keuntungan_so = SalesOrderItem.objects.filter(
                    **profit_so_filter
                ).annotate(
                    margin=ExpressionWrapper(
                        (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah'),
                        output_field=DecimalField()
                    )
                ).aggregate(total=Sum('margin'))['total'] or 0
                
                # Keuntungan dari POS Transaction
                from apps.pos.models import POSTransactionItem
                profit_pos_filter = {'transaction__status': 'paid'}
                if filter_start:
                    profit_pos_filter['transaction__tanggal__date__gte'] = filter_start
                if filter_end:
                    profit_pos_filter['transaction__tanggal__date__lte'] = filter_end
                
                keuntungan_pos = POSTransactionItem.objects.filter(
                    **profit_pos_filter
                ).annotate(
                    margin=ExpressionWrapper(
                        (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah_konversi'),
                        output_field=DecimalField()
                    )
                ).aggregate(total=Sum('margin'))['total'] or 0
                
                # Total keuntungan dari semua penjualan
                total_keuntungan = float(keuntungan_so or 0) + float(keuntungan_pos or 0)
                
                # Total revenue (untuk persentase margin) — DIPERBAIKI: filter tanggal diterapkan
                revenue_so_filter = {'status__in': ['confirmed', 'delivered', 'completed']}
                if filter_start:
                    revenue_so_filter['tanggal__date__gte'] = filter_start
                if filter_end:
                    revenue_so_filter['tanggal__date__lte'] = filter_end
                total_sales_revenue = SalesOrder.objects.filter(
                    **revenue_so_filter
                ).aggregate(total=Sum('total_harga'))['total'] or 0
                
                revenue_pos_filter = {'status': 'paid'}
                if filter_start:
                    revenue_pos_filter['tanggal__date__gte'] = filter_start
                if filter_end:
                    revenue_pos_filter['tanggal__date__lte'] = filter_end
                revenue_pos = POSTransaction.objects.filter(
                    **revenue_pos_filter
                ).aggregate(total=Sum('total_harga'))['total'] or 0
                
                total_revenue = float(total_sales_revenue or 0) + float(revenue_pos or 0)

                # Tambahkan pendapatan Service Center ke total revenue & keuntungan
                try:
                    from apps.service_center.models import OrderService as SC_OrderProfit
                    sc_profit_filter = {'status_bayar': 'lunas'}
                    if filter_start:
                        sc_profit_filter['tanggal_masuk__date__gte'] = filter_start
                    if filter_end:
                        sc_profit_filter['tanggal_masuk__date__lte'] = filter_end
                    sc_revenue = SC_OrderProfit.objects.filter(
                        **sc_profit_filter
                    ).aggregate(total=Sum('biaya_akhir'))['total'] or 0

                    # Hitung modal sparepart (COGS service) — menggunakan harga_beli produk
                    # bukan harga_satuan (yang merupakan harga jual ke pelanggan)
                    from apps.service_center.models import PenggunaanSparepart as SC_SP
                    sc_sp_filter = {'order_service__status_bayar': 'lunas'}
                    if filter_start:
                        sc_sp_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                    if filter_end:
                        sc_sp_filter['order_service__tanggal_masuk__date__lte'] = filter_end
                    sc_sparepart_cogs = SC_SP.objects.filter(
                        **sc_sp_filter
                    ).annotate(
                        _subtotal=ExpressionWrapper(
                            F('jumlah') * F('produk__harga_beli'),
                            output_field=DecimalField()
                        )
                    ).aggregate(total=Sum('_subtotal'))['total'] or 0

                    sc_profit = float(sc_revenue or 0) - float(sc_sparepart_cogs or 0)
                    total_revenue += float(sc_revenue or 0)
                    total_keuntungan += sc_profit
                except Exception as e:
                    logger.warning("Error tidak terduga: %s", e)
                
                # Persentase margin keuntungan
                profit_margin = round((total_keuntungan / total_revenue * 100), 1) if total_revenue > 0 else 0
                
                # Ambil data pembelian sebagai referensi — DIPERBAIKI: Hanya PO received yang dihitung sebagai pengeluaran
                purchase_cost_filter = {'status': 'received'}
                if filter_start:
                    purchase_cost_filter['tanggal__date__gte'] = filter_start
                if filter_end:
                    purchase_cost_filter['tanggal__date__lte'] = filter_end
                total_purchase_cost = PurchaseOrder.objects.filter(
                    **purchase_cost_filter
                ).aggregate(total=Sum('total_harga'))['total'] or 0
                
                # Total biaya operasional — DIPERBAIKI: hanya biaya 'approved' yang dihitung
                # Biaya draft/submitted/rejected bukan pengeluaran nyata
                biaya_filter_dashboard = {'status': 'approved'}
                if filter_start:
                    biaya_filter_dashboard['tanggal__gte'] = filter_start
                if filter_end:
                    biaya_filter_dashboard['tanggal__lte'] = filter_end
                total_expenses = TransaksiBiaya.objects.filter(
                    **biaya_filter_dashboard
                ).aggregate(total=Sum('jumlah'))['total'] or 0
                
                context['profit_data'] = {
                    'gross_profit': total_keuntungan,
                    'net_profit': total_keuntungan - float(total_expenses or 0),
                    'revenue': total_revenue,
                    'cogs': total_purchase_cost,
                    'expenses': total_expenses,
                    'margin_percent': profit_margin,
                    'is_profit': total_keuntungan > 0
                }

                
                # 3. Pembelian/Purchase data
                total_pembelian_count = PurchaseOrder.objects.exclude(status='cancelled').count()
                
                context['pembelian_data'] = {
                    'total_count': total_pembelian_count,
                    'total_value': total_purchase_cost
                }
                
                # 4. Biaya/Expense total
                context['biaya_total'] = total_expenses
                
                # 5. Data cabang/gudang dengan rincian keuntungan & pembelian
                # Menggunakan FK gudang langsung dari SalesOrder dan PurchaseOrder
                # (lebih akurat daripada via Produk.cabang yang bisa berubah)
                from apps.penjualan.models import SalesOrderItem
                # Import dari modul internal proyek
                from apps.pos.models import POSTransactionItem
                
                cabang_list = Gudang.objects.filter(aktif=True).order_by('nama')[:7]
                cabang_stats = []
                cabang_biaya_values = []  # Total pembelian per cabang untuk chart biaya
                
                for gudang in cabang_list:
                    # Hitung jumlah produk di gudang ini
                    produk_count = Produk.objects.filter(cabang=gudang, aktif=True).count()
                    
                    # === KEUNTUNGAN per cabang (dari SalesOrder.gudang langsung) ===
                    # Bangun filter SO per cabang — dengan filter waktu dashboard
                    gudang_so_filter = {
                        'gudang': gudang,
                        'status__in': ['confirmed', 'delivered', 'completed'],
                    }
                    if filter_start:
                        gudang_so_filter['tanggal__date__gte'] = filter_start
                    if filter_end:
                        gudang_so_filter['tanggal__date__lte'] = filter_end
                    
                    # Revenue SO di gudang ini (dengan filter waktu)
                    gudang_revenue_so = SalesOrder.objects.filter(
                        **gudang_so_filter
                    ).aggregate(total=Sum('total_harga'))['total'] or 0
                    
                    # Bangun filter SO Item per cabang — dengan filter waktu
                    gudang_so_item_filter = {
                        'sales_order__gudang': gudang,
                        'sales_order__status__in': ['confirmed', 'delivered', 'completed'],
                    }
                    if filter_start:
                        gudang_so_item_filter['sales_order__tanggal__date__gte'] = filter_start
                    if filter_end:
                        gudang_so_item_filter['sales_order__tanggal__date__lte'] = filter_end
                    
                    # Margin keuntungan SO di gudang ini (dengan filter waktu)
                    gudang_profit_so = SalesOrderItem.objects.filter(
                        **gudang_so_item_filter
                    ).annotate(
                        margin=ExpressionWrapper(
                            (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah'),
                            output_field=DecimalField()
                        )
                    ).aggregate(total=Sum('margin'))['total'] or 0
                    
                    # Bangun filter POS per cabang — dengan filter waktu
                    gudang_pos_filter = {
                        'transaction__gudang': gudang,
                        'transaction__status': 'paid',
                    }
                    if filter_start:
                        gudang_pos_filter['transaction__tanggal__date__gte'] = filter_start
                    if filter_end:
                        gudang_pos_filter['transaction__tanggal__date__lte'] = filter_end
                    
                    # Revenue & margin POS (dengan filter waktu)
                    gudang_revenue_pos = POSTransactionItem.objects.filter(
                        **gudang_pos_filter
                    ).aggregate(total=Sum('subtotal'))['total'] or 0
                    
                    gudang_profit_pos = POSTransactionItem.objects.filter(
                        **gudang_pos_filter
                    ).annotate(
                        margin=ExpressionWrapper(
                            (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah_konversi'),
                            output_field=DecimalField()
                        )
                    ).aggregate(total=Sum('margin'))['total'] or 0
                    
                    gudang_revenue = float(gudang_revenue_so or 0) + float(gudang_revenue_pos or 0)
                    gudang_profit = float(gudang_profit_so or 0) + float(gudang_profit_pos or 0)
                    
                    # === SERVICE CENTER per cabang (sparepart.gudang) ===
                    try:
                        from apps.service_center.models import PenggunaanSparepart as SC_SP_Cabang
                        from apps.service_center.models import OrderService as SC_OrdCabang
                        
                        # Revenue SC: order service lunas yang sparepart-nya dari gudang ini
                        gudang_sc_sp_filter = {
                            'gudang': gudang,
                            'order_service__status_bayar': 'lunas',
                        }
                        if filter_start:
                            gudang_sc_sp_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                        if filter_end:
                            gudang_sc_sp_filter['order_service__tanggal_masuk__date__lte'] = filter_end
                        
                        # Revenue sparepart per gudang (harga jual ke pelanggan)
                        gudang_sc_revenue = SC_SP_Cabang.objects.filter(
                            **gudang_sc_sp_filter
                        ).annotate(
                            _sub=ExpressionWrapper(
                                F('jumlah') * F('harga_satuan'),
                                output_field=DecimalField()
                            )
                        ).aggregate(total=Sum('_sub'))['total'] or 0
                        
                        # Profit sparepart per gudang (harga_jual - harga_beli) × qty
                        gudang_sc_profit = SC_SP_Cabang.objects.filter(
                            **gudang_sc_sp_filter
                        ).annotate(
                            margin=ExpressionWrapper(
                                (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah'),
                                output_field=DecimalField()
                            )
                        ).aggregate(total=Sum('margin'))['total'] or 0
                        
                        gudang_revenue += float(gudang_sc_revenue or 0)
                        gudang_profit += float(gudang_sc_profit or 0)
                    except Exception as e:
                        logger.warning("Error tidak terduga: %s", e)
                    
                    # === PEMBELIAN per cabang (dengan filter waktu) ===
                    gudang_po_filter = {
                        'gudang': gudang,
                        'status': 'received',
                    }
                    if filter_start:
                        gudang_po_filter['tanggal__date__gte'] = filter_start
                    if filter_end:
                        gudang_po_filter['tanggal__date__lte'] = filter_end
                    
                    gudang_pembelian = PurchaseOrder.objects.filter(
                        **gudang_po_filter
                    ).aggregate(total=Sum('total_harga'))['total'] or 0
                    
                    cabang_stats.append({
                        'nama': gudang.nama,
                        'kode': gudang.kode,
                        'produk_count': produk_count,
                        'revenue': gudang_revenue,
                        'profit': gudang_profit,
                        'pembelian': float(gudang_pembelian or 0)
                    })
                    cabang_biaya_values.append(float(gudang_pembelian or 0))
                
                context['cabang_profit_data'] = cabang_stats

                # Grafik Keuntungan per Cabang — data dari penjualan riil per SO.gudang
                cabang_name_list = [c['nama'][:10] for c in cabang_stats] if cabang_stats else ['Belum ada']
                context['cabang_names'] = cabang_name_list
                
                if cabang_stats:
                    profit_values = [float(c['profit']) for c in cabang_stats]
                    # Nilai absolut untuk tinggi bar (agar semua bar tumbuh ke atas)
                    context['live_visitors_data'] = [abs(v) for v in profit_values]
                    # Nilai asli profit (untuk tooltip: menampilkan untung/rugi)
                    context['cabang_profit_original'] = profit_values
                # ══════════════════════════════════════════════════════════
                # GRAFIK BESAR: PENJUALAN PER CABANG
                # Wave chart: setiap cabang punya series sendiri
                # Data: SO revenue + POS revenue per gudang
                # 
                # SMART AGGREGATION:
                # - Filter pendek (≤ 62 hari) → agregasi per HARI
                #   sehingga chart menampilkan garis bergelombang yang informatif
                # - Filter panjang (> 62 hari) atau default → agregasi per BULAN
                #   agar chart tidak terlalu padat
                # ══════════════════════════════════════════════════════════
                from datetime import date as date_type
                import calendar
                
                now = timezone.now()
                
                # Hitung rentang hari dari filter untuk menentukan mode agregasi
                if filter_start and filter_end:
                    rentang_hari = (filter_end - filter_start).days + 1
                elif filter_start:
                    rentang_hari = (now.date() - filter_start).days + 1
                elif filter_end:
                    rentang_hari = 180  # Default 6 bulan → pakai bulanan
                else:
                    rentang_hari = 180  # Default tanpa filter → pakai bulanan
                
                # Mode agregasi: HARIAN jika rentang ≤ 62 hari, BULANAN jika lebih
                use_daily = rentang_hari <= 62
                
                sales_cabang_labels = []
                sales_cabang_series = []
                
                if use_daily:
                    # ═══ MODE HARIAN — untuk filter pendek ═══
                    # Tentukan tanggal awal dan akhir
                    if filter_start and filter_end:
                        day_start = filter_start
                        day_end = filter_end
                    elif filter_start:
                        day_start = filter_start
                        day_end = now.date()
                    else:
                        # Seharusnya tidak masuk sini (karena rentang default = 180)
                        day_start = now.date() - timedelta(days=30)
                        day_end = now.date()
                    
                    # Generate list tanggal dari start sampai end
                    hari_list = []
                    current_day = day_start
                    while current_day <= day_end:
                        hari_list.append(current_day)
                        current_day += timedelta(days=1)
                    
                    # Label sumbu X: format tanggal pendek (contoh: "01 Mar", "02 Mar")
                    sales_cabang_labels = [d.strftime('%d %b') for d in hari_list]
                    
                    for gudang in cabang_list:
                        daily_data = []
                        for hari in hari_list:
                            # Query SO revenue per hari per gudang
                            so_rev = SalesOrder.objects.filter(
                                gudang=gudang,
                                status__in=['confirmed', 'delivered', 'completed'],
                                tanggal__date=hari
                            ).aggregate(total=Sum('total_harga'))['total'] or 0
                            
                            # Query POS revenue per hari per gudang
                            pos_rev = POSTransaction.objects.filter(
                                gudang=gudang,
                                status='paid',
                                tanggal__date=hari
                            ).aggregate(total=Sum('total_harga'))['total'] or 0
                            
                            daily_data.append(float(so_rev or 0) + float(pos_rev or 0))
                        
                        sales_cabang_series.append({
                            'name': gudang.nama,
                            'data': daily_data
                        })
                    
                    # === Service Center series (tidak per gudang) ===
                    try:
                        from apps.service_center.models import OrderService as SC_OrdDaily
                        sc_daily_data = []
                        for hari in hari_list:
                            sc_rev = SC_OrdDaily.objects.filter(
                                status_bayar='lunas',
                                tanggal_masuk__date=hari
                            ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
                            sc_daily_data.append(float(sc_rev or 0))
                        sales_cabang_series.append({
                            'name': 'Service Center',
                            'data': sc_daily_data
                        })
                    except Exception as e:
                        logger.warning("Gagal memproses AI request: %s", e)
                else:
                    # ═══ MODE BULANAN — untuk filter panjang / default ═══
                    # Tentukan rentang bulan berdasarkan filter
                    if filter_start and filter_end:
                        start_y, start_m = filter_start.year, filter_start.month
                        end_y, end_m = filter_end.year, filter_end.month
                    elif filter_start:
                        start_y, start_m = filter_start.year, filter_start.month
                        end_y, end_m = now.year, now.month
                    elif filter_end:
                        dt_start = filter_end.replace(day=1)
                        for _ in range(5):
                            dt_start = (dt_start - timedelta(days=1)).replace(day=1)
                        start_y, start_m = dt_start.year, dt_start.month
                        end_y, end_m = filter_end.year, filter_end.month
                    else:
                        dt_start = now.date().replace(day=1)
                        for _ in range(5):
                            dt_start = (dt_start - timedelta(days=1)).replace(day=1)
                        start_y, start_m = dt_start.year, dt_start.month
                        end_y, end_m = now.year, now.month
                    
                    # Generate list bulan dari start sampai end
                    bulan_list = []
                    y, m = start_y, start_m
                    while (y < end_y) or (y == end_y and m <= end_m):
                        bulan_list.append({
                            'year': y,
                            'month': m,
                            'label': datetime(y, m, 1).strftime('%b %Y')
                        })
                        m += 1
                        if m > 12:
                            m = 1
                            y += 1
                    
                    # Batasi maksimal 12 bulan agar chart tidak terlalu padat
                    if len(bulan_list) > 12:
                        bulan_list = bulan_list[-12:]
                    
                    sales_cabang_labels = [b['label'] for b in bulan_list]
                    
                    for gudang in cabang_list:
                        monthly_data = []
                        for bulan in bulan_list:
                            so_filter = {
                                'gudang': gudang,
                                'status__in': ['confirmed', 'delivered', 'completed'],
                                'tanggal__year': bulan['year'],
                                'tanggal__month': bulan['month'],
                            }
                            pos_filter = {
                                'gudang': gudang,
                                'status': 'paid',
                                'tanggal__year': bulan['year'],
                                'tanggal__month': bulan['month'],
                            }
                            
                            # Tambahkan batas hari jika bulan awal/akhir filter
                            if filter_start and bulan['year'] == filter_start.year and bulan['month'] == filter_start.month:
                                so_filter['tanggal__date__gte'] = filter_start
                                pos_filter['tanggal__date__gte'] = filter_start
                            if filter_end and bulan['year'] == filter_end.year and bulan['month'] == filter_end.month:
                                so_filter['tanggal__date__lte'] = filter_end
                                pos_filter['tanggal__date__lte'] = filter_end
                            
                            so_rev = SalesOrder.objects.filter(**so_filter).aggregate(
                                total=Sum('total_harga')
                            )['total'] or 0
                            
                            pos_rev = POSTransaction.objects.filter(**pos_filter).aggregate(
                                total=Sum('total_harga')
                            )['total'] or 0
                            
                            monthly_data.append(float(so_rev or 0) + float(pos_rev or 0))
                        
                        sales_cabang_series.append({
                            'name': gudang.nama,
                            'data': monthly_data
                        })
                    
                    # === Service Center series bulanan (tidak per gudang) ===
                    try:
                        from apps.service_center.models import OrderService as SC_OrdMonthly
                        sc_monthly_data = []
                        for bulan in bulan_list:
                            sc_m_filter = {
                                'status_bayar': 'lunas',
                                'tanggal_masuk__year': bulan['year'],
                                'tanggal_masuk__month': bulan['month'],
                            }
                            if filter_start and bulan['year'] == filter_start.year and bulan['month'] == filter_start.month:
                                sc_m_filter['tanggal_masuk__date__gte'] = filter_start
                            if filter_end and bulan['year'] == filter_end.year and bulan['month'] == filter_end.month:
                                sc_m_filter['tanggal_masuk__date__lte'] = filter_end
                            
                            sc_rev = SC_OrdMonthly.objects.filter(**sc_m_filter).aggregate(
                                total=Sum('biaya_akhir')
                            )['total'] or 0
                            sc_monthly_data.append(float(sc_rev or 0))
                        sales_cabang_series.append({
                            'name': 'Service Center',
                            'data': sc_monthly_data
                        })
                    except Exception as e:
                        logger.warning("Error tidak terduga: %s", e)
                context['sales_cabang_labels'] = sales_cabang_labels
                context['sales_cabang_series'] = sales_cabang_series

                
                # Grafik Biaya per Cabang — total pembelian (PO) per gudang
                # Jika ada data pembelian per cabang, tampilkan itu
                # Jika tidak ada PO, fallback ke biaya operasional per kategori
                has_po_data = any(v > 0 for v in cabang_biaya_values)
                
                if has_po_data:
                    # Tampilkan total pembelian per cabang
                    context['visits_by_day_data'] = cabang_biaya_values
                    context['biaya_labels'] = cabang_name_list
                else:
                    # Fallback: biaya operasional per kategori
                    expenses_by_cat = TransaksiBiaya.objects.filter(
                        **biaya_filter_dashboard
                    ).values('kategori__nama').annotate(
                        total=Sum('jumlah')
                    ).order_by('-total')[:7]
                    
                    if expenses_by_cat:
                        expense_values = [float(item['total']) for item in expenses_by_cat]
                        expense_labels = [item['kategori__nama'] or 'Lainnya' for item in expenses_by_cat]
                        context['visits_by_day_data'] = expense_values
                        context['biaya_labels'] = expense_labels

                
                # 6. Loss/Kerugian per cabang (expenses allocated)
                if total_gudang > 0:
                    expense_per_gudang = total_expenses / total_gudang
                    context['expense_per_cabang'] = expense_per_gudang
                else:
                    context['expense_per_cabang'] = 0
                

                
            except Exception as erp_error:
                logger.error("[DASHBOARD ERP CARDS] Error: %s", erp_error, exc_info=True)
                # Pastikan chart data selalu ada meskipun terjadi error
                context.setdefault('sales_cabang_labels', [])
                context.setdefault('sales_cabang_series', [])
                context.setdefault('cabang_profit_data', [])
                context.setdefault('cabang_names', ['Belum ada'])
                context.setdefault('biaya_labels', ['Belum ada'])

            # --- WIDGET PIUTANG ---
            # Statistik piutang (Accounts Receivable):
            # - sisa_piutang: total piutang yang belum lunas
            # - total_jatuh_tempo: jumlah piutang yang sudah lewat tanggal jatuh tempo
            # - customer_aktif: jumlah customer yang masih punya piutang
            try:
                from apps.piutang.models import Piutang
                piutang_qs = Piutang.objects.exclude(status='lunas')
                piutang_stats = piutang_qs.aggregate(
                    total_belum_lunas=Sum('jumlah_total'),
                    total_dibayar=Sum('jumlah_dibayar'),
                )
                total_belum_lunas = piutang_stats['total_belum_lunas'] or Decimal('0')
                total_dibayar = piutang_stats['total_dibayar'] or Decimal('0')
                sisa_piutang = total_belum_lunas - total_dibayar

                total_jatuh_tempo = Piutang.objects.filter(
                    jatuh_tempo__lt=today,
                    status__in=['belum_bayar', 'sebagian']
                ).count()

                customer_aktif = Piutang.objects.filter(
                    status__in=['belum_bayar', 'sebagian']
                ).values('customer').distinct().count()

                context['piutang_widget'] = {
                    'total_piutang': total_belum_lunas,
                    'sisa_piutang': sisa_piutang,
                    'total_jatuh_tempo': total_jatuh_tempo,
                    'customer_aktif': customer_aktif,
                }
            except Exception as piutang_err:
                logger.error("[DASHBOARD PIUTANG] Error: %s", piutang_err, exc_info=True)
                context['piutang_widget'] = {
                    'total_piutang': 0, 'sisa_piutang': 0,
                    'total_jatuh_tempo': 0, 'customer_aktif': 0,
                }


        except Exception as e:
            # Catat error fatal dashboard — gunakan nilai default aman
            logger.error("[DASHBOARD ERROR] %s", e, exc_info=True)
            # Nilai default aman jika seluruh proses gagal
            context.update({
                'sales_overview': {
                    'total_sales': 0, 'revenue': 0, 'growth': 0,
                    'new_customers': 0, 'products': 0, 'stock': 0,
                    'total_keseluruhan_aset': 0, 'total_harga_beli': 0,
                    'total_harga_jual': 0, 'estimasi_keuntungan': 0
                },
                'total_produk': 0, 'total_sales': 0, 'total_revenue': 0,
                'sales_chart_data': [0, 0, 0, 0, 0, 0, 0], 
                'live_visitors_data': [0, 0, 0, 0, 0, 0, 0], 
                'visits_by_day_data': [0, 0, 0, 0, 0, 0, 0], 
                'latest_users': [],
                'marketing_sales_data': [], 
                'weekly_sales_data': [
                    {
                        'category': 'Transaksi POS',
                        'items': [
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                        ],
                        'earning': 'Rp 0', 'growth': 0, 'product_image': None
                    },
                    {
                        'category': 'Sales Order',
                        'items': [
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                        ],
                        'earning': 'Rp 0', 'growth': 0, 'product_image': None
                    },
                    {
                        'category': 'Produk Stock Terbanyak',
                        'items': [
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                            {'name': 'Belum ada data', 'count': 0},
                        ],
                        'earning': 'Rp 0', 'growth': 0, 'product_image': None
                    },
                ],
                'top_products': [],
                'activity_timeline': [],
                'sales_this_month': 0,
                'total_customers': 0,
                # Nilai default aman untuk Card Dashboard ERP
                'cabang_data': {
                    'total_gudang': 0,
                    'total_produk': 0,
                    'gudang_percent': 0,
                    'produk_percent': 0
                },
                'profit_data': {
                    'gross_profit': 0,
                    'net_profit': 0,
                    'revenue': 0,
                    'cogs': 0,
                    'expenses': 0,
                    'margin_percent': 0,
                    'is_profit': False
                },
                'pembelian_data': {
                    'total_count': 0,
                    'total_value': 0
                },
                'biaya_total': 0,
                'cabang_profit_data': [],
                'expense_per_cabang': 0,
                'cabang_names': ['Belum ada'],
                'biaya_labels': ['Belum ada'],
                'sales_chart_labels': [],
                'sales_cabang_labels': [],
                'sales_cabang_series': [],
                # Nilai default aman untuk Service Center
                'service_overview': {
                    'order_aktif': 0, 'order_selesai': 0, 'pending_bayar': 0,
                    'total_revenue': 0, 'total_pelanggan': 0, 'sparepart_cost': 0,
                },
                'piutang_widget': {
                    'total_piutang': 0, 'sisa_piutang': 0,
                    'total_jatuh_tempo': 0, 'customer_aktif': 0,
                },
            })

        return context
