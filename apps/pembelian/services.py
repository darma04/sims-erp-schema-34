"""
==========================================================================
 PEMBELIAN SERVICES - Atomic Status Transition untuk Purchase Order
==========================================================================
 Service layer untuk mengelola transisi status Purchase Order secara atomic.
 Menggabungkan validasi status + efek akuntansi (jurnal, stok, hutang, mutasi).

 Pola mengikuti transition_biaya_status() di apps/biaya/services.py:
 - transaction.atomic() + select_for_update() untuk race condition prevention
 - Delegasi ke create_reversal_jurnal() untuk pembatalan
 - Idempotent: cek existing sebelum create
 - Error logging ke activity_log

 Forward transitions (existing signal logic tetap untuk saat ini):
 - draft → submitted, submitted → approved: hanya status change
 - approved → received: stock addition + journal sudah di-handle oleh signal

 Cancellation (NEW):
 - submitted/approved/received → cancelled: reversal journal + reduce stock + cancel hutang/mutasi
==========================================================================
"""

from decimal import Decimal
import logging

from django.db import transaction

from apps.pembelian.models import PurchaseOrder
from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_reversal_jurnal

logger = logging.getLogger(__name__)


def transition_po_status(purchase_order, new_status, user=None):
    """
    Atomic: validate transition + create/reverse journal + stock + hutang/mutasi.

    Parameters:
        purchase_order: PurchaseOrder instance
        new_status: target status string
        user: User performing the action

    Returns:
        PurchaseOrder instance (saved)

    Raises:
        ValidationError: if transition is invalid
        ValueError: if accounting operation fails
    """
    with transaction.atomic():
        # Lock record untuk mencegah race condition
        locked = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)

        # Simpan status lama untuk logic cancellation
        old_status = locked.status

        # Validate transition (raises ValidationError if invalid)
        locked.transition_status(new_status, user)

        if new_status == 'cancelled':
            _cancel_po(locked, old_status, user)

        locked.save()

    return locked


def _cancel_po(po, old_status, user):
    """
    Handle PO cancellation: reversal journal + stock reduce + cancel hutang/mutasi.

    Dipanggil dalam transaction.atomic() context dari transition_po_status().
    """
    from apps.produk.models import Stok
    from apps.kas_bank.models import KasBankTransaction

    # 1. Reverse all journals for this PO
    jurnals = JurnalEntry.objects.filter(
        sumber='po', sumber_id=po.pk, is_reversed=False
    )
    for jurnal in jurnals:
        try:
            create_reversal_jurnal(
                jurnal,
                alasan=f'Pembatalan PO {po.nomor_po}',
                user=user
            )
        except ValueError:
            # Already reversed — skip
            pass

    # 2. Reduce stock (reverse of receive_goods) — hanya jika sudah received
    if old_status == 'received':
        for item in po.items.select_related('produk'):
            qty_reduce = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
            try:
                stok = Stok.objects.select_for_update().get(
                    produk=item.produk, gudang=po.gudang
                )
                stok.jumlah -= qty_reduce
                # Jangan biarkan stok negatif
                if stok.jumlah < Decimal('0'):
                    stok.jumlah = Decimal('0')
                stok.save()

                # Update cabang produk ke gudang dengan stok terbanyak
                produk = item.produk
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()
                if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                    produk.cabang = stok_terbanyak.gudang
                    produk.save(update_fields=['cabang'])
            except Stok.DoesNotExist:
                # Stok record tidak ada — skip (mungkin sudah dihapus)
                pass

    # 3. Cancel KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='pembelian',
        sumber_model='PurchaseOrder',
        sumber_id=po.pk,
        status='posted'
    ).update(status='cancelled')

    # 4. Cancel Hutang
    try:
        from apps.hutang.models import Hutang
        Hutang.objects.filter(
            sumber='po',
            purchase_order=po
        ).exclude(
            status='lunas'
        ).update(status='macet')
    except Exception as e:
        logger.warning(f"[PO] Gagal cancel hutang untuk {po.nomor_po}: {e}")

    # 5. Log ke activity_log
    try:
        from apps.activity_log.models import UserActivity
        UserActivity.objects.create(
            user=user,
            action='cancel',
            model_name='PurchaseOrder',
            object_id=str(po.pk),
            object_repr=f'Pembatalan PO {po.nomor_po}',
            description=(
                f'PO {po.nomor_po} dibatalkan dari status {old_status}. '
                f'Jurnal di-reverse, stok dikurangi, hutang/mutasi dibatalkan.'
            ),
            source_type='purchase',
            source_id=str(po.pk),
            source_repr=po.nomor_po,
        )
    except Exception as e:
        logger.warning(f"[PO] Gagal log activity untuk pembatalan {po.nomor_po}: {e}")
