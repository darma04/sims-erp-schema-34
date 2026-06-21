"""
==========================================================================
 POS SIGNALS - Auto-Jurnal untuk Transaksi POS
==========================================================================
 Signal ini membuat jurnal otomatis saat transaksi POS selesai (status='paid').
 
 Jurnal yang dibuat:
 D: Kas/Bank (1-1000 atau sesuai metode pembayaran)    Rp total
    K: Pendapatan Penjualan (4-1000)                    Rp subtotal
    K: PPN Keluaran (2-2000)                            Rp pajak (jika ada)
 
 PSAK 23: Pendapatan diakui saat barang diserahkan dan pembayaran diterima.
==========================================================================
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)


def ensure_pos_faktur_pajak(instance, subtotal=None, diskon=None, pajak=None):
    subtotal = subtotal if subtotal is not None else (instance.subtotal or Decimal('0'))
    diskon = diskon if diskon is not None else (instance.diskon or Decimal('0'))
    pajak = pajak if pajak is not None else (instance.pajak or Decimal('0'))
    dpp_pajak = subtotal - diskon
    if pajak <= 0 or dpp_pajak <= 0:
        return None

    from apps.pajak.models import FakturPajak, SettingPajak

    if FakturPajak.objects.filter(pos_transaction=instance, tipe='keluaran').exists():
        return None

    setting = SettingPajak.get_setting()
    tarif = (pajak / dpp_pajak * Decimal('100')) if dpp_pajak else setting.tarif_ppn
    nama_lawan = (
        instance.customer.nama
        if instance.customer_id
        else (instance.nama_customer or 'Customer POS')
    )
    return FakturPajak.objects.create(
        nomor_seri=f'AUTO-POS-{instance.pk}',
        tipe='keluaran',
        tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
        dpp=dpp_pajak,
        tarif_ppn=tarif,
        nama_lawan=nama_lawan,
        npwp_lawan='',
        pos_transaction=instance,
        status='approved',
        keterangan=f'Auto Faktur PPN Keluaran dari POS {instance.nomor_transaksi}',
        created_by=instance.kasir,
    )


@receiver(post_save, sender='pos.POSTransaction')
def create_pos_journal(sender, instance, created, **kwargs):
    """
    Auto-create jurnal saat POS transaction status = 'paid'.
    
    Jurnal:
    D: Kas/Bank (1-1000)                Rp total
       K: Pendapatan Penjualan (4-1000)     Rp subtotal
       K: PPN Keluaran (2-2000)             Rp pajak
    
    Trigger: post_save POSTransaction
    Kondisi: status = 'paid' dan belum ada jurnal
    """
    if kwargs.get('raw'):
        return

    # ── Handle POS Kasbon (unpaid) — buat jurnal piutang ──
    if instance.status == 'unpaid':
        try:
            from apps.pos.services import ensure_pos_kasbon_accounting
            ensure_pos_kasbon_accounting(instance, user=instance.kasir)
        except IntegrityError as exc:
            logger.warning(
                f'[POS] Duplicate jurnal kasbon untuk {instance.nomor_transaksi}: {exc}',
            )
        except Exception as exc:
            logger.error(
                f'[POS] Failed to create kasbon accounting for {instance.nomor_transaksi}: {exc}',
                exc_info=True,
            )
            try:
                from apps.activity_log.models import UserActivity
                UserActivity.objects.create(
                    user=instance.kasir,
                    action='create',
                    model_name='JurnalEntry',
                    object_id=str(instance.pk),
                    object_repr=f'GAGAL: Jurnal POS Kasbon {instance.nomor_transaksi}',
                    description=f'[JURNAL GAGAL] Auto-jurnal untuk POS kasbon {instance.nomor_transaksi} gagal. '
                                f'Error: {str(exc)[:200]}.',
                    source_type='pos',
                    source_id=str(instance.pk),
                    source_repr=instance.nomor_transaksi,
            )
            except Exception as e:
                logger.warning("Gagal mencatat activity log: %s", e)
            # raise  # Disabled: transaksi tetap tersimpan meskipun jurnal gagal
        return  # Don't continue to paid handling

    # Hanya buat jurnal jika status = paid
    if instance.status != 'paid':
        return
    
    subtotal = instance.subtotal or Decimal('0')
    pajak = instance.pajak or Decimal('0')
    diskon = instance.diskon or Decimal('0')

    # ── FIX BUG-02: wrap duplicate check + creation in atomic + select_for_update ──
    from apps.akuntansi.models import JurnalEntry
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        # Lock to prevent concurrent duplicate journal creation
        existing = JurnalEntry.objects.select_for_update().filter(
            sumber='pos',
            sumber_id=instance.pk
        ).exists()

        if existing:
            ensure_pos_faktur_pajak(instance, subtotal, diskon, pajak)
            return

        # Hitung total
        total = instance.total_harga or Decimal('0')
        hpp_total = sum(
            (item.hpp_subtotal or (
                (item.produk.harga_beli or Decimal('0')) *
                (item.jumlah_konversi or item.jumlah or Decimal('0'))
            ))
            for item in instance.items.select_related('produk')
        )

        # Validasi: total harus > 0
        if total <= 0:
            logger.warning(f"[POS] Skip auto-jurnal untuk {instance.nomor_transaksi}: total = {total}")
            return

        from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping
        kas_bank_account, _, akun_kas = resolve_kas_bank_mapping(instance.metode_pembayaran)

        # Build lines data
        # ══════════════════════════════════════════════════════════════
        # TREATMENT DISKON POS (CONTRA-PENDAPATAN)
        # ══════════════════════════════════════════════════════════════
        # Pendapatan dicatat sebesar subtotal (sebelum diskon) pada akun 4-1000.
        # Diskon dicatat terpisah sebagai contra-pendapatan (akun 4-1002, saldo_normal=debit)
        # yang MENGURANGI total pendapatan di laporan Laba Rugi.
        #
        # Alasan desain (sesuai PSAK 23):
        # - Pendapatan bruto tetap tercatat penuh untuk audit trail
        # - Diskon sebagai contra-pendapatan (bukan beban) agar margin kotor
        #   mencerminkan efek diskon secara langsung
        # - Di Laba Rugi: Pendapatan Bruto - Diskon = Pendapatan Bersih
        #
        # Total kas yang diterima = subtotal - diskon + pajak
        # ══════════════════════════════════════════════════════════════
        lines_data = [
            {
                'akun_kode': akun_kas,
                'debit': total,
                'kredit': Decimal('0'),
                'keterangan': f'Penerimaan kas dari POS {instance.nomor_transaksi}'
            },
            {
                'akun_kode': '4-1000',
                'debit': Decimal('0'),
                'kredit': subtotal,
                'keterangan': f'Pendapatan penjualan POS {instance.nomor_transaksi}'
            }
        ]

        if diskon > 0:
            lines_data.append({
                'akun_kode': '4-1002',
                'debit': diskon,
                'kredit': Decimal('0'),
                'keterangan': f'Diskon penjualan POS {instance.nomor_transaksi}'
            })

        if pajak > 0:
            lines_data.append({
                'akun_kode': '2-2000',
                'debit': Decimal('0'),
                'kredit': pajak,
                'keterangan': f'PPN Keluaran POS {instance.nomor_transaksi}'
            })

        if hpp_total > 0:
            lines_data.extend([
                {
                    'akun_kode': '5-1000',
                    'debit': hpp_total,
                    'kredit': Decimal('0'),
                    'keterangan': f'HPP penjualan POS {instance.nomor_transaksi}'
                },
                {
                    'akun_kode': '1-3000',
                    'debit': Decimal('0'),
                    'kredit': hpp_total,
                    'keterangan': f'Pengurangan persediaan POS {instance.nomor_transaksi}'
                },
            ])

        # Create jurnal
        try:
            from apps.akuntansi.services import create_jurnal

            jurnal = create_jurnal(
                tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
                deskripsi=f'Penjualan POS - {instance.nomor_transaksi}',
                lines_data=lines_data,
                sumber='pos',
                sumber_id=instance.pk,
                sumber_ref=instance.nomor_transaksi,
                cabang=instance.gudang,
                user=instance.kasir,
                auto_post=True,
            )
            create_operational_mutation(
                akun_kas_bank=kas_bank_account,
                tipe='masuk',
                tanggal=instance.tanggal,
                jumlah=total,
                deskripsi=f'Penerimaan POS {instance.nomor_transaksi}',
                akun_lawan=None,
                cabang=instance.gudang,
                metode_pembayaran=instance.metode_pembayaran,
                sumber_app='pos',
                sumber_model='POSTransaction',
                sumber_id=instance.pk,
                sumber_ref=instance.nomor_transaksi,
                jurnal_entry=jurnal,
                user=instance.kasir,
            )

            ensure_pos_faktur_pajak(instance, subtotal, diskon, pajak)

            logger.info(f'[POS] Auto-jurnal created for {instance.nomor_transaksi}: {jurnal.nomor}')

        except IntegrityError as e:
            logger.warning(f"[POS] Duplicate jurnal untuk {instance.nomor_transaksi}: {e}")
        except Exception as e:
            logger.error(f'[POS] Failed to create auto-jurnal for {instance.nomor_transaksi}: {e}', exc_info=True)
            try:
                from apps.activity_log.models import UserActivity
                UserActivity.objects.create(
                    user=instance.kasir,
                    action='create',
                    model_name='JurnalEntry',
                    object_id=str(instance.pk),
                    object_repr=f'GAGAL: Jurnal POS {instance.nomor_transaksi}',
                    description=f'[JURNAL GAGAL] Auto-jurnal untuk POS {instance.nomor_transaksi} gagal dibuat. '
                                f'Error: {str(e)[:200]}. Transaksi tetap berstatus paid tapi TIDAK memiliki jurnal. '
                                f'Perbaiki via Rekonsiliasi Keuangan.',
                    source_type='pos',
                    source_id=str(instance.pk),
                    source_repr=instance.nomor_transaksi,
                )
            except Exception as e:
                logger.warning("Gagal mencatat activity log: %s", e)
            # raise  # Disabled: transaksi tetap tersimpan meskipun jurnal gagal


@receiver(post_delete, sender='pos.POSTransactionItem')
def recalculate_pos_on_item_delete(sender, instance, **kwargs):
    """Recalculate parent POS transaction totals when item is deleted."""
    if instance.transaction_id:
        try:
            pos = instance.transaction
            pos.calculate_total()
            pos.save()
        except Exception:
            pass  # POS might already be deleted (CASCADE)
