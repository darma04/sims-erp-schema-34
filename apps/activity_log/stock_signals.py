"""
==========================================================================
 STOCK SIGNALS - Tracking Detail Perubahan Stok
==========================================================================
 File ini berisi fungsi-fungsi khusus untuk mencatat perubahan stok
 dengan detail LENGKAP (quantity before/after, sumber, gudang, dll).

 Berbeda dengan signals.py yang auto-log semua model secara generik,
 file ini KHUSUS untuk tracking stok dengan informasi yang lebih kaya.

 Fungsi-fungsi yang tersedia:
 ┌──────────────────────────┬────────────────────────────────────────┐
 │ Fungsi                   │ Dipanggil dari mana?                  │
 ├──────────────────────────┼────────────────────────────────────────┤
 │ log_stock_change()       │ Fungsi utama (dipanggil oleh semua)   │
 │ log_purchase_stock_in()  │ pembelian/views.py saat PO diterima   │
 │ log_sales_stock_out()    │ penjualan/views.py saat SO dikonfirmasi│
 │ log_adjustment_stock()   │ inventory/views.py saat adjustment    │
 │ log_transfer_stock()     │ inventory/views.py saat transfer      │
 │ log_pos_stock_out()      │ pos/views.py saat transaksi POS       │
 └──────────────────────────┴────────────────────────────────────────┘

 Data yang dicatat per perubahan stok:
 - Produk dan gudang yang terpengaruh
 - Quantity sebelum dan sesudah (quantity_before, quantity_after)
 - Selisih perubahan (quantity_change)
 - Sumber perubahan (PO, SO, POS, transfer, adjustment)
 - Nomor referensi sumber (nomor_po, nomor_so, dll)
 - User yang melakukan aksi dan IP address

 Terhubung dengan:
 - models.py → UserActivity (target penyimpanan)
 - pembelian/views.py, penjualan/views.py, pos/views.py, inventory/views.py
==========================================================================
"""

# Import dari modul internal proyek
from apps.activity_log.models import UserActivity
from decimal import Decimal


def get_client_ip(request):
    """Mendapatkan IP address client dari HTTP request"""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


# Fungsi log_stock_change
def log_stock_change(
    user,
    produk,
    gudang,
    action,
    source_type,
    source_id,
    source_repr,
    quantity_before,
    quantity_after,
    description=None,
    request=None
):
    """
    Log perubahan stok dengan detail lengkap.
    
    Args:
        user: User yang melakukan aksi
        produk: Instance Produk yang stoknya berubah
        gudang: Instance Gudang tempat stok berubah
        action: Jenis aksi (stock_in, stock_out, stock_adjustment, dll)
        source_type: Tipe sumber (purchase, sales, pos, transfer, adjustment, manual)
        source_id: ID/nomor referensi sumber
        source_repr: Representasi string sumber (misal: "PO/2026/02/0001")
        quantity_before: Jumlah stok sebelum perubahan
        quantity_after: Jumlah stok sesudah perubahan
        description: Deskripsi tambahan (optional)
        request: HTTP Request object (optional)
    """
    try:
        quantity_change = Decimal(str(quantity_after)) - Decimal(str(quantity_before))
        
        # Buat deskripsi otomatis jika tidak disediakan
        if not description:
            action_verb = {
                'stock_in': 'masuk',
                'stock_out': 'keluar',
                'stock_adjustment': 'diubah',
                'stock_transfer_in': 'masuk (transfer)',
                'stock_transfer_out': 'keluar (transfer)',
            }.get(action, 'berubah')
            
            description = f"Stok {produk.nama} {action_verb}: {quantity_before} → {quantity_after} ({'+' if quantity_change >= 0 else ''}{quantity_change}) di {gudang.nama}"
            if source_repr:
                description += f" | Ref: {source_repr}"
        
        # Import dari modul internal proyek
        from apps.produk.models import Stok
        # Query database — ambil data stok yang sesuai filter
        stok = Stok.objects.filter(produk=produk, gudang=gudang).first()
        
        UserActivity.objects.create(
            user=user,
            action=action,
            model_name='Stok',
            object_id=str(stok.pk) if stok else None,
            object_repr=f"{produk.nama} - {gudang.nama}",
            description=description,
            source_type=source_type,
            source_id=str(source_id),
            source_repr=source_repr,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            quantity_change=quantity_change,
            gudang_id=str(gudang.pk),
            gudang_name=gudang.nama,
            ip_address=get_client_ip(request) if request else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else None,
        )
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        # Catat error tapi jangan ganggu operasi utama
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error logging stock change: {e}")


def log_purchase_stock_in(po, user, request=None):
    """
    Log stok masuk dari Purchase Order yang diterima.
    Dipanggil setelah PO status berubah ke 'received'.
    
    Args:
        po: PurchaseOrder instance
        user: User yang menerima barang
        request: HTTP request (optional)
    """
    from apps.produk.models import Stok
    
    for item in po.items.all():
        # Get stok setelah update (karena fungsi ini dipanggil setelah stok diupdate)
        stok = Stok.objects.filter(produk=item.produk, gudang=po.gudang).first()
        quantity_after = stok.jumlah if stok else 0
        quantity_before = quantity_after - item.jumlah
        
        log_stock_change(
            user=user,
            produk=item.produk,
            gudang=po.gudang,
            action='stock_in',
            source_type='purchase',
            source_id=po.pk,
            source_repr=po.nomor_po,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            description=f"Pembelian dari {po.supplier.nama}: +{item.jumlah} {item.produk.satuan.singkatan if item.produk.satuan else 'unit'} | {po.nomor_po}",
            request=request,
        )


