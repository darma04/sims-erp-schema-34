"""
==========================================================================
 PENJUALAN SIGNALS - Auto-Jurnal & Piutang untuk Sales Order
==========================================================================
 Signal ini membuat jurnal otomatis dan piutang saat Sales Order dikonfirmasi.
 
 Jurnal yang dibuat tergantung metode pembayaran:
 
 CASH:
 D: Kas/Bank (1-1000 atau sesuai metode)    Rp total
    K: Pendapatan Penjualan (4-1000)            Rp subtotal
    K: PPN Keluaran (2-2000)                    Rp pajak (jika ada)
 
 CREDIT:
 D: Piutang Usaha (1-2000)                   Rp total
    K: Pendapatan Penjualan (4-1000)            Rp subtotal
    K: PPN Keluaran (2-2000)                    Rp pajak (jika ada)
 
 Operasional ERP ini mengakui piutang/jurnal saat SO confirmed karena stok sudah keluar
 dari gudang dan kewajiban customer sudah terbentuk.
==========================================================================
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def ensure_so_faktur_pajak(instance, subtotal=None, diskon=None, pajak=None, biaya_pengiriman=None):
    subtotal = subtotal if subtotal is not None else (instance.subtotal or Decimal('0'))
    diskon = diskon if diskon is not None else (instance.diskon or Decimal('0'))
    pajak = pajak if pajak is not None else (instance.pajak or Decimal('0'))
    biaya_pengiriman = biaya_pengiriman if biaya_pengiriman is not None else (instance.biaya_pengiriman or Decimal('0'))
    dpp_pajak = subtotal - diskon + biaya_pengiriman
    if pajak <= 0 or dpp_pajak <= 0:
        return None

    from apps.pajak.models import FakturPajak, SettingPajak

    if FakturPajak.objects.filter(sales_order=instance, tipe='keluaran').exists():
        return None

    setting = SettingPajak.get_setting()
    tarif = (pajak / dpp_pajak * Decimal('100')) if dpp_pajak else setting.tarif_ppn
    return FakturPajak.objects.create(
        nomor_seri=f'AUTO-SO-{instance.pk}',
        tipe='keluaran',
        tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
        dpp=dpp_pajak,
        tarif_ppn=tarif,
        nama_lawan=instance.customer.nama if instance.customer_id else 'Customer',
        npwp_lawan='',
        sales_order=instance,
        status='approved',
        keterangan=f'Auto Faktur PPN Keluaran dari SO {instance.nomor_so}',
        created_by=instance.dibuat_oleh,
    )


def ensure_so_piutang(instance, total=None):
    """Pastikan SO kredit memiliki record Piutang. Idempotent."""
    from apps.kas_bank.services import metode_is_credit

    is_credit = instance.metode_pembayaran is None or metode_is_credit(instance.metode_pembayaran)
    if not is_credit:
        return None

    total = total if total is not None else (instance.total_harga or Decimal('0'))
    if total <= 0:
        return None

    from apps.piutang.models import Piutang
    from datetime import timedelta

    tanggal_so = instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal
    if hasattr(tanggal_so, 'date'):
        tanggal_so = tanggal_so.date()

    tanggal_jatuh_tempo = tanggal_so + timedelta(days=30)

    piutang, _ = Piutang.objects.get_or_create(
        sumber='so',
        sales_order=instance,
        defaults={
            'customer': instance.customer,
            'sumber_ref': instance.nomor_so,
            'tanggal': tanggal_so,
            'jatuh_tempo': tanggal_jatuh_tempo,
            'jumlah_total': total,
            'jumlah_dibayar': Decimal('0'),
            'status': 'belum_bayar',
            'cabang': instance.gudang,
            'keterangan': f'Piutang dari SO {instance.nomor_so}',
            'jurnal_pembayaran': None,
            'created_by': instance.dibuat_oleh
        }
    )
    return piutang


@receiver(post_save, sender='penjualan.SalesOrder')
def create_so_journal_and_piutang(sender, instance, created, **kwargs):
    """
    Auto-create jurnal dan piutang saat SO confirmed/delivered/completed.
    
    Jika payment_method = cash:
    D: Kas (1-1000)                    Rp total
       K: Pendapatan Penjualan (4-1000)    Rp subtotal
       K: PPN Keluaran (2-2000)            Rp pajak
    
    Jika payment_method = credit:
    D: Piutang Usaha (1-2000)          Rp total
       K: Pendapatan Penjualan (4-1000)    Rp subtotal
       K: PPN Keluaran (2-2000)            Rp pajak
    
    Trigger: post_save SalesOrder
    Kondisi: status = 'confirmed', 'delivered', atau 'completed' dan belum ada jurnal
    """
    if kwargs.get('raw'):
        return

    # Proses sejak SO confirmed; delivered/completed tetap didukung untuk data lama.
    if instance.status not in ('confirmed', 'delivered', 'completed'):
        return
    
    subtotal = instance.subtotal or Decimal('0')
    pajak = instance.pajak or Decimal('0')
    diskon = instance.diskon or Decimal('0')
    biaya_pengiriman = instance.biaya_pengiriman or Decimal('0')
    total = instance.total_harga or Decimal('0')

    # Cek apakah sudah ada jurnal untuk SO ini
    from apps.akuntansi.models import JurnalEntry
    existing = JurnalEntry.objects.filter(
        sumber='so',
        sumber_id=instance.pk
    ).exists()
    
    if existing:
        ensure_so_faktur_pajak(instance, subtotal, diskon, pajak, biaya_pengiriman)
        ensure_so_piutang(instance, total)
        return
    
    hpp_total = sum(
        (item.hpp_subtotal or (
            (item.produk.harga_beli or Decimal('0')) *
            (item.jumlah_konversi or item.jumlah or Decimal('0'))
        ))
        for item in instance.items.select_related('produk')
    )
    
    # Validasi: total harus > 0
    if total <= 0:
        logger.warning(f"[SO] Skip auto-jurnal untuk {instance.nomor_so}: total = {total}")
        return
    
    from apps.kas_bank.services import create_operational_mutation, metode_is_credit, resolve_kas_bank_mapping
    is_credit = instance.metode_pembayaran is None or metode_is_credit(instance.metode_pembayaran)
    kas_bank_account, _, kas_bank_akun_kode = resolve_kas_bank_mapping(instance.metode_pembayaran)
    akun_debit = '1-2000' if is_credit else kas_bank_akun_kode
    desc_debit = 'Piutang dari penjualan' if is_credit else 'Penerimaan kas dari penjualan'

    # Build lines data
    # Pendapatan dicatat sebesar subtotal (sebelum diskon)
    # Diskon dicatat terpisah sebagai contra-pendapatan (akun 4-1002)
    lines_data = [
        {
            'akun_kode': akun_debit,
            'debit': total,
            'kredit': Decimal('0'),
            'keterangan': f'{desc_debit} SO {instance.nomor_so}'
        },
        {
            'akun_kode': '4-1000',  # Pendapatan Penjualan
            'debit': Decimal('0'),
            'kredit': subtotal,
            'keterangan': f'Pendapatan penjualan SO {instance.nomor_so}'
        }
    ]

    # Ongkir penjualan menambah tagihan customer dan dicatat sebagai pendapatan lain.
    if biaya_pengiriman > 0:
        from apps.akuntansi.services import get_akun_by_kode
        akun_ongkir = '4-3000' if get_akun_by_kode('4-3000') else '4-1000'
        lines_data.append({
            'akun_kode': akun_ongkir,
            'debit': Decimal('0'),
            'kredit': biaya_pengiriman,
            'keterangan': f'Pendapatan ongkir SO {instance.nomor_so}'
        })

    # Tambah Diskon Penjualan jika ada (contra-pendapatan)
    if diskon > 0:
        lines_data.append({
            'akun_kode': '4-1002',  # Diskon Penjualan (contra pendapatan)
            'debit': diskon,
            'kredit': Decimal('0'),
            'keterangan': f'Diskon penjualan SO {instance.nomor_so}'
        })
    
    # Tambah PPN jika ada
    if pajak > 0:
        lines_data.append({
            'akun_kode': '2-2000',  # PPN Keluaran
            'debit': Decimal('0'),
            'kredit': pajak,
            'keterangan': f'PPN Keluaran SO {instance.nomor_so}'
        })

    if hpp_total > 0:
        lines_data.extend([
            {
                'akun_kode': '5-1000',
                'debit': hpp_total,
                'kredit': Decimal('0'),
                'keterangan': f'HPP penjualan SO {instance.nomor_so}'
            },
            {
                'akun_kode': '1-3000',
                'debit': Decimal('0'),
                'kredit': hpp_total,
                'keterangan': f'Pengurangan persediaan SO {instance.nomor_so}'
            },
        ])
    
    # Create jurnal
    try:
        from apps.akuntansi.services import create_jurnal
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            jurnal = create_jurnal(
                tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
                deskripsi=f'Penjualan - {instance.nomor_so}',
                lines_data=lines_data,
                sumber='so',
                sumber_id=instance.pk,
                sumber_ref=instance.nomor_so,
                cabang=instance.gudang,
                user=instance.dibuat_oleh,
                auto_post=True,
            )
            if not is_credit:
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe='masuk',
                    tanggal=instance.tanggal,
                    jumlah=total,
                    deskripsi=f'Penerimaan Sales Order {instance.nomor_so}',
                    akun_lawan=None,
                    cabang=instance.gudang,
                    metode_pembayaran=instance.metode_pembayaran,
                    sumber_app='penjualan',
                    sumber_model='SalesOrder',
                    sumber_id=instance.pk,
                    sumber_ref=instance.nomor_so,
                    jurnal_entry=jurnal,
                    user=instance.dibuat_oleh,
                )
            
            # Jika credit, buat piutang
            if is_credit:
                ensure_so_piutang(instance, total)
                logger.info(f'[SO] Auto-piutang created for {instance.nomor_so}')

            ensure_so_faktur_pajak(instance, subtotal, diskon, pajak, biaya_pengiriman)
        
        logger.info(f'[SO] Auto-jurnal created for {instance.nomor_so}: {jurnal.nomor}')
        
    except Exception as e:
        logger.error(f'[SO] Failed to create auto-jurnal for {instance.nomor_so}: {e}', exc_info=True)
        # Catat kegagalan ke activity log agar terdeteksi di Rekonsiliasi Keuangan
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action='create',
                model_name='JurnalEntry',
                object_id=str(instance.pk),
                object_repr=f'GAGAL: Jurnal SO {instance.nomor_so}',
                description=f'[JURNAL GAGAL] Auto-jurnal untuk SO {instance.nomor_so} gagal dibuat. '
                            f'Error: {str(e)[:200]}. Transaksi tetap berstatus {instance.status} tapi TIDAK memiliki jurnal. '
                            f'Perbaiki via Rekonsiliasi Keuangan.',
                source_type='sales',
                source_id=str(instance.pk),
                source_repr=instance.nomor_so,
            )
        except Exception:
            pass
        raise


@receiver(post_delete, sender='penjualan.SalesOrderItem')
def recalculate_so_on_item_delete(sender, instance, **kwargs):
    """Recalculate parent SO totals when item is deleted."""
    if instance.sales_order_id:
        try:
            so = instance.sales_order
            so.calculate_total()
            so.save()
        except Exception:
            pass  # SO might already be deleted (CASCADE)
