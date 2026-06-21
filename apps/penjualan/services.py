"""
==========================================================================
 PENJUALAN SERVICES - Atomic Status Transition untuk Sales Order
==========================================================================
 Service layer untuk mengelola transisi status Sales Order secara atomic.
 Menggabungkan validasi status + efek akuntansi (jurnal, stok, piutang, mutasi).

 Pola mengikuti transition_biaya_status() di apps/biaya/services.py:
 - transaction.atomic() + select_for_update() untuk race condition prevention
 - Delegasi ke create_reversal_jurnal() untuk pembatalan
 - Idempotent: cek existing sebelum create
 - Error logging ke activity_log

 Forward transitions (existing signal logic tetap untuk saat ini):
 - draft → confirmed: stock reduction + journal sudah di-handle oleh signal
 - confirmed → delivered: hanya status change
 - delivered → completed: hanya status change

 Cancellation (NEW):
 - confirmed/delivered → cancelled: reversal journal + restore stock + cancel piutang/mutasi
==========================================================================
"""

from decimal import Decimal
import logging

from django.db import transaction

from apps.penjualan.models import SalesOrder
from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_reversal_jurnal

logger = logging.getLogger(__name__)


@transaction.atomic
def transition_so_status(sales_order, new_status, user=None):
    """
    Atomic: validate transition + create/reverse journal + stock + piutang/mutasi.

    Parameters:
        sales_order: SalesOrder instance
        new_status: target status string
        user: User performing the action

    Returns:
        SalesOrder instance (saved)

    Raises:
        ValidationError: if transition is invalid
        ValueError: if accounting operation fails
    """
    with transaction.atomic():
        # Lock record untuk mencegah race condition
        locked = SalesOrder.objects.select_for_update().get(pk=sales_order.pk)

        # Simpan status lama untuk logic cancellation
        old_status = locked.status

        # Validate transition (raises ValidationError if invalid)
        locked.transition_status(new_status, user)

        if new_status == 'cancelled':
            _cancel_so(locked, old_status, user)

        locked.save()

    return locked


def _cancel_so(so, old_status, user):
    """
    Handle SO cancellation: reversal journal + stock restore + cancel piutang/mutasi.

    Dipanggil dalam transaction.atomic() context dari transition_so_status().
    """
    from apps.produk.models import Stok
    from apps.kas_bank.models import KasBankTransaction

    # 1. Reverse all journals for this SO
    jurnals = JurnalEntry.objects.filter(
        sumber='so', sumber_id=so.pk, is_reversed=False
    )
    for jurnal in jurnals:
        try:
            create_reversal_jurnal(
                jurnal,
                alasan=f'Pembatalan SO {so.nomor_so}',
                user=user
            )
        except ValueError:
            # Already reversed — skip
            pass

    # 2. Restore stock (reverse of confirm_order)
    # Stok dikurangi saat confirmed, jadi restore jika pernah confirmed
    if old_status in ('confirmed', 'delivered', 'completed'):
        for item in so.items.select_related('produk'):
            qty_restore = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
            stok, _ = Stok.objects.select_for_update().get_or_create(
                produk=item.produk,
                gudang=so.gudang,
                defaults={'jumlah': Decimal('0')}
            )
            stok.jumlah += qty_restore
            stok.save()

            # Update cabang produk ke gudang dengan stok terbanyak
            produk = item.produk
            stok_terbanyak = Stok.objects.filter(
                produk=produk, jumlah__gt=0
            ).order_by('-jumlah').first()
            if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                produk.cabang = stok_terbanyak.gudang
                produk.save(update_fields=['cabang'])

    # 3. Cancel KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='penjualan',
        sumber_model='SalesOrder',
        sumber_id=so.pk,
        status='posted'
    ).update(status='cancelled')

    # 4. Cancel Piutang
    try:
        from apps.piutang.models import Piutang
        Piutang.objects.filter(
            sumber='so',
            sales_order=so
        ).exclude(
            status__in=['lunas', 'dihapuskan']
        ).update(status='dihapuskan')
    except Exception as e:
        logger.warning(f"[SO] Gagal cancel piutang untuk {so.nomor_so}: {e}")

    # 5. Log ke activity_log
    try:
        from apps.activity_log.models import UserActivity
        UserActivity.objects.create(
            user=user,
            action='cancel',
            model_name='SalesOrder',
            object_id=str(so.pk),
            object_repr=f'Pembatalan SO {so.nomor_so}',
            description=(
                f'SO {so.nomor_so} dibatalkan dari status {old_status}. '
                f'Jurnal di-reverse, stok dikembalikan, piutang/mutasi dibatalkan.'
            ),
            source_type='sales',
            source_id=str(so.pk),
            source_repr=so.nomor_so,
        )
    except Exception as e:
        logger.warning(f"[SO] Gagal log activity untuk pembatalan {so.nomor_so}: {e}")
