import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.aset.models import DisposalAset, Penyusutan
from apps.aset.services import ensure_disposal_accounting, ensure_penyusutan_accounting


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Penyusutan)
def create_penyusutan_journal(sender, instance, **kwargs):
    """Auto-create jurnal penyusutan dari model-level save."""
    if kwargs.get("raw") or instance.jurnal_id:
        return

    try:
        ensure_penyusutan_accounting(instance, user=instance.created_by)
    except Exception as exc:
        logger.error(
            "[ASET] Failed to create penyusutan journal for %s %02d/%s: %s",
            instance.aset.kode,
            instance.bulan,
            instance.tahun,
            exc,
            exc_info=True,
        )


@receiver(post_save, sender=DisposalAset)
def create_disposal_journal(sender, instance, **kwargs):
    """Auto-create jurnal disposal dari model-level save."""
    if kwargs.get("raw") or instance.jurnal_id:
        return

    try:
        ensure_disposal_accounting(instance, user=instance.created_by)
    except Exception as exc:
        logger.error(
            "[ASET] Failed to create disposal journal for %s: %s",
            instance.aset.kode,
            exc,
            exc_info=True,
        )
