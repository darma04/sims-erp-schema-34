from decimal import Decimal

from apps.akuntansi.services import create_jurnal
from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping


def ensure_penyusutan_accounting(penyusutan, user=None, tanggal=None):
    """
    Pastikan record Penyusutan memiliki jurnal D:Beban Penyusutan K:Akumulasi.
    Idempotent: jika jurnal sudah ada, langsung dikembalikan.
    """
    if penyusutan.jurnal_id:
        return penyusutan.jurnal

    aset = penyusutan.aset
    jumlah = Decimal(str(penyusutan.jumlah or 0))
    if jumlah <= 0:
        raise ValueError("Nominal penyusutan harus lebih besar dari 0.")

    jurnal = create_jurnal(
        tanggal=tanggal or penyusutan.dibuat_pada.date(),
        deskripsi=f"Penyusutan {aset.nama} - {penyusutan.bulan:02d}/{penyusutan.tahun}",
        lines_data=[
            {
                "akun_kode": "6-4000",
                "debit": jumlah,
                "kredit": Decimal("0"),
                "keterangan": f"Beban penyusutan {aset.kode}",
            },
            {
                "akun_kode": "1-4100",
                "debit": Decimal("0"),
                "kredit": jumlah,
                "keterangan": f"Akumulasi penyusutan {aset.kode}",
            },
        ],
        sumber="aset",
        sumber_id=penyusutan.pk,
        sumber_ref=f"{aset.kode}-SUSUT-{penyusutan.tahun}-{penyusutan.bulan:02d}",
        cabang=aset.cabang,
        user=user or penyusutan.created_by,
        auto_post=True,
    )
    penyusutan.jurnal = jurnal
    penyusutan.save(update_fields=["jurnal"])
    return jurnal


def build_disposal_lines(disposal, kas_akun_kode):
    aset = disposal.aset
    akumulasi = Decimal(str(aset.akumulasi_penyusutan or 0))
    harga_jual = Decimal(str(disposal.harga_jual or 0))
    laba_rugi = Decimal(str(disposal.laba_rugi or 0))
    akun_aset_kode = aset.akun_aset.kode if aset.akun_aset else "1-4000"

    lines = [
        {
            "akun_kode": "1-4100",
            "debit": akumulasi,
            "kredit": Decimal("0"),
            "keterangan": f"Hapus akumulasi penyusutan {aset.kode}",
        },
    ]
    if harga_jual > 0:
        lines.append({
            "akun_kode": kas_akun_kode,
            "debit": harga_jual,
            "kredit": Decimal("0"),
            "keterangan": f"Kas dari penjualan aset {aset.kode}",
        })

    lines.append({
        "akun_kode": akun_aset_kode,
        "debit": Decimal("0"),
        "kredit": aset.harga_perolehan,
        "keterangan": f"Hapus aset {aset.kode}",
    })

    if laba_rugi > 0:
        lines.append({
            "akun_kode": "4-2000",
            "debit": Decimal("0"),
            "kredit": laba_rugi,
            "keterangan": f"Laba penjualan aset {aset.kode}",
        })
    elif laba_rugi < 0:
        lines.append({
            "akun_kode": "6-5000",
            "debit": abs(laba_rugi),
            "kredit": Decimal("0"),
            "keterangan": f"Rugi penjualan aset {aset.kode}",
        })
    return lines


def ensure_disposal_accounting(disposal, user=None):
    """
    Pastikan disposal aset memiliki jurnal dan mutasi kas/bank jika dijual.
    Idempotent: jika jurnal sudah ada, langsung dikembalikan.
    """
    if disposal.jurnal_id:
        return disposal.jurnal

    aset = disposal.aset
    kas_bank_account, _, kas_akun_kode = resolve_kas_bank_mapping(None)
    jurnal = create_jurnal(
        tanggal=disposal.tanggal,
        deskripsi=f"Disposal aset: {aset.nama} ({disposal.get_tipe_display()})",
        lines_data=build_disposal_lines(disposal, kas_akun_kode),
        sumber="aset",
        sumber_id=disposal.pk,
        sumber_ref=f"{aset.kode}-DISPOSAL-{disposal.pk}",
        cabang=aset.cabang,
        user=user or disposal.created_by,
        auto_post=True,
    )
    disposal.jurnal = jurnal
    disposal.save(update_fields=["jurnal"])

    harga_jual = Decimal(str(disposal.harga_jual or 0))
    if harga_jual > 0:
        create_operational_mutation(
            akun_kas_bank=kas_bank_account,
            tipe="masuk",
            tanggal=disposal.tanggal,
            jumlah=harga_jual,
            deskripsi=f"Penjualan aset tetap {aset.kode}",
            akun_lawan=aset.akun_aset,
            cabang=aset.cabang,
            sumber_app="aset",
            sumber_model="DisposalAset",
            sumber_id=disposal.pk,
            sumber_ref=aset.kode,
            jurnal_entry=jurnal,
            user=user or disposal.created_by,
        )
    return jurnal
