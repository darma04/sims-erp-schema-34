from decimal import Decimal
from datetime import date, datetime, time

from django.db import transaction
from django.utils import timezone

from apps.akuntansi.services import create_jurnal, get_akun_by_kode
from .models import KasBankAccount, KasBankTransaction


CREDIT_METHOD_CODES = {"CREDIT", "KREDIT", "TEMPO", "HUTANG", "PIUTANG"}
BANK_METHOD_CODES = {"TRF", "TRANSFER", "BANK", "QRIS", "EWALLET"}


def metode_is_credit(metode_pembayaran):
    if not metode_pembayaran:
        return False
    return (metode_pembayaran.kode or "").upper() in CREDIT_METHOD_CODES


def ensure_default_kas_bank_account(akun, metode_pembayaran=None):
    if not akun:
        return None

    tipe = "bank" if akun.kode == "1-1100" else "kas"
    if metode_pembayaran:
        metode_code = (metode_pembayaran.kode or "").upper()
        if metode_code in {"QRIS"}:
            tipe = "qris"
        elif metode_code in {"EWALLET"}:
            tipe = "ewallet"
        elif metode_code in BANK_METHOD_CODES:
            tipe = "bank"

    kode = f"AUTO-{akun.kode}"[:30]
    is_default = not KasBankAccount.objects.filter(aktif=True, is_default=True).exists()
    account, _ = KasBankAccount.objects.get_or_create(
        kode=kode,
        defaults={
            "nama": akun.nama,
            "tipe": tipe,
            "akun": akun,
            "aktif": True,
            "is_default": is_default,
        },
    )
    return account


def resolve_kas_bank_mapping(metode_pembayaran=None, default_akun_kode="1-1000"):
    """
    Return tuple: (KasBankAccount|None, Akun|None, akun_kode).
    Metode pembayaran adalah cara bayar; KasBankAccount dan Akun adalah ledger treasury/accounting.
    """
    account = None
    akun = None

    if metode_pembayaran:
        account = getattr(metode_pembayaran, "kas_bank_account", None)
        akun = getattr(metode_pembayaran, "akun_kas_bank", None)
        if account and not akun:
            akun = account.akun

    if not akun:
        fallback_code = default_akun_kode
        if metode_pembayaran and (metode_pembayaran.kode or "").upper() in BANK_METHOD_CODES:
            fallback_code = "1-1100"
        akun = get_akun_by_kode(fallback_code)

    if not account and akun:
        account = (
            KasBankAccount.objects.filter(akun=akun, aktif=True)
            .order_by("-is_default", "kode")
            .first()
        )

    if not account:
        account = KasBankAccount.objects.filter(aktif=True, is_default=True).order_by("kode").first()

    if not account and akun:
        account = ensure_default_kas_bank_account(akun, metode_pembayaran)

    akun_kode = akun.kode if akun else default_akun_kode
    return account, akun, akun_kode


def create_operational_mutation(
    *,
    akun_kas_bank,
    tipe,
    tanggal,
    jumlah,
    deskripsi,
    akun_lawan=None,
    cabang=None,
    metode_pembayaran=None,
    sumber_app,
    sumber_model,
    sumber_id,
    sumber_ref="",
    jurnal_entry=None,
    user=None,
):
    if not akun_kas_bank:
        return None

    jumlah = Decimal(str(jumlah or 0))
    if jumlah <= 0:
        return None
    if isinstance(tanggal, date) and not isinstance(tanggal, datetime):
        tanggal = timezone.make_aware(datetime.combine(tanggal, time.min))

    defaults = {
        "tanggal": tanggal,
        "jumlah": jumlah,
        "deskripsi": deskripsi,
        "akun_lawan": akun_lawan,
        "cabang": cabang,
        "metode_pembayaran": metode_pembayaran,
        "sumber_ref": sumber_ref,
        "jurnal_entry": jurnal_entry,
        "status": "posted",
        "dibuat_oleh": user,
    }
    mutation = KasBankTransaction.objects.filter(
        akun_kas_bank=akun_kas_bank,
        tipe=tipe,
        sumber_app=sumber_app,
        sumber_model=sumber_model,
        sumber_id=sumber_id,
        status="posted",
    ).first()
    created = mutation is None
    if created:
        mutation = KasBankTransaction.objects.create(
            akun_kas_bank=akun_kas_bank,
            tipe=tipe,
            sumber_app=sumber_app,
            sumber_model=sumber_model,
            sumber_id=sumber_id,
            **defaults,
        )
    if not created:
        update_fields = []
        for field, value in defaults.items():
            if getattr(mutation, field) is None and value is not None:
                setattr(mutation, field, value)
                update_fields.append(field)
        if update_fields:
            mutation.save(update_fields=update_fields)
    return mutation


