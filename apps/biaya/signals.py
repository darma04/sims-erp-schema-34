import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.biaya.models import TransaksiBiaya
from apps.biaya.services import ensure_biaya_accounting


logger = logging.getLogger(__name__)


@receiver(post_save, sender=TransaksiBiaya)
def create_biaya_journal(sender, instance, **kwargs):
    """Auto-create jurnal biaya saat status menjadi approved."""
    if kwargs.get("raw") or instance.status != "approved":
        return

    try:
        ensure_biaya_accounting(instance, user=instance.disetujui_oleh)
    except Exception as exc:
        logger.error(
            "[BIAYA] Failed to create auto-jurnal for %s: %s",
            instance.nomor_transaksi,
            exc,
            exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity

            UserActivity.objects.create(
                user=instance.disetujui_oleh,
                action="create",
                model_name="JurnalEntry",
                object_id=str(instance.pk),
                object_repr=f"GAGAL: Jurnal Biaya {instance.nomor_transaksi}",
                description=(
                    f"[JURNAL GAGAL] Auto-jurnal biaya {instance.nomor_transaksi} gagal dibuat. "
                    f"Error: {str(exc)[:200]}. Transaksi tetap approved tapi TIDAK memiliki jurnal."
                ),
                source_type="expense",
                source_id=str(instance.pk),
                source_repr=instance.nomor_transaksi,
            )
        except Exception:
            pass
