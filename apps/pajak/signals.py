"""
==========================================================================
 PAJAK SIGNALS — Jurnal Otomatis Pembayaran PPN
==========================================================================
 Trigger: post_save pada model PembayaranPPN
 Kondisi: belum punya jurnal

 Jurnal setor PPN (PPN Keluaran > PPN Masukan):
   D: 2-2000 PPN Keluaran           Rp total_ppn_keluaran
      K: 1-1500 PPN Masukan            Rp total_ppn_masukan
      K: Kas/Bank                       Rp jumlah_setor (selisih)

 Jurnal restitusi PPN (PPN Masukan > PPN Keluaran):
   D: 2-2000 PPN Keluaran           Rp total_ppn_keluaran
   D: Kas/Bank                       Rp jumlah_restitusi (selisih)
      K: 1-1500 PPN Masukan            Rp total_ppn_masukan

 Setelah jurnal dibuat, semua FakturPajak periode tersebut
 diupdate statusnya menjadi 'reported'.
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal

logger = logging.getLogger(__name__)


@receiver(post_save, sender='pajak.PembayaranPPN')
def create_ppn_journal(sender, instance, **kwargs):
    """
    Auto-create jurnal saat PembayaranPPN disimpan.

    Idempotent: cek jurnal existing sebelum buat baru.
    """
    if kwargs.get("raw"):
        return

    # Skip jika sudah punya jurnal
    if instance.jurnal_id:
        return

    jumlah_setor = Decimal(str(instance.jumlah_setor or 0))
    if jumlah_setor <= 0:
        return

    try:
        from apps.akuntansi.services import create_jurnal, get_akun_by_kode
        from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping
        from apps.pajak.models import FakturPajak

        ppn_keluaran = Decimal(str(instance.total_ppn_keluaran or 0))
        ppn_masukan = Decimal(str(instance.total_ppn_masukan or 0))

        # Akun CoA
        akun_ppn_keluaran = get_akun_by_kode("2-2000")
        akun_ppn_masukan = get_akun_by_kode("1-1500")

        if not akun_ppn_keluaran:
            raise ValueError("Akun 2-2000 (PPN Keluaran) belum tersedia di CoA.")
        if not akun_ppn_masukan:
            raise ValueError("Akun 1-1500 (PPN Masukan) belum tersedia di CoA.")

        # Resolve kas/bank
        try:
            kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(instance.metode_pembayaran)
        except Exception:
            akun_kas_kode = "1-1000"
            kas_bank_account = None

        periode_ref = f"{instance.masa_bulan:02d}/{instance.masa_tahun}"

        if instance.tipe == "setor":
            # PPN Keluaran > PPN Masukan → setor selisih ke negara
            lines_data = [
                {
                    "akun": akun_ppn_keluaran,
                    "debit": ppn_keluaran,
                    "kredit": Decimal("0"),
                    "keterangan": f"Clearing PPN Keluaran periode {periode_ref}",
                },
                {
                    "akun": akun_ppn_masukan,
                    "debit": Decimal("0"),
                    "kredit": ppn_masukan,
                    "keterangan": f"Clearing PPN Masukan periode {periode_ref}",
                },
                {
                    "akun_kode": akun_kas_kode,
                    "debit": Decimal("0"),
                    "kredit": jumlah_setor,
                    "keterangan": f"Setor PPN periode {periode_ref}",
                },
            ]
        else:
            # Restitusi: PPN Masukan > PPN Keluaran → terima selisih dari negara
            lines_data = [
                {
                    "akun": akun_ppn_keluaran,
                    "debit": ppn_keluaran,
                    "kredit": Decimal("0"),
                    "keterangan": f"Clearing PPN Keluaran periode {periode_ref}",
                },
                {
                    "akun_kode": akun_kas_kode,
                    "debit": jumlah_setor,
                    "kredit": Decimal("0"),
                    "keterangan": f"Restitusi PPN periode {periode_ref}",
                },
                {
                    "akun": akun_ppn_masukan,
                    "debit": Decimal("0"),
                    "kredit": ppn_masukan,
                    "keterangan": f"Clearing PPN Masukan periode {periode_ref}",
                },
            ]

        jurnal = create_jurnal(
            tanggal=instance.tanggal_setor,
            deskripsi=f"Pembayaran PPN - Masa {periode_ref}",
            lines_data=lines_data,
            sumber="pajak",
            sumber_id=instance.pk,
            sumber_ref=instance.nomor,
            user=instance.created_by,
            auto_post=True,
        )

        # Simpan referensi jurnal tanpa trigger save() rekursif
        from apps.pajak.models import PembayaranPPN
        PembayaranPPN.objects.filter(pk=instance.pk).update(jurnal=jurnal)
        instance.jurnal = jurnal

        # ── Buat mutasi kas/bank ──
        if kas_bank_account:
            tipe_mutasi = "keluar" if instance.tipe == "setor" else "masuk"
            create_operational_mutation(
                akun_kas_bank=kas_bank_account,
                tipe=tipe_mutasi,
                tanggal=instance.tanggal_setor,
                jumlah=jumlah_setor,
                deskripsi=f"{'Setor' if instance.tipe == 'setor' else 'Restitusi'} PPN masa {periode_ref}",
                akun_lawan=akun_ppn_keluaran if instance.tipe == "setor" else akun_ppn_masukan,
                cabang=None,
                metode_pembayaran=instance.metode_pembayaran,
                sumber_app="pajak",
                sumber_model="PembayaranPPN",
                sumber_id=instance.pk,
                sumber_ref=instance.nomor,
                jurnal_entry=jurnal,
                user=instance.created_by,
            )

        # ── Update status FakturPajak periode ini menjadi 'reported' ──
        FakturPajak.objects.filter(
            tanggal__month=instance.masa_bulan,
            tanggal__year=instance.masa_tahun,
            status="approved",
        ).update(status="reported")

        logger.info(
            "[PAJAK] Jurnal PPN berhasil dibuat: %s | Jurnal #%s | Rp %s",
            instance.nomor, jurnal.pk, f"{jumlah_setor:,.0f}",
        )

    except Exception as exc:
        logger.error(
            "[PAJAK] Failed to create auto-jurnal for PembayaranPPN #%s: %s",
            instance.pk,
            exc,
            exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity

            UserActivity.objects.create(
                user=instance.created_by,
                action="create",
                model_name="JurnalEntry",
                object_id=str(instance.pk),
                object_repr=f"GAGAL: Jurnal PPN {instance.nomor}",
                description=(
                    f"[JURNAL GAGAL] Auto-jurnal PPN {instance.nomor} gagal dibuat. "
                    f"Error: {str(exc)[:200]}. Pembayaran PPN tetap tersimpan tapi TIDAK memiliki jurnal."
                ),
                source_type="tax",
                source_id=str(instance.pk),
                source_repr=instance.nomor,
            )
        except Exception:
            pass
