"""
==========================================================================
 SERVICE CENTER SIGNALS - Auto-Jurnal untuk Transaksi Service
==========================================================================
 Signal ini memicu jurnal otomatis saat pembayaran (dp/lunas) OrderService
 diubah. Sinkronisasi jurnal dan Kas/Bank dihandle secara aman oleh
 sync_service_payment_accounting dari services.py.
==========================================================================
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='service_center.OrderService')
def trigger_service_payment_accounting(sender, instance, created, **kwargs):
    """
    Auto-create/update/reverse jurnal saat OrderService disimpan.
    Memanggil fungsi sinkronisasi akuntansi.
    """
    if kwargs.get('raw'):
        return

    try:
        from apps.service_center.services import sync_service_payment_accounting
        sync_service_payment_accounting(instance, user=instance.diterima_oleh)
        logger.info(f'[Service Center] Auto-jurnal triggered for {instance.nomor_service}')
    except Exception as e:
        logger.error(f'[Service Center] Failed to trigger auto-jurnal for {instance.nomor_service}: {e}', exc_info=True)
        # Catat kegagalan ke activity log agar terdeteksi di Rekonsiliasi Keuangan
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.diterima_oleh,
                action='create',
                model_name='JurnalEntry',
                object_id=str(instance.pk),
                object_repr=f'GAGAL: Jurnal Service {instance.nomor_service}',
                description=f'[JURNAL GAGAL] Auto-jurnal untuk Service Center {instance.nomor_service} gagal dibuat. '
                            f'Error: {str(e)[:200]}. Transaksi tetap tersimpan tapi TIDAK memiliki jurnal yang sesuai. '
                            f'Perbaiki via Rekonsiliasi Keuangan atau simpan ulang.',
                source_type='service_center',
                source_id=str(instance.pk),
                source_repr=instance.nomor_service,
            )
        except Exception:
            pass
        raise
