"""
==========================================================================
 INVENTORY SIGNALS — Jurnal Otomatis Adjustment Stok
==========================================================================
 Trigger: post_save pada model AdjustmentStok
 Kondisi: record baru (created=True)
 → Panggil ensure_adjustment_accounting()
==========================================================================
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='inventory.AdjustmentStok')
def create_adjustment_journal(sender, instance, created, **kwargs):
    """Auto-create jurnal saat AdjustmentStok baru dibuat."""
    if kwargs.get('raw') or not created:
        return

    try:
        from apps.inventory.services import ensure_adjustment_accounting
        ensure_adjustment_accounting(instance, user=instance.dibuat_oleh)
    except Exception as exc:
        logger.error(
            f'[INVENTORY] Failed to create auto-jurnal for {instance.nomor_adjustment}: {exc}',
            exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action='create',
                model_name='JurnalEntry',
                object_id=str(instance.pk),
                object_repr=f'GAGAL: Jurnal Adjustment {instance.nomor_adjustment}',
                description=f'[JURNAL GAGAL] Auto-jurnal adjustment {instance.nomor_adjustment} gagal. '
                            f'Error: {str(exc)[:200]}.',
                source_type='inventory',
                source_id=str(instance.pk),
                source_repr=instance.nomor_adjustment,
            )
        except Exception:
            pass
