"""
==========================================================================
 INVENTORY SERVICES - Integrasi Akuntansi untuk Adjustment Stok
==========================================================================
 Fungsi ini membuat jurnal otomatis saat AdjustmentStok disimpan:
 - Tipe 'out' (barang rusak/hilang): D:Beban Kerusakan(6-5000) K:Persediaan(1-3000)
 - Tipe 'in' (barang ditemukan): D:Persediaan(1-3000) K:Pendapatan Lainnya(4-3000)

 Nilai dihitung dari: produk.harga_beli * jumlah (atau field nilai jika ada)
 Idempotent: skip jika jurnal sudah ada (sumber='inventori', sumber_id=adjustment.pk)
==========================================================================
"""

from decimal import Decimal
from django.db import transaction

from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_jurnal


def ensure_adjustment_accounting(adjustment, user=None):
    """
    Pastikan AdjustmentStok memiliki jurnal akuntansi.
    Idempotent: jika jurnal sudah ada, tidak membuat duplikat.

    Parameters:
        adjustment: AdjustmentStok instance
        user: User yang melakukan operasi (default: adjustment.dibuat_oleh)

    Returns:
        JurnalEntry atau None jika skip

    Jurnal:
    - Tipe 'out': D:6-5000 Beban Kerusakan/Kehilangan  K:1-3000 Persediaan
    - Tipe 'in':  D:1-3000 Persediaan  K:4-3000 Pendapatan Lainnya
    """
    # Idempotent check — skip jika jurnal sudah pernah dibuat
    if JurnalEntry.objects.filter(sumber='inventori', sumber_id=adjustment.pk).exists():
        return None

    # Hitung nilai barang
    # Gunakan field 'nilai' jika ada di model, else harga_beli * jumlah
    nilai = getattr(adjustment, 'nilai', None)
    if not nilai or nilai <= 0:
        harga_beli = adjustment.produk.harga_beli or Decimal('0')
        nilai = harga_beli * adjustment.jumlah

    if nilai <= 0:
        return None  # Tidak bisa buat jurnal dengan nominal 0

    user = user or adjustment.dibuat_oleh
    tanggal = adjustment.tanggal.date() if hasattr(adjustment.tanggal, 'date') else adjustment.tanggal

    with transaction.atomic():
        if adjustment.tipe == 'out':
            # Barang rusak/hilang: D:Beban Kerusakan K:Persediaan
            lines_data = [
                {
                    'akun_kode': '6-5000',  # Beban Kerusakan/Kehilangan
                    'debit': nilai,
                    'kredit': Decimal('0'),
                    'keterangan': f'Adjustment stok keluar: {adjustment.produk.nama} - {adjustment.alasan}',
                },
                {
                    'akun_kode': '1-3000',  # Persediaan Barang
                    'debit': Decimal('0'),
                    'kredit': nilai,
                    'keterangan': f'Pengurangan persediaan: {adjustment.produk.nama}',
                },
            ]
            deskripsi = f'Adjustment Stok Keluar - {adjustment.nomor_adjustment}'
        else:
            # Barang ditemukan/koreksi tambah: D:Persediaan K:Pendapatan Lainnya
            lines_data = [
                {
                    'akun_kode': '1-3000',  # Persediaan Barang
                    'debit': nilai,
                    'kredit': Decimal('0'),
                    'keterangan': f'Penambahan persediaan: {adjustment.produk.nama}',
                },
                {
                    'akun_kode': '4-3000',  # Pendapatan Lainnya
                    'debit': Decimal('0'),
                    'kredit': nilai,
                    'keterangan': f'Adjustment stok masuk: {adjustment.produk.nama} - {adjustment.alasan}',
                },
            ]
            deskripsi = f'Adjustment Stok Masuk - {adjustment.nomor_adjustment}'

        jurnal = create_jurnal(
            tanggal=tanggal,
            deskripsi=deskripsi,
            lines_data=lines_data,
            sumber='inventori',
            sumber_id=adjustment.pk,
            sumber_ref=adjustment.nomor_adjustment,
            cabang=adjustment.gudang,
            user=user,
            auto_post=True,
        )

    return jurnal
