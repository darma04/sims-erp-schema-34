import logging
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import ReimburseRequest

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ReimburseRequest)
def handle_reimburse_status_change(sender, instance, created, **kwargs):
    if instance.status == 'paid':
        from .services import ensure_reimburse_accounting
        try:
            ensure_reimburse_accounting(instance)
        except Exception as e:
            logger.error(f"[JURNAL GAGAL] Reimburse {instance.nomor}: {e}")
    elif instance.status == 'cancelled' and not created:
        from .services import cancel_reimburse_accounting
        try:
            cancel_reimburse_accounting(instance)
        except Exception as e:
            logger.error(f"[JURNAL GAGAL] Cancel Reimburse {instance.nomor}: {e}")
