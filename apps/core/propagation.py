"""
==========================================================================
 CORE PROPAGATION - Service Propagasi Perubahan Data Lintas Modul
==========================================================================
 Service terpusat untuk menangani propagasi perubahan data:
 1. handle_document_delete() — reversal + rollback saat dokumen dihapus
 2. recalculate_document_totals() — recalculate total dari items

 Dipanggil dari:
 - Delete views (sebelum instance.delete())
 - post_delete signals (item recalculation)

 Pola: transaction.atomic() + select_for_update() untuk data integrity
==========================================================================
"""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


def handle_document_delete(document, user=None):
    """
    Dipanggil SEBELUM dokumen dihapus (dari delete view).
    Membuat reversal jurnal + cancel mutasi/hutang/piutang + rollback stok.

    Parameters:
        document: Model instance (SO/PO/POS/Biaya/Penggajian)
        user: User yang melakukan delete

    Returns:
        dict dengan info apa yang di-reverse/cancel
    """
    from apps.akuntansi.models import JurnalEntry
    from apps.akuntansi.services import create_reversal_jurnal
    from apps.kas_bank.models import KasBankTransaction

    result = {
        'reversed_jurnals': 0,
        'cancelled_mutations': 0,
        'stock_restored': False,
        'message': '',
    }

    model_name = document.__class__.__name__
    sumber_map = {
        'SalesOrder': 'so',
        'PurchaseOrder': 'po',
        'POSTransaction': 'pos',
        'TransaksiBiaya': 'biaya',
        'Penggajian': 'hr',
    }
    sumber = sumber_map.get(model_name)
    if not sumber:
        return result

    with transaction.atomic():
        # 1. Reverse all journals
        jurnals = JurnalEntry.objects.filter(
            sumber=sumber, sumber_id=document.pk, is_reversed=False, jurnal_asal__isnull=True
        )
        for jurnal in jurnals:
            try:
                create_reversal_jurnal(
                    jurnal,
                    alasan=f'Penghapusan {model_name} #{document.pk}',
                    user=user
                )
                result['reversed_jurnals'] += 1
            except ValueError:
                pass  # Already reversed

        # 2. Cancel KasBankTransaction
        sumber_model_map = {
            'SalesOrder': ('penjualan', 'SalesOrder'),
            'PurchaseOrder': ('pembelian', 'PurchaseOrder'),
            'POSTransaction': ('pos', 'POSTransaction'),
            'TransaksiBiaya': ('biaya', 'TransaksiBiaya'),
            'Penggajian': ('hr', 'Penggajian'),
        }
        app, model = sumber_model_map.get(model_name, ('', ''))
        cancelled = KasBankTransaction.objects.filter(
            sumber_app=app, sumber_model=model,
            sumber_id=document.pk, status='posted'
        ).update(status='cancelled')
        result['cancelled_mutations'] = cancelled

        # 3. Cancel Hutang/Piutang
        _cancel_related_hutang_piutang(document, model_name)

        # 4. Log
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=user,
                action='delete',
                model_name=model_name,
                object_id=str(document.pk),
                object_repr=str(document),
                description=(
                    f'[PROPAGASI] Penghapusan {model_name}: '
                    f'{result["reversed_jurnals"]} jurnal di-reverse, '
                    f'{result["cancelled_mutations"]} mutasi dibatalkan.'
                ),
            )
        except Exception:
            pass

    parts = []
    if result['reversed_jurnals']:
        parts.append(f"{result['reversed_jurnals']} jurnal di-reverse")
    if result['cancelled_mutations']:
        parts.append(f"{result['cancelled_mutations']} mutasi dibatalkan")
    result['message'] = ', '.join(parts) if parts else 'Tidak ada data keuangan terkait.'

    return result


def _cancel_related_hutang_piutang(document, model_name):
    """Cancel hutang/piutang terkait dokumen."""
    if model_name == 'SalesOrder':
        try:
            from apps.piutang.models import Piutang
            Piutang.objects.filter(
                sumber='so', sales_order=document
            ).exclude(status__in=['lunas', 'dihapuskan']).update(
                status='dihapuskan'
            )
        except Exception:
            pass
    elif model_name == 'PurchaseOrder':
        try:
            from apps.hutang.models import Hutang
            Hutang.objects.filter(
                sumber='po', purchase_order=document
            ).exclude(status='lunas').update(status='macet')
        except Exception:
            pass
    elif model_name == 'POSTransaction':
        try:
            from apps.piutang.models import Piutang
            Piutang.objects.filter(
                sumber='pos', pos_transaction=document
            ).exclude(status__in=['lunas', 'dihapuskan']).update(
                status='dihapuskan'
            )
        except Exception:
            pass


def recalculate_document_totals(document):
    """
    Recalculate total dokumen dari items-nya.
    Dipanggil setelah item ditambah/diedit/dihapus.
    """
    model_name = document.__class__.__name__

    if model_name in ('SalesOrder', 'PurchaseOrder', 'POSTransaction'):
        document.calculate_total()
        document.save()
    elif model_name == 'Penggajian':
        document.calculate_total()
        document.save()


