"""
==========================================================================
 PEMBELIAN SIGNALS - Auto-Jurnal & Hutang untuk Purchase Order
==========================================================================
 Signal ini membuat jurnal otomatis dan hutang saat Purchase Order diterima.
 
 Jurnal yang dibuat tergantung metode pembayaran:
 
 CASH:
 D: Persediaan Barang (1-3000)           Rp subtotal
 D: PPN Masukan (1-1500)                 Rp pajak (jika ada)
    K: Kas/Bank (1-1000 atau sesuai metode)    Rp total
 
 CREDIT:
 D: Persediaan Barang (1-3000)           Rp subtotal
 D: PPN Masukan (1-1500)                 Rp pajak (jika ada)
    K: Hutang Usaha (2-1000)                   Rp total
 
 Catatan operasional: hutang dan persediaan diakui saat status='received',
 karena barang sudah masuk gudang dan nominal pembelian sudah final.
==========================================================================
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)


def ensure_po_faktur_pajak(instance, subtotal=None, pajak=None, biaya_pengiriman=None):
    subtotal = subtotal if subtotal is not None else (instance.subtotal or Decimal('0'))
    pajak = pajak if pajak is not None else (instance.pajak or Decimal('0'))
    biaya_pengiriman = biaya_pengiriman if biaya_pengiriman is not None else (instance.biaya_pengiriman or Decimal('0'))
    dpp_pajak = subtotal + biaya_pengiriman
    if pajak <= 0 or dpp_pajak <= 0:
        return None

    from apps.pajak.models import FakturPajak, SettingPajak

    if FakturPajak.objects.filter(purchase_order=instance, tipe='masukan').exists():
        return None

    setting = SettingPajak.get_setting()
    tarif = (pajak / dpp_pajak * Decimal('100')) if dpp_pajak else setting.tarif_ppn
    return FakturPajak.objects.create(
        nomor_seri=f'AUTO-PO-{instance.pk}',
        tipe='masukan',
        tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
        dpp=dpp_pajak,
        tarif_ppn=tarif,
        nama_lawan=instance.supplier.nama if instance.supplier_id else 'Supplier',
        npwp_lawan='',
        purchase_order=instance,
        status='approved',
        keterangan=f'Auto Faktur PPN Masukan dari PO {instance.nomor_po}',
        created_by=instance.dibuat_oleh,
    )


def ensure_po_hutang(instance, total=None):
    """Pastikan PO kredit memiliki record Hutang. Idempotent."""
    from apps.kas_bank.services import metode_is_credit

    is_credit = instance.metode_pembayaran is None or metode_is_credit(instance.metode_pembayaran)
    if not is_credit:
        return None

    total = total if total is not None else (instance.total_harga or Decimal('0'))
    if total <= 0:
        return None

    from apps.hutang.models import Hutang
    from datetime import timedelta

    tanggal_po = instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal
    if hasattr(tanggal_po, 'date'):
        tanggal_po = tanggal_po.date()

    tanggal_jatuh_tempo = tanggal_po + timedelta(days=30)

    hutang, _ = Hutang.objects.get_or_create(
        sumber='po',
        purchase_order=instance,
        defaults={
            'supplier': instance.supplier,
            'sumber_ref': instance.nomor_po,
            'tanggal': tanggal_po,
            'jatuh_tempo': tanggal_jatuh_tempo,
            'jumlah_total': total,
            'jumlah_dibayar': Decimal('0'),
            'status': 'belum_bayar',
            'cabang': instance.gudang,
            'keterangan': f'Hutang dari PO {instance.nomor_po}',
            'jurnal_pembayaran': None,
            'created_by': instance.dibuat_oleh
        }
    )
    return hutang


@receiver(post_save, sender='pembelian.PurchaseOrder')
def create_po_journal_and_hutang(sender, instance, created, **kwargs):
    """
    Auto-create jurnal dan hutang saat PO received.
    
    Jika payment_method = cash:
    D: Persediaan Barang (1-3000)           Rp subtotal
    D: PPN Masukan (1-1500)                 Rp pajak
       K: Kas/Bank (1-1000)                     Rp total
    
    Jika payment_method = credit:
    D: Persediaan Barang (1-3000)           Rp subtotal
    D: PPN Masukan (1-1500)                 Rp pajak
       K: Hutang Usaha (2-1000)                 Rp total
    
    Trigger: post_save PurchaseOrder
    Kondisi: status = 'received' dan belum ada jurnal
    """
    if kwargs.get('raw'):
        return

    # Jurnal persediaan/hutang dibuat saat barang benar-benar diterima.
    if instance.status != 'received':
        return
    
    subtotal = instance.subtotal or Decimal('0')
    pajak = instance.pajak or Decimal('0')
    biaya_pengiriman = instance.biaya_pengiriman or Decimal('0')
    total = instance.total_harga or Decimal('0')

    # Cek apakah sudah ada jurnal untuk PO ini (race-condition safe)
    from apps.akuntansi.models import JurnalEntry
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        existing = JurnalEntry.objects.select_for_update().filter(
            sumber='po',
            sumber_id=instance.pk
        ).exists()
    
        if existing:
            ensure_po_faktur_pajak(instance, subtotal, pajak, biaya_pengiriman)
            ensure_po_hutang(instance, total)
            return
    
    # Validasi: total harus > 0
    if total <= 0:
        logger.warning(f"[PO] Skip auto-jurnal untuk {instance.nomor_po}: total = {total}")
        return
    
    from apps.kas_bank.services import create_operational_mutation, metode_is_credit, resolve_kas_bank_mapping
    is_credit = instance.metode_pembayaran is None or metode_is_credit(instance.metode_pembayaran)
    kas_bank_account, _, kas_bank_akun_kode = resolve_kas_bank_mapping(instance.metode_pembayaran)
    akun_kredit = '2-1000' if is_credit else kas_bank_akun_kode
    desc_kredit = 'Hutang pembelian ke supplier' if is_credit else 'Pembayaran kas untuk pembelian'
    
    # Build lines data
    lines_data = [
        {
            'akun_kode': '1-3000',  # Persediaan Barang
            'debit': subtotal + biaya_pengiriman,
            'kredit': Decimal('0'),
            'keterangan': f'Pembelian barang PO {instance.nomor_po}'
        }
    ]
    
    # Tambah PPN Masukan jika ada
    if pajak > 0:
        lines_data.append({
            'akun_kode': '1-1500',  # PPN Masukan (Dibayar Dimuka)
            'debit': pajak,
            'kredit': Decimal('0'),
            'keterangan': f'PPN Masukan PO {instance.nomor_po}'
        })
    
    # Tambah akun kredit (Kas/Bank atau Hutang)
    lines_data.append({
        'akun_kode': akun_kredit,
        'debit': Decimal('0'),
        'kredit': total,
        'keterangan': f'{desc_kredit} PO {instance.nomor_po}'
    })
    
    # Create jurnal
    try:
        from apps.akuntansi.services import create_jurnal

        with db_transaction.atomic():
            jurnal = create_jurnal(
                tanggal=instance.tanggal.date() if hasattr(instance.tanggal, 'date') else instance.tanggal,
                deskripsi=f'Pembelian - {instance.nomor_po}',
                lines_data=lines_data,
                sumber='po',
                sumber_id=instance.pk,
                sumber_ref=instance.nomor_po,
                cabang=instance.gudang,
                user=instance.dibuat_oleh,
                auto_post=True,
            )
            if not is_credit:
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe='keluar',
                    tanggal=instance.tanggal,
                    jumlah=total,
                    deskripsi=f'Pembayaran Purchase Order {instance.nomor_po}',
                    akun_lawan=None,
                    cabang=instance.gudang,
                    metode_pembayaran=instance.metode_pembayaran,
                    sumber_app='pembelian',
                    sumber_model='PurchaseOrder',
                    sumber_id=instance.pk,
                    sumber_ref=instance.nomor_po,
                    jurnal_entry=jurnal,
                    user=instance.dibuat_oleh,
                )
            
            # Jika credit, buat hutang
            if is_credit:
                ensure_po_hutang(instance, total)
                logger.info(f'[PO] Auto-hutang created for {instance.nomor_po}')

            ensure_po_faktur_pajak(instance, subtotal, pajak, biaya_pengiriman)
        
        logger.info(f'[PO] Auto-jurnal created for {instance.nomor_po}: {jurnal.nomor}')
        
    except IntegrityError as e:
        logger.warning(f"[PO] Duplicate jurnal untuk {instance.nomor_po}: {e}")
    except Exception as e:
        logger.error(f'[PO] Failed to create auto-jurnal for {instance.nomor_po}: {e}', exc_info=True)
        # Catat kegagalan ke activity log agar terdeteksi di Rekonsiliasi Keuangan
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action='create',
                model_name='JurnalEntry',
                object_id=str(instance.pk),
                object_repr=f'GAGAL: Jurnal PO {instance.nomor_po}',
                description=f'[JURNAL GAGAL] Auto-jurnal untuk PO {instance.nomor_po} gagal dibuat. '
                            f'Error: {str(e)[:200]}. Transaksi tetap berstatus received tapi TIDAK memiliki jurnal. '
                            f'Perbaiki via Rekonsiliasi Keuangan.',
                source_type='purchase',
                source_id=str(instance.pk),
                source_repr=instance.nomor_po,
            )
        except Exception as e:
            logger.warning("Gagal mencatat activity log: %s", e)
        # raise  # Disabled: transaksi tetap tersimpan meskipun jurnal gagal


@receiver(post_delete, sender='pembelian.PurchaseOrderItem')
def recalculate_po_on_item_delete(sender, instance, **kwargs):
    """Recalculate parent PO totals when item is deleted."""
    if instance.purchase_order_id:
        try:
            po = instance.purchase_order
            po.calculate_total()
            po.save()
        except Exception:
            pass  # PO might already be deleted (CASCADE)
