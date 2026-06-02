"""
==========================================================================
 PIUTANG SIGNALS — Activity Log & Monitoring Pembayaran Piutang
==========================================================================
 Model PembayaranPiutang sudah punya auto-jurnal di save() method:
   D: Kas/Bank    K: 1-2000 Piutang Usaha

 Signal ini TIDAK membuat jurnal duplikat, melainkan:
 1. Monitoring: log successful journal creation
 2. Safety net: detect jika save() gagal buat jurnal

 Ini memastikan setiap pembayaran piutang PASTI tercatat di activity log.
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='piutang.PembayaranPiutang')
def monitor_piutang_journal(sender, instance, created, **kwargs):
    """
    Monitor auto-jurnal pembayaran piutang yang dibuat di PembayaranPiutang.save().

    Bukan pembuat jurnal — hanya memastikan jurnal benar-benar terbuat.
    Jika tidak ada jurnal setelah save, log warning.
    """
    if kwargs.get("raw") or not created:
        return

    # Refresh instance dari DB untuk cek jurnal terbaru
    try:
        instance.refresh_from_db()
    except Exception:
        return

    if instance.jurnal_id:
        logger.info(
            "[PIUTANG] Auto-jurnal penerimaan berhasil: %s | Jurnal #%s | Rp %s",
            instance.piutang.nomor,
            instance.jurnal_id,
            f"{instance.jumlah:,.0f}",
        )
    else:
        logger.warning(
            "[PIUTANG] Pembayaran piutang %s (#%s) TIDAK memiliki jurnal. "
            "Periksa PembayaranPiutang.save() — kemungkinan akun CoA belum tersedia.",
            instance.piutang.nomor,
            instance.pk,
        )
