"""
==========================================================================
 HR SERVICES - Atomic Status Transition untuk Penggajian
==========================================================================
 Service layer untuk mengelola transisi status Penggajian secara atomic.
 Menggabungkan validasi status + efek akuntansi (jurnal, mutasi kas/bank).

 Pola mengikuti transition_biaya_status() di apps/biaya/services.py:
 - transaction.atomic() + select_for_update() untuk race condition prevention
 - Delegasi ke create_reversal_jurnal() untuk pembatalan
 - Idempotent: cek existing sebelum create
 - Error logging ke activity_log

 Forward transitions (existing signal logic tetap untuk saat ini):
 - draft → diproses: recalculate totals, lock fields
 - diproses → dibayar: journal + mutasi sudah di-handle oleh signal

 Cancellation (NEW):
 - draft/diproses/dibayar → batal: reversal journal + cancel mutasi
==========================================================================
"""

import logging

from django.db import transaction

from apps.hr.models import Penggajian
from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_reversal_jurnal

logger = logging.getLogger(__name__)


def transition_penggajian_status(penggajian, new_status, user=None):
    """
    Atomic: validate transition + create/reverse journal + mutasi.

    Parameters:
        penggajian: Penggajian instance
        new_status: target status string
        user: User performing the action

    Returns:
        Penggajian instance (saved)

    Raises:
        ValidationError: if transition is invalid
        ValueError: if accounting operation fails
    """
    with transaction.atomic():
        # Lock record untuk mencegah race condition
        locked = Penggajian.objects.select_for_update().get(pk=penggajian.pk)

        # Simpan status lama untuk logic cancellation
        old_status = locked.status

        # Validate transition (raises ValidationError if invalid)
        locked.transition_status(new_status, user)

        if new_status == 'batal':
            _cancel_penggajian(locked, old_status, user)

        locked.save()

    return locked


def _cancel_penggajian(penggajian, old_status, user):
    """
    Handle Penggajian cancellation: reversal journal + cancel mutasi.

    Dipanggil dalam transaction.atomic() context dari transition_penggajian_status().
    Hanya perlu reverse jurnal dan cancel mutasi jika sebelumnya sudah dibayar.
    """
    from apps.kas_bank.models import KasBankTransaction

    # 1. Reverse all journals for this Penggajian
    jurnals = JurnalEntry.objects.filter(
        sumber__in=['payroll', 'hr'], sumber_id=penggajian.pk, is_reversed=False
    )
    for jurnal in jurnals:
        try:
            karyawan_nama = penggajian.karyawan.nama if penggajian.karyawan else 'Unknown'
            create_reversal_jurnal(
                jurnal,
                alasan=f'Pembatalan gaji {karyawan_nama} - {penggajian.periode_bulan}/{penggajian.periode_tahun}',
                user=user
            )
        except ValueError:
            # Already reversed — skip
            pass

    # 2. Cancel KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='hr',
        sumber_model='Penggajian',
        sumber_id=penggajian.pk,
        status='posted'
    ).update(status='cancelled')

    # 3. Log ke activity_log
    try:
        from apps.activity_log.models import UserActivity
        karyawan_nama = penggajian.karyawan.nama if penggajian.karyawan else 'Unknown'
        periode_ref = f"{penggajian.periode_bulan:02d}/{penggajian.periode_tahun}"
        UserActivity.objects.create(
            user=user,
            action='cancel',
            model_name='Penggajian',
            object_id=str(penggajian.pk),
            object_repr=f'Pembatalan Gaji {karyawan_nama} - {periode_ref}',
            description=(
                f'Penggajian {karyawan_nama} periode {periode_ref} dibatalkan '
                f'dari status {old_status}. '
                f'Jurnal di-reverse, mutasi kas/bank dibatalkan.'
            ),
            source_type='payroll',
            source_id=str(penggajian.pk),
            source_repr=f'GAJI-{penggajian.pk}-{periode_ref}',
        )
    except Exception as e:
        logger.warning(
            f"[HR] Gagal log activity untuk pembatalan gaji Penggajian #{penggajian.pk}: {e}"
        )