def log_sales_stock_out(so, user, request=None):
    """
    Log stok keluar dari Sales Order yang dikonfirmasi.
    Dipanggil setelah SO status berubah ke 'confirmed'.
    
    Args:
        so: SalesOrder instance
        user: User yang mengkonfirmasi order
        request: HTTP request (optional)
    """
    from apps.produk.models import Stok
    
    for item in so.items.all():
        # Get stok setelah update (karena fungsi ini dipanggil setelah stok diupdate)
        stok = Stok.objects.filter(produk=item.produk, gudang=so.gudang).first()
        quantity_after = stok.jumlah if stok else 0
        quantity_before = quantity_after + item.jumlah  # Ditambah karena sudah dikurangi
        
        log_stock_change(
            user=user,
            produk=item.produk,
            gudang=so.gudang,
            action='stock_out',
            source_type='sales',
            source_id=so.pk,
            source_repr=so.nomor_so,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            description=f"Penjualan ke {so.customer.nama}: -{item.jumlah} {item.produk.satuan.singkatan if item.produk.satuan else 'unit'} | {so.nomor_so}",
            request=request,
        )


def log_adjustment_stock(adjustment, user, stok_before, request=None):
    """
    Log adjustment stok (penambahan atau pengurangan).
    Dipanggil setelah AdjustmentStok dibuat.
    
    Args:
        adjustment: AdjustmentStok instance
        user: User yang membuat adjustment
        stok_before: Jumlah stok sebelum adjustment
        request: HTTP request (optional)
    """
    from apps.produk.models import Stok
    
    # Query database — ambil data stok yang sesuai filter
    stok = Stok.objects.filter(produk=adjustment.produk, gudang=adjustment.gudang).first()
    quantity_after = stok.jumlah if stok else 0
    
    action_type = 'stock_in' if adjustment.tipe == 'in' else 'stock_out'
    qty_change = adjustment.jumlah if adjustment.tipe == 'in' else -adjustment.jumlah
    
    log_stock_change(
        user=user,
        produk=adjustment.produk,
        gudang=adjustment.gudang,
        action='stock_adjustment',
        source_type='adjustment',
        source_id=adjustment.pk,
        source_repr=adjustment.nomor_adjustment,
        quantity_before=stok_before,
        quantity_after=quantity_after,
        description=f"Adjustment: {'+' if adjustment.tipe == 'in' else '-'}{adjustment.jumlah} | Alasan: {adjustment.alasan[:100]}",
        request=request,
    )


def log_transfer_stock(transfer, user, request=None):
    """
    Log transfer stok antar gudang.
    Dipanggil setelah TransferStok diapprove/complete.
    
    Args:
        transfer: TransferStok instance
        user: User yang approve transfer
        request: HTTP request (optional)
    """
    from apps.produk.models import Stok
    
    for item in transfer.items.all():
        # Log transfer keluar dari gudang asal
        stok_asal = Stok.objects.filter(produk=item.produk, gudang=transfer.gudang_asal).first()
        qty_after_asal = stok_asal.jumlah if stok_asal else 0
        qty_before_asal = qty_after_asal + item.jumlah  # Ditambah karena sudah dikurangi
        
        log_stock_change(
            user=user,
            produk=item.produk,
            gudang=transfer.gudang_asal,
            action='stock_transfer_out',
            source_type='transfer',
            source_id=transfer.pk,
            source_repr=transfer.nomor_transfer,
            quantity_before=qty_before_asal,
            quantity_after=qty_after_asal,
            description=f"Transfer keluar ke {transfer.gudang_tujuan.nama}: -{item.jumlah} | {transfer.nomor_transfer}",
            request=request,
        )
        
        # Log transfer masuk ke gudang tujuan
        stok_tujuan = Stok.objects.filter(produk=item.produk, gudang=transfer.gudang_tujuan).first()
        qty_after_tujuan = stok_tujuan.jumlah if stok_tujuan else 0
        qty_before_tujuan = qty_after_tujuan - item.jumlah  # Dikurangi karena sudah ditambah
        
        log_stock_change(
            user=user,
            produk=item.produk,
            gudang=transfer.gudang_tujuan,
            action='stock_transfer_in',
            source_type='transfer',
            source_id=transfer.pk,
            source_repr=transfer.nomor_transfer,
            quantity_before=qty_before_tujuan,
            quantity_after=qty_after_tujuan,
            description=f"Transfer masuk dari {transfer.gudang_asal.nama}: +{item.jumlah} | {transfer.nomor_transfer}",
            request=request,
        )


def log_pos_stock_out(transaksi, user, request=None):
    """
    Log stok keluar dari transaksi POS.
    
    Args:
        transaksi: TransaksiPOS instance
        user: User kasir
        request: HTTP request (optional)
    """
    from apps.produk.models import Stok
    
    # Asumsikan transaksi memiliki relasi items
    if hasattr(transaksi, 'items'):
        for item in transaksi.items.all():
            # Query database — ambil data stok yang sesuai filter
            stok = Stok.objects.filter(produk=item.produk, gudang=transaksi.gudang).first() if hasattr(transaksi, 'gudang') else None
            
            if stok:
                quantity_after = stok.jumlah
                quantity_before = quantity_after + item.jumlah
                
                log_stock_change(
                    user=user,
                    produk=item.produk,
                    gudang=transaksi.gudang,
                    action='stock_out',
                    source_type='pos',
                    source_id=transaksi.pk,
                    source_repr=getattr(transaksi, 'nomor_transaksi', str(transaksi.pk)),
                    quantity_before=quantity_before,
                    quantity_after=quantity_after,
                    description=f"POS: -{item.jumlah} | {getattr(transaksi, 'nomor_transaksi', '')}",
                    request=request,
                )
