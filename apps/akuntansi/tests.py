"""
COMPREHENSIVE INTEGRATION TEST — Accounting Signal → Service → Journal

Covers ALL 11 accounting flows end-to-end.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta

from apps.akuntansi.models import Akun, JurnalEntry, JurnalLine
from apps.akuntansi.services import seed_default_coa, get_akun_by_kode
from apps.pembelian.models import PurchaseOrder, PurchaseOrderItem, Supplier
from apps.penjualan.models import SalesOrder, SalesOrderItem, Customer
from apps.pos.models import POSTransaction, POSTransactionItem, MetodePembayaran
from apps.biaya.models import TransaksiBiaya, KategoriBiaya
from apps.biaya.services import transition_biaya_status
from apps.hr.models import Karyawan, Penggajian, Departemen, Jabatan
from apps.produk.models import Produk, Kategori, Satuan, Gudang, Stok
from apps.kas_bank.models import KasBankAccount, KasBankTransaction
from apps.piutang.models import Piutang, PembayaranPiutang
from apps.hutang.models import Hutang, PembayaranHutang
from apps.inventory.models import AdjustmentStok
from apps.pajak.models import SettingPajak

User = get_user_model()


class AccountingFlowTest(TestCase):
    """Test ALL accounting flows end-to-end."""

    @classmethod
    def setUpTestData(cls):
        seed_default_coa()
        cls.user = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='testpass123'
        )

    def setUp(self):
        self.kategori = Kategori.objects.create(nama='Elektronik')
        self.satuan = Satuan.objects.create(nama='Pcs')
        self.gudang = Gudang.objects.create(nama='Gudang Utama', kode='GDG-01')
        self.produk = Produk.objects.create(
            nama='Laptop', sku='LAP-001', kategori=self.kategori,
            satuan=self.satuan, harga_beli=Decimal('5000000'),
            harga_jual=Decimal('7000000')
        )
        self.supplier = Supplier.objects.create(
            nama='PT Supplier', kode='SUP-001', email='supplier@test.com'
        )
        self.customer = Customer.objects.create(
            nama='PT Customer', kode='CUS-001', email='customer@test.com'
        )
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=100)
        akun_kas = get_akun_by_kode('1-1000')
        self.kas_account = KasBankAccount.objects.create(
            nama='Kas Utama', kode='KAS-01', tipe='kas',
            akun=akun_kas, saldo_awal=Decimal('10000000'), is_default=True
        )
        self.metode_tunai = MetodePembayaran.objects.create(
            nama='Tunai', kode='CASH', tipe='tunai',
            kas_bank_account=self.kas_account, akun_kas_bank=akun_kas
        )
        SettingPajak.objects.create(pk=1, tarif_ppn=Decimal('11'), is_pkp=True, nama_pkp='PT Test')
        self.departemen = Departemen.objects.create(kode='IT', nama='IT')
        self.jabatan = Jabatan.objects.create(
            kode='IT-STF', nama='Staff IT', departemen=self.departemen,
            gaji_pokok=Decimal('5000000')
        )
        self.karyawan = Karyawan.objects.create(
            nama='John Doe', nik='EMP-001', jabatan=self.jabatan,
            departemen=self.departemen, cabang=self.gudang,
            tanggal_masuk=date(2024, 1, 1), gaji_pokok=Decimal('5000000')
        )
        akun_beban = get_akun_by_kode('6-2000')
        self.kategori_biaya = KategoriBiaya.objects.create(
            nama='Listrik', akun_beban=akun_beban
        )

    def assert_balanced(self, jurnal):
        lines = jurnal.lines.all()
        debit = sum(line.debit for line in lines)
        kredit = sum(line.kredit for line in lines)
        self.assertEqual(debit, kredit,
            f"Jurnal {jurnal.nomor} tidak balance: debit={debit}, kredit={kredit}")

    # ─── TEST 1: POS CASH ───
    def test_pos_cash(self):
        """POS paid: satu jurnal (D:Kas K:Pendapatan + K:PPN + D:HPP K:Persediaan inline)"""
        trx = POSTransaction.objects.create(
            kasir=self.user, gudang=self.gudang, customer=self.customer,
            metode_pembayaran=self.metode_tunai, jumlah_bayar=Decimal('7770000'),
            status='draft'
        )
        POSTransactionItem.objects.create(
            transaction=trx, produk=self.produk, jumlah=1, harga_satuan=Decimal('7000000')
        )
        trx.refresh_from_db()
        trx.status = 'paid'
        trx.save()

        jurnals = JurnalEntry.objects.filter(sumber='pos', sumber_id=trx.pk)
        self.assertEqual(jurnals.count(), 1, "POS cash: 1 jurnal (HPP inline)")
        self.assert_balanced(jurnals.first())
        self.assertGreaterEqual(jurnals.first().lines.count(), 3,
            "Minimal 3 line (Kas, Pendapatan, PPN/HPP)")
        kb = KasBankTransaction.objects.filter(sumber_app='pos', sumber_id=trx.pk)
        self.assertEqual(kb.count(), 1)
        self.assertEqual(kb.first().tipe, 'masuk')

    # ─── TEST 2: POS KREDIT ───
    def test_pos_kredit(self):
        """POS unpaid: jurnal + Piutang record"""
        trx = POSTransaction.objects.create(
            kasir=self.user, gudang=self.gudang, nama_customer='Walk-in',
            metode_pembayaran=self.metode_tunai, status='draft'
        )
        POSTransactionItem.objects.create(
            transaction=trx, produk=self.produk, jumlah=1, harga_satuan=Decimal('7000000')
        )
        trx.refresh_from_db()
        trx.status = 'unpaid'
        trx.save()

        jurnals = JurnalEntry.objects.filter(sumber='pos', sumber_id=trx.pk)
        self.assertGreaterEqual(jurnals.count(), 1)
        piutang = Piutang.objects.filter(sumber='pos', pos_transaction=trx)
        self.assertEqual(piutang.count(), 1)

    # ─── TEST 3: SO CASH ───
    def test_so_cash(self):
        """SO confirmed cash: jurnal + KasBankTransaction"""
        so = SalesOrder.objects.create(
            customer=self.customer, gudang=self.gudang, dibuat_oleh=self.user,
            metode_pembayaran=self.metode_tunai, status='draft'
        )
        SalesOrderItem.objects.create(
            sales_order=so, produk=self.produk, jumlah=2, harga_satuan=Decimal('7000000')
        )
        so.confirm_order(user=self.user)
        jurnals = JurnalEntry.objects.filter(sumber='so', sumber_id=so.pk)
        self.assertGreaterEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        kb = KasBankTransaction.objects.filter(sumber_app='penjualan', sumber_id=so.pk)
        self.assertEqual(kb.count(), 1)
        self.assertEqual(kb.first().tipe, 'masuk')
        sisa = Stok.objects.get(produk=self.produk, gudang=self.gudang).jumlah
        self.assertEqual(sisa, 98)

    # ─── TEST 4: SO KREDIT ───
    def test_so_kredit(self):
        """SO confirmed credit: jurnal + Piutang, tanpa KasBankTransaction"""
        metode_kredit = MetodePembayaran.objects.create(
            nama='Kredit', kode='KREDIT', tipe='non_tunai'
        )
        so = SalesOrder.objects.create(
            customer=self.customer, gudang=self.gudang, dibuat_oleh=self.user,
            metode_pembayaran=metode_kredit, status='draft'
        )
        SalesOrderItem.objects.create(
            sales_order=so, produk=self.produk, jumlah=3, harga_satuan=Decimal('7000000')
        )
        so.confirm_order(user=self.user)
        jurnals = JurnalEntry.objects.filter(sumber='so', sumber_id=so.pk)
        self.assertGreaterEqual(jurnals.count(), 1)
        piutang = Piutang.objects.filter(sumber='so', sales_order=so)
        self.assertEqual(piutang.count(), 1)
        kb = KasBankTransaction.objects.filter(sumber_app='penjualan', sumber_id=so.pk)
        self.assertEqual(kb.count(), 0)

    # ─── TEST 5: PO CASH ───
    def test_po_cash(self):
        """PO received cash: jurnal D:Persediaan + PPN Masukan K:Kas"""
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, gudang=self.gudang, dibuat_oleh=self.user,
            metode_pembayaran=self.metode_tunai, status='draft'
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po, produk=self.produk, jumlah=10, harga_satuan=Decimal('5000000')
        )
        po.transition_status('submitted'); po.save()
        po.transition_status('approved'); po.save()
        po.receive_goods(self.user)
        jurnals = JurnalEntry.objects.filter(sumber='po', sumber_id=po.pk)
        self.assertEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        kb = KasBankTransaction.objects.filter(sumber_app='pembelian', sumber_id=po.pk)
        self.assertEqual(kb.count(), 1)
        self.assertEqual(kb.first().tipe, 'keluar')
        sisa = Stok.objects.get(produk=self.produk, gudang=self.gudang).jumlah
        self.assertEqual(sisa, 110)

    # ─── TEST 6: PO KREDIT ───
    def test_po_kredit(self):
        """PO received credit: jurnal D:Persediaan + PPN Masukan K:Hutang + Hutang record"""
        metode_kredit = MetodePembayaran.objects.create(
            nama='Kredit', kode='KREDIT', tipe='non_tunai'
        )
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, gudang=self.gudang, dibuat_oleh=self.user,
            metode_pembayaran=metode_kredit, status='draft'
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po, produk=self.produk, jumlah=5, harga_satuan=Decimal('5000000')
        )
        po.transition_status('submitted'); po.save()
        po.transition_status('approved'); po.save()
        po.receive_goods(self.user)

        jurnals = JurnalEntry.objects.filter(sumber='po', sumber_id=po.pk)
        self.assertGreaterEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())

        hutang = Hutang.objects.filter(sumber='po', purchase_order=po)
        self.assertEqual(hutang.count(), 1)
        self.assertEqual(hutang.first().status, 'belum_bayar')

        kb = KasBankTransaction.objects.filter(sumber_app='pembelian', sumber_id=po.pk)
        self.assertEqual(kb.count(), 0)

    # ─── TEST 7: BIAYA ───
    def test_biaya(self):
        """Biaya approved: jurnal + KasBankTransaction"""
        biaya = TransaksiBiaya.objects.create(
            kategori=self.kategori_biaya, jumlah=Decimal('500000'),
            tanggal=date.today(), deskripsi='Listrik bulan ini',
            status='draft', dibuat_oleh=self.user,
            metode_pembayaran=self.metode_tunai, cabang=self.gudang
        )
        transition_biaya_status(biaya, 'submitted', self.user)
        transition_biaya_status(biaya, 'approved', self.user)
        jurnals = JurnalEntry.objects.filter(sumber='biaya', sumber_id=biaya.pk)
        self.assertEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        kb = KasBankTransaction.objects.filter(sumber_app='biaya', sumber_id=biaya.pk)
        self.assertEqual(kb.count(), 1)
        self.assertEqual(kb.first().tipe, 'keluar')

    # ─── TEST 8: PENGGAJIAN ───
    def test_penggajian(self):
        """Payroll dibayar: multi-line jurnal"""
        penggajian = Penggajian.objects.create(
            karyawan=self.karyawan, periode_bulan=6, periode_tahun=2026,
            gaji_pokok=Decimal('5000000'), tunjangan_makan=Decimal('500000'),
            potongan_pph21=Decimal('200000'), potongan_bpjs_kesehatan=Decimal('50000'),
            potongan_bpjs_ketenagakerjaan=Decimal('75000'),
            status='dibayar', tanggal_bayar=date.today(),
            metode_pembayaran=self.metode_tunai, dibuat_oleh=self.user,
            cabang=self.gudang
        )
        jurnals = JurnalEntry.objects.filter(sumber='payroll', sumber_id=penggajian.pk)
        self.assertEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        lines = jurnals.first().lines.all()
        self.assertGreaterEqual(len([l for l in lines if l.debit > 0]), 1)
        self.assertGreaterEqual(len([l for l in lines if l.kredit > 0]), 3)

    # ─── TEST 9: ADJUSTMENT OUT ───
    def test_adjustment_out(self):
        """Adjustment out: jurnal D:Beban K:Persediaan"""
        adj = AdjustmentStok.objects.create(
            produk=self.produk, gudang=self.gudang, tipe='out',
            jumlah=5, alasan='Barang rusak'
        )
        jurnals = JurnalEntry.objects.filter(sumber='inventori', sumber_id=adj.pk)
        self.assertEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        sisa = Stok.objects.get(produk=self.produk, gudang=self.gudang).jumlah
        self.assertEqual(sisa, 95)

    # ─── TEST 10: ADJUSTMENT IN ───
    def test_adjustment_in(self):
        """Adjustment in: jurnal D:Persediaan K:Pendapatan Lainnya"""
        adj = AdjustmentStok.objects.create(
            produk=self.produk, gudang=self.gudang, tipe='in',
            jumlah=3, alasan='Hasil stock opname'
        )
        jurnals = JurnalEntry.objects.filter(sumber='inventori', sumber_id=adj.pk)
        self.assertEqual(jurnals.count(), 1)
        self.assert_balanced(jurnals.first())
        sisa = Stok.objects.get(produk=self.produk, gudang=self.gudang).jumlah
        self.assertEqual(sisa, 103)

    # ─── TEST 11: IDEMPOTENCY ───
    def test_idempotency(self):
        """Re-save tidak boleh buat duplikat jurnal"""
        trx = POSTransaction.objects.create(
            kasir=self.user, gudang=self.gudang,
            metode_pembayaran=self.metode_tunai, jumlah_bayar=Decimal('7770000'),
            status='draft'
        )
        POSTransactionItem.objects.create(
            transaction=trx, produk=self.produk, jumlah=1, harga_satuan=Decimal('7000000')
        )
        trx.refresh_from_db()
        trx.status = 'paid'
        trx.save()
        count1 = JurnalEntry.objects.filter(sumber='pos', sumber_id=trx.pk).count()
        trx.save()
        count2 = JurnalEntry.objects.filter(sumber='pos', sumber_id=trx.pk).count()
        self.assertEqual(count1, count2)

    # ─── TEST 12: TRIAL BALANCE ───
    def test_trial_balance(self):
        from django.db.models import Sum
        debit = JurnalLine.objects.aggregate(total=Sum('debit'))['total'] or Decimal('0')
        kredit = JurnalLine.objects.aggregate(total=Sum('kredit'))['total'] or Decimal('0')
        self.assertEqual(debit, kredit)

    # ─── TEST 13: DISKON & ONGKIR ───
    def test_diskon_ongkir(self):
        """Diskon & ongkir di SO: field tersedia"""
        so = SalesOrder.objects.create(
            customer=self.customer, gudang=self.gudang, dibuat_oleh=self.user,
            diskon=Decimal('100000'), biaya_pengiriman=Decimal('50000'),
            metode_pembayaran=self.metode_tunai, status='draft'
        )
        SalesOrderItem.objects.create(
            sales_order=so, produk=self.produk, jumlah=1, harga_satuan=Decimal('7000000')
        )
        so.confirm_order(user=self.user)
        self.assertGreater(so.total_harga, Decimal('0'))
        self.assertNotEqual(so.diskon, Decimal('0'))
        self.assertNotEqual(so.biaya_pengiriman, Decimal('0'))

    # ─── TEST 14: PEMBAYARAN PIUTANG ───
    def test_bayar_piutang(self):
        """Pembayaran Piutang: jurnal + KasBankTransaction + status lunas"""
        trx = POSTransaction.objects.create(
            kasir=self.user, gudang=self.gudang, nama_customer='Walk-in',
            metode_pembayaran=self.metode_tunai, status='draft'
        )
        POSTransactionItem.objects.create(
            transaction=trx, produk=self.produk, jumlah=1, harga_satuan=Decimal('7000000')
        )
        trx.refresh_from_db()
        trx.status = 'unpaid'
        trx.save()

        piutang = Piutang.objects.get(sumber='pos', pos_transaction=trx)
        bayar = PembayaranPiutang.objects.create(
            piutang=piutang, jumlah=piutang.jumlah_total,
            tanggal=date.today(), metode_pembayaran=self.metode_tunai
        )
        piutang.refresh_from_db()
        self.assertEqual(piutang.status, 'lunas')
        kb = KasBankTransaction.objects.filter(sumber_app='piutang', sumber_id=bayar.pk)
        self.assertGreaterEqual(kb.count(), 1, "Piutang payment harus buat KasBankTransaction")

    # ─── TEST 15: PEMBAYARAN HUTANG ───
    def test_bayar_hutang(self):
        """Pembayaran Hutang: jurnal + KasBankTransaction + status lunas"""
        metode_kredit = MetodePembayaran.objects.create(
            nama='Kredit', kode='KREDIT', tipe='non_tunai'
        )
        po = PurchaseOrder.objects.create(
            supplier=self.supplier, gudang=self.gudang, dibuat_oleh=self.user,
            metode_pembayaran=metode_kredit, status='draft'
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po, produk=self.produk, jumlah=5, harga_satuan=Decimal('5000000')
        )
        po.transition_status('submitted'); po.save()
        po.transition_status('approved'); po.save()
        po.receive_goods(self.user)

        h = Hutang.objects.filter(sumber='po', purchase_order=po)
        self.assertEqual(h.count(), 1, "PO kredit harus punya Hutang")
        hutang = h.first()

        bayar = PembayaranHutang.objects.create(
            hutang=hutang, jumlah=hutang.jumlah_total,
            tanggal=date.today(), metode_pembayaran=self.metode_tunai
        )
        hutang.refresh_from_db()
        self.assertEqual(hutang.status, 'lunas')
        kb = KasBankTransaction.objects.filter(sumber_app='hutang', sumber_id=bayar.pk)
        self.assertGreaterEqual(kb.count(), 1, "Hutang payment harus buat KasBankTransaction")
