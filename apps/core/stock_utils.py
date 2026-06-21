"""
==========================================================================
 CORE STOCK UTILITIES - Fungsi Utility Bersama untuk Operasi Stok
==========================================================================
 File ini berisi fungsi-fungsi utility yang digunakan BERSAMA oleh banyak
 modul (POS, Penjualan, Pembelian, Inventory) untuk menghindari duplikasi
 kode (DRY - Don't Repeat Yourself).

 FUNGSI:
   update_cabang_ke_stok_terbanyak() -> Update cabang produk ke gudang
                                        dengan stok terbanyak
   rollback_stok_items()             -> Kembalikan stok ke gudang saat
                                        transaksi dihapus/dibatalkan
   get_gudang_context_data()         -> Bangun data gudang + pajak untuk
                                        context template
   DEFAULT_MARKUP_FACTOR             -> Konstanta markup default 20%

 DIPAKAI OLEH:
   - apps/pos/views.py
   - apps/penjualan/views.py
   - apps/pembelian/views.py
   - apps/inventory/views.py
   - apps/inventory/models.py
   - apps/penjualan/models.py
   - apps/pembelian/models.py
   - apps/pos/services.py
   - apps/penjualan/services.py
   - apps/pembelian/services.py
==========================================================================
"""

import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

# =====================================================================
# KONSTANTA BISNIS
# =====================================================================
# Markup default 20% dari harga beli untuk harga jual (saat auto-create produk)
DEFAULT_MARKUP_FACTOR = Decimal('1.2')

# Ambang batas rating produk berdasarkan persentil penjualan (qty terjual)
RATING_THRESHOLDS = [
    (Decimal('0.8'), 5),   # Top 20% produk terlaris -> 5 bintang
    (Decimal('0.6'), 4),   # 60-80%                 -> 4 bintang
    (Decimal('0.4'), 3),   # 40-60%                 -> 3 bintang
    (Decimal('0.2'), 2),   # 20-40%                 -> 2 bintang
    (Decimal('0.0'), 1),   # Bottom 20%             -> 1 bintang
]


# =====================================================================
# UPDATE CABANG KE STOK TERBANYAK
# =====================================================================
def update_cabang_ke_stok_terbanyak(produk):
    """
    Update cabang produk ke gudang yang memiliki stok terbanyak.

    Dipanggil setelah stok berubah (penjualan, pembelian, transfer,
    adjustment, penghapusan transaksi, dll). Fungsi ini memastikan
    field `produk.cabang` selalu menunjuk ke gudang dengan stok
    tertinggi agar data konsisten.

    Parameters:
        produk: Produk instance (harus sudah tersimpan di DB)

    Returns:
        bool -- True jika cabang diperbarui, False jika tidak berubah

    Contoh penggunaan:
        from apps.core.stock_utils import update_cabang_ke_stok_terbanyak
        update_cabang_ke_stok_terbanyak(produk)
    """
    from apps.produk.models import Stok

    stok_terbanyak = Stok.objects.filter(
        produk=produk, jumlah__gt=0
    ).order_by('-jumlah').first()

    if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
        produk.cabang = stok_terbanyak.gudang
        produk.save(update_fields=['cabang'])
        logger.debug(
            "Cabang produk %s diperbarui ke gudang %s (stok: %s)",
            produk.nama, stok_terbanyak.gudang.nama, stok_terbanyak.jumlah
        )
        return True
    return False


# =====================================================================
# ROLLBACK STOK ITEMS
# =====================================================================
def rollback_stok_items(items_queryset, gudang):
    """
    Kembalikan stok ke gudang saat transaksi dihapus atau dibatalkan.

    Iterasi semua item dalam queryset, tambahkan kembali qty ke stok
    di gudang yang sesuai. Menggunakan select_for_update() untuk
    mencegah race condition.

    Parameters:
        items_queryset: QuerySet of item (harus punya field `produk`
                        dan `jumlah` atau `jumlah_konversi`)
        gudang: Gudang instance tempat stok dikembalikan

    Returns:
        int -- Jumlah item yang di-rollback

    Contoh penggunaan:
        from apps.core.stock_utils import rollback_stok_items
        rollback_stok_items(sales_order.items.all(), sales_order.gudang)
    """
    from apps.produk.models import Stok

    rollback_count = 0
    for item in items_queryset.select_related('produk'):
        qty_rollback = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
        stok, _ = Stok.objects.select_for_update().get_or_create(
            produk=item.produk,
            gudang=gudang,
            defaults={'jumlah': 0}
        )
        stok.jumlah += qty_rollback
        stok.save()

        # Update cabang produk ke gudang dengan stok terbanyak
        update_cabang_ke_stok_terbanyak(item.produk)
        rollback_count += 1

    logger.info(
        "Rollback stok: %d item dikembalikan ke gudang %s",
        rollback_count, gudang.nama
    )
    return rollback_count


# =====================================================================
# GUDANG CONTEXT DATA (untuk template)
# =====================================================================
def get_gudang_context_data():
    """
    Bangun list data gudang aktif beserta tarif pajak untuk context template.

    Digunakan di berbagai view (POS, Penjualan, Pembelian) yang perlu
    mengirim data gudang + pajak ke frontend untuk kalkulasi JavaScript.

    Returns:
        list[dict] -- List berisi dict dengan keys:
            - id: int
            - nama: str
            - kode: str
            - pajak_persen: float (tarif PPN efektif)

    Contoh penggunaan:
        from apps.core.stock_utils import get_gudang_context_data
        context['gudang_list'] = get_gudang_context_data()
    """
    from apps.produk.models import Gudang

    gudang_list = []
    for g in Gudang.objects.filter(aktif=True):
        gudang_list.append({
            'id': g.id,
            'nama': g.nama,
            'kode': g.kode,
            'pajak_persen': float(g.get_tarif_ppn()),
        })
    return gudang_list


# =====================================================================
# HITUNG RATING DARI RASIO
# =====================================================================
def hitung_rating_dari_rasio(rasio):
    """
    Mapping rasio penjualan ke rating bintang 1-5 berdasarkan persentil.

    Parameters:
        rasio: Decimal atau float -- rasio qty produk terhadap qty produk terlaris
               (0.0 sampai 1.0)

    Returns:
        int -- Rating 1-5

    Contoh:
        hitung_rating_dari_rasio(0.85)  -> 5  (top 20%)
        hitung_rating_dari_rasio(0.50)  -> 3  (40-60%)
        hitung_rating_dari_rasio(0.05)  -> 1  (bottom 20%)
    """
    rasio = Decimal(str(rasio))
    for threshold, rating in RATING_THRESHOLDS:
        if rasio >= threshold:
            return rating
    return 1
