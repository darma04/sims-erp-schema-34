"""
SERVICE CENTER SIGNALS — Auto-Jurnal untuk Service Center Akuntansi.
==========================================================================
Signal ini membuat jurnal otomatis saat OrderService dibayar (lunas/dp).

Mengikuti pola modul lain (penjualan, biaya, hr, pos):
- Idempotent: hanya buat jurnal jika belum ada
- Error logging ke UserActivity dengan prefix [JURNAL GAGAL]
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='service_center.OrderService')
def sync_service_accounting_on_save(sender, instance, **kwargs):
    """
    Auto-sync accounting saat OrderService payment/status berubah.

    Trigger: post_save OrderService
    Kondisi:
      - status='dibatalkan'  → cancel/reverse accounting
      - status_bayar='dp'/'lunas' → sync/create accounting
      - status_bayar='belum_bayar'/lain → skip
    Idempotent: sync/cancel fungsi sudah mengecek existing JurnalEntry.
    """
    if kwargs.get('raw'):
        return

    # Lazy import — accounting modules mungkin tidak ada (v39 SIMS tanpa akuntansi)
    try:
        from apps.service_center.services import cancel_service_payment_accounting
        from apps.service_center.services import sync_service_payment_accounting
    except ImportError:
        return

    try:
        if instance.status == 'dibatalkan':
            cancel_service_payment_accounting(
                instance,
                user=instance.diterima_oleh,
                reason=f"Signal auto-cancel: OrderService #{instance.pk} dibatalkan"
            )
            return

        if instance.status_bayar in ('dp', 'lunas'):
            sync_service_payment_accounting(instance, user=instance.diterima_oleh)

    except Exception as exc:
        logger.error(
            '[Service Center] Gagal auto-jurnal OrderService #%s: %s',
            instance.pk, exc, exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.diterima_oleh,
                action='create',
                model_name='JurnalEntry',
                object_id=str(instance.pk),
                object_repr=f'GAGAL: Jurnal Service {instance.nomor_service}',
                description=(
                    f'[JURNAL GAGAL] Auto-jurnal Service Center {instance.nomor_service} '
                    f'gagal. Error: {str(exc)[:200]}. '
                    f'Transaksi tetap tercatat tapi TIDAK memiliki jurnal. '
                    f'Perbaiki via Rekonsiliasi Keuangan.'
                ),
                source_type='service_center',
                source_id=str(instance.pk),
                source_repr=instance.nomor_service,
            )
        except Exception as e:
            logger.warning("Gagal mencatat activity log: %s", e)
        # raise  # Disabled: transaksi tetap tersimpan meskipun sinyal gagal