def post_manual_kas_bank_transaction(kas_bank_transaction, user=None):
    if kas_bank_transaction.status != "posted" or kas_bank_transaction.jurnal_entry_id:
        return kas_bank_transaction.jurnal_entry

    if kas_bank_transaction.tipe not in {"masuk", "keluar", "penyesuaian_masuk", "penyesuaian_keluar"}:
        return None

    if not kas_bank_transaction.akun_lawan_id:
        raise ValueError("Akun lawan wajib diisi untuk mutasi posted.")

    tanggal = kas_bank_transaction.tanggal.date()
    kas_akun = kas_bank_transaction.akun_kas_bank.akun
    lawan = kas_bank_transaction.akun_lawan
    jumlah = kas_bank_transaction.jumlah
    is_incoming = kas_bank_transaction.tipe in {"masuk", "penyesuaian_masuk"}

    if is_incoming:
        lines_data = [
            {"akun": kas_akun, "debit": jumlah, "kredit": 0, "keterangan": kas_bank_transaction.deskripsi},
            {"akun": lawan, "debit": 0, "kredit": jumlah, "keterangan": kas_bank_transaction.deskripsi},
        ]
    else:
        lines_data = [
            {"akun": lawan, "debit": jumlah, "kredit": 0, "keterangan": kas_bank_transaction.deskripsi},
            {"akun": kas_akun, "debit": 0, "kredit": jumlah, "keterangan": kas_bank_transaction.deskripsi},
        ]

    with transaction.atomic():
        jurnal = create_jurnal(
            tanggal=tanggal,
            deskripsi=f"Mutasi Kas/Bank - {kas_bank_transaction.deskripsi}",
            lines_data=lines_data,
            sumber="kas_bank",
            sumber_id=kas_bank_transaction.pk,
            sumber_ref=kas_bank_transaction.nomor,
            cabang=kas_bank_transaction.cabang,
            user=user or kas_bank_transaction.dibuat_oleh,
            auto_post=True,
        )
        kas_bank_transaction.jurnal_entry = jurnal
        kas_bank_transaction.save(update_fields=["jurnal_entry", "diubah_pada"])
    return jurnal


def sync_saldo_awal_jurnal(kas_bank_account, user=None):
    """
    Sinkronisasi saldo_awal KasBankAccount dengan jurnal saldo awal di Accounting.
    Jika saldo_awal > 0 dan belum ada jurnal saldo awal, buat jurnal:
      D: Akun Kas/Bank (sesuai mapping)    Rp saldo_awal
      K: 3-1000 Modal Pemilik              Rp saldo_awal

    Jika sudah ada jurnal saldo awal sebelumnya, buat jurnal pembalik lalu buat baru.
    Ini memastikan Treasury dan Accounting selalu sinkron dari hari pertama.
    """
    from apps.akuntansi.models import JurnalEntry

    saldo_awal = Decimal(str(kas_bank_account.saldo_awal or 0))

    # Cari jurnal saldo awal yang sudah ada untuk akun ini
    existing_jurnal = JurnalEntry.objects.filter(
        sumber='kas_bank',
        sumber_ref=f'SALDO-AWAL-{kas_bank_account.kode}',
        is_posted=True,
    ).first()

    # Jika saldo_awal == 0 dan tidak ada jurnal existing, tidak perlu apa-apa
    if saldo_awal == 0 and not existing_jurnal:
        return None

    # Jika ada jurnal existing, balik dulu
    if existing_jurnal:
        from apps.akuntansi.services import create_jurnal_pembalik
        create_jurnal_pembalik(existing_jurnal, user=user)

    # Jika saldo_awal > 0, buat jurnal baru
    if saldo_awal > 0:
        akun_kas = kas_bank_account.akun
        akun_modal = get_akun_by_kode('3-1000')
        if not akun_modal:
            return None

        from django.utils import timezone as tz
        lines_data = [
            {'akun': akun_kas, 'debit': saldo_awal, 'kredit': Decimal('0'),
             'keterangan': f'Saldo awal {kas_bank_account.nama}'},
            {'akun': akun_modal, 'debit': Decimal('0'), 'kredit': saldo_awal,
             'keterangan': f'Saldo awal {kas_bank_account.nama}'},
        ]

        jurnal = create_jurnal(
            tanggal=tz.now().date(),
            deskripsi=f'Saldo Awal Kas/Bank - {kas_bank_account.nama}',
            lines_data=lines_data,
            sumber='kas_bank',
            sumber_ref=f'SALDO-AWAL-{kas_bank_account.kode}',
            user=user,
            auto_post=True,
        )
        return jurnal

    return None


