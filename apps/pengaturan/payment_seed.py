from django.apps import apps
from django.db import transaction
from django.db.models import Q


DEFAULT_PAYMENT_METHODS = [
    {
        "kode": "CASH",
        "nama": "Tunai",
        "aliases": ["Cash"],
        "tipe": "tunai",
        "deskripsi": "Metode pembayaran tunai default.",
    },
    {
        "kode": "BANK",
        "nama": "Transfer Bank",
        "aliases": ["Bank Transfer", "Transfer"],
        "tipe": "non_tunai",
        "deskripsi": "Metode pembayaran transfer bank default.",
    },
    {
        "kode": "QRIS",
        "nama": "QRIS",
        "aliases": [],
        "tipe": "non_tunai",
        "deskripsi": "Metode pembayaran QRIS default.",
    },
    {
        "kode": "EWALLET",
        "nama": "E-Wallet",
        "aliases": ["E Wallet", "Dompet Digital"],
        "tipe": "non_tunai",
        "deskripsi": "Metode pembayaran dompet digital default.",
    },
    {
        "kode": "CREDIT",
        "nama": "Kredit/Tempo",
        "aliases": ["Kredit", "Tempo"],
        "tipe": "kredit",
        "deskripsi": "Metode pembayaran tempo untuk transaksi piutang.",
    },
]


def _get_model(label):
    try:
        return apps.get_model(label)
    except LookupError:
        return None


def _find_existing_method(model, item):
    metode = model.objects.filter(kode=item["kode"]).first()
    if metode:
        return metode

    name_filter = Q(nama__iexact=item["nama"])
    for alias in item.get("aliases", []):
        name_filter |= Q(nama__iexact=alias)
    return model.objects.filter(name_filter).order_by("id").first()


def _save_method(metode, item):
    changed = False
    for field in ["nama", "tipe", "deskripsi"]:
        value = item[field]
        if getattr(metode, field) != value:
            setattr(metode, field, value)
            changed = True

    if not metode.kode:
        metode.kode = item["kode"]
        changed = True
    if not metode.aktif:
        metode.aktif = True
        changed = True
    if changed:
        metode.save()
    return changed


@transaction.atomic
def seed_default_payment_methods():
    MetodePembayaran = _get_model("pos.MetodePembayaran")
    if MetodePembayaran is None:
        raise RuntimeError("Model MetodePembayaran tidak ditemukan.")

    stats = {
        "created": 0,
        "updated": 0,
        "branches_updated": 0,
        "products_updated": 0,
        "payroll_updated": 0,
        "expenses_updated": 0,
        "po_updated": 0,
        "so_updated": 0,
        "pos_updated": 0,
    }
    seeded = {}

    for item in DEFAULT_PAYMENT_METHODS:
        metode = _find_existing_method(MetodePembayaran, item)
        if metode:
            if _save_method(metode, item):
                stats["updated"] += 1
        else:
            metode = MetodePembayaran.objects.create(
                kode=item["kode"],
                nama=item["nama"],
                tipe=item["tipe"],
                deskripsi=item["deskripsi"],
                aktif=True,
            )
            stats["created"] += 1
        seeded[item["kode"]] = metode

    default_cash = seeded.get("CASH") or MetodePembayaran.objects.filter(aktif=True, tipe="tunai").first()
    default_credit = seeded.get("CREDIT") or default_cash
    if not default_cash:
        return stats

    Gudang = _get_model("produk.Gudang")
    if Gudang is not None:
        stats["branches_updated"] = Gudang.objects.filter(
            aktif=True,
            metode_pembayaran_default__isnull=True,
        ).update(metode_pembayaran_default=default_cash)

    Produk = _get_model("produk.Produk")
    if Produk is not None:
        stats["products_updated"] = Produk.objects.filter(
            aktif=True,
            metode_pembayaran__isnull=True,
        ).update(metode_pembayaran=default_cash)

    Penggajian = _get_model("hr.Penggajian")
    if Penggajian is not None:
        for slip in Penggajian.objects.filter(status="dibayar").select_related("cabang", "karyawan"):
            update_fields = []
            if not slip.cabang_id and getattr(slip, "karyawan_id", None):
                slip.cabang = getattr(slip.karyawan, "cabang", None)
                update_fields.append("cabang")
            if not slip.metode_pembayaran_id:
                slip.metode_pembayaran = getattr(slip.cabang, "metode_pembayaran_default", None) or default_cash
                update_fields.append("metode_pembayaran")
            if update_fields:
                slip.save(update_fields=update_fields)
                stats["payroll_updated"] += 1

    TransaksiBiaya = _get_model("biaya.TransaksiBiaya")
    if TransaksiBiaya is not None:
        stats["expenses_updated"] = TransaksiBiaya.objects.filter(
            status="approved",
            metode_pembayaran__isnull=True,
        ).update(metode_pembayaran=default_cash)

    PurchaseOrder = _get_model("pembelian.PurchaseOrder")
    if PurchaseOrder is not None:
        stats["po_updated"] = PurchaseOrder.objects.filter(
            status__in=["approved", "received"],
            metode_pembayaran__isnull=True,
        ).update(metode_pembayaran=default_cash)

    SalesOrder = _get_model("penjualan.SalesOrder")
    if SalesOrder is not None:
        stats["so_updated"] = SalesOrder.objects.filter(
            status__in=["confirmed", "delivered", "completed"],
            metode_pembayaran__isnull=True,
        ).update(metode_pembayaran=default_credit)

    POSTransaction = _get_model("pos.POSTransaction")
    if POSTransaction is not None:
        stats["pos_updated"] = POSTransaction.objects.filter(
            metode_pembayaran__isnull=True,
        ).update(metode_pembayaran=default_cash)

    return stats
