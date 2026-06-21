"""
Service Center accounting integration.

This module keeps SIMS-specific service revenue and sparepart cost aligned with
the accounting and Kas/Bank modules without changing the shared Accounting35
models.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum


SERVICE_JOURNAL_SOURCE = "service"
SERVICE_SOURCE_APP = "service_center"
SERVICE_SOURCE_MODEL = "OrderService"


def _decimal(value):
    return Decimal(str(value or 0))


def get_service_payment_amount(order):
    """Return the amount that should currently be recognized as paid."""
    if order.status == "dibatalkan" or order.status_bayar == "belum_bayar":
        return Decimal("0")

    total = _decimal(order.biaya_akhir or order.total_biaya)
    if total <= 0:
        return Decimal("0")

    if order.status_bayar == "dp":
        return min(_decimal(order.dp_bayar), total)
    if order.status_bayar == "lunas":
        return total
    return Decimal("0")


def get_service_hpp_amount(order):
    """Return inventory cost for spareparts used in a fully paid service order."""
    if order.status_bayar != "lunas" or order.status == "dibatalkan":
        return Decimal("0")

    total = Decimal("0")
    for penggunaan in order.penggunaan_sparepart.select_related("produk"):
        harga_beli = _decimal(getattr(penggunaan.produk, "harga_beli", 0))
        total += _decimal(penggunaan.jumlah) * harga_beli
    return total


def _payment_ref(order):
    return f"{order.nomor_service}/PAYMENT"


def _active_service_journals(order):
    from apps.akuntansi.models import JurnalEntry

    return JurnalEntry.objects.filter(
        sumber=SERVICE_JOURNAL_SOURCE,
        sumber_id=order.pk,
        is_reversed=False,
    ).exclude(sumber_ref__endswith="_reversal")


def _active_mutation(order):
    from apps.kas_bank.models import KasBankTransaction

    return KasBankTransaction.objects.filter(
        sumber_app=SERVICE_SOURCE_APP,
        sumber_model=SERVICE_SOURCE_MODEL,
        sumber_id=order.pk,
        status="posted",
    ).first()


def _journal_signature(journal):
    income_total = journal.lines.filter(
        akun__kode__in=["4-2000", "2-2000"]
    ).aggregate(total=Sum("kredit"))["total"] or Decimal("0")
    hpp_total = journal.lines.filter(
        akun__kode="5-1000"
    ).aggregate(total=Sum("debit"))["total"] or Decimal("0")
    return _decimal(income_total), _decimal(hpp_total)


def cancel_service_payment_accounting(order, user=None, reason="Pembatalan accounting service"):
    """Reverse active service journals and cancel active Kas/Bank mutations."""
    from apps.akuntansi.services import create_reversal_jurnal
    from apps.kas_bank.models import KasBankTransaction

    with transaction.atomic():
        for journal in _active_service_journals(order).select_for_update():
            create_reversal_jurnal(journal, alasan=reason, user=user)

        KasBankTransaction.objects.filter(
            sumber_app=SERVICE_SOURCE_APP,
            sumber_model=SERVICE_SOURCE_MODEL,
            sumber_id=order.pk,
            status="posted",
        ).update(status="cancelled")


def sync_service_payment_accounting(order, user=None):
    """
    Synchronize service payment to Accounting and Kas/Bank.

    - DP/lunas creates one active journal and one Kas/Bank mutation.
    - Lunas also records sparepart HPP: D HPP, K Persediaan.
    - Any amount/method/HPP change reverses the old active journal and recreates it.
    - Belum bayar/dibatalkan reverses active service accounting.
    """
    from apps.akuntansi.services import create_jurnal
    from apps.kas_bank.services import (
        create_operational_mutation,
        metode_is_credit,
        resolve_kas_bank_mapping,
    )

    with transaction.atomic():
        order = order.__class__.objects.select_for_update().get(pk=order.pk)
        amount = get_service_payment_amount(order)
        hpp_amount = get_service_hpp_amount(order)

        if amount <= 0:
            cancel_service_payment_accounting(order, user=user, reason="Service belum dibayar atau dibatalkan")
            return None

        if not order.metode_pembayaran_id:
            raise ValueError("Metode pembayaran wajib dipilih untuk accounting service.")
        if metode_is_credit(order.metode_pembayaran):
            raise ValueError("Metode Kredit/Tempo tidak boleh dipakai untuk pembayaran service DP/lunas.")

        mutation = _active_mutation(order)
        active_journals = list(_active_service_journals(order).select_for_update())
        if len(active_journals) == 1 and mutation:
            current_amount, current_hpp = _journal_signature(active_journals[0])
            same_amount = current_amount == amount
            same_hpp = current_hpp == hpp_amount
            same_method = mutation.metode_pembayaran_id == order.metode_pembayaran_id
            same_cabang = mutation.cabang_id == order.cabang_id
            if same_amount and same_hpp and same_method and same_cabang:
                return active_journals[0]

        cancel_service_payment_accounting(order, user=user, reason="Perubahan pembayaran service")

        kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(order.metode_pembayaran)

        total_tagihan = _decimal(order.biaya_akhir or order.total_biaya)
        pajak = _decimal(order.pajak)
        ppn_portion = Decimal("0")
        if pajak > 0 and total_tagihan > 0:
            ppn_portion = (pajak * amount / total_tagihan).quantize(Decimal("0.01"))
        pendapatan = amount - ppn_portion

        lines_data = [
            {
                "akun_kode": akun_kas_kode,
                "debit": amount,
                "kredit": Decimal("0"),
                "keterangan": f"Penerimaan service {order.nomor_service}",
            },
            {
                "akun_kode": "4-2000",
                "debit": Decimal("0"),
                "kredit": pendapatan,
                "keterangan": f"Pendapatan jasa service {order.nomor_service}",
            },
        ]
        if ppn_portion > 0:
            lines_data.append({
                "akun_kode": "2-2000",
                "debit": Decimal("0"),
                "kredit": ppn_portion,
                "keterangan": f"PPN Keluaran service {order.nomor_service}",
            })
        if hpp_amount > 0:
            lines_data.extend([
                {
                    "akun_kode": "5-1000",
                    "debit": hpp_amount,
                    "kredit": Decimal("0"),
                    "keterangan": f"HPP sparepart service {order.nomor_service}",
                },
                {
                    "akun_kode": "1-3000",
                    "debit": Decimal("0"),
                    "kredit": hpp_amount,
                    "keterangan": f"Pengurangan persediaan sparepart service {order.nomor_service}",
                },
            ])

        tanggal = order.tanggal_diambil or order.tanggal_selesai or order.tanggal_masuk
        tanggal_jurnal = tanggal.date() if hasattr(tanggal, "date") else tanggal

        try:
            journal = create_jurnal(
                tanggal=tanggal_jurnal,
                deskripsi=f"Pendapatan Service - {order.nomor_service}",
                lines_data=lines_data,
                sumber=SERVICE_JOURNAL_SOURCE,
                sumber_id=order.pk,
                sumber_ref=_payment_ref(order),
                cabang=order.cabang,
                user=user or order.diterima_oleh,
                auto_post=True,
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'[Service Center] Gagal create_jurnal untuk {order.nomor_service}: {e}', exc_info=True)
            try:
                from apps.activity_log.models import UserActivity
                UserActivity.objects.create(
                    user=user or order.diterima_oleh,
                    action='create',
                    model_name='JurnalEntry',
                    object_id=str(order.pk),
                    object_repr=f'GAGAL: Jurnal Service {order.nomor_service}',
                    description=f'[JURNAL GAGAL] Auto-jurnal untuk Service Center {order.nomor_service} gagal dibuat. Error: {str(e)[:200]}',
                    source_type='service_center',
                    source_id=str(order.pk),
                    source_repr=order.nomor_service,
                )
            except Exception as e:
                logger.warning("Gagal mencatat activity log: %s", e)
            raise

        create_operational_mutation(
            akun_kas_bank=kas_bank_account,
            tipe="masuk",
            tanggal=tanggal,
            jumlah=amount,
            deskripsi=f"Penerimaan Service {order.nomor_service}",
            akun_lawan=None,
            cabang=order.cabang,
            metode_pembayaran=order.metode_pembayaran,
            sumber_app=SERVICE_SOURCE_APP,
            sumber_model=SERVICE_SOURCE_MODEL,
            sumber_id=order.pk,
            sumber_ref=order.nomor_service,
            jurnal_entry=journal,
            user=user or order.diterima_oleh,
        )

        return journal
