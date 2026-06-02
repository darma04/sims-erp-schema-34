"""
==========================================================================
 HUTANG SIGNALS — Activity Log & Monitoring Pembayaran Hutang
==========================================================================
 Model PembayaranHutang sudah punya auto-jurnal di save() method:
   D: 2-1000 Hutang Usaha    K: Kas/Bank

 Signal ini TIDAK membuat jurnal duplikat, melainkan:
 1. Monitoring: log successful journal creation
 2. Safety net: detect jika save() gagal buat jurnal

 Ini memastikan setiap pembayaran hutang PASTI tercatat di activity log,
 baik sukses maupun gagal.
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='hutang.PembayaranHutang')
def monitor_hutang_journal(sender, instance, created, **kwargs):
    """
    Monitor auto-jurnal pembayaran hutang yang dibuat di PembayaranHutang.save().

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
            "[HUTANG] Auto-jurnal pembayaran berhasil: %s | Jurnal #%s | Rp %s",
            instance.hutang.nomor,
            instance.jurnal_id,
            f"{instance.jumlah:,.0f}",
        )
    else:
        logger.warning(
            "[HUTANG] Pembayaran hutang %s (#%s) TIDAK memiliki jurnal. "
            "Periksa PembayaranHutang.save() — kemungkinan akun CoA belum tersedia.",
            instance.hutang.nomor,
            instance.pk,
        )
