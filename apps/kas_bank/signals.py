"""
==========================================================================
 KAS BANK SIGNALS — Jurnal Otomatis Mutasi & Transfer
==========================================================================
 Trigger 1: post_save pada KasBankTransaction
   Kondisi: status='posted', sumber_app kosong (mutasi manual), belum punya jurnal
   → Panggil post_manual_kas_bank_transaction()

 Trigger 2: post_save pada KasBankTransfer
   Kondisi: status='posted', belum punya jurnal
   → Panggil post_kas_bank_transfer()

 Mutasi OPERASIONAL (dari SO/PO/Biaya/dll) TIDAK diproses di sini
 karena sudah diproses oleh signal masing-masing modul.
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='kas_bank.KasBankTransaction')
def auto_journal_kas_bank_transaction(sender, instance, **kwargs):
    """
    Auto-create jurnal untuk mutasi kas/bank MANUAL yang di-post.

    Hanya proses mutasi manual (sumber_app kosong).
    Mutasi operasional dari SO/PO/Biaya sudah dihandle signal masing-masing.
    """
    if kwargs.get("raw"):
        return

    # Skip jika bukan posted atau sudah punya jurnal
    if instance.status != "posted" or instance.jurnal_entry_id:
        return

    # Skip mutasi operasional — sudah dihandle oleh signal modul lain
    if instance.sumber_app:
        return

    # Hanya mutasi manual yang punya akun_lawan
    if not instance.akun_lawan_id:
        return

    try:
        from apps.kas_bank.services import post_manual_kas_bank_transaction

        jurnal = post_manual_kas_bank_transaction(instance, user=instance.dibuat_oleh)
        if jurnal:
            logger.info(
                "[KAS_BANK] Auto-jurnal mutasi manual berhasil: %s | Jurnal #%s",
                instance.nomor,
                jurnal.pk,
            )

    except Exception as exc:
        logger.error(
            "[KAS_BANK] Failed to create auto-jurnal for transaction %s: %s",
            instance.nomor,
            exc,
            exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity

            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action="create",
                model_name="JurnalEntry",
                object_id=str(instance.pk),
                object_repr=f"GAGAL: Jurnal Mutasi {instance.nomor}",
                description=(
                    f"[JURNAL GAGAL] Auto-jurnal mutasi kas/bank {instance.nomor} gagal dibuat. "
                    f"Error: {str(exc)[:200]}. Mutasi tetap posted tapi TIDAK memiliki jurnal."
                ),
                source_type="treasury",
                source_id=str(instance.pk),
                source_repr=instance.nomor,
            )
        except Exception:
            pass


@receiver(post_save, sender='kas_bank.KasBankTransfer')
def auto_journal_kas_bank_transfer(sender, instance, **kwargs):
    """
    Auto-create jurnal untuk transfer antar kas/bank yang di-post.

    Jurnal:
      D: Akun Kas/Bank tujuan      Rp jumlah
      K: Akun Kas/Bank sumber      Rp (jumlah + biaya_admin)
      D: Akun Biaya Admin           Rp biaya_admin (jika ada)
    """
    if kwargs.get("raw"):
        return

    # Skip jika bukan posted atau sudah punya jurnal
    if instance.status != "posted" or instance.jurnal_entry_id:
        return

    try:
        from apps.kas_bank.services import post_kas_bank_transfer

        jurnal = post_kas_bank_transfer(instance, user=instance.dibuat_oleh)
        if jurnal:
            logger.info(
                "[KAS_BANK] Auto-jurnal transfer berhasil: %s | Jurnal #%s",
                instance.nomor,
                jurnal.pk,
            )

    except Exception as exc:
        logger.error(
            "[KAS_BANK] Failed to create auto-jurnal for transfer %s: %s",
            instance.nomor,
            exc,
            exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity

            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action="create",
                model_name="JurnalEntry",
                object_id=str(instance.pk),
                object_repr=f"GAGAL: Jurnal Transfer {instance.nomor}",
                description=(
                    f"[JURNAL GAGAL] Auto-jurnal transfer kas/bank {instance.nomor} gagal dibuat. "
                    f"Error: {str(exc)[:200]}. Transfer tetap posted tapi TIDAK memiliki jurnal."
                ),
                source_type="treasury",
                source_id=str(instance.pk),
                source_repr=instance.nomor,
            )
        except Exception:
            pass
