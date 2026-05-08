"""
==========================================================================
 LAPORAN VIEWS - Views Halaman Laporan / Report (Read-Only)
==========================================================================
 File ini berisi views untuk menampilkan laporan bisnis.
 Semua views bersifat READ-ONLY (hanya menampilkan, tidak mengubah data).

 Daftar View:
 ┌─────────────────────────────┬───────────────────────────────────────┐
 │ View                        │ Penjelasan                            │
 ├─────────────────────────────┼───────────────────────────────────────┤
 │ LaporanProdukView           │ Laporan produk + nilai aset           │
 │ LaporanProdukDetailView     │ Detail produk + riwayat stok          │
 │ LaporanStokView             │ Ringkasan stok per gudang             │
 │ LaporanStokDetailView       │ Detail stok + riwayat transfer/adj    │
 │ LaporanPenjualanView        │ Laporan penjualan (SO + POS)          │
 │ LaporanPenjualanDetailView  │ Detail Sales Order                    │
 │ LaporanPembelianView        │ Laporan pembelian (PO)                │
 │ LaporanPembelianDetailView  │ Detail Purchase Order                 │
 │ LaporanKeuanganView         │ Ringkasan keuangan (laba/rugi)        │
 └─────────────────────────────┴───────────────────────────────────────┘

 Fitur umum semua view:
 - ReadPermissionMixin → Cek permission SubCRUD laporan_produk/stok/dll
 - Filter tanggal (start_date, end_date) via GET parameter
 - Kalkulasi keuntungan (harga_jual - harga_beli) per transaksi
 - Activity Log integration untuk riwayat perubahan

 Terhubung dengan:
 - apps/produk/models.py → Produk, Kategori, Stok, Gudang
 - apps/penjualan/models.py → SalesOrder, SalesOrderItem, Customer
 - apps/pembelian/models.py → PurchaseOrder, PurchaseOrderItem, Supplier
 - apps/biaya/models.py → TransaksiBiaya, KategoriBiaya
 - apps/pos/models.py → POSTransaction, POSTransactionItem
 - apps/activity_log/models.py → UserActivity (riwayat perubahan)
==========================================================================
"""
from django.shortcuts import render, get_object_or_404
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import TemplateView, ListView, DetailView
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.db.models import Count, Sum, Q, F, ExpressionWrapper
from django.db import models
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.produk.models import Produk, Kategori, Stok, Gudang
# Import dari modul internal proyek
from apps.penjualan.models import SalesOrder, SalesOrderItem, Customer
# Import dari modul internal proyek
from apps.pembelian.models import PurchaseOrder, PurchaseOrderItem, Supplier
# Import dari modul internal proyek
from apps.biaya.models import TransaksiBiaya, KategoriBiaya
# Import dari modul internal proyek
from apps.activity_log.models import UserActivity
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin


