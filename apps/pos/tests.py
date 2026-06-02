from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from apps.akuntansi.models import JurnalEntry, JurnalLine
from apps.akuntansi.services import get_akun_by_kode, seed_default_coa
from apps.hr.models import Departemen, Jabatan, Karyawan, Penggajian
from apps.kas_bank.models import KasBankAccount
from apps.piutang.models import Piutang
from apps.pos.models import MetodePembayaran, POSTransaction, POSTransactionItem
from apps.produk.models import Gudang, Kategori, Produk, Satuan, Stok
from apps.penjualan.models import Customer


class AccountingFixtureMixin:
    def setup_accounting_fixture(self):
        seed_default_coa()

        self.user = User.objects.create_user(username="kasir1", password="password123")
        self.kategori = Kategori.objects.create(nama="Elektronik")
        self.satuan_pcs = Satuan.objects.create(nama="Pcs", singkatan="pcs")

        self.gudang = Gudang.objects.create(nama="Gudang Utama", kode="GDG-01")
        self.produk = Produk.objects.create(
            nama="Lampu LED",
            sku="PRD-002",
            kategori=self.kategori,
            satuan=self.satuan_pcs,
            harga_beli=Decimal("5000"),
            harga_jual=Decimal("80000"),
        )
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=50)

        akun_kas = get_akun_by_kode("1-1000")
        self.kas_bank_account = KasBankAccount.objects.create(
            kode="CASH",
            nama="Kas Tunai",
            tipe="kas",
            akun=akun_kas,
            is_default=True,
            dibuat_oleh=self.user,
        )
        self.metode_tunai = MetodePembayaran.objects.create(
            nama="Tunai",
            kode="CASH",
            saldo=Decimal("10000000"),
            kas_bank_account=self.kas_bank_account,
            akun_kas_bank=akun_kas,
        )
        self.produk.metode_pembayaran = self.metode_tunai
        self.produk.save(update_fields=["metode_pembayaran"])

    def assert_journal_balanced(self, jurnal):
        totals = JurnalLine.objects.filter(jurnal=jurnal)
        debit = sum(line.debit for line in totals)
        kredit = sum(line.kredit for line in totals)
        self.assertEqual(debit, kredit)


class MetodePembayaranFinancialTest(AccountingFixtureMixin, TestCase):
    def setUp(self):
        self.setup_accounting_fixture()
        self.customer = Customer.objects.create(kode="CUST-001", nama="Walk in Customer")

    def test_total_pengeluaran_menggunakan_jumlah_konversi(self):
        pengeluaran_awal = self.metode_tunai.total_pengeluaran
        self.assertEqual(pengeluaran_awal, Decimal("250000"))

        trx = POSTransaction.objects.create(
            nomor_transaksi="POS-001",
            kasir=self.user,
            customer=self.customer,
            metode_pembayaran=self.metode_tunai,
            gudang=self.gudang,
            status="draft",
            jumlah_bayar=Decimal("200000"),
        )
        POSTransactionItem.objects.create(
            transaction=trx,
            produk=self.produk,
            satuan_transaksi=self.satuan_pcs,
            jumlah=Decimal("20"),
            jumlah_konversi=Decimal("20"),
            harga_satuan=Decimal("80000"),
        )

        trx.status = "paid"
        trx.save()

        pengeluaran_akhir = self.metode_tunai.total_pengeluaran
        self.assertEqual(pengeluaran_akhir, Decimal("350000"))


class POSKasbonAccountingTest(AccountingFixtureMixin, TestCase):
    def setUp(self):
        self.setup_accounting_fixture()

    def test_unpaid_pos_without_customer_creates_customer_piutang_and_journal(self):
        trx = POSTransaction.objects.create(
            nomor_transaksi="POS-KASBON-001",
            kasir=self.user,
            nama_customer="Walk-in Kasbon",
            metode_pembayaran=self.metode_tunai,
            gudang=self.gudang,
            status="draft",
        )
        POSTransactionItem.objects.create(
            transaction=trx,
            produk=self.produk,
            satuan_transaksi=self.satuan_pcs,
            jumlah=Decimal("2"),
            jumlah_konversi=Decimal("2"),
            harga_satuan=Decimal("80000"),
        )

        trx.status = "unpaid"
        trx.save()
        trx.refresh_from_db()

        self.assertIsNotNone(trx.customer_id)
        self.assertEqual(trx.customer.nama, "Walk-in Kasbon")

        piutang = Piutang.objects.get(sumber="pos", pos_transaction=trx)
        self.assertEqual(piutang.customer_id, trx.customer_id)
        self.assertEqual(piutang.jumlah_total, trx.total_harga)
        self.assertEqual(piutang.status, "belum_bayar")

        jurnals = JurnalEntry.objects.filter(sumber="pos", sumber_id=trx.pk)
        self.assertTrue(jurnals.filter(sumber_ref=trx.nomor_transaksi).exists())
        self.assertTrue(jurnals.filter(sumber_ref=f"{trx.nomor_transaksi}_hpp").exists())
        for jurnal in jurnals:
            self.assert_journal_balanced(jurnal)


class PayrollAccountingTest(AccountingFixtureMixin, TestCase):
    def setUp(self):
        self.setup_accounting_fixture()
        self.departemen = Departemen.objects.create(kode="FIN", nama="Finance")
        self.jabatan = Jabatan.objects.create(
            kode="FIN-STF",
            nama="Staff Finance",
            departemen=self.departemen,
            gaji_pokok=Decimal("5000000"),
        )
        self.karyawan = Karyawan.objects.create(
            nik="EMP-001",
            nama="Staff Payroll",
            jabatan=self.jabatan,
            departemen=self.departemen,
            cabang=self.gudang,
            tanggal_masuk=date(2026, 1, 1),
            gaji_pokok=Decimal("5000000"),
            dibuat_oleh=self.user,
        )

    def test_penggajian_dibayar_uses_payroll_source_and_is_idempotent(self):
        penggajian = Penggajian.objects.create(
            karyawan=self.karyawan,
            periode_bulan=5,
            periode_tahun=2026,
            gaji_pokok=Decimal("5000000"),
            status="dibayar",
            tanggal_bayar=date(2026, 5, 25),
            metode_pembayaran=self.metode_tunai,
            dibuat_oleh=self.user,
        )

        payroll_journals = JurnalEntry.objects.filter(
            sumber="payroll",
            sumber_id=penggajian.pk,
        )
        self.assertEqual(payroll_journals.count(), 1)
        self.assertFalse(JurnalEntry.objects.filter(sumber="hr", sumber_id=penggajian.pk).exists())
        self.assert_journal_balanced(payroll_journals.get())

        penggajian.save()
        self.assertEqual(payroll_journals.count(), 1)
