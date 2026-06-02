from decimal import Decimal

from django.db.models import Sum


ZERO = Decimal("0")


def _sum(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def _has_field(queryset, field_name):
    return any(field.name == field_name for field in queryset.model._meta.get_fields())


def aggregate_sales_amounts(queryset):
    """
    Agregat transaksi penjualan untuk laporan operasional.

    subtotal = nilai barang/jasa sebelum diskon header dan PPN
    diskon = pengurang pendapatan
    ongkir = biaya pengiriman yang ditagihkan, termasuk pendapatan operasional
    pajak = PPN keluaran, bukan pendapatan
    total = nilai tagihan/kas masuk
    net = pendapatan bersih sebelum PPN
    """
    aggregate_fields = {
        "_subtotal": Sum("subtotal"),
        "_diskon": Sum("diskon"),
        "_pajak": Sum("pajak"),
        "_total_harga": Sum("total_harga"),
    }
    if _has_field(queryset, "biaya_pengiriman"):
        aggregate_fields["_biaya_pengiriman"] = Sum("biaya_pengiriman")

    result = queryset.aggregate(**aggregate_fields)
    subtotal = result["_subtotal"] or ZERO
    diskon = result["_diskon"] or ZERO
    pajak = result["_pajak"] or ZERO
    biaya_pengiriman = result.get("_biaya_pengiriman") or ZERO
    total = result["_total_harga"] or ZERO
    return {
        "subtotal": subtotal,
        "diskon": diskon,
        "biaya_pengiriman": biaya_pengiriman,
        "pajak": pajak,
        "total": total,
        "net": subtotal - diskon + biaya_pengiriman,
    }


def aggregate_purchase_amounts(queryset):
    """
    Agregat transaksi pembelian untuk laporan operasional.

    subtotal = nilai pembelian/persediaan sebelum PPN
    ongkir = biaya kirim pembelian yang dikapitalisasi ke persediaan/DPP
    pajak = PPN masukan, bukan beban
    total = nilai pembayaran/hutang
    """
    aggregate_fields = {
        "_subtotal": Sum("subtotal"),
        "_pajak": Sum("pajak"),
        "_total_harga": Sum("total_harga"),
    }
    if _has_field(queryset, "biaya_pengiriman"):
        aggregate_fields["_biaya_pengiriman"] = Sum("biaya_pengiriman")

    result = queryset.aggregate(**aggregate_fields)
    subtotal = result["_subtotal"] or ZERO
    pajak = result["_pajak"] or ZERO
    biaya_pengiriman = result.get("_biaya_pengiriman") or ZERO
    total = result["_total_harga"] or ZERO
    return {
        "subtotal": subtotal + biaya_pengiriman,
        "biaya_pengiriman": biaya_pengiriman,
        "pajak": pajak,
        "total": total,
    }
