"""
==========================================================================
 HR SIGNALS — Jurnal Otomatis Penggajian
==========================================================================
 Trigger: post_save pada model Penggajian
 Kondisi: status == 'dibayar' dan belum punya jurnal

 Jurnal yang dibuat:
   D: 6-1000 Beban Gaji & Tunjangan    Rp gaji_bersih
      K: Kas/Bank (dari metode_pembayaran)  Rp gaji_bersih

 Akun 6-1000 ada di DEFAULT_COA seed ('Beban Gaji & Tunjangan').
 Akun 5-xxxx adalah HPP — BUKAN beban gaji.
==========================================================================
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal

logger = logging.getLogger(__name__)


@receiver(post_save, sender='hr.Penggajian')
def create_penggajian_journal(sender, instance, **kwargs):
    """
    Auto-create jurnal biaya gaji saat Penggajian status='dibayar'.

    Idempotent: cek JurnalEntry existing (sumber='payroll'/'hr', sumber_id=pk) sebelum buat baru.
    Tidak trigger jika: raw save, status bukan 'dibayar', atau total_pendapatan <= 0.

    Akun:
    - Debit  : 6-1000 Beban Gaji & Tunjangan
    - Kredit : Kas/Bank sesuai metode_pembayaran (atau 1-1000 jika tidak diset)
    """
    if kwargs.get("raw") or instance.status != "dibayar":
        return

    total_pendapatan = Decimal(str(instance.total_pendapatan or 0))
    gaji_bersih = Decimal(str(instance.gaji_bersih or 0))
    if total_pendapatan <= 0:
        return

    try:
        from apps.akuntansi.models import JurnalEntry
        from apps.akuntansi.services import create_jurnal, get_akun_by_kode
        from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping
        from django.db import transaction as db_transaction

        # Idempotent check — jangan buat duplikat jurnal
        if JurnalEntry.objects.filter(sumber__in=["payroll", "hr"], sumber_id=instance.pk).exists():
            return

        # ── Resolve akun kas/bank dari metode_pembayaran ──
        # Gunakan metode_pembayaran di Penggajian (jika diset), else fallback ke kas default
        try:
            kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(instance.metode_pembayaran)
        except Exception:
            akun_kas_kode = "1-1000"
            kas_bank_account = None

        # ── Resolve akun beban gaji (6-1000 = Beban Gaji & Tunjangan) ──
        akun_beban_gaji = get_akun_by_kode("6-1000")
        if not akun_beban_gaji:
            raise ValueError(
                "Akun 6-1000 (Beban Gaji & Tunjangan) belum tersedia di CoA. "
                "Jalankan 'python manage.py seed_coa' atau tambahkan akun via menu Akuntansi."
            )

        # ── Tentukan tanggal jurnal ──
        tanggal = instance.tanggal_bayar
        if not tanggal:
            from django.utils import timezone
            tanggal = timezone.now().date()

        # ── Referensi ──
        karyawan_nama = instance.karyawan.nama if instance.karyawan else "Unknown"
        periode_ref = f"{instance.periode_bulan:02d}/{instance.periode_tahun}"
        sumber_ref = f"PAY-{instance.pk}"

        # ── Cabang: dari field Penggajian.cabang (sudah auto-fill dari karyawan) ──
        cabang = instance.cabang or (instance.karyawan.cabang if instance.karyawan_id else None)
        bpjs_total = (
            Decimal(str(instance.potongan_bpjs_kesehatan or 0)) +
            Decimal(str(instance.potongan_bpjs_ketenagakerjaan or 0))
        )
        lines_data = [
            {
                "akun": akun_beban_gaji,
                "debit": total_pendapatan,
                "kredit": Decimal("0"),
                "keterangan": f"Beban gaji {karyawan_nama} - {periode_ref}",
            }
        ]
        if gaji_bersih > 0:
            lines_data.append({
                "akun_kode": akun_kas_kode,
                "debit": Decimal("0"),
                "kredit": gaji_bersih,
                "keterangan": f"Pembayaran gaji bersih {karyawan_nama}",
            })
        if instance.potongan_pph21 > 0:
            lines_data.append({
                "akun_kode": "2-3100",
                "debit": Decimal("0"),
                "kredit": instance.potongan_pph21,
                "keterangan": f"Hutang PPh 21 {karyawan_nama}",
            })
        if bpjs_total > 0:
            lines_data.append({
                "akun_kode": "2-3200",
                "debit": Decimal("0"),
                "kredit": bpjs_total,
                "keterangan": f"Hutang BPJS {karyawan_nama}",
            })
        if instance.potongan_lainnya > 0:
            lines_data.append({
                "akun_kode": "2-3000",
                "debit": Decimal("0"),
                "kredit": instance.potongan_lainnya,
                "keterangan": f"Potongan lain gaji {karyawan_nama}",
            })

        with db_transaction.atomic():
            # ── Buat jurnal: D:6-1000 Beban Gaji  K:Kas/Bank ──
            jurnal = create_jurnal(
                tanggal=tanggal,
                deskripsi=f"Pembayaran Gaji - {karyawan_nama} - {periode_ref}",
                lines_data=lines_data,
                sumber="payroll",
                sumber_id=instance.pk,
                sumber_ref=sumber_ref,
                cabang=cabang,
                user=instance.dibuat_oleh,
                auto_post=True,
            )

            # ── Buat mutasi kas/bank ──
            if kas_bank_account:
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe="keluar",
                    tanggal=tanggal,
                    jumlah=gaji_bersih,
                    deskripsi=f"Pembayaran Gaji {karyawan_nama} - {periode_ref}",
                    akun_lawan=akun_beban_gaji,
                    cabang=cabang,
                    metode_pembayaran=instance.metode_pembayaran,
                    sumber_app="hr",
                    sumber_model="Penggajian",
                    sumber_id=instance.pk,
                    sumber_ref=sumber_ref,
                    jurnal_entry=jurnal,
                    user=instance.dibuat_oleh,
                )

        logger.info(
            "[HR] Jurnal gaji dibuat: %s | Jurnal #%s | Rp %s",
            sumber_ref, jurnal.pk, f"{gaji_bersih:,.0f}",
        )

    except Exception as exc:
        logger.error(
            "[HR] Gagal buat auto-jurnal Penggajian #%s: %s",
            instance.pk, exc, exc_info=True,
        )
        try:
            from apps.activity_log.models import UserActivity
            UserActivity.objects.create(
                user=instance.dibuat_oleh,
                action="create",
                model_name="JurnalEntry",
                object_id=str(instance.pk),
                object_repr=f"GAGAL: Jurnal Gaji {instance.karyawan.nama if instance.karyawan else ''}",
                description=(
                    f"[JURNAL GAGAL] Auto-jurnal gaji Penggajian #{instance.pk} gagal. "
                    f"Error: {str(exc)[:200]}. Slip gaji tercatat tapi TIDAK ada jurnalnya."
                ),
                source_type="payroll",
                source_id=str(instance.pk),
            )
        except Exception as e:
            logger.warning("Gagal mencatat activity log: %s", e)
        # raise  # Disabled: transaksi tetap tersimpan meskipun jurnal gagal