def post_kas_bank_transfer(kas_bank_transfer, user=None):
    if kas_bank_transfer.status != "posted" or kas_bank_transfer.jurnal_entry_id:
        return kas_bank_transfer.jurnal_entry

    tanggal = kas_bank_transfer.tanggal.date()
    biaya_admin = Decimal(str(kas_bank_transfer.biaya_admin or 0))
    jumlah = Decimal(str(kas_bank_transfer.jumlah or 0))
    total_keluar = jumlah + biaya_admin
    akun_biaya = kas_bank_transfer.akun_biaya_admin or get_akun_by_kode("6-9000")

    lines_data = [
        {
            "akun": kas_bank_transfer.ke_akun.akun,
            "debit": jumlah,
            "kredit": 0,
            "keterangan": f"Transfer masuk {kas_bank_transfer.nomor}",
        },
        {
            "akun": kas_bank_transfer.dari_akun.akun,
            "debit": 0,
            "kredit": total_keluar,
            "keterangan": f"Transfer keluar {kas_bank_transfer.nomor}",
        },
    ]
    if biaya_admin > 0:
        if not akun_biaya:
            raise ValueError("Akun biaya admin wajib tersedia untuk transfer dengan biaya admin.")
        lines_data.append(
            {
                "akun": akun_biaya,
                "debit": biaya_admin,
                "kredit": 0,
                "keterangan": f"Biaya admin transfer {kas_bank_transfer.nomor}",
            }
        )

    with transaction.atomic():
        jurnal = create_jurnal(
            tanggal=tanggal,
            deskripsi=f"Transfer Kas/Bank - {kas_bank_transfer.nomor}",
            lines_data=lines_data,
            sumber="kas_bank",
            sumber_id=kas_bank_transfer.pk,
            sumber_ref=kas_bank_transfer.nomor,
            cabang=kas_bank_transfer.cabang,
            user=user or kas_bank_transfer.dibuat_oleh,
            auto_post=True,
        )
        kas_bank_transfer.jurnal_entry = jurnal
        kas_bank_transfer.save(update_fields=["jurnal_entry", "diubah_pada"])

        create_operational_mutation(
            akun_kas_bank=kas_bank_transfer.dari_akun,
            tipe="transfer_keluar",
            tanggal=kas_bank_transfer.tanggal,
            jumlah=total_keluar,
            deskripsi=f"Transfer ke {kas_bank_transfer.ke_akun.nama}",
            akun_lawan=kas_bank_transfer.ke_akun.akun,
            cabang=kas_bank_transfer.cabang,
            sumber_app="kas_bank",
            sumber_model="KasBankTransfer",
            sumber_id=kas_bank_transfer.pk,
            sumber_ref=kas_bank_transfer.nomor,
            jurnal_entry=jurnal,
            user=user or kas_bank_transfer.dibuat_oleh,
        )
        create_operational_mutation(
            akun_kas_bank=kas_bank_transfer.ke_akun,
            tipe="transfer_masuk",
            tanggal=kas_bank_transfer.tanggal,
            jumlah=jumlah,
            deskripsi=f"Transfer dari {kas_bank_transfer.dari_akun.nama}",
            akun_lawan=kas_bank_transfer.dari_akun.akun,
            cabang=kas_bank_transfer.cabang,
            sumber_app="kas_bank",
            sumber_model="KasBankTransfer",
            sumber_id=kas_bank_transfer.pk,
            sumber_ref=kas_bank_transfer.nomor,
            jurnal_entry=jurnal,
            user=user or kas_bank_transfer.dibuat_oleh,
        )
    return jurnal