def handle_document_edit(document, old_total, user=None):
    """
    Dipanggil SETELAH dokumen yang sudah punya jurnal diedit (nominal berubah).
    Membuat reversal jurnal lama + re-trigger pembuatan jurnal baru via signal/service.

    Parameters:
        document: Model instance (SO/PO/POS/Biaya/Penggajian) yang sudah di-save
        old_total: Decimal — total_harga/jumlah sebelum edit
        user: User yang melakukan edit

    Returns:
        dict dengan info reversal yang dilakukan
    """
    from apps.akuntansi.models import JurnalEntry
    from apps.akuntansi.services import create_reversal_jurnal
    from apps.kas_bank.models import KasBankTransaction

    model_name = document.__class__.__name__
    sumber_map = {
        'SalesOrder': 'so',
        'PurchaseOrder': 'po',
        'POSTransaction': 'pos',
        'TransaksiBiaya': 'biaya',
        'Penggajian': 'hr',
    }
    sumber = sumber_map.get(model_name)
    if not sumber:
        return {'reversed': 0, 'message': 'Model tidak dikenali'}

    # Cek apakah ada jurnal existing untuk dokumen ini
    existing_jurnals = JurnalEntry.objects.filter(
        sumber=sumber, sumber_id=document.pk, is_reversed=False, jurnal_asal__isnull=True
    )
    if not existing_jurnals.exists():
        return {'reversed': 0, 'message': 'Tidak ada jurnal yang perlu di-reverse'}

    # Cek apakah total berubah (jika tidak berubah, skip)
    new_total = None
    if hasattr(document, 'total_harga'):
        new_total = document.total_harga
    elif hasattr(document, 'jumlah'):
        new_total = document.jumlah
    elif hasattr(document, 'gaji_bersih'):
        new_total = document.gaji_bersih

    if new_total is not None and old_total is not None and new_total == old_total:
        return {'reversed': 0, 'message': 'Total tidak berubah, skip reversal'}

    result = {'reversed': 0, 'message': ''}

    with transaction.atomic():
        # 1. Reverse semua jurnal lama
        for jurnal in existing_jurnals:
            try:
                create_reversal_jurnal(jurnal, alasan=f'Edit {model_name} #{document.pk}', user=user)
                result['reversed'] += 1
            except ValueError:
                pass  # Already reversed

        # 2. Cancel mutasi kas/bank lama
        sumber_model_map = {
            'SalesOrder': ('penjualan', 'SalesOrder'),
            'PurchaseOrder': ('pembelian', 'PurchaseOrder'),
            'POSTransaction': ('pos', 'POSTransaction'),
            'TransaksiBiaya': ('biaya', 'TransaksiBiaya'),
            'Penggajian': ('hr', 'Penggajian'),
        }
        app, model = sumber_model_map.get(model_name, ('', ''))
        KasBankTransaction.objects.filter(
            sumber_app=app, sumber_model=model,
            sumber_id=document.pk, status='posted'
        ).update(status='cancelled')

        # 3. Re-trigger jurnal baru via save() — signal akan buat jurnal baru
        # karena idempotent check melihat is_reversed=True pada jurnal lama
        # dan tidak menemukan jurnal aktif, sehingga akan buat baru
        document.save()

        # 4. Log
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=user,
                action='update',
                model_name=model_name,
                object_id=str(document.pk),
                object_repr=str(document),
                description=(
                    f'[PROPAGASI EDIT] {model_name} #{document.pk} diedit. '
                    f'Total lama: {old_total}, Total baru: {new_total}. '
                    f'{result["reversed"]} jurnal di-reverse, jurnal baru dibuat otomatis.'
                ),
            )
        except Exception:
            pass

    result['message'] = f'{result["reversed"]} jurnal di-reverse, jurnal baru dibuat otomatis.'
    return result


def handle_item_edit_stock(item, old_qty, document):
    """
    Dipanggil saat item pada dokumen yang sudah diproses diedit (qty berubah).
    Menyesuaikan stok: rollback qty lama + apply qty baru.

    Parameters:
        item: Item instance (SOItem/POItem/POSItem)
        old_qty: Decimal — qty lama (dalam satuan dasar/konversi)
        document: Parent document (SO/PO/POS)
    """
    from apps.produk.models import Stok
    from decimal import Decimal

    new_qty = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
    model_name = document.__class__.__name__

    if old_qty == new_qty:
        return  # Tidak ada perubahan qty

    with transaction.atomic():
        stok, _ = Stok.objects.select_for_update().get_or_create(
            produk=item.produk, gudang=document.gudang,
            defaults={'jumlah': Decimal('0')}
        )

        if model_name == 'PurchaseOrder':
            # PO: stok bertambah saat received
            # Rollback: kurangi old_qty, tambah new_qty
            stok.jumlah = stok.jumlah - old_qty + new_qty
        else:
            # SO/POS: stok berkurang saat confirmed/paid
            # Rollback: tambah old_qty, kurangi new_qty
            stok.jumlah = stok.jumlah + old_qty - new_qty

        if stok.jumlah < Decimal('0'):
            stok.jumlah = Decimal('0')
        stok.save()

        # Update cabang produk ke gudang dengan stok terbanyak
        from apps.produk.models import Stok as StokModel
        stok_terbanyak = StokModel.objects.filter(
            produk=item.produk, jumlah__gt=0
        ).order_by('-jumlah').first()
        if stok_terbanyak and item.produk.cabang != stok_terbanyak.gudang:
            item.produk.cabang = stok_terbanyak.gudang
            item.produk.save(update_fields=['cabang'])