class LaporanProdukView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Laporan Produk — daftar produk + kalkulasi nilai aset.
    URL: /laporan/produk/
    Filter: start_date, end_date (mempengaruhi qty terjual)
    Cards: total aset, harga beli ready, harga jual ready, estimasi keuntungan
    """
    model = Produk
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/produk.html'
    context_object_name = 'produk_list'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_produk'  # SubCRUD permission
    
    # Override queryset — filter atau optimasi query data
    def get_queryset(self):
        # Prefetch stok dengan gudang untuk efisiensi query
        """Override queryset — filter atau optimasi query data."""
        return Produk.objects.prefetch_related(
            'stok_set', 
            'stok_set__gudang'
        ).select_related('kategori', 'satuan', 'cabang')
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database — ambil semua data context['kategori_list']
        # Data konteks: kategori_list — untuk ditampilkan di template
        context['kategori_list'] = Kategori.objects.all()
        
        # Tambah daftar gudang untuk referensi dan filter
        context['gudang_list'] = Gudang.objects.filter(aktif=True)
        
        from decimal import Decimal
        from datetime import datetime
        # Import dari framework Django
        from django.db.models import Sum, Q
        # Import dari modul internal proyek
        from apps.penjualan.models import SalesOrderItem
        # Import dari modul internal proyek
        from apps.pos.models import POSTransactionItem
        
        # Parse filter params for date filtering
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        # Data konteks: filter_start_date — untuk ditampilkan di template
        context['filter_start_date'] = start_date_str
        # Data konteks: filter_end_date — untuk ditampilkan di template
        context['filter_end_date'] = end_date_str
        
        filter_start = None
        filter_end = None
        if start_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        if end_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        
        # ===== Hitung qty terjual per produk =====
        # Dari Sales Order items (status bukan cancelled)
        so_sold_filter = Q(sales_order__status__in=['confirmed', 'delivered', 'completed'])
        if filter_start:
            so_sold_filter &= Q(sales_order__tanggal__date__gte=filter_start)
        if filter_end:
            so_sold_filter &= Q(sales_order__tanggal__date__lte=filter_end)
        
        so_sold_by_produk = {}
        # Query database — ambil data for item in SalesOrderItem.objects.filter(so_sold_filter).values('produk_id').annotate(total_qty yang sesuai filter
        for item in SalesOrderItem.objects.filter(so_sold_filter).values('produk_id').annotate(total_qty=Sum('jumlah')):
            so_sold_by_produk[item['produk_id']] = item['total_qty']
        
        # Dari POS Transaction items (status paid)
        pos_sold_filter = Q(transaction__status='paid')
        if filter_start:
            pos_sold_filter &= Q(transaction__tanggal__date__gte=filter_start)
        if filter_end:
            pos_sold_filter &= Q(transaction__tanggal__date__lte=filter_end)
        
        pos_sold_by_produk = {}
        # Query database — ambil data for item in POSTransactionItem.objects.filter(pos_sold_filter).values('produk_id').annotate(total_qty yang sesuai filter
        for item in POSTransactionItem.objects.filter(pos_sold_filter).values('produk_id').annotate(total_qty=Sum('jumlah')):
            pos_sold_by_produk[item['produk_id']] = item['total_qty']
        
        # DIPERBAIKI #10: Dari Service Center sparepart usage (order bukan dibatalkan)
        from apps.service_center.models import PenggunaanSparepart
        sc_used_filter = ~Q(order_service__status='dibatalkan')
        if filter_start:
            sc_used_filter &= Q(order_service__tanggal_masuk__date__gte=filter_start)
        if filter_end:
            sc_used_filter &= Q(order_service__tanggal_masuk__date__lte=filter_end)
        
        sc_used_by_produk = {}
        for item in PenggunaanSparepart.objects.filter(sc_used_filter, stok_dikurangi=True).values('produk_id').annotate(total_qty=Sum('jumlah')):
            sc_used_by_produk[item['produk_id']] = item['total_qty']
        
        # DIPERBAIKI QA-L1: Tambahkan Adjustment Out (sinkron dengan Dashboard + Laporan Keuangan)
        from apps.inventory.models import AdjustmentStok
        adj_out_by_produk = {}
        for item in AdjustmentStok.objects.filter(
            tipe='out'
        ).values('produk_id').annotate(total_qty=Sum('jumlah')):
            adj_out_by_produk[item['produk_id']] = item['total_qty']
        
        # ===== Hitung semua cards =====
        total_keseluruhan_aset = Decimal('0')
        total_harga_beli_ready = Decimal('0')
        total_harga_jual_ready = Decimal('0')
        total_stok = Decimal('0')
        total_nilai_beli = Decimal('0')
        total_nilai_jual = Decimal('0')
        produk_count = 0
        
        for produk in Produk.objects.prefetch_related('stok_set').all():
            stok_saat_ini = sum(s.jumlah for s in produk.stok_set.all())
            
            # Qty yang sudah terjual/keluar (SO + POS + SC sparepart + Adjustment Out)
            qty_sold_so = so_sold_by_produk.get(produk.pk, Decimal('0'))
            qty_sold_pos = pos_sold_by_produk.get(produk.pk, Decimal('0'))
            qty_used_sc = sc_used_by_produk.get(produk.pk, Decimal('0'))
            qty_adj_out = adj_out_by_produk.get(produk.pk, Decimal('0'))
            qty_total_pernah_masuk = stok_saat_ini + qty_sold_so + qty_sold_pos + qty_used_sc + qty_adj_out
            
            # Card 1: Total Keseluruhan Aset = harga_beli × total stok pernah masuk
            total_keseluruhan_aset += produk.harga_beli * qty_total_pernah_masuk
            
            # Untuk ringkasan tfoot
            total_stok += stok_saat_ini
            total_nilai_beli += produk.harga_beli * stok_saat_ini
            total_nilai_jual += produk.harga_jual * stok_saat_ini
            produk_count += 1
            
            # Cards 2,3,4: Hanya produk ready (stok > 0)
            if stok_saat_ini > 0:
                total_harga_beli_ready += produk.harga_beli * stok_saat_ini
                total_harga_jual_ready += produk.harga_jual * stok_saat_ini
        
        estimasi_keuntungan = total_harga_jual_ready - total_harga_beli_ready
        
        # Data konteks: total_keseluruhan_aset — untuk ditampilkan di template
        context['total_keseluruhan_aset'] = total_keseluruhan_aset
        # Data konteks: total_harga_beli_ready — untuk ditampilkan di template
        context['total_harga_beli_ready'] = total_harga_beli_ready
        # Data konteks: total_harga_jual_ready — untuk ditampilkan di template
        context['total_harga_jual_ready'] = total_harga_jual_ready
        # Data konteks: estimasi_keuntungan — untuk ditampilkan di template
        context['estimasi_keuntungan'] = estimasi_keuntungan
        
        # Untuk ringkasan tfoot / backward compat
        context['total_produk'] = produk_count
        # Data konteks: total_nilai_beli — untuk ditampilkan di template
        context['total_nilai_beli'] = total_nilai_beli
        # Data konteks: total_nilai_jual — untuk ditampilkan di template
        context['total_nilai_jual'] = total_nilai_jual
        # Data konteks: total_stok — untuk ditampilkan di template
        context['total_stok'] = int(total_stok)
        
        return context


class LaporanStokView(ReadPermissionMixin, ListView):
    """
    Laporan Stok — ringkasan stok per produk per gudang.
    URL: /laporan/stok/
    Cards: total produk, total gudang, stok habis, stok rendah
    """
    model = Stok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/stok.html'
    context_object_name = 'stok_list'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_stok'  # SubCRUD permission
    
    def get_queryset(self):
        """Override queryset — filter atau optimasi query data."""
        return Stok.objects.select_related('produk', 'gudang').all()
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database — ambil semua data context['gudang_list']
        # Data konteks: gudang_list — untuk ditampilkan di template
        context['gudang_list'] = Gudang.objects.all()
        # Summary stats
        context['total_produk'] = Produk.objects.count()
        # Hitung jumlah data yang cocok
        # Data konteks: total_gudang — untuk ditampilkan di template
        context['total_gudang'] = Gudang.objects.count()
        # Query database — ambil data context['stok_habis'] yang sesuai filter
        # Data konteks: stok_habis — untuk ditampilkan di template
        context['stok_habis'] = Stok.objects.filter(jumlah=0).count()
        # Query database — ambil data context['stok_rendah'] yang sesuai filter
        # Data konteks: stok_rendah — untuk ditampilkan di template
        context['stok_rendah'] = Stok.objects.filter(jumlah__gt=0, jumlah__lte=10).count()
        
        # Aggregated total for summary row
        total_stok_aggregate = Stok.objects.aggregate(total_stok=Sum('jumlah'))
        # Data konteks: total_stok — untuk ditampilkan di template
        context['total_stok'] = int(total_stok_aggregate['total_stok'] or 0)
        
        return context


class LaporanPenjualanView(ReadPermissionMixin, ListView):
    """
    Laporan Penjualan — gabungan Sales Order + POS Transaction.
    URL: /laporan/penjualan/
    Filter: start_date, end_date
    Cards: total penjualan, total keuntungan, rata-rata order
    Menghitung harga_beli dan keuntungan per order.
    """
    model = SalesOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/penjualan.html'
    context_object_name = 'sales_order_list'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_penjualan'  # SubCRUD permission
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database — ambil semua data context['customer_list']
        # Data konteks: customer_list — untuk ditampilkan di template
        context['customer_list'] = Customer.objects.all()
        
        # Import POS model
        from apps.pos.models import POSTransaction, POSTransactionItem
        from decimal import Decimal
        from datetime import datetime
        
        # Parse filter params
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        # Data konteks: filter_start_date — untuk ditampilkan di template
        context['filter_start_date'] = start_date_str
        # Data konteks: filter_end_date — untuk ditampilkan di template
        context['filter_end_date'] = end_date_str
        
        filter_start = None
        filter_end = None
        if start_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        if end_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        
        # ===== Build filter kwargs =====
        so_filter = {'status__in': ['draft', 'confirmed', 'delivered', 'completed']}
        pos_filter = {'status__in': ['draft', 'unpaid', 'paid']}
        if filter_start:
            so_filter['tanggal__date__gte'] = filter_start
            pos_filter['tanggal__date__gte'] = filter_start
        if filter_end:
            so_filter['tanggal__date__lte'] = filter_end
            pos_filter['tanggal__date__lte'] = filter_end
        
        # ===== Sales Order: hitung harga_beli dan keuntungan per SO =====
        so_qs = SalesOrder.objects.filter(**so_filter).prefetch_related('items__produk')
        so_list_annotated = []
        so_total = Decimal('0')
        so_harga_beli_total = Decimal('0')
        so_keuntungan_total = Decimal('0')
        
        for so in so_qs:
            harga_beli_so = Decimal('0')
            for item in so.items.all():
                harga_beli_so += item.produk.harga_beli * item.jumlah
            keuntungan_so = so.total_harga - harga_beli_so
            so.harga_beli_calc = harga_beli_so
            so.keuntungan_calc = keuntungan_so
            so_list_annotated.append(so)
            so_total += so.total_harga
            so_harga_beli_total += harga_beli_so
            so_keuntungan_total += keuntungan_so
        
        so_count = len(so_list_annotated)
        
        # ===== POS Transaction: hitung harga_beli dan keuntungan per POS =====
        # CATATAN (Fix Maret 2026 — K8): Sebelumnya query ini dibatasi [:50] transaksi,
        # yang menyebabkan laporan penjualan POS tidak lengkap. Limit dihapus.
        pos_qs = POSTransaction.objects.filter(**pos_filter).prefetch_related('items__produk').order_by('-tanggal')
        pos_list_annotated = []
        pos_total = Decimal('0')
        pos_harga_beli_total = Decimal('0')
        pos_keuntungan_total = Decimal('0')
        
        for pos in pos_qs:
            harga_beli_pos = Decimal('0')
            for item in pos.items.all():
                harga_beli_pos += item.produk.harga_beli * item.jumlah
            keuntungan_pos = pos.total_harga - harga_beli_pos
            pos.harga_beli_calc = harga_beli_pos
            pos.keuntungan_calc = keuntungan_pos
            pos_list_annotated.append(pos)
            pos_total += pos.total_harga
            pos_harga_beli_total += harga_beli_pos
            pos_keuntungan_total += keuntungan_pos
        
        pos_count = len(pos_list_annotated)
        
        # ===== Combined stats =====
        total_penjualan = so_total + pos_total
        total_harga_beli = so_harga_beli_total + pos_harga_beli_total
        total_keuntungan = so_keuntungan_total + pos_keuntungan_total
        total_order = so_count + pos_count
        
        # Summary cards
        context['total_penjualan'] = total_penjualan
        # Data konteks: total_keuntungan — untuk ditampilkan di template
        context['total_keuntungan'] = total_keuntungan
        # Data konteks: total_harga_beli — untuk ditampilkan di template
        context['total_harga_beli'] = total_harga_beli
        # Data konteks: rata_rata_order — untuk ditampilkan di template
        context['rata_rata_order'] = int(total_penjualan / total_order) if total_order > 0 else 0
        
        # SO breakdown
        context['so_total'] = so_total
        # Data konteks: so_count — untuk ditampilkan di template
        context['so_count'] = so_count
        # Data konteks: so_harga_beli_total — untuk ditampilkan di template
        context['so_harga_beli_total'] = so_harga_beli_total
        # Data konteks: so_keuntungan_total — untuk ditampilkan di template
        context['so_keuntungan_total'] = so_keuntungan_total
        
        # POS breakdown
        context['pos_total'] = pos_total
        # Data konteks: pos_count — untuk ditampilkan di template
        context['pos_count'] = pos_count
        # Data konteks: pos_harga_beli_total — untuk ditampilkan di template
        context['pos_harga_beli_total'] = pos_harga_beli_total
        # Data konteks: pos_keuntungan_total — untuk ditampilkan di template
        context['pos_keuntungan_total'] = pos_keuntungan_total
        
        # Override queryset & POS list with annotated versions
        context['sales_order_list'] = so_list_annotated
        # Data konteks: pos_transaction_list — untuk ditampilkan di template
        context['pos_transaction_list'] = pos_list_annotated

        # ===== Service Center: pendapatan dari order service lunas =====
        sc_total = Decimal('0')
        sc_count = 0
        sc_list = []
        try:
            from apps.service_center.models import OrderService as SC_OrderPenj
            sc_filter = {'status_bayar': 'lunas'}
            if filter_start:
                sc_filter['tanggal_masuk__date__gte'] = filter_start
            if filter_end:
                sc_filter['tanggal_masuk__date__lte'] = filter_end
            sc_qs = SC_OrderPenj.objects.filter(
                **sc_filter
            ).select_related('pelanggan', 'metode_pembayaran').order_by('-tanggal_masuk')
            for sc in sc_qs:
                sc_total += sc.biaya_akhir or Decimal('0')
                sc_count += 1
                sc_list.append(sc)
        except Exception:
            pass

        # Update combined stats to include service
        total_penjualan += sc_total
        total_order += sc_count
        context['total_penjualan'] = total_penjualan
        context['rata_rata_order'] = int(total_penjualan / total_order) if total_order > 0 else 0

        context['sc_total'] = sc_total
        context['sc_count'] = sc_count
        context['service_order_list'] = sc_list
        
        return context


class LaporanPembelianView(ReadPermissionMixin, ListView):
    """
    Laporan Pembelian — daftar Purchase Order + statistik.
    URL: /laporan/pembelian/
    Filter: start_date, end_date
    Cards: total pembelian, total PO, total pajak, total stok masuk
    """
    model = PurchaseOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/pembelian.html'
    context_object_name = 'purchase_order_list'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_pembelian'  # SubCRUD permission
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database — ambil semua data context['supplier_list']
        # Data konteks: supplier_list — untuk ditampilkan di template
        context['supplier_list'] = Supplier.objects.all()
        
        from datetime import datetime
        from decimal import Decimal
        
        # Parse filter params
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        # Data konteks: filter_start_date — untuk ditampilkan di template
        context['filter_start_date'] = start_date_str
        # Data konteks: filter_end_date — untuk ditampilkan di template
        context['filter_end_date'] = end_date_str
        
        filter_start = None
        filter_end = None
        if start_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        if end_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        
        # Bangun filter kwargs
        po_filter = {}
        if filter_start:
            po_filter['tanggal__date__gte'] = filter_start
        if filter_end:
            po_filter['tanggal__date__lte'] = filter_end
        
        # Query database — ambil data po_qs yang sesuai filter
        po_qs = PurchaseOrder.objects.filter(**po_filter).prefetch_related('items__produk').order_by('-tanggal')
        
        # Annotate each PO with product names, total stok, pajak
        po_list_annotated = []
        total_pembelian = Decimal('0')
        total_pajak = Decimal('0')
        total_stok = Decimal('0')
        
        for po in po_qs:
            produk_names = []
            stok_total = Decimal('0')
            for item in po.items.all():
                produk_names.append(item.produk.nama)
                stok_total += item.jumlah
            po.produk_list = ', '.join(produk_names) if produk_names else '-'
            po.stok_total = stok_total
            po.pajak_display = po.pajak
            po_list_annotated.append(po)
            total_pembelian += po.total_harga
            total_pajak += po.pajak
            total_stok += stok_total
        
        total_po = len(po_list_annotated)
        
        # Summary stats with filter
        context['total_pembelian'] = total_pembelian
        # Data konteks: total_po — untuk ditampilkan di template
        context['total_po'] = total_po
        # Data konteks: total_pajak — untuk ditampilkan di template
        context['total_pajak'] = total_pajak
        # Data konteks: total_stok — untuk ditampilkan di template
        context['total_stok'] = total_stok
        # Hitung jumlah data yang cocok
        # Data konteks: total_supplier — untuk ditampilkan di template
        context['total_supplier'] = Supplier.objects.count()
        # Data konteks: rata_rata_po — untuk ditampilkan di template
        context['rata_rata_po'] = int(total_pembelian / total_po) if total_po > 0 else 0
        
        # Override queryset with annotated version
        context['purchase_order_list'] = po_list_annotated
        
        # Tambahkan total pengeluaran produk (Tambah Produk / Import Produk)
        # DIPERBAIKI: Menggunakan qty HISTORIS (sinkron dengan Laporan Keuangan)
        from decimal import Decimal as Dec
        from apps.penjualan.models import SalesOrderItem as SOItem
        from apps.pos.models import POSTransactionItem as POSItem
        from apps.inventory.models import AdjustmentStok
        total_produk_pengeluaran = Dec('0')
        try:
            # Pre-fetch qty terjual dan adj_out (kumulatif historis)
            so_sold_map = {}
            for item in SOItem.objects.filter(
                sales_order__status__in=['confirmed', 'delivered', 'completed']
            ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                so_sold_map[item['produk_id']] = item['total_qty']
            
            pos_sold_map = {}
            for item in POSItem.objects.filter(
                transaction__status='paid'
            ).values('produk_id').annotate(total_qty=Sum('jumlah_konversi')):
                pos_sold_map[item['produk_id']] = item['total_qty']
            
            adj_out_map = {}
            for item in AdjustmentStok.objects.filter(
                tipe='out'
            ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                adj_out_map[item['produk_id']] = item['total_qty']
                
            sc_used_map = {}
            try:
                from apps.service_center.models import PenggunaanSparepart
                for item in PenggunaanSparepart.objects.filter(
                    stok_dikurangi=True
                ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                    sc_used_map[item['produk_id']] = item['total_qty']
            except Exception:
                pass
            
            for p in Produk.objects.filter(metode_pembayaran__isnull=False).prefetch_related('stok_set'):
                stok_saat_ini = sum(s.jumlah for s in p.stok_set.all())
                qty_historis = stok_saat_ini + so_sold_map.get(p.pk, Dec('0')) + pos_sold_map.get(p.pk, Dec('0')) + adj_out_map.get(p.pk, Dec('0')) + sc_used_map.get(p.pk, Dec('0'))
                total_produk_pengeluaran += p.harga_beli * qty_historis
        except Exception:
            pass
        context['total_produk_pengeluaran'] = total_produk_pengeluaran
        context['total_keseluruhan_pembelian'] = total_pembelian + total_produk_pengeluaran
        
        return context


class LaporanKeuanganView(ReadPermissionMixin, TemplateView):
    """
    Laporan Keuangan — ringkasan laba/rugi + pengeluaran.
    URL: /laporan/keuangan/
    Filter: start_date, end_date
    Hitung: pendapatan (SO+POS), pengeluaran (PO+Biaya), laba bersih
    """
    template_name = 'laporan/keuangan.html'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_keuangan'  # SubCRUD permission
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        
        # Import dari modul internal proyek
        from apps.pos.models import POSTransaction, MetodePembayaran
        from datetime import datetime
        
        # Parse filter params
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        cabang_id = self.request.GET.get('cabang', '')
        metode_id = self.request.GET.get('metode_pembayaran', '')
        
        filter_start = None
        filter_end = None
        if start_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        if end_date_str:
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Tangkap error ValueError — lanjutkan tanpa crash
            except ValueError:
                pass
        
        # Data konteks: filter_start_date — untuk ditampilkan di template
        context['filter_start_date'] = start_date_str
        # Data konteks: filter_end_date — untuk ditampilkan di template
        context['filter_end_date'] = end_date_str
        # Data konteks: filter_cabang — untuk ditampilkan di template
        context['filter_cabang'] = cabang_id
        # Data konteks: filter_metode — untuk ditampilkan di template
        context['filter_metode'] = metode_id
        
        # Kirim data filter ke template
        context['gudang_list'] = Gudang.objects.filter(aktif=True)
        # Query database — ambil data context['metode_pembayaran_list'] yang sesuai filter
        # Data konteks: metode_pembayaran_list — untuk ditampilkan di template
        context['metode_pembayaran_list'] = MetodePembayaran.objects.filter(aktif=True)
        
        # Bangun filter kwargs berdasarkan tanggal + cabang + metode
        so_filter = {'status__in': ['confirmed', 'delivered', 'completed']}
        pos_filter = {'status': 'paid'}
        # Filter status PO menggunakan 'approved' dan 'received' (bukan 'confirmed')
        # CATATAN (Fix Maret 2026 — K7): Sebelumnya menggunakan ['confirmed', 'received', 'completed']
        # yang salah karena PO tidak memiliki status 'confirmed' maupun 'completed'.
        # Status alur PO yang benar: draft → approved → received
        po_filter = {'status__in': ['approved', 'received']}
        biaya_filter = {'status': 'approved'}  # Hanya biaya yang disetujui = pengeluaran nyata
        
        if filter_start:
            so_filter['tanggal__date__gte'] = filter_start
            pos_filter['tanggal__date__gte'] = filter_start
            po_filter['tanggal__date__gte'] = filter_start
            biaya_filter['tanggal__gte'] = filter_start
        if filter_end:
            so_filter['tanggal__date__lte'] = filter_end
            pos_filter['tanggal__date__lte'] = filter_end
            po_filter['tanggal__date__lte'] = filter_end
            biaya_filter['tanggal__lte'] = filter_end
        
        # Filter cabang (gudang)
        if cabang_id:
            so_filter['gudang_id'] = cabang_id
            pos_filter['gudang_id'] = cabang_id
            po_filter['gudang_id'] = cabang_id
            biaya_filter['cabang_id'] = cabang_id
        
        # Filter metode pembayaran
        if metode_id:
            so_filter['metode_pembayaran_id'] = metode_id
            pos_filter['metode_pembayaran_id'] = metode_id
            po_filter['metode_pembayaran_id'] = metode_id
            biaya_filter['metode_pembayaran_id'] = metode_id
        
        # Pemasukan dari penjualan (Sales Order + POS)
        total_sales_order = SalesOrder.objects.filter(
            **so_filter
        ).aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        
        # Query database — ambil data total_pos yang sesuai filter
        total_pos = POSTransaction.objects.filter(
            **pos_filter
        ).aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        
        total_pemasukan = total_sales_order + total_pos

        # Pemasukan dari Service Center (order lunas)
        total_service = 0
        try:
            from apps.service_center.models import OrderService as SC_OrderKeu
            sc_keu_filter = {'status_bayar': 'lunas'}
            if filter_start:
                sc_keu_filter['tanggal_masuk__date__gte'] = filter_start
            if filter_end:
                sc_keu_filter['tanggal_masuk__date__lte'] = filter_end
            if cabang_id:
                pass  # Service center belum punya field cabang
            if metode_id:
                sc_keu_filter['metode_pembayaran_id'] = metode_id
            total_service = SC_OrderKeu.objects.filter(
                **sc_keu_filter
            ).aggregate(Sum('biaya_akhir'))['biaya_akhir__sum'] or 0
        except Exception:
            pass

        total_pemasukan += total_service
        
        # Pengeluaran dari pembelian + biaya
        total_pembelian = PurchaseOrder.objects.filter(
            **po_filter
        ).aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        # Query database — ambil data total_biaya yang sesuai filter
        total_biaya = TransaksiBiaya.objects.filter(
            **biaya_filter
        ).aggregate(Sum('jumlah'))['jumlah__sum'] or 0

        # Pengeluaran dari pembelian produk/sparepart (Tambah Produk, Tambah Sparepart, Import)
        # DIPERBAIKI: Menggunakan qty HISTORIS (stok + terjual + adj_out) bukan stok saat ini
        # Alasan: Modal yang sudah keluar bersifat TETAP, tidak berkurang saat barang terjual.
        # Sebelumnya: harga_beli × stok_saat_ini → nominal pengeluaran menyusut saat barang terjual (BUG)
        # Sekarang: harga_beli × qty_total_pernah_masuk → nominal pengeluaran tetap historis
        from decimal import Decimal as Dec
        from decimal import Decimal
        from apps.produk.models import Stok
        from apps.penjualan.models import SalesOrderItem
        from apps.pos.models import POSTransactionItem
        from apps.inventory.models import AdjustmentStok
        total_pembelian_produk = Dec('0')
        produk_filter = {'metode_pembayaran__isnull': False}
        if metode_id:
            produk_filter['metode_pembayaran_id'] = metode_id
        if cabang_id:
            produk_filter['cabang_id'] = cabang_id
        try:
            # Pre-fetch qty terjual dan adj_out per produk (kumulatif historis)
            so_sold_map = {}
            for item in SalesOrderItem.objects.filter(
                sales_order__status__in=['confirmed', 'delivered', 'completed']
            ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                so_sold_map[item['produk_id']] = item['total_qty']
            
            pos_sold_map = {}
            for item in POSTransactionItem.objects.filter(
                transaction__status='paid'
            ).values('produk_id').annotate(total_qty=Sum('jumlah_konversi')):
                pos_sold_map[item['produk_id']] = item['total_qty']
            
            adj_out_map = {}
            for item in AdjustmentStok.objects.filter(
                tipe='out'
            ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                adj_out_map[item['produk_id']] = item['total_qty']
                
            sc_used_map = {}
            try:
                from apps.service_center.models import PenggunaanSparepart
                for item in PenggunaanSparepart.objects.filter(
                    stok_dikurangi=True
                ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                    sc_used_map[item['produk_id']] = item['total_qty']
            except Exception:
                pass
            
            produk_qs = Produk.objects.filter(**produk_filter).prefetch_related('stok_set')
            for p in produk_qs:
                stok_saat_ini = sum(s.jumlah for s in p.stok_set.all())
                qty_sold_so = so_sold_map.get(p.pk, Dec('0'))
                qty_sold_pos = pos_sold_map.get(p.pk, Dec('0'))
                qty_adj_out = adj_out_map.get(p.pk, Dec('0'))
                qty_sc_used = sc_used_map.get(p.pk, Dec('0'))
                # Qty historis = stok sekarang + yang sudah terjual + yang keluar via adjustment + yang terpakai di service center
                qty_historis = stok_saat_ini + qty_sold_so + qty_sold_pos + qty_adj_out + qty_sc_used
                total_pembelian_produk += p.harga_beli * qty_historis
        except Exception:
            pass

        total_pengeluaran = total_pembelian + total_biaya + total_pembelian_produk

        # CATATAN: Sparepart BUKAN pengeluaran terpisah.
        # Sparepart dibeli via PO (sudah masuk total_pembelian), lalu dijual ke pelanggan via service (pemasukan).
        # Menghitung sparepart sebagai pengeluaran = double-counting.
        total_biaya_sparepart_service = 0
        
        # Laba/rugi
        laba_rugi = total_pemasukan - total_pengeluaran
        
        # ===== Total Aset — Formula Inventori Historis (SINKRON dengan Dashboard) =====
        # Total Aset = harga_beli × semua qty yang pernah masuk (stok + terjual + adj_out)
        # Tidak dipengaruhi filter tanggal — bersifat kumulatif historis
        # Menjadi patokan untuk deteksi kecurangan/selisih
        from apps.produk.models import Produk, Stok
        from apps.penjualan.models import SalesOrderItem
        from apps.pos.models import POSTransactionItem
        from apps.inventory.models import AdjustmentStok
        from decimal import Decimal
        
        total_aset = Decimal('0')
        total_harga_beli_ready = Decimal('0')
        total_harga_jual_ready = Decimal('0')
        
        try:
            # Qty terjual per produk dari SO (kumulatif historis)
            so_sold_by_produk = {}
            for item in SalesOrderItem.objects.filter(
                sales_order__status__in=['confirmed', 'delivered', 'completed']
            ).values('produk_id').annotate(total_qty=Sum('jumlah')):
                so_sold_by_produk[item['produk_id']] = item['total_qty']
            
            # Qty terjual per produk dari POS (kumulatif historis)
            pos_sold_by_produk = {}
            for item in POSTransactionItem.objects.filter(
                transaction__status='paid'
            ).values('produk_id').annotate(total_qty=Sum('jumlah_konversi')):
                pos_sold_by_produk[item['produk_id']] = item['total_qty']
            
            # Qty adjustment out per produk (kumulatif historis)
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
            except Exception:
                pass

            # Hitung per produk
            for produk in Produk.objects.prefetch_related('stok_set').all():
                stok_saat_ini = sum(s.jumlah for s in produk.stok_set.all())
                qty_sold_so = so_sold_by_produk.get(produk.pk, Decimal('0'))
                qty_sold_pos = pos_sold_by_produk.get(produk.pk, Decimal('0'))
                qty_adj_out = adj_out_by_produk.get(produk.pk, Decimal('0'))
                qty_sc_used = sc_used_by_produk.get(produk.pk, Decimal('0'))
                qty_total_pernah_masuk = stok_saat_ini + qty_sold_so + qty_sold_pos + qty_adj_out + qty_sc_used
                
                total_aset += produk.harga_beli * qty_total_pernah_masuk
                
                if stok_saat_ini > 0:
                    total_harga_beli_ready += produk.harga_beli * stok_saat_ini
                    total_harga_jual_ready += produk.harga_jual * stok_saat_ini
        except Exception:
            pass
        
        estimasi_keuntungan = total_harga_jual_ready - total_harga_beli_ready
        
        # ===== Keuntungan Kotor dari penjualan (margin per item terjual) =====
        # Sinkron dengan Dashboard profit_data.gross_profit
        keuntungan_kotor = Decimal('0')
        try:
            from django.db.models import F, DecimalField, ExpressionWrapper
            
            # Keuntungan dari SO
            ke_so_filter = {'sales_order__status__in': ['confirmed', 'delivered', 'completed']}
            if filter_start:
                ke_so_filter['sales_order__tanggal__date__gte'] = filter_start
            if filter_end:
                ke_so_filter['sales_order__tanggal__date__lte'] = filter_end
            if cabang_id:
                ke_so_filter['sales_order__gudang_id'] = cabang_id
            
            keuntungan_so = SalesOrderItem.objects.filter(
                **ke_so_filter
            ).annotate(
                margin=ExpressionWrapper(
                    (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah'),
                    output_field=DecimalField()
                )
            ).aggregate(total=Sum('margin'))['total'] or Decimal('0')
            
            # Keuntungan dari POS
            ke_pos_filter = {'transaction__status': 'paid'}
            if filter_start:
                ke_pos_filter['transaction__tanggal__date__gte'] = filter_start
            if filter_end:
                ke_pos_filter['transaction__tanggal__date__lte'] = filter_end
            if cabang_id:
                ke_pos_filter['transaction__gudang_id'] = cabang_id
            
            keuntungan_pos = POSTransactionItem.objects.filter(
                **ke_pos_filter
            ).annotate(
                margin=ExpressionWrapper(
                    (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah_konversi'),
                    output_field=DecimalField()
                )
            ).aggregate(total=Sum('margin'))['total'] or Decimal('0')
            
            # Keuntungan dari Service Center (revenue - COGS sparepart)
            keuntungan_sc = Decimal('0')
            try:
                from apps.service_center.models import PenggunaanSparepart as SC_SP_Keu
                # SC revenue sudah dihitung sebagai total_service di atas
                # DIPERBAIKI #17: Ubah dari per-item loop ke aggregate query (performa)
                sc_cogs_filter = {'order_service__status_bayar': 'lunas'}
                if filter_start:
                    sc_cogs_filter['order_service__tanggal_masuk__date__gte'] = filter_start
                if filter_end:
                    sc_cogs_filter['order_service__tanggal_masuk__date__lte'] = filter_end
                if metode_id:
                    sc_cogs_filter['order_service__metode_pembayaran_id'] = metode_id
                sc_cogs = SC_SP_Keu.objects.filter(**sc_cogs_filter).aggregate(
                    total=Sum(F('jumlah') * F('produk__harga_beli'))
                )['total'] or Decimal('0')
                keuntungan_sc = Decimal(str(total_service)) - sc_cogs
            except Exception:
                pass

            keuntungan_kotor = keuntungan_so + keuntungan_pos + keuntungan_sc
        except Exception:
            pass
        
        # Data konteks: total_pemasukan — untuk ditampilkan di template
        context['total_pemasukan'] = total_pemasukan
        # Data konteks: total_sales_order — untuk ditampilkan di template
        context['total_sales_order'] = total_sales_order
        # Data konteks: total_pos — untuk ditampilkan di template
        context['total_pos'] = total_pos
        # Data konteks: total_service — pendapatan dari Service Center
        context['total_service'] = total_service
        # Data konteks: total_biaya_sparepart_service — biaya sparepart (pengeluaran)
        context['total_biaya_sparepart_service'] = total_biaya_sparepart_service
        # Data konteks: total_pengeluaran — untuk ditampilkan di template
        context['total_pengeluaran'] = total_pengeluaran
        # Data konteks: total_pembelian — untuk ditampilkan di template
        context['total_pembelian'] = total_pembelian
        # Data konteks: total_biaya — untuk ditampilkan di template
        context['total_biaya'] = total_biaya
        # Data konteks: laba_rugi — untuk ditampilkan di template
        context['laba_rugi'] = laba_rugi
        # Data konteks: total_aset — Nilai inventori historis (sinkron Dashboard)
        context['total_aset'] = total_aset
        # Data konteks tambahan — sinkron dengan Dashboard
        context['total_harga_beli_ready'] = total_harga_beli_ready
        context['total_harga_jual_ready'] = total_harga_jual_ready
        context['estimasi_keuntungan'] = estimasi_keuntungan
        context['keuntungan_kotor'] = keuntungan_kotor
        
        # List data — with all filters applied + select_related for new columns
        # DIPERBAIKI: Tambahkan filter status agar list konsisten dengan summary cards
        so_list_filter = {'status__in': ['confirmed', 'delivered', 'completed']}
        pos_list_filter = {'status': 'paid'}
        po_list_filter = {'status__in': ['approved', 'received']}
        biaya_list_filter = {'status': 'approved'}  # Hanya tampilkan biaya yang disetujui
        if filter_start:
            so_list_filter['tanggal__date__gte'] = filter_start
            pos_list_filter['tanggal__date__gte'] = filter_start
            po_list_filter['tanggal__date__gte'] = filter_start
            biaya_list_filter['tanggal__gte'] = filter_start
        if filter_end:
            so_list_filter['tanggal__date__lte'] = filter_end
            pos_list_filter['tanggal__date__lte'] = filter_end
            po_list_filter['tanggal__date__lte'] = filter_end
            biaya_list_filter['tanggal__lte'] = filter_end
        if cabang_id:
            so_list_filter['gudang_id'] = cabang_id
            pos_list_filter['gudang_id'] = cabang_id
            po_list_filter['gudang_id'] = cabang_id
            biaya_list_filter['cabang_id'] = cabang_id
        if metode_id:
            so_list_filter['metode_pembayaran_id'] = metode_id
            pos_list_filter['metode_pembayaran_id'] = metode_id
            po_list_filter['metode_pembayaran_id'] = metode_id
            biaya_list_filter['metode_pembayaran_id'] = metode_id
        
        # Query database — ambil data context['sales_order_list'] yang sesuai filter
        # Data konteks: sales_order_list — untuk ditampilkan di template
        context['sales_order_list'] = SalesOrder.objects.filter(
            **so_list_filter
        ).select_related('gudang', 'metode_pembayaran', 'customer').order_by('-tanggal')[:100]
        
        # Query database — ambil data context['pos_transaction_list'] yang sesuai filter
        # Data konteks: pos_transaction_list — untuk ditampilkan di template
        context['pos_transaction_list'] = POSTransaction.objects.filter(
            **pos_list_filter
        ).select_related('gudang', 'metode_pembayaran').order_by('-tanggal')[:100]
        
        # Query database — ambil data context['purchase_order_list'] yang sesuai filter
        # Data konteks: purchase_order_list — untuk ditampilkan di template
        context['purchase_order_list'] = PurchaseOrder.objects.filter(
            **po_list_filter
        ).select_related('gudang', 'metode_pembayaran', 'supplier').order_by('-tanggal')[:100]
        
        # Query database — ambil data context['transaksi_biaya_list'] yang sesuai filter
        # Data konteks: transaksi_biaya_list — untuk ditampilkan di template
        context['transaksi_biaya_list'] = TransaksiBiaya.objects.filter(
            **biaya_list_filter
        ).select_related('cabang', 'metode_pembayaran', 'kategori').order_by('-tanggal')[:100]

        # Tambahkan Produk dan Sparepart yang dibeli langsung sebagai pengeluaran
        # DIPERBAIKI: Menggunakan qty_historis (sinkron dengan total pengeluaran di atas)
        try:
            from apps.produk.models import Produk as ProdukKeu
            produk_keu_filter = {'metode_pembayaran__isnull': False}
            if metode_id:
                produk_keu_filter['metode_pembayaran_id'] = metode_id
            
            pembelian_produk = ProdukKeu.objects.filter(
                **produk_keu_filter
            ).select_related('metode_pembayaran', 'satuan').prefetch_related('stok_set').order_by('-dibuat_pada')[:100]
            
            # Reuse sold maps yang sudah di-build sebelumnya (so_sold_map, pos_sold_map, adj_out_map, sc_used_map)
            pembelian_produk_list = []
            for p in pembelian_produk:
                stok_saat_ini = sum(s.jumlah for s in p.stok_set.all())
                qty_historis = stok_saat_ini + so_sold_map.get(p.pk, Dec('0')) + pos_sold_map.get(p.pk, Dec('0')) + adj_out_map.get(p.pk, Dec('0')) + sc_used_map.get(p.pk, Dec('0'))
                p.qty_historis = qty_historis
                p.total_pengeluaran_produk = p.harga_beli * qty_historis
                pembelian_produk_list.append(p)
            context['pembelian_produk_list'] = pembelian_produk_list
        except Exception:
            context['pembelian_produk_list'] = []

        # Query database — ambil data Order Service untuk laporan keuangan
        try:
            from apps.service_center.models import OrderService as SC_OrderList
            sc_list_filter = {'status_bayar': 'lunas'}
            if filter_start:
                sc_list_filter['tanggal_masuk__date__gte'] = filter_start
            if filter_end:
                sc_list_filter['tanggal_masuk__date__lte'] = filter_end
            if metode_id:
                sc_list_filter['metode_pembayaran_id'] = metode_id
            context['service_order_list'] = SC_OrderList.objects.filter(
                **sc_list_filter
            ).select_related('pelanggan', 'metode_pembayaran').order_by('-tanggal_masuk')[:100]
        except Exception:
            context['service_order_list'] = []

        # sparepart_usage_list tidak lagi ditampilkan di tabel pengeluaran
        # (sparepart bukan pengeluaran, sudah masuk via PO)
        context['sparepart_usage_list'] = []
        
        return context



class LaporanProdukDetailView(ReadPermissionMixin, DetailView):
    """
    Detail Produk — info lengkap + riwayat stok + activity log.
    URL: /laporan/produk/<pk>/
    Context: margin, activity_logs, stok_list, po_items, so_items
    """
    model = Produk
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/produk_detail.html'
    context_object_name = 'produk'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        produk = self.object
        
        # Hitung margin
        context['margin'] = produk.harga_jual - produk.harga_beli
        
        # Riwayat Activity Log yang KOMPREHENSIF untuk produk ini
        # Mencakup: perubahan langsung pada produk DAN semua perubahan stok terkait
        context['activity_logs'] = UserActivity.objects.filter(
            Q(model_name__icontains='produk', object_id=str(produk.pk)) |  # Perubahan langsung pada produk
            Q(  # Stock-specific actions untuk produk ini di semua gudang  
                action__in=['stock_in', 'stock_out', 'stock_adjustment', 'stock_transfer_in', 'stock_transfer_out'],
                object_repr__icontains=produk.nama
            ) |
            Q(  # Perubahan pada stok produk ini
                model_name__icontains='stok',
                object_repr__icontains=produk.nama
            )
        ).select_related('user').order_by('-timestamp')[:100]
        
        # Related data - Stok di gudang
        context['stok_list'] = Stok.objects.filter(produk=produk).select_related('gudang')
        
        # Related data - Item di Purchase Orders
        context['po_items'] = PurchaseOrderItem.objects.filter(
            produk=produk
        ).select_related('purchase_order', 'purchase_order__supplier').order_by('-purchase_order__tanggal')[:10]
        
        # Related data - Item di Sales Orders
        context['so_items'] = SalesOrderItem.objects.filter(
            produk=produk
        ).select_related('sales_order', 'sales_order__customer').order_by('-sales_order__tanggal')[:10]
        
        return context



class LaporanPenjualanDetailView(ReadPermissionMixin, DetailView):
    """
    Detail Sales Order — info SO + activity log.
    URL: /laporan/penjualan/<pk>/
    Context: activity_logs (riwayat perubahan SO)
    """
    model = SalesOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/penjualan_detail.html'
    context_object_name = 'sales_order'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        sales_order = self.object
        
        # Riwayat Activity Log untuk SO ini
        so = self.object
        
        # Activity Log untuk SO ini
        context['activity_logs'] = UserActivity.objects.filter(
            Q(model_name__icontains='sales order') | Q(model_name__icontains='penjualan'),
            object_id=str(so.pk)
        ).select_related('user').order_by('-timestamp')[:50]
        
        return context



class LaporanPembelianDetailView(ReadPermissionMixin, DetailView):
    """
    Detail Purchase Order — info PO + activity log.
    URL: /laporan/pembelian/<pk>/
    Context: activity_logs (riwayat perubahan PO)
    """
    model = PurchaseOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/pembelian_detail.html'
    context_object_name = 'purchase_order'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        po = self.object
        
        # Activity Log untuk PO ini
        context['activity_logs'] = UserActivity.objects.filter(
            Q(model_name__icontains='purchase order') | Q(model_name__icontains='pembelian'),
            object_id=str(po.pk)
        ).select_related('user').order_by('-timestamp')[:50]
        
        return context



class LaporanStokDetailView(ReadPermissionMixin, DetailView):
    """
    Detail Stok — info stok produk + riwayat perubahan komprehensif.
    URL: /laporan/stok/<pk>/
    Context: activity_logs, po_items, so_items, adjustment_list, transfer_list
    """
    model = Stok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'laporan/stok_detail.html'
    context_object_name = 'stok'
    # Modul permission yang dicek: 'laporan'
    permission_module = 'laporan'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        stok = self.object
        
        # Query untuk activity logs yang lebih komprehensif
        # Mencakup: stock-specific actions DAN update pada model stok ini
        activity_logs = UserActivity.objects.filter(
            Q(model_name__icontains='stok', object_id=str(stok.pk)) |  # Perubahan langsung pada stok
            Q(  # Stock-specific actions untuk produk+gudang ini
                action__in=['stock_in', 'stock_out', 'stock_adjustment', 'stock_transfer_in', 'stock_transfer_out'],
                gudang_id=str(stok.gudang.pk),
                object_repr__icontains=stok.produk.nama
            )
        ).select_related('user').order_by('-timestamp')[:100]
        
        # Data konteks: activity_logs — untuk ditampilkan di template
        context['activity_logs'] = activity_logs
        
        # Related - PO items yang mempengaruhi stok produk ini (di gudang ini)
        context['po_items'] = PurchaseOrderItem.objects.filter(
            produk=stok.produk,
            purchase_order__gudang=stok.gudang
        ).select_related('purchase_order', 'purchase_order__supplier').order_by('-purchase_order__tanggal')[:20]
        
        # Related - SO items yang mempengaruhi stok produk ini (di gudang ini)
        context['so_items'] = SalesOrderItem.objects.filter(
            produk=stok.produk,
            sales_order__gudang=stok.gudang
        ).select_related('sales_order', 'sales_order__customer').order_by('-sales_order__tanggal')[:20]
        
        # Related - Adjustment pada produk+gudang ini
        from apps.inventory.models import AdjustmentStok, TransferStok
        # Query database — ambil data context['adjustment_list'] yang sesuai filter
        # Data konteks: adjustment_list — untuk ditampilkan di template
        context['adjustment_list'] = AdjustmentStok.objects.filter(
            produk=stok.produk,
            gudang=stok.gudang
        ).order_by('-dibuat_pada')[:20]
        
        # Related - Transfer yang melibatkan gudang ini
        context['transfer_list'] = TransferStok.objects.filter(
            Q(gudang_asal=stok.gudang) | Q(gudang_tujuan=stok.gudang),
            items__produk=stok.produk
        ).distinct().order_by('-dibuat_pada')[:20]
        
        return context


# ═══════════════════════════════════════════════════════════════
#  LAPORAN SERVICE — Laporan Order Service Center
# ═══════════════════════════════════════════════════════════════

class LaporanServiceView(ReadPermissionMixin, TemplateView):
    """
    Laporan Service Center — Analitik order service.
    URL: /laporan/service/
    Filter: start_date, end_date, status, teknisi
    Cards: total order, total revenue, order selesai, rata-rata biaya
    """
    template_name = 'laporan/service.html'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from datetime import datetime
        from decimal import Decimal
        from django.contrib.auth.models import User
        from apps.service_center.models import OrderService, ItemService, PenggunaanSparepart

        # Parse filter params
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        filter_status = self.request.GET.get('status', '')
        filter_teknisi = self.request.GET.get('teknisi', '')
        context['filter_start_date'] = start_date_str
        context['filter_end_date'] = end_date_str
        context['filter_status'] = filter_status
        context['filter_teknisi'] = filter_teknisi
        context['status_choices'] = OrderService.STATUS_CHOICES
        context['teknisi_list'] = User.objects.filter(
            order_service_teknisi__isnull=False
        ).distinct()

        filter_start = None
        filter_end = None
        if start_date_str:
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Base queryset
        qs = OrderService.objects.select_related(
            'pelanggan', 'jenis_perangkat', 'teknisi', 'diterima_oleh', 'metode_pembayaran'
        ).prefetch_related('items', 'penggunaan_sparepart')

        if filter_start:
            qs = qs.filter(tanggal_masuk__date__gte=filter_start)
        if filter_end:
            qs = qs.filter(tanggal_masuk__date__lte=filter_end)
        if filter_status:
            qs = qs.filter(status=filter_status)
        if filter_teknisi:
            qs = qs.filter(teknisi_id=filter_teknisi)

        order_list = qs.order_by('-tanggal_masuk')

        # === Summary cards ===
        total_order = order_list.count()
        order_selesai = order_list.filter(status__in=['selesai', 'diambil']).count()
        order_dibatalkan = order_list.filter(status='dibatalkan').count()

        # Revenue: total biaya_akhir untuk order lunas
        total_revenue = order_list.filter(
            status_bayar='lunas'
        ).aggregate(total=Sum('biaya_akhir'))['total'] or Decimal('0')

        # Total biaya layanan
        total_biaya_layanan = Decimal('0')
        total_biaya_sparepart = Decimal('0')
        for order in order_list:
            total_biaya_layanan += sum(item.biaya for item in order.items.all())
            total_biaya_sparepart += sum(
                sp.jumlah * sp.harga_satuan for sp in order.penggunaan_sparepart.all()
            )

        rata_rata_biaya = int(total_revenue / total_order) if total_order > 0 else 0

        # Status distribution
        status_dist = {}
        for code, label in OrderService.STATUS_CHOICES:
            count = order_list.filter(status=code).count()
            if count > 0:
                status_dist[label] = count

        # Top 5 teknisi by completed orders
        top_teknisi = order_list.filter(
            teknisi__isnull=False,
            status__in=['selesai', 'diambil']
        ).values(
            'teknisi__username', 'teknisi__first_name', 'teknisi__last_name'
        ).annotate(
            total_order=Count('id'),
            total_revenue=Sum('biaya_akhir')
        ).order_by('-total_order')[:5]

        # Top 5 jenis perangkat
        top_perangkat = order_list.values(
            'jenis_perangkat__nama'
        ).annotate(
            total=Count('id')
        ).order_by('-total')[:5]

        context.update({
            'order_list': order_list,
            'total_order': total_order,
            'order_selesai': order_selesai,
            'order_dibatalkan': order_dibatalkan,
            'total_revenue': total_revenue,
            'total_biaya_layanan': total_biaya_layanan,
            'total_biaya_sparepart': total_biaya_sparepart,
            'rata_rata_biaya': rata_rata_biaya,
            'status_dist': status_dist,
            'top_teknisi': top_teknisi,
            'top_perangkat': top_perangkat,
        })

        # Template cetak untuk export PDF
        from apps.pengaturan.models import TemplateCetak
        try:
            context['export_pdf_template'] = TemplateCetak.objects.first()
        except Exception:
            context['export_pdf_template'] = None

        return context


# ═══════════════════════════════════════════════════════════════
#  LAPORAN SPAREPART — Laporan Penggunaan Sparepart untuk Service
# ═══════════════════════════════════════════════════════════════

class LaporanSparepartView(ReadPermissionMixin, TemplateView):
    """
    Laporan Sparepart — Analitik penggunaan sparepart pada service.
    URL: /laporan/sparepart/
    Filter: start_date, end_date
    Cards: total penggunaan, total COGS, top sparepart, gudang impact
    """
    template_name = 'laporan/sparepart.html'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_sparepart'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from datetime import datetime
        from decimal import Decimal
        from apps.service_center.models import PenggunaanSparepart
        from apps.produk.models import Gudang

        # Parse filter params
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        context['filter_start_date'] = start_date_str
        context['filter_end_date'] = end_date_str

        filter_start = None
        filter_end = None
        if start_date_str:
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Base queryset
        qs = PenggunaanSparepart.objects.select_related(
            'order_service', 'order_service__pelanggan', 'produk', 'gudang'
        )
        if filter_start:
            qs = qs.filter(dibuat_pada__date__gte=filter_start)
        if filter_end:
            qs = qs.filter(dibuat_pada__date__lte=filter_end)

        sparepart_list = qs.order_by('-dibuat_pada')

        # === Summary cards ===
        total_penggunaan = sparepart_list.count()
        total_qty = sparepart_list.aggregate(total=Sum('jumlah'))['total'] or Decimal('0')

        # COGS: sum(jumlah × harga_satuan) — hitung di Python karena subtotal = property
        total_cogs = Decimal('0')
        for sp in sparepart_list:
            total_cogs += sp.jumlah * sp.harga_satuan

        # Top 10 sparepart paling banyak digunakan
        top_sparepart_raw = sparepart_list.values(
            'produk__nama', 'produk__sku'
        ).annotate(
            total_qty=Sum('jumlah'),
            total_used=Count('id')
        ).order_by('-total_qty')[:10]
        
        top_sparepart = list(top_sparepart_raw)

        # Annotate COGS per sparepart entirely in Python
        for sp_item in top_sparepart:
            cost = Decimal('0')
            for sp in sparepart_list:
                if sp.produk.nama == sp_item['produk__nama']:
                    cost += sp.jumlah * sp.harga_satuan
            sp_item['total_cost'] = cost

        # Impact per gudang via Dictionary aggregation
        gudang_dict = {}
        for sp in sparepart_list:
            gn = sp.gudang.nama if sp.gudang else 'Gudang Utama'
            if gn not in gudang_dict:
                gudang_dict[gn] = {'gudang__nama': gn, 'total_qty': Decimal('0'), 'total_cost': Decimal('0'), 'total_items': 0}
            
            gudang_dict[gn]['total_qty'] += sp.jumlah
            gudang_dict[gn]['total_cost'] += sp.jumlah * sp.harga_satuan
            gudang_dict[gn]['total_items'] += 1

        gudang_impact = list(gudang_dict.values())
        gudang_impact.sort(key=lambda x: x['total_qty'], reverse=True)

        context.update({
            'sparepart_list': sparepart_list,
            'total_penggunaan': total_penggunaan,
            'total_qty': total_qty,
            'total_cogs': total_cogs,
            'top_sparepart': top_sparepart,
            'gudang_impact': gudang_impact,
        })

        # Template cetak untuk export PDF
        from apps.pengaturan.models import TemplateCetak
        try:
            context['export_pdf_template'] = TemplateCetak.objects.first()
        except Exception:
            context['export_pdf_template'] = None

        return context


# ═══════════════════════════════════════════════════════════════
#  LAPORAN CABANG — Laporan Performa per Cabang/Gudang
# ═══════════════════════════════════════════════════════════════

class LaporanCabangView(ReadPermissionMixin, TemplateView):
    """
    Laporan Cabang/Gudang — Analitik performa per cabang.
    URL: /laporan/cabang/
    Filter: cabang (wajib), start_date, end_date
    5 Kategori Data:
      1. Pemasukan (SO + POS + Service)
      2. Pengeluaran (PO + Biaya)
      3. Inventori & Mutasi (Stok, Transfer, Adjustment)
      4. Laba/Rugi Cabang
      5. Leaderboard (Top Produk, Top Kasir)
    """
    template_name = 'laporan/cabang.html'
    permission_module = 'laporan'
    permission_sub_module = 'laporan_cabang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['is_laporan_cabang'] = True
        from datetime import datetime
        from decimal import Decimal

        # === Daftar gudang untuk dropdown filter ===
        context['gudang_list'] = Gudang.objects.filter(aktif=True)

        # === Parse filter params ===
        cabang_id = self.request.GET.get('cabang', '')
        start_date_str = self.request.GET.get('start_date', '')
        end_date_str = self.request.GET.get('end_date', '')
        context['filter_cabang'] = cabang_id
        context['filter_start_date'] = start_date_str
        context['filter_end_date'] = end_date_str
        context['has_date_filter'] = bool(start_date_str or end_date_str)

        filter_start = None
        filter_end = None
        if start_date_str:
            try:
                filter_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                filter_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Template cetak untuk export Excel/PDF
        from apps.pengaturan.models import TemplateCetak
        try:
            context['export_pdf_template'] = TemplateCetak.objects.first()
        except Exception:
            context['export_pdf_template'] = None

        # Jika belum ada cabang dipilih, sediakan data ringkasan semua cabang
        if not cabang_id:
            context['selected_gudang'] = None

            # === Data summary SEMUA cabang untuk tabel awal ===
            from apps.pos.models import POSTransaction
            from django.contrib.auth.models import User as AuthUser
            summary_cabang = []
            for gudang in context['gudang_list']:
                gid = gudang.pk
                # Jumlah produk (tipe produk) yang punya stok di gudang ini
                stok_qs_all = Stok.objects.filter(gudang_id=gid)
                jml_produk = stok_qs_all.filter(produk__tipe='produk').count()
                jml_sparepart = stok_qs_all.filter(produk__tipe='sparepart').count()
                total_unit_stok = stok_qs_all.aggregate(t=Sum('jumlah'))['t'] or 0

                # Nilai aset
                nilai_aset = Decimal('0')
                for si in stok_qs_all.select_related('produk'):
                    nilai_aset += si.produk.harga_beli * si.jumlah

                # Jumlah karyawan di cabang ini
                jml_karyawan = 0
                try:
                    from apps.hr.models import Karyawan as KaryawanModel
                    jml_karyawan = KaryawanModel.objects.filter(aktif=True, cabang_id=gid).count()
                except Exception:
                    pass

                # Transaksi POS di cabang ini
                jml_trx_pos = POSTransaction.objects.filter(gudang_id=gid, status='paid').count()
                # SO di cabang ini
                jml_trx_so = SalesOrder.objects.filter(gudang_id=gid, status__in=['confirmed', 'delivered', 'completed']).count()
                # PO di cabang ini
                jml_trx_po = PurchaseOrder.objects.filter(gudang_id=gid, status__in=['approved', 'received']).count()

                # Order Service di cabang ini
                from apps.service_center.models import OrderService as OSModel
                jml_order_service = OSModel.objects.filter(cabang_id=gid).count()
                pemasukan_service = OSModel.objects.filter(
                    cabang_id=gid, status_bayar='lunas'
                ).aggregate(t=Sum('biaya_akhir'))['t'] or Decimal('0')

                # Total Pemasukan
                pemasukan_so = SalesOrder.objects.filter(
                    gudang_id=gid, status__in=['confirmed', 'delivered', 'completed']
                ).aggregate(t=Sum('total_harga'))['t'] or Decimal('0')
                pemasukan_pos = POSTransaction.objects.filter(
                    gudang_id=gid, status='paid'
                ).aggregate(t=Sum('total_harga'))['t'] or Decimal('0')
                total_pemasukan = pemasukan_so + pemasukan_pos + pemasukan_service

                # Total Pengeluaran
                pengeluaran_po = PurchaseOrder.objects.filter(
                    gudang_id=gid, status__in=['approved', 'received']
                ).aggregate(t=Sum('total_harga'))['t'] or Decimal('0')
                pengeluaran_biaya = TransaksiBiaya.objects.filter(
                    cabang_id=gid, status='approved'
                ).aggregate(t=Sum('jumlah'))['t'] or Decimal('0')
                total_pengeluaran = pengeluaran_po + pengeluaran_biaya

                summary_cabang.append({
                    'nama': gudang.nama,
                    'kode': gudang.kode,
                    'pk': gudang.pk,
                    'jml_produk': jml_produk,
                    'jml_sparepart': jml_sparepart,
                    'total_unit_stok': int(total_unit_stok),
                    'nilai_aset': nilai_aset,
                    'jml_trx_pos': jml_trx_pos,
                    'jml_trx_so': jml_trx_so,
                    'jml_trx_po': jml_trx_po,
                    'jml_order_service': jml_order_service,
                    'pemasukan_service': pemasukan_service,
                    'total_pemasukan': total_pemasukan,
                    'total_pengeluaran': total_pengeluaran,
                    'laba_rugi': total_pemasukan - total_pengeluaran,
                })

            context['summary_cabang'] = summary_cabang
            return context

        # Ambil objek gudang
        try:
            selected_gudang = Gudang.objects.get(pk=cabang_id)
        except Gudang.DoesNotExist:
            context['selected_gudang'] = None
            return context

        context['selected_gudang'] = selected_gudang

        # ════════════════════════════════════════════════════════
        # 1. PEMASUKAN CABANG (SO + POS + Service)
        # ════════════════════════════════════════════════════════
        from apps.pos.models import POSTransaction

        # Sales Order
        so_filter = {
            'status__in': ['confirmed', 'delivered', 'completed'],
            'gudang_id': cabang_id,
        }
        if filter_start:
            so_filter['tanggal__date__gte'] = filter_start
        if filter_end:
            so_filter['tanggal__date__lte'] = filter_end

        total_so_cabang = SalesOrder.objects.filter(
            **so_filter
        ).aggregate(total=Sum('total_harga'))['total'] or Decimal('0')
        so_count = SalesOrder.objects.filter(**so_filter).count()

        # POS Transaction
        pos_filter = {
            'status': 'paid',
            'gudang_id': cabang_id,
        }
        if filter_start:
            pos_filter['tanggal__date__gte'] = filter_start
        if filter_end:
            pos_filter['tanggal__date__lte'] = filter_end

        total_pos_cabang = POSTransaction.objects.filter(
            **pos_filter
        ).aggregate(total=Sum('total_harga'))['total'] or Decimal('0')
        pos_count = POSTransaction.objects.filter(**pos_filter).count()

        # Service Center — filter per cabang
        total_service_cabang = Decimal('0')
        service_count = 0
        try:
            from apps.service_center.models import OrderService
            sc_filter = {'status_bayar': 'lunas', 'cabang_id': cabang_id}
            if filter_start:
                sc_filter['tanggal_masuk__date__gte'] = filter_start
            if filter_end:
                sc_filter['tanggal_masuk__date__lte'] = filter_end
            total_service_cabang = OrderService.objects.filter(
                **sc_filter
            ).aggregate(total=Sum('biaya_akhir'))['total'] or Decimal('0')
            service_count = OrderService.objects.filter(**sc_filter).count()
        except Exception:
            pass

        total_pemasukan_cabang = total_so_cabang + total_pos_cabang + total_service_cabang

        context['total_so_cabang'] = total_so_cabang
        context['so_count'] = so_count
        context['total_pos_cabang'] = total_pos_cabang
        context['pos_count'] = pos_count
        context['total_service_cabang'] = total_service_cabang
        context['service_count'] = service_count
        context['total_pemasukan_cabang'] = total_pemasukan_cabang

        # ════════════════════════════════════════════════════════
        # 2. PENGELUARAN CABANG (PO + Biaya)
        # ════════════════════════════════════════════════════════

        # Purchase Order
        po_filter = {
            'status__in': ['approved', 'received'],
            'gudang_id': cabang_id,
        }
        if filter_start:
            po_filter['tanggal__date__gte'] = filter_start
        if filter_end:
            po_filter['tanggal__date__lte'] = filter_end

        total_po_cabang = PurchaseOrder.objects.filter(
            **po_filter
        ).aggregate(total=Sum('total_harga'))['total'] or Decimal('0')
        po_count = PurchaseOrder.objects.filter(**po_filter).count()

        # Transaksi Biaya
        biaya_filter = {
            'status': 'approved',
            'cabang_id': cabang_id,
        }
        if filter_start:
            biaya_filter['tanggal__gte'] = filter_start
        if filter_end:
            biaya_filter['tanggal__lte'] = filter_end

        total_biaya_cabang = TransaksiBiaya.objects.filter(
            **biaya_filter
        ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
        biaya_count = TransaksiBiaya.objects.filter(**biaya_filter).count()

        # Pengeluaran dari Tambah Produk (harga_beli x jumlah stok tipe=produk)
        stok_produk_qs = Stok.objects.filter(
            gudang_id=cabang_id, produk__tipe='produk'
        ).select_related('produk')
        total_tambah_produk = Decimal('0')
        tambah_produk_count = stok_produk_qs.count()
        for sp in stok_produk_qs:
            total_tambah_produk += sp.produk.harga_beli * sp.jumlah

        # Pengeluaran dari Tambah Sparepart (harga_beli x jumlah stok tipe=sparepart)
        stok_sparepart_qs = Stok.objects.filter(
            gudang_id=cabang_id, produk__tipe='sparepart'
        ).select_related('produk')
        total_tambah_sparepart = Decimal('0')
        tambah_sparepart_count = stok_sparepart_qs.count()
        for ss in stok_sparepart_qs:
            total_tambah_sparepart += ss.produk.harga_beli * ss.jumlah

        total_pengeluaran_cabang = total_po_cabang + total_biaya_cabang + total_tambah_produk + total_tambah_sparepart

        context['total_po_cabang'] = total_po_cabang
        context['po_count'] = po_count
        context['total_biaya_cabang'] = total_biaya_cabang
        context['biaya_count'] = biaya_count
        context['total_tambah_produk'] = total_tambah_produk
        context['tambah_produk_count'] = tambah_produk_count
        context['total_tambah_sparepart'] = total_tambah_sparepart
        context['tambah_sparepart_count'] = tambah_sparepart_count
        context['total_pengeluaran_cabang'] = total_pengeluaran_cabang

        # ════════════════════════════════════════════════════════
        # 3. INVENTORI & MUTASI
        # ════════════════════════════════════════════════════════

        # Stok di gudang ini
        stok_qs = Stok.objects.filter(gudang_id=cabang_id).select_related('produk')
        total_item_stok = stok_qs.count()
        total_stok_qty = stok_qs.aggregate(total=Sum('jumlah'))['total'] or Decimal('0')

        # Nilai aset gudang ini: sum(harga_beli × jumlah) per stok
        total_aset_cabang = Decimal('0')
        total_nilai_jual_cabang = Decimal('0')
        for stok_item in stok_qs:
            total_aset_cabang += stok_item.produk.harga_beli * stok_item.jumlah
            total_nilai_jual_cabang += stok_item.produk.harga_jual * stok_item.jumlah

        # Transfer masuk/keluar
        transfer_in_count = 0
        transfer_out_count = 0
        adjustment_count = 0
        try:
            from apps.inventory.models import TransferStok, AdjustmentStok
            transfer_in_filter = {'gudang_tujuan_id': cabang_id}
            transfer_out_filter = {'gudang_asal_id': cabang_id}
            adj_filter = {'gudang_id': cabang_id}
            if filter_start:
                transfer_in_filter['dibuat_pada__date__gte'] = filter_start
                transfer_out_filter['dibuat_pada__date__gte'] = filter_start
                adj_filter['dibuat_pada__date__gte'] = filter_start
            if filter_end:
                transfer_in_filter['dibuat_pada__date__lte'] = filter_end
                transfer_out_filter['dibuat_pada__date__lte'] = filter_end
                adj_filter['dibuat_pada__date__lte'] = filter_end
            transfer_in_count = TransferStok.objects.filter(**transfer_in_filter).count()
            transfer_out_count = TransferStok.objects.filter(**transfer_out_filter).count()
            adjustment_count = AdjustmentStok.objects.filter(**adj_filter).count()
        except Exception:
            pass

        context['total_item_stok'] = total_item_stok
        context['total_stok_qty'] = int(total_stok_qty)
        context['total_aset_cabang'] = total_aset_cabang
        context['total_nilai_jual_cabang'] = total_nilai_jual_cabang
        context['transfer_in_count'] = transfer_in_count
        context['transfer_out_count'] = transfer_out_count
        context['adjustment_count'] = adjustment_count

        # ════════════════════════════════════════════════════════
        # 4. LABA/RUGI CABANG
        # ════════════════════════════════════════════════════════
        laba_rugi_cabang = total_pemasukan_cabang - total_pengeluaran_cabang
        context['laba_rugi_cabang'] = laba_rugi_cabang

        # ════════════════════════════════════════════════════════
        # 5. LEADERBOARD
        # ════════════════════════════════════════════════════════
        from apps.penjualan.models import SalesOrderItem
        from apps.pos.models import POSTransactionItem

        # Top 5 Produk Terlaris di cabang ini (dari SO + POS)
        so_item_filter = {
            'sales_order__gudang_id': cabang_id,
            'sales_order__status__in': ['confirmed', 'delivered', 'completed'],
        }
        pos_item_filter = {
            'transaction__gudang_id': cabang_id,
            'transaction__status': 'paid',
        }
        if filter_start:
            so_item_filter['sales_order__tanggal__date__gte'] = filter_start
            pos_item_filter['transaction__tanggal__date__gte'] = filter_start
        if filter_end:
            so_item_filter['sales_order__tanggal__date__lte'] = filter_end
            pos_item_filter['transaction__tanggal__date__lte'] = filter_end

        # Gabungkan qty terjual per item dari SO dan POS — PISAHKAN produk vs sparepart
        all_items_qty = {}
        for item in SalesOrderItem.objects.filter(**so_item_filter).values('produk__nama', 'produk__sku', 'produk__tipe').annotate(total_qty=Sum('jumlah')):
            key = item['produk__nama']
            all_items_qty[key] = {
                'nama': item['produk__nama'],
                'sku': item['produk__sku'],
                'tipe': item['produk__tipe'],
                'qty': item['total_qty'] or Decimal('0'),
            }
        for item in POSTransactionItem.objects.filter(**pos_item_filter).values('produk__nama', 'produk__sku', 'produk__tipe').annotate(total_qty=Sum('jumlah')):
            key = item['produk__nama']
            if key in all_items_qty:
                all_items_qty[key]['qty'] += item['total_qty'] or Decimal('0')
            else:
                all_items_qty[key] = {
                    'nama': item['produk__nama'],
                    'sku': item['produk__sku'],
                    'tipe': item['produk__tipe'],
                    'qty': item['total_qty'] or Decimal('0'),
                }

        # Top 5 Produk Terlaris (tipe='produk')
        produk_only = [v for v in all_items_qty.values() if v.get('tipe') == 'produk']
        top_produk = sorted(produk_only, key=lambda x: x['qty'], reverse=True)[:5]
        context['top_produk_cabang'] = top_produk

        # Top 5 Sparepart Terlaris (tipe='sparepart')
        sparepart_only = [v for v in all_items_qty.values() if v.get('tipe') == 'sparepart']
        top_sparepart = sorted(sparepart_only, key=lambda x: x['qty'], reverse=True)[:5]
        context['top_sparepart_cabang'] = top_sparepart

        # Jumlah Produk vs Sparepart di gudang ini (stok)
        stok_produk_count = stok_qs.filter(produk__tipe='produk').count()
        stok_sparepart_count = stok_qs.filter(produk__tipe='sparepart').count()
        stok_produk_qty = stok_qs.filter(produk__tipe='produk').aggregate(t=Sum('jumlah'))['t'] or 0
        stok_sparepart_qty = stok_qs.filter(produk__tipe='sparepart').aggregate(t=Sum('jumlah'))['t'] or 0
        context['stok_produk_count'] = stok_produk_count
        context['stok_sparepart_count'] = stok_sparepart_count
        context['stok_produk_qty'] = int(stok_produk_qty)
        context['stok_sparepart_qty'] = int(stok_sparepart_qty)

        # Top 5 Kasir TIDAK DIGUNAKAN LAGI — diganti produk/sparepart
        # Tetap simpan untuk backward compat
        top_kasir = POSTransaction.objects.filter(
            **pos_filter
        ).values(
            'kasir__username', 'kasir__first_name', 'kasir__last_name'
        ).annotate(
            total_trx=Count('id'),
            total_nominal=Sum('total_harga')
        ).order_by('-total_trx')[:5]
        context['top_kasir_cabang'] = top_kasir

        # ════════════════════════════════════════════════════════
        # 6. SERVICE CENTER PER CABANG
        # ════════════════════════════════════════════════════════
        try:
            from apps.service_center.models import OrderService as OS, PenggunaanSparepart as PS

            sc_base_filter = {'cabang_id': cabang_id}
            if filter_start:
                sc_base_filter['tanggal_masuk__date__gte'] = filter_start
            if filter_end:
                sc_base_filter['tanggal_masuk__date__lte'] = filter_end

            sc_qs = OS.objects.filter(**sc_base_filter)

            sc_total_order = sc_qs.count()
            sc_order_selesai = sc_qs.filter(status__in=['selesai', 'diambil']).count()
            sc_order_dibatalkan = sc_qs.filter(status='dibatalkan').count()
            sc_revenue = sc_qs.filter(status_bayar='lunas').aggregate(
                t=Sum('biaya_akhir'))['t'] or Decimal('0')
            sc_rata_biaya = int(sc_revenue / sc_total_order) if sc_total_order > 0 else 0

            # Distribusi status order service
            sc_status_dist = {}
            for code, label in OS.STATUS_CHOICES:
                cnt = sc_qs.filter(status=code).count()
                if cnt > 0:
                    sc_status_dist[label] = cnt

            # Top 5 jenis perangkat di cabang ini
            sc_top_perangkat = sc_qs.values(
                'jenis_perangkat__nama'
            ).annotate(total=Count('id')).order_by('-total')[:5]

            # Top 5 teknisi di cabang ini
            sc_top_teknisi = sc_qs.filter(
                teknisi__isnull=False, status__in=['selesai', 'diambil']
            ).values(
                'teknisi__username', 'teknisi__first_name', 'teknisi__last_name'
            ).annotate(
                total_order=Count('id'),
                total_revenue=Sum('biaya_akhir')
            ).order_by('-total_order')[:5]

            context['sc_total_order'] = sc_total_order
            context['sc_order_selesai'] = sc_order_selesai
            context['sc_order_dibatalkan'] = sc_order_dibatalkan
            context['sc_revenue'] = sc_revenue
            context['sc_rata_biaya'] = sc_rata_biaya
            context['sc_status_dist'] = sc_status_dist
            context['sc_top_perangkat'] = sc_top_perangkat
            context['sc_top_teknisi'] = sc_top_teknisi

            # ── Penggunaan Sparepart untuk Service di gudang cabang ini ──
            sp_filter = {'gudang_id': cabang_id}
            if filter_start:
                sp_filter['dibuat_pada__date__gte'] = filter_start
            if filter_end:
                sp_filter['dibuat_pada__date__lte'] = filter_end

            sp_qs = PS.objects.filter(**sp_filter).select_related('produk', 'order_service')
            sp_service_total = sp_qs.count()
            sp_service_qty = sp_qs.aggregate(t=Sum('jumlah'))['t'] or Decimal('0')

            sp_service_cogs = Decimal('0')
            for sp in sp_qs:
                sp_service_cogs += sp.jumlah * sp.harga_satuan

            # Top 5 sparepart paling sering dipakai di service dari gudang ini
            sp_service_top = sp_qs.values(
                'produk__nama', 'produk__sku'
            ).annotate(
                total_qty=Sum('jumlah'),
                total_used=Count('id')
            ).order_by('-total_qty')[:5]

            context['sp_service_total'] = sp_service_total
            context['sp_service_qty'] = int(sp_service_qty)
            context['sp_service_cogs'] = sp_service_cogs
            context['sp_service_top'] = sp_service_top

        except Exception:
            context['sc_total_order'] = 0
            context['sc_order_selesai'] = 0
            context['sc_order_dibatalkan'] = 0
            context['sc_revenue'] = Decimal('0')
            context['sc_rata_biaya'] = 0
            context['sc_status_dist'] = {}
            context['sc_top_perangkat'] = []
            context['sc_top_teknisi'] = []
            context['sp_service_total'] = 0
            context['sp_service_qty'] = 0
            context['sp_service_cogs'] = Decimal('0')
            context['sp_service_top'] = []

        # ════════════════════════════════════════════════════════
        # 7. KARYAWAN & ABSENSI PER CABANG
        # ════════════════════════════════════════════════════════
        try:
            from apps.hr.models import Karyawan as KaryawanModel, Absensi as AbsensiModel

            # Karyawan yang terdaftar di cabang ini
            karyawan_cabang_qs = KaryawanModel.objects.filter(
                cabang_id=cabang_id, aktif=True
            ).select_related('jabatan', 'departemen', 'cabang').order_by('nama')

            total_karyawan_cabang = karyawan_cabang_qs.count()

            # Absensi hari ini di cabang ini
            from django.utils import timezone
            today = timezone.now().date()

            absensi_hari_ini = AbsensiModel.objects.filter(
                cabang_id=cabang_id, tanggal=today
            )
            karyawan_hadir = absensi_hari_ini.filter(
                status__in=['hadir', 'terlambat']
            ).count()
            karyawan_terlambat = absensi_hari_ini.filter(
                status='terlambat'
            ).count()

            # Tingkat kehadiran (%) — berdasarkan periode filter
            absensi_filter = {'cabang_id': cabang_id}
            if filter_start:
                absensi_filter['tanggal__gte'] = filter_start
            if filter_end:
                absensi_filter['tanggal__lte'] = filter_end

            absensi_periode = AbsensiModel.objects.filter(**absensi_filter)
            total_absensi_record = absensi_periode.count()
            total_hadir_record = absensi_periode.filter(
                status__in=['hadir', 'terlambat']
            ).count()

            tingkat_kehadiran = 0
            if total_absensi_record > 0:
                tingkat_kehadiran = round((total_hadir_record / total_absensi_record) * 100, 1)

            # Absensi list untuk tabel (dengan filter tanggal)
            absensi_list_cabang = absensi_periode.select_related(
                'karyawan', 'karyawan__jabatan', 'karyawan__departemen'
            ).order_by('-tanggal', '-jam_masuk')[:100]

            context['karyawan_list_cabang'] = karyawan_cabang_qs
            context['total_karyawan_cabang'] = total_karyawan_cabang
            context['karyawan_hadir_hari_ini'] = karyawan_hadir
            context['karyawan_terlambat_hari_ini'] = karyawan_terlambat
            context['tingkat_kehadiran'] = tingkat_kehadiran
            context['absensi_list_cabang'] = absensi_list_cabang
            context['total_absensi_record'] = total_absensi_record

        except Exception:
            context['karyawan_list_cabang'] = []
            context['total_karyawan_cabang'] = 0
            context['karyawan_hadir_hari_ini'] = 0
            context['karyawan_terlambat_hari_ini'] = 0
            context['tingkat_kehadiran'] = 0
            context['absensi_list_cabang'] = []
            context['total_absensi_record'] = 0

        # Template cetak untuk export
        from apps.pengaturan.models import TemplateCetak
        try:
            context['export_pdf_template'] = TemplateCetak.objects.first()
        except Exception:
            context['export_pdf_template'] = None

        return context

