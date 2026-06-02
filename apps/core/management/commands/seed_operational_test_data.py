from collections import defaultdict
import calendar
from datetime import datetime, time, timedelta
from decimal import Decimal
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.akuntansi.models import Akun, JurnalEntry, PeriodeAkuntansi
from apps.akuntansi.services import create_jurnal, seed_default_coa
from apps.aset.models import AsetTetap, Penyusutan
from apps.biaya.models import KategoriBiaya, TransaksiBiaya
from apps.fraud_detection.models import CashReconciliation, FraudAlert
from apps.hr.models import Absensi, Departemen, Jabatan, Karyawan, Penggajian
from apps.hutang.models import Hutang, PembayaranHutang
from apps.inventory.models import AdjustmentStok, TransferStok, TransferStokItem
from apps.kas_bank.models import (
    KasBankAccount,
    KasBankReconciliation,
    KasBankTransaction,
    KasBankTransfer,
)
from apps.kas_bank.services import (
    create_operational_mutation,
    post_kas_bank_transfer,
    post_manual_kas_bank_transaction,
)
from apps.pajak.models import FakturPajak, PembayaranPPN, SettingPajak
from apps.pembelian.models import PurchaseOrder, PurchaseOrderItem, Supplier
from apps.penjualan.models import Customer, SalesOrder, SalesOrderItem
from apps.piutang.models import PembayaranPiutang, Piutang
from apps.pos.models import MetodePembayaran, POSTransaction, POSTransactionItem
from apps.produk.models import Gudang, Kategori, Produk, Satuan, Stok


TEST_MARK = "[TST]"
PREFIX = "TST"
PPN_RATE = Decimal("11")


def dec(value):
    return Decimal(str(value))


class Command(BaseCommand):
    help = (
        "Membuat data testing operasional massal untuk modul produk, stok, POS, "
        "penjualan, pembelian, biaya, Kas & Bank, Accounting, pajak, aset, AR/AP, "
        "HR, payroll, inventory, dan fraud detection."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale",
            type=int,
            default=1,
            help="Skala data. 1 cukup untuk smoke/UAT ringan, 2+ untuk data lebih banyak.",
        )
        parser.add_argument(
            "--months",
            type=int,
            default=4,
            help="Jumlah bulan periode dan transaksi historis yang dibuat.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=34,
            help="Seed random agar data testing tetap repeatable.",
        )
        parser.add_argument(
            "--clear-test-data",
            action="store_true",
            help="Hapus data testing berprefix TST sebelum membuat ulang data.",
        )
        parser.add_argument(
            "--confirm",
            default="",
            help="Wajib bernilai CLEAR_TEST_DATA saat memakai --clear-test-data.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validasi command dan tampilkan rencana tanpa menulis database.",
        )

    def handle(self, *args, **options):
        self.scale = max(1, options["scale"])
        self.months = max(1, options["months"])
        self.random = random.Random(options["seed"])
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.counts = defaultdict(int)
        self.warnings = []

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: tidak ada data yang ditulis."))
            self.stdout.write(f"Scale: {self.scale}")
            self.stdout.write(f"Months: {self.months}")
            self.stdout.write(f"Seed: {options['seed']}")
            self.stdout.write("Command siap dijalankan tanpa --dry-run untuk membuat data testing.")
            return

        if options["clear_test_data"]:
            if options["confirm"] != "CLEAR_TEST_DATA":
                raise CommandError(
                    "Gunakan --confirm CLEAR_TEST_DATA untuk menghapus data testing berprefix TST."
                )
            self.clear_test_data()

        with transaction.atomic():
            self.user = self.get_seed_user()
            self.seed_accounting_base()
            self.seed_tax_setting()
            self.seed_treasury_base()
            self.seed_master_data()
            self.seed_hr_payroll()
            self.seed_purchase_flow()
            self.seed_sales_order_flow()
            self.seed_pos_flow()
            self.seed_inventory_flow()
            self.seed_expense_flow()
            self.seed_ar_ap_payments()
            self.seed_cash_bank_flow()
            self.seed_fixed_asset_flow()
            self.seed_tax_flow()
            self.seed_fraud_detection_flow()

        self.print_summary()

    def get_seed_user(self):
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if user:
            return user

        user, created = User.objects.get_or_create(
            username="serptech_tester",
            defaults={
                "email": "serptech_tester@example.test",
                "first_name": "SERPTECH",
                "last_name": "Tester",
                "is_staff": True,
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            self.counts["User testing"] += 1
        return user

    def month_bounds(self, offset):
        year = self.today.year
        month = self.today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        last_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, 1).date(), datetime(year, month, last_day).date()

    def dt(self, date_value, hour=9, minute=0):
        return timezone.make_aware(datetime.combine(date_value, time(hour, minute)))

    def safe_day(self, offset, day, hour=9, minute=0):
        start, end = self.month_bounds(offset)
        chosen_day = min(day, end.day)
        return self.dt(start.replace(day=chosen_day), hour, minute)

    def inc(self, label, created=True):
        if created:
            self.counts[label] += 1

    def akun(self, kode):
        akun = Akun.objects.filter(kode=kode, is_active=True).first()
        if not akun:
            raise CommandError(f"Akun {kode} tidak ditemukan. Jalankan seed_default_coa dahulu.")
        return akun

    def update_datetime_field(self, obj, field_name, value):
        obj.__class__.objects.filter(pk=obj.pk).update(**{field_name: value})
        setattr(obj, field_name, value)

    def tagged(self, text):
        return f"{TEST_MARK} {text}"

    def seed_accounting_base(self):
        created, skipped = seed_default_coa()
        self.counts["COA dibuat"] += created
        self.counts["COA tersedia"] += skipped

        for offset in range(self.months + 1):
            start, end = self.month_bounds(offset)
            periode, created = PeriodeAkuntansi.objects.get_or_create(
                nama=f"{PREFIX} Periode {start:%Y-%m}",
                defaults={
                    "tanggal_mulai": start,
                    "tanggal_akhir": end,
                    "is_aktif": offset == 0,
                    "is_tutup": False,
                },
            )
            if not created and periode.is_tutup:
                periode.is_tutup = False
                periode.save(update_fields=["is_tutup"])
            self.inc("Periode akuntansi", created)

    def seed_tax_setting(self):
        setting = SettingPajak.get_setting()
        setting.tarif_ppn = PPN_RATE
        setting.is_pkp = True
        setting.nama_pkp = setting.nama_pkp or "PT SERPTECH TESTING"
        setting.npwp = setting.npwp or "00.000.000.0-000.000"
        setting.alamat_pkp = setting.alamat_pkp or "Alamat testing SERPTECH"
        setting.save()

    def seed_treasury_base(self):
        kas_akun = self.akun("1-1000")
        bank_akun = self.akun("1-1100")

        specs = [
            ("TST-KAS", "TST Kas Operasional", "kas", kas_akun, dec("25000000"), True),
            ("TST-BANK", "TST Bank Operasional", "bank", bank_akun, dec("100000000"), False),
            ("TST-QRIS", "TST QRIS Settlement", "qris", bank_akun, dec("15000000"), False),
        ]
        self.kas_bank_accounts = {}
        for kode, nama, tipe, akun, saldo, is_default in specs:
            account, created = KasBankAccount.objects.update_or_create(
                kode=kode,
                defaults={
                    "nama": nama,
                    "tipe": tipe,
                    "akun": akun,
                    "saldo_awal": saldo,
                    "aktif": True,
                    "is_default": is_default,
                    "dibuat_oleh": self.user,
                },
            )
            self.kas_bank_accounts[kode] = account
            self.inc("Akun Kas & Bank", created)

        method_specs = [
            ("TST-CASH", "TST Tunai", self.kas_bank_accounts["TST-KAS"], dec("25000000")),
            ("TST-BANK", "TST Transfer Bank", self.kas_bank_accounts["TST-BANK"], dec("100000000")),
            ("TST-QRIS", "TST QRIS", self.kas_bank_accounts["TST-QRIS"], dec("15000000")),
        ]
        self.payment_methods = {}
        for kode, nama, account, saldo in method_specs:
            method, created = MetodePembayaran.objects.update_or_create(
                kode=kode,
                defaults={
                    "nama": nama,
                    "nama_pemilik": "PT SERPTECH TESTING",
                    "deskripsi": self.tagged("Metode pembayaran testing operasional"),
                    "saldo": saldo,
                    "kas_bank_account": account,
                    "akun_kas_bank": account.akun,
                    "aktif": True,
                },
            )
            self.payment_methods[kode] = method
            self.inc("Metode pembayaran", created)

    def seed_master_data(self):
        self.gudangs = []
        for index in range(1, max(3, self.scale + 2) + 1):
            method = self.payment_methods["TST-CASH"] if index == 1 else self.payment_methods["TST-BANK"]
            gudang, created = Gudang.objects.update_or_create(
                kode=f"TST-CBG-{index:02d}",
                defaults={
                    "nama": f"TST Cabang Operasional {index:02d}",
                    "alamat": self.tagged(f"Alamat cabang testing {index:02d}"),
                    "pajak_persen": PPN_RATE,
                    "aktif": True,
                    "metode_pembayaran_default": method,
                },
            )
            self.gudangs.append(gudang)
            self.inc("Cabang/Gudang", created)

        kategori_names = ["Elektronik", "Sparepart Umum", "Bahan Konsumsi", "Jasa Pendukung"]
        self.kategoris = []
        for name in kategori_names:
            kategori, created = Kategori.objects.get_or_create(
                nama=f"TST {name}",
                defaults={
                    "deskripsi": self.tagged(f"Kategori testing {name.lower()}"),
                    "dibuat_oleh": self.user,
                },
            )
            self.kategoris.append(kategori)
            self.inc("Kategori produk", created)

        self.satuan_pcs, created = Satuan.objects.get_or_create(
            nama="TST Pieces",
            defaults={"singkatan": "tpcs"},
        )
        self.inc("Satuan", created)
        self.satuan_box, created = Satuan.objects.get_or_create(
            nama="TST Box",
            defaults={"singkatan": "tbox"},
        )
        self.inc("Satuan", created)

        self.products = []
        product_count = max(12, self.scale * 12)
        for index in range(1, product_count + 1):
            kategori = self.kategoris[(index - 1) % len(self.kategoris)]
            gudang = self.gudangs[(index - 1) % len(self.gudangs)]
            harga_beli = dec(25000 + (index * 3500))
            harga_jual = (harga_beli * dec("1.35")).quantize(dec("0.01"))
            product, created = Produk.objects.update_or_create(
                sku=f"TST-PRD-{index:03d}",
                defaults={
                    "barcode": f"TSTBAR{index:05d}",
                    "nama": f"TST Produk Operasional {index:03d}",
                    "deskripsi": self.tagged("Produk untuk QA operasional lintas modul"),
                    "kategori": kategori,
                    "satuan": self.satuan_pcs,
                    "cabang": gudang,
                    "harga_beli": harga_beli,
                    "harga_jual": harga_jual,
                    "aktif": True,
                    "metode_pembayaran": self.payment_methods["TST-CASH"],
                    "dibuat_oleh": self.user,
                },
            )
            self.products.append(product)
            self.inc("Produk", created)

            for gudang_idx, stock_gudang in enumerate(self.gudangs, start=1):
                stok, stock_created = Stok.objects.get_or_create(
                    produk=product,
                    gudang=stock_gudang,
                    defaults={"jumlah": dec(120 + index + (gudang_idx * 20))},
                )
                if not stock_created and stok.jumlah < dec(60):
                    stok.jumlah = dec(120 + index + (gudang_idx * 20))
                    stok.save(update_fields=["jumlah"])
                self.inc("Stok awal", stock_created)

        self.customers = []
        for index in range(1, max(8, self.scale * 8) + 1):
            customer, created = Customer.objects.update_or_create(
                kode=f"TST-CUS-{index:03d}",
                defaults={
                    "nama": f"TST Customer {index:03d}",
                    "telepon": f"08120000{index:04d}",
                    "email": f"customer{index:03d}@example.test",
                    "alamat": self.tagged(f"Alamat customer {index:03d}"),
                    "aktif": True,
                },
            )
            self.customers.append(customer)
            self.inc("Customer", created)

        self.suppliers = []
        for index in range(1, max(6, self.scale * 6) + 1):
            supplier, created = Supplier.objects.update_or_create(
                kode=f"TST-SUP-{index:03d}",
                defaults={
                    "nama": f"TST Supplier {index:03d}",
                    "kontak": f"PIC Supplier {index:03d}",
                    "telepon": f"08220000{index:04d}",
                    "email": f"supplier{index:03d}@example.test",
                    "alamat": self.tagged(f"Alamat supplier {index:03d}"),
                    "aktif": True,
                },
            )
            self.suppliers.append(supplier)
            self.inc("Supplier", created)

    def seed_hr_payroll(self):
        dep_specs = [
            ("TST-FIN", "TST Finance"),
            ("TST-SLS", "TST Sales"),
            ("TST-WHS", "TST Warehouse"),
            ("TST-OPS", "TST Operations"),
        ]
        self.departments = []
        for kode, nama in dep_specs:
            dep, created = Departemen.objects.update_or_create(
                kode=kode,
                defaults={
                    "nama": nama,
                    "deskripsi": self.tagged("Departemen testing operasional"),
                    "aktif": True,
                },
            )
            self.departments.append(dep)
            self.inc("Departemen", created)

        self.jobs = []
        for index, dep in enumerate(self.departments, start=1):
            job, created = Jabatan.objects.update_or_create(
                kode=f"{dep.kode}-STF",
                defaults={
                    "nama": f"Staff {dep.nama.replace('TST ', '')}",
                    "departemen": dep,
                    "level": "staff",
                    "gaji_pokok": dec(4500000 + (index * 500000)),
                    "tunjangan_jabatan": dec(500000),
                    "deskripsi": self.tagged("Jabatan testing operasional"),
                    "aktif": True,
                },
            )
            self.jobs.append(job)
            self.inc("Jabatan", created)

        self.employees = []
        employee_count = max(8, self.scale * 8)
        for index in range(1, employee_count + 1):
            job = self.jobs[(index - 1) % len(self.jobs)]
            dep = job.departemen
            birth_date = self.today - timedelta(days=365 * (25 + (index % 10)))
            karyawan, created = Karyawan.objects.update_or_create(
                nik=f"TST-EMP-{index:04d}",
                defaults={
                    "nama": f"TST Karyawan {index:04d}",
                    "email": f"karyawan{index:04d}@example.test",
                    "telepon": f"08330000{index:04d}",
                    "alamat": self.tagged(f"Alamat karyawan {index:04d}"),
                    "tempat_lahir": "Jakarta",
                    "tanggal_lahir": birth_date,
                    "jenis_kelamin": "L" if index % 2 else "P",
                    "jabatan": job,
                    "departemen": dep,
                    "cabang": self.gudangs[(index - 1) % len(self.gudangs)],
                    "tanggal_masuk": self.today - timedelta(days=365 + index),
                    "status": "aktif",
                    "gaji_pokok": job.gaji_pokok,
                    "aktif": True,
                    "dibuat_oleh": self.user,
                },
            )
            self.employees.append(karyawan)
            self.inc("Karyawan", created)

        for index, employee in enumerate(self.employees[: min(len(self.employees), self.scale * 5 + 5)], start=1):
            for day_offset in range(1, 6):
                attendance_date = self.today - timedelta(days=day_offset)
                status = "terlambat" if (index + day_offset) % 6 == 0 else "hadir"
                absensi, created = Absensi.objects.update_or_create(
                    karyawan=employee,
                    tanggal=attendance_date,
                    defaults={
                        "jam_masuk": time(8, 15) if status == "terlambat" else time(8, 0),
                        "jam_keluar": time(17, 0),
                        "status": status,
                        "persentase_kemiripan": dec("96.5"),
                        "lokasi_masuk": self.tagged("Lokasi masuk testing"),
                        "lokasi_keluar": self.tagged("Lokasi keluar testing"),
                        "jarak_masuk": dec("20.0"),
                        "jarak_keluar": dec("25.0"),
                        "cabang": employee.cabang,
                        "catatan": self.tagged("Absensi testing operasional"),
                    },
                )
                self.inc("Absensi", created)

        for employee in self.employees[: min(len(self.employees), self.scale * 5 + 5)]:
            payroll, created = Penggajian.objects.update_or_create(
                karyawan=employee,
                periode_bulan=self.today.month,
                periode_tahun=self.today.year,
                defaults={
                    "gaji_pokok": employee.gaji_pokok,
                    "tunjangan_jabatan": employee.jabatan.tunjangan_jabatan,
                    "tunjangan_makan": dec("500000"),
                    "tunjangan_transport": dec("350000"),
                    "lembur": dec("150000"),
                    "bonus": dec("100000"),
                    "potongan_bpjs_kesehatan": dec("75000"),
                    "potongan_bpjs_ketenagakerjaan": dec("100000"),
                    "potongan_pph21": dec("125000"),
                    "status": "dibayar",
                    "tanggal_bayar": self.today,
                    "catatan": self.tagged("Payroll testing operasional"),
                    "dibuat_oleh": self.user,
                },
            )
            self.inc("Penggajian", created)

    def seed_purchase_flow(self):
        self.purchase_orders = []
        count = max(6, self.scale * 6)
        for index in range(1, count + 1):
            tanggal = self.safe_day(index % self.months, min(5 + index, 26), 10, 0)
            supplier = self.suppliers[(index - 1) % len(self.suppliers)]
            gudang = self.gudangs[index % len(self.gudangs)]
            po = PurchaseOrder.objects.create(
                tanggal=tanggal,
                supplier=supplier,
                gudang=gudang,
                status="draft",
                catatan=self.tagged(f"Purchase order testing {index:03d}"),
                dibuat_oleh=self.user,
                metode_pembayaran=None if index % 3 == 0 else self.payment_methods["TST-BANK"],
            )
            self.inc("Purchase Order")
            for item_no in range(1, 3 + (index % 2)):
                product = self.products[(index + item_no) % len(self.products)]
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    produk=product,
                    jumlah=dec(8 + item_no + index),
                    harga_satuan=product.harga_beli,
                    satuan_transaksi=product.satuan,
                    catatan=self.tagged("Item PO testing"),
                )
                self.inc("Item PO")

            po.refresh_from_db()
            po.pajak = (po.subtotal * PPN_RATE / dec("100")).quantize(dec("0.01"))
            if index % 4 == 0:
                po.status = "submitted"
                po.save()
            elif index % 4 == 1:
                po.status = "approved"
                po.save()
            else:
                po.status = "approved"
                po.save()
                po.receive_goods(self.user)
            self.purchase_orders.append(po)

    def seed_sales_order_flow(self):
        self.sales_orders = []
        count = max(8, self.scale * 8)
        for index in range(1, count + 1):
            tanggal = self.safe_day(index % self.months, min(10 + index, 27), 14, 0)
            customer = self.customers[(index - 1) % len(self.customers)]
            gudang = self.gudangs[(index - 1) % len(self.gudangs)]
            so = SalesOrder.objects.create(
                tanggal=tanggal,
                customer=customer,
                gudang=gudang,
                status="draft",
                diskon=dec("0"),
                pajak=dec("0"),
                catatan=self.tagged(f"Sales order testing {index:03d}"),
                dibuat_oleh=self.user,
                metode_pembayaran=None if index % 3 == 0 else self.payment_methods["TST-BANK"],
            )
            self.inc("Sales Order")
            for item_no in range(1, 3):
                product = self.products[(index + item_no + 2) % len(self.products)]
                SalesOrderItem.objects.create(
                    sales_order=so,
                    produk=product,
                    jumlah=dec(1 + (index + item_no) % 3),
                    harga_satuan=product.harga_jual,
                    diskon=dec("2500") if item_no == 2 and index % 2 == 0 else dec("0"),
                    satuan_transaksi=product.satuan,
                    catatan=self.tagged("Item SO testing"),
                )
                self.inc("Item SO")

            so.refresh_from_db()
            so.diskon = dec("10000") if index % 2 == 0 else dec("0")
            dpp = max(so.subtotal - so.diskon, dec("0"))
            so.pajak = (dpp * PPN_RATE / dec("100")).quantize(dec("0.01"))
            so.save()

            if index % 4 == 0:
                so.status = "draft"
                so.save()
            elif index % 4 == 1:
                so.confirm_order(self.user)
            else:
                so.confirm_order(self.user)
                so.status = "completed"
                so.save()
            self.sales_orders.append(so)

    def seed_pos_flow(self):
        self.pos_transactions = []
        count = max(10, self.scale * 10)
        for index in range(1, count + 1):
            tanggal = self.safe_day(index % self.months, min(12 + index, 28), 11, index % 50)
            gudang = self.gudangs[(index - 1) % len(self.gudangs)]
            transaction_obj = POSTransaction.objects.create(
                kasir=self.user,
                gudang=gudang,
                customer=self.customers[index % len(self.customers)] if index % 3 == 0 else None,
                nama_customer=f"TST Walk-in {index:03d}",
                diskon=dec("0"),
                pajak=dec("0"),
                metode_pembayaran=self.payment_methods["TST-CASH"] if index % 2 else self.payment_methods["TST-QRIS"],
                jumlah_bayar=dec("0"),
                status="draft",
                catatan=self.tagged(f"POS testing {index:03d}"),
            )
            self.update_datetime_field(transaction_obj, "tanggal", tanggal)
            self.inc("POS")
            for item_no in range(1, 3):
                product = self.products[(index + item_no + 5) % len(self.products)]
                POSTransactionItem.objects.create(
                    transaction=transaction_obj,
                    produk=product,
                    jumlah=dec(1 + ((index + item_no) % 2)),
                    harga_satuan=product.harga_jual,
                    diskon=dec("1500") if index % 3 == 0 else dec("0"),
                    satuan_transaksi=product.satuan,
                )
                self.inc("Item POS")

            transaction_obj.refresh_from_db()
            transaction_obj.diskon = dec("5000") if index % 4 == 0 else dec("0")
            dpp = max(transaction_obj.subtotal - transaction_obj.diskon, dec("0"))
            transaction_obj.pajak = (dpp * PPN_RATE / dec("100")).quantize(dec("0.01"))
            transaction_obj.calculate_total()
            if index % 5 == 0:
                transaction_obj.status = "unpaid"
                transaction_obj.jumlah_bayar = dec("0")
            else:
                transaction_obj.status = "paid"
                transaction_obj.jumlah_bayar = transaction_obj.total_harga
            transaction_obj.save()
            if transaction_obj.status == "paid":
                transaction_obj.update_stock()
            self.pos_transactions.append(transaction_obj)

    def seed_inventory_flow(self):
        for index in range(1, max(3, self.scale * 3) + 1):
            source = self.gudangs[0]
            target = self.gudangs[(index % (len(self.gudangs) - 1)) + 1]
            transfer = TransferStok.objects.create(
                gudang_asal=source,
                gudang_tujuan=target,
                status="draft",
                catatan=self.tagged(f"Transfer stok testing {index:03d}"),
                dibuat_oleh=self.user,
            )
            self.update_datetime_field(transfer, "tanggal", self.safe_day(index % self.months, 18, 9, 0))
            self.inc("Transfer Stok")
            for item_no in range(1, 3):
                product = self.products[(index + item_no) % len(self.products)]
                TransferStokItem.objects.create(
                    transfer=transfer,
                    produk=product,
                    jumlah=dec(2 + item_no),
                    catatan=self.tagged("Item transfer testing"),
                )
                self.inc("Item Transfer Stok")
            if index % 2 == 1:
                transfer.approve(self.user)

        for index in range(1, max(3, self.scale * 3) + 1):
            product = self.products[(index * 2) % len(self.products)]
            gudang = self.gudangs[index % len(self.gudangs)]
            adjustment = AdjustmentStok.objects.create(
                produk=product,
                gudang=gudang,
                tipe="in" if index % 2 else "out",
                jumlah=dec(1 + index),
                alasan=self.tagged(f"Adjustment stok testing {index:03d}"),
                dibuat_oleh=self.user,
            )
            self.update_datetime_field(adjustment, "tanggal", self.safe_day(index % self.months, 20, 16, 0))
            self.inc("Adjustment Stok")

    def seed_expense_flow(self):
        specs = [
            ("TST Listrik", "6-2000"),
            ("TST Sewa", "6-3000"),
            ("TST Transport", "6-7000"),
            ("TST Operasional Lainnya", "6-9000"),
        ]
        self.expense_categories = []
        for name, _ in specs:
            category, created = KategoriBiaya.objects.get_or_create(
                nama=name,
                defaults={
                    "deskripsi": self.tagged("Kategori biaya testing"),
                    "aktif": True,
                },
            )
            self.expense_categories.append(category)
            self.inc("Kategori Biaya", created)

        for index in range(1, max(6, self.scale * 6) + 1):
            category, akun_kode = specs[(index - 1) % len(specs)]
            category_obj = next(item for item in self.expense_categories if item.nama == category)
            tanggal = self.safe_day(index % self.months, min(6 + index, 24), 13, 0).date()
            expense = TransaksiBiaya.objects.create(
                tanggal=tanggal,
                kategori=category_obj,
                jumlah=dec(250000 + (index * 75000)),
                deskripsi=self.tagged(f"Biaya operasional testing {index:03d}"),
                status="approved" if index % 4 != 0 else "submitted",
                dibuat_oleh=self.user,
                disetujui_oleh=self.user if index % 4 != 0 else None,
                metode_pembayaran=self.payment_methods["TST-BANK"] if index % 2 else self.payment_methods["TST-CASH"],
                cabang=self.gudangs[index % len(self.gudangs)],
            )
            self.inc("Transaksi Biaya")

            if expense.status == "approved":
                self.create_expense_journal(expense, akun_kode)

    def create_expense_journal(self, expense, akun_beban_kode):
        if JurnalEntry.objects.filter(sumber="biaya", sumber_id=expense.pk).exists():
            return

        account = expense.metode_pembayaran.kas_bank_account if expense.metode_pembayaran else self.kas_bank_accounts["TST-KAS"]
        jurnal = create_jurnal(
            tanggal=expense.tanggal,
            deskripsi=self.tagged(f"Biaya operasional - {expense.nomor_transaksi}"),
            lines_data=[
                {
                    "akun_kode": akun_beban_kode,
                    "debit": expense.jumlah,
                    "kredit": dec("0"),
                    "keterangan": expense.deskripsi,
                },
                {
                    "akun": account.akun,
                    "debit": dec("0"),
                    "kredit": expense.jumlah,
                    "keterangan": expense.deskripsi,
                },
            ],
            sumber="biaya",
            sumber_id=expense.pk,
            sumber_ref=expense.nomor_transaksi,
            cabang=expense.cabang,
            user=self.user,
            auto_post=True,
        )
        create_operational_mutation(
            akun_kas_bank=account,
            tipe="keluar",
            tanggal=expense.tanggal,
            jumlah=expense.jumlah,
            deskripsi=self.tagged(f"Pembayaran biaya {expense.nomor_transaksi}"),
            akun_lawan=self.akun(akun_beban_kode),
            cabang=expense.cabang,
            metode_pembayaran=expense.metode_pembayaran,
            sumber_app="biaya",
            sumber_model="TransaksiBiaya",
            sumber_id=expense.pk,
            sumber_ref=expense.nomor_transaksi,
            jurnal_entry=jurnal,
            user=self.user,
        )
        self.counts["Jurnal Biaya"] += 1

    def seed_ar_ap_payments(self):
        for index in range(1, max(3, self.scale * 3) + 1):
            piutang = Piutang.objects.create(
                customer=self.customers[(index - 1) % len(self.customers)],
                sumber="manual",
                sumber_ref=f"TST-AR-MANUAL-{timezone.now().strftime('%Y%m%d%H%M%S')}-{index:03d}",
                jumlah_total=dec(1500000 + (index * 250000)),
                jumlah_dibayar=dec("0"),
                tanggal=self.today - timedelta(days=20 + index),
                jatuh_tempo=self.today + timedelta(days=10 + index),
                cabang=self.gudangs[index % len(self.gudangs)],
                keterangan=self.tagged(f"Piutang manual testing {index:03d}"),
                created_by=self.user,
            )
            self.inc("Piutang manual")
            amount = (piutang.jumlah_total * dec("0.40")).quantize(dec("0.01"))
            PembayaranPiutang.objects.create(
                piutang=piutang,
                tanggal=self.today - timedelta(days=index),
                jumlah=amount,
                metode_pembayaran=self.payment_methods["TST-BANK"],
                keterangan=self.tagged(f"Pembayaran piutang testing {index:03d}"),
                created_by=self.user,
            )
            self.inc("Pembayaran Piutang")

            hutang = Hutang.objects.create(
                supplier=self.suppliers[(index - 1) % len(self.suppliers)],
                sumber="manual",
                sumber_ref=f"TST-AP-MANUAL-{timezone.now().strftime('%Y%m%d%H%M%S')}-{index:03d}",
                jumlah_total=dec(2000000 + (index * 300000)),
                jumlah_dibayar=dec("0"),
                tanggal=self.today - timedelta(days=25 + index),
                jatuh_tempo=self.today + timedelta(days=7 + index),
                cabang=self.gudangs[index % len(self.gudangs)],
                keterangan=self.tagged(f"Hutang manual testing {index:03d}"),
                created_by=self.user,
            )
            self.inc("Hutang manual")
            amount = (hutang.jumlah_total * dec("0.35")).quantize(dec("0.01"))
            PembayaranHutang.objects.create(
                hutang=hutang,
                tanggal=self.today - timedelta(days=index),
                jumlah=amount,
                metode_pembayaran=self.payment_methods["TST-BANK"],
                keterangan=self.tagged(f"Pembayaran hutang testing {index:03d}"),
                created_by=self.user,
            )
            self.inc("Pembayaran Hutang")

    def seed_cash_bank_flow(self):
        incoming = KasBankTransaction.objects.create(
            akun_kas_bank=self.kas_bank_accounts["TST-KAS"],
            tipe="masuk",
            tanggal=self.dt(self.today - timedelta(days=3), 9, 30),
            deskripsi=self.tagged("Setoran modal kas testing"),
            jumlah=dec("3500000"),
            akun_lawan=self.akun("3-1000"),
            cabang=self.gudangs[0],
            metode_pembayaran=self.payment_methods["TST-CASH"],
            sumber_app="kas_bank",
            sumber_model="ManualSeed",
            sumber_id=0,
            sumber_ref=f"TST-KB-IN-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            status="posted",
            catatan=self.tagged("Mutasi masuk manual testing"),
            dibuat_oleh=self.user,
        )
        post_manual_kas_bank_transaction(incoming, self.user)
        self.inc("Mutasi Kas/Bank")

        outgoing = KasBankTransaction.objects.create(
            akun_kas_bank=self.kas_bank_accounts["TST-BANK"],
            tipe="keluar",
            tanggal=self.dt(self.today - timedelta(days=2), 10, 45),
            deskripsi=self.tagged("Biaya administrasi bank testing"),
            jumlah=dec("125000"),
            akun_lawan=self.akun("6-9000"),
            cabang=self.gudangs[0],
            metode_pembayaran=self.payment_methods["TST-BANK"],
            sumber_app="kas_bank",
            sumber_model="ManualSeed",
            sumber_id=0,
            sumber_ref=f"TST-KB-OUT-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            status="posted",
            catatan=self.tagged("Mutasi keluar manual testing"),
            dibuat_oleh=self.user,
        )
        post_manual_kas_bank_transaction(outgoing, self.user)
        self.inc("Mutasi Kas/Bank")

        transfer = KasBankTransfer.objects.create(
            tanggal=self.dt(self.today - timedelta(days=1), 15, 0),
            dari_akun=self.kas_bank_accounts["TST-KAS"],
            ke_akun=self.kas_bank_accounts["TST-BANK"],
            jumlah=dec("1000000"),
            biaya_admin=dec("6500"),
            akun_biaya_admin=self.akun("6-9000"),
            cabang=self.gudangs[0],
            status="posted",
            catatan=self.tagged("Transfer kas bank testing"),
            dibuat_oleh=self.user,
        )
        post_kas_bank_transfer(transfer, self.user)
        self.inc("Transfer Kas/Bank")

        for account in self.kas_bank_accounts.values():
            saldo_sistem = account.saldo_terhitung
            reconciliation = KasBankReconciliation.objects.create(
                akun_kas_bank=account,
                tanggal_mulai=self.month_bounds(0)[0],
                tanggal_akhir=self.today,
                saldo_sistem=saldo_sistem,
                saldo_statement=saldo_sistem + dec("2500"),
                status="reconciled",
                catatan=self.tagged("Rekonsiliasi kas bank testing"),
                dibuat_oleh=self.user,
            )
            self.inc("Rekonsiliasi Kas/Bank")

    def seed_fixed_asset_flow(self):
        for index in range(1, max(3, self.scale * 3) + 1):
            asset, created = AsetTetap.objects.update_or_create(
                kode=f"TST-AST-{index:03d}",
                defaults={
                    "nama": f"TST Aset Tetap {index:03d}",
                    "kategori": "peralatan" if index % 2 else "kendaraan",
                    "deskripsi": self.tagged(f"Aset testing {index:03d}"),
                    "akun_aset": self.akun("1-4000"),
                    "harga_perolehan": dec(6000000 + (index * 1500000)),
                    "nilai_residu": dec(500000),
                    "umur_ekonomis": 48,
                    "tanggal_perolehan": self.today - timedelta(days=180 + index),
                    "metode_penyusutan": "garis_lurus",
                    "supplier": self.suppliers[(index - 1) % len(self.suppliers)],
                    "status": "aktif",
                    "cabang": self.gudangs[index % len(self.gudangs)],
                    "created_by": self.user,
                },
            )
            self.inc("Aset Tetap", created)

            monthly_depreciation = ((asset.harga_perolehan - asset.nilai_residu) / dec(asset.umur_ekonomis)).quantize(dec("0.01"))
            month = self.today.month
            year = self.today.year
            penyusutan, dep_created = Penyusutan.objects.get_or_create(
                aset=asset,
                bulan=month,
                tahun=year,
                defaults={
                    "jumlah": monthly_depreciation,
                    "akumulasi": monthly_depreciation,
                    "created_by": self.user,
                },
            )
            self.inc("Penyusutan", dep_created)
            if dep_created:
                jurnal = create_jurnal(
                    tanggal=self.today,
                    deskripsi=self.tagged(f"Penyusutan aset {asset.kode}"),
                    lines_data=[
                        {
                            "akun_kode": "6-4000",
                            "debit": monthly_depreciation,
                            "kredit": dec("0"),
                            "keterangan": self.tagged("Beban penyusutan testing"),
                        },
                        {
                            "akun_kode": "1-4100",
                            "debit": dec("0"),
                            "kredit": monthly_depreciation,
                            "keterangan": self.tagged("Akumulasi penyusutan testing"),
                        },
                    ],
                    sumber="aset",
                    sumber_id=asset.pk,
                    sumber_ref=asset.kode,
                    cabang=asset.cabang,
                    user=self.user,
                    auto_post=True,
                )
                penyusutan.jurnal = jurnal
                penyusutan.save(update_fields=["jurnal"])
                self.counts["Jurnal Penyusutan"] += 1

    def seed_tax_flow(self):
        tax_month = self.today.month
        tax_year = self.today.year
        output_tax = (
            FakturPajak.objects.filter(tipe="keluaran", tanggal__year=tax_year, tanggal__month=tax_month)
            .exclude(keterangan__icontains="batal")
        )
        input_tax = (
            FakturPajak.objects.filter(tipe="masukan", tanggal__year=tax_year, tanggal__month=tax_month)
            .exclude(keterangan__icontains="batal")
        )
        total_output = sum((item.ppn for item in output_tax), dec("0"))
        total_input = sum((item.ppn for item in input_tax), dec("0"))

        if not PembayaranPPN.objects.filter(masa_bulan=tax_month, masa_tahun=tax_year).exists():
            amount = max(total_output - total_input, dec("0"))
            payment = PembayaranPPN.objects.create(
                tipe="setor",
                masa_bulan=tax_month,
                masa_tahun=tax_year,
                total_ppn_keluaran=total_output,
                total_ppn_masukan=total_input,
                jumlah_setor=amount,
                tanggal_setor=self.today,
                metode_pembayaran=self.payment_methods["TST-BANK"],
                nomor_bukti=f"TST-PPN-{tax_year}{tax_month:02d}",
                keterangan=self.tagged("Pembayaran PPN testing"),
                created_by=self.user,
            )
            self.inc("Pembayaran PPN")
            if amount > 0:
                jurnal = create_jurnal(
                    tanggal=self.today,
                    deskripsi=self.tagged(f"Setor PPN {tax_month:02d}/{tax_year}"),
                    lines_data=[
                        {
                            "akun_kode": "2-2000",
                            "debit": total_output,
                            "kredit": dec("0"),
                            "keterangan": self.tagged("PPN keluaran dikompensasi"),
                        },
                        {
                            "akun_kode": "1-1500",
                            "debit": dec("0"),
                            "kredit": min(total_input, total_output),
                            "keterangan": self.tagged("PPN masukan dikompensasi"),
                        },
                        {
                            "akun": self.kas_bank_accounts["TST-BANK"].akun,
                            "debit": dec("0"),
                            "kredit": amount,
                            "keterangan": self.tagged("Setor PPN via bank"),
                        },
                    ],
                    sumber="pajak",
                    sumber_id=payment.pk,
                    sumber_ref=payment.nomor,
                    cabang=self.gudangs[0],
                    user=self.user,
                    auto_post=True,
                )
                payment.jurnal = jurnal
                payment.save(update_fields=["jurnal"])
                self.counts["Jurnal PPN"] += 1
        else:
            self.warnings.append(
                f"Pembayaran PPN {tax_month:02d}/{tax_year} sudah ada, seed PPN payment dilewati."
            )

    def seed_fraud_detection_flow(self):
        paid_cash_total = sum(
            (trx.total_harga for trx in self.pos_transactions if trx.status == "paid"),
            dec("0"),
        )
        recon = CashReconciliation.objects.create(
            kasir=self.user,
            gudang=self.gudangs[0],
            shift_start=self.dt(self.today, 8, 0),
            shift_end=self.dt(self.today, 17, 0),
            expected_amount=paid_cash_total,
            actual_amount=paid_cash_total - dec("15000"),
            catatan=self.tagged("Cash reconciliation fraud testing"),
            status="closed",
        )
        self.inc("Cash Reconciliation Fraud")

        FraudAlert.objects.create(
            jenis="lainnya",
            severity="medium",
            status="pending",
            deskripsi=self.tagged("Alert testing dari selisih cash reconciliation"),
            user_terkait=self.user,
            nominal=abs(recon.discrepancy),
            model_name="CashReconciliation",
            object_id=str(recon.pk),
            data_snapshot={
                "expected_amount": str(recon.expected_amount),
                "actual_amount": str(recon.actual_amount),
                "discrepancy": str(recon.discrepancy),
                "seed": True,
            },
        )
        self.inc("Fraud Alert")

    def clear_test_data(self):
        self.stdout.write(self.style.WARNING("Menghapus data testing berprefix TST..."))
        so_ids = list(
            SalesOrder.objects.filter(catatan__icontains=TEST_MARK).values_list("id", flat=True)
        )
        po_ids = list(
            PurchaseOrder.objects.filter(catatan__icontains=TEST_MARK).values_list("id", flat=True)
        )
        pos_ids = list(
            POSTransaction.objects.filter(catatan__icontains=TEST_MARK).values_list("id", flat=True)
        )
        expense_ids = list(
            TransaksiBiaya.objects.filter(deskripsi__icontains=TEST_MARK).values_list("id", flat=True)
        )
        piutang_ids = list(
            Piutang.objects.filter(
                Q(keterangan__icontains=TEST_MARK)
                | Q(sumber_ref__startswith=PREFIX)
                | Q(sales_order_id__in=so_ids)
                | Q(pos_transaction_id__in=pos_ids)
            ).values_list("id", flat=True)
        )
        hutang_ids = list(
            Hutang.objects.filter(
                Q(keterangan__icontains=TEST_MARK)
                | Q(sumber_ref__startswith=PREFIX)
                | Q(purchase_order_id__in=po_ids)
            ).values_list("id", flat=True)
        )
        payment_ar_ids = list(
            PembayaranPiutang.objects.filter(
                Q(keterangan__icontains=TEST_MARK) | Q(piutang_id__in=piutang_ids)
            ).values_list("id", flat=True)
        )
        payment_ap_ids = list(
            PembayaranHutang.objects.filter(
                Q(keterangan__icontains=TEST_MARK) | Q(hutang_id__in=hutang_ids)
            ).values_list("id", flat=True)
        )
        asset_ids = list(
            AsetTetap.objects.filter(kode__startswith=f"{PREFIX}-").values_list("id", flat=True)
        )
        ppn_payment_ids = list(
            PembayaranPPN.objects.filter(
                Q(keterangan__icontains=TEST_MARK) | Q(nomor_bukti__startswith=PREFIX)
            ).values_list("id", flat=True)
        )
        kb_transfer_ids = list(
            KasBankTransfer.objects.filter(catatan__icontains=TEST_MARK).values_list("id", flat=True)
        )
        journal_filter = (
            Q(deskripsi__icontains=TEST_MARK)
            | Q(sumber_ref__startswith=PREFIX)
            | Q(sumber="so", sumber_id__in=so_ids)
            | Q(sumber="po", sumber_id__in=po_ids)
            | Q(sumber="pos", sumber_id__in=pos_ids)
            | Q(sumber="biaya", sumber_id__in=expense_ids)
            | Q(sumber="piutang", sumber_id__in=payment_ar_ids)
            | Q(sumber="hutang", sumber_id__in=payment_ap_ids)
            | Q(sumber="aset", sumber_id__in=asset_ids)
            | Q(sumber="pajak", sumber_id__in=ppn_payment_ids)
            | Q(sumber="kas_bank", sumber_id__in=kb_transfer_ids)
        )
        kas_bank_transaction_filter = (
            Q(catatan__icontains=TEST_MARK)
            | Q(deskripsi__icontains=TEST_MARK)
            | Q(sumber_ref__startswith=PREFIX)
            | Q(sumber_app="penjualan", sumber_model="SalesOrder", sumber_id__in=so_ids)
            | Q(sumber_app="pembelian", sumber_model="PurchaseOrder", sumber_id__in=po_ids)
            | Q(sumber_app="pos", sumber_model="POSTransaction", sumber_id__in=pos_ids)
            | Q(sumber_app="biaya", sumber_model="TransaksiBiaya", sumber_id__in=expense_ids)
            | Q(sumber_app="piutang", sumber_model="PembayaranPiutang", sumber_id__in=payment_ar_ids)
            | Q(sumber_app="hutang", sumber_model="PembayaranHutang", sumber_id__in=payment_ap_ids)
            | Q(sumber_app="kas_bank", sumber_model="KasBankTransfer", sumber_id__in=kb_transfer_ids)
        )
        delete_plan = [
            ("Fraud Alert", FraudAlert.objects.filter(Q(deskripsi__icontains=TEST_MARK) | Q(object_id__startswith=PREFIX))),
            ("Cash Reconciliation Fraud", CashReconciliation.objects.filter(catatan__icontains=TEST_MARK)),
            ("Pembayaran PPN", PembayaranPPN.objects.filter(Q(keterangan__icontains=TEST_MARK) | Q(nomor_bukti__startswith=PREFIX))),
            (
                "Faktur Pajak",
                FakturPajak.objects.filter(
                    Q(keterangan__icontains=TEST_MARK)
                    | Q(nomor_seri__startswith=PREFIX)
                    | Q(sales_order_id__in=so_ids)
                    | Q(purchase_order_id__in=po_ids)
                    | Q(pos_transaction_id__in=pos_ids)
                ),
            ),
            ("Penyusutan", Penyusutan.objects.filter(aset__kode__startswith=f"{PREFIX}-")),
            ("Aset Tetap", AsetTetap.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Pembayaran Piutang", PembayaranPiutang.objects.filter(Q(keterangan__icontains=TEST_MARK) | Q(piutang_id__in=piutang_ids))),
            ("Pembayaran Hutang", PembayaranHutang.objects.filter(Q(keterangan__icontains=TEST_MARK) | Q(hutang_id__in=hutang_ids))),
            (
                "Piutang",
                Piutang.objects.filter(
                    Q(keterangan__icontains=TEST_MARK)
                    | Q(sumber_ref__startswith=PREFIX)
                    | Q(sales_order_id__in=so_ids)
                    | Q(pos_transaction_id__in=pos_ids)
                ),
            ),
            (
                "Hutang",
                Hutang.objects.filter(
                    Q(keterangan__icontains=TEST_MARK)
                    | Q(sumber_ref__startswith=PREFIX)
                    | Q(purchase_order_id__in=po_ids)
                ),
            ),
            ("Rekonsiliasi Kas/Bank", KasBankReconciliation.objects.filter(catatan__icontains=TEST_MARK)),
            ("Transfer Kas/Bank", KasBankTransfer.objects.filter(catatan__icontains=TEST_MARK)),
            ("Mutasi Kas/Bank", KasBankTransaction.objects.filter(kas_bank_transaction_filter)),
            ("Transaksi Biaya", TransaksiBiaya.objects.filter(deskripsi__icontains=TEST_MARK)),
            ("Adjustment Stok", AdjustmentStok.objects.filter(alasan__icontains=TEST_MARK)),
            ("Transfer Stok", TransferStok.objects.filter(catatan__icontains=TEST_MARK)),
            ("POS", POSTransaction.objects.filter(catatan__icontains=TEST_MARK)),
            ("Sales Order", SalesOrder.objects.filter(catatan__icontains=TEST_MARK)),
            ("Purchase Order", PurchaseOrder.objects.filter(catatan__icontains=TEST_MARK)),
            ("Penggajian", Penggajian.objects.filter(catatan__icontains=TEST_MARK)),
            ("Absensi", Absensi.objects.filter(catatan__icontains=TEST_MARK)),
            ("Karyawan", Karyawan.objects.filter(nik__startswith=f"{PREFIX}-")),
            ("Jabatan", Jabatan.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Departemen", Departemen.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Jurnal", JurnalEntry.objects.filter(journal_filter)),
            ("Stok", Stok.objects.filter(Q(produk__sku__startswith=f"{PREFIX}-") | Q(gudang__kode__startswith=f"{PREFIX}-"))),
            ("Produk", Produk.objects.filter(sku__startswith=f"{PREFIX}-")),
            ("Supplier", Supplier.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Customer", Customer.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Kategori Biaya", KategoriBiaya.objects.filter(nama__startswith=f"{PREFIX} ")),
            ("Cabang/Gudang", Gudang.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Kategori Produk", Kategori.objects.filter(nama__startswith=f"{PREFIX} ")),
            ("Satuan", Satuan.objects.filter(nama__startswith=f"{PREFIX} ")),
            ("Metode Pembayaran", MetodePembayaran.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Akun Kas & Bank", KasBankAccount.objects.filter(kode__startswith=f"{PREFIX}-")),
            ("Periode Akuntansi", PeriodeAkuntansi.objects.filter(nama__startswith=f"{PREFIX} ")),
        ]

        with transaction.atomic():
            for label, queryset in delete_plan:
                count = queryset.count()
                if count:
                    queryset.delete()
                    self.counts[f"{label} dihapus"] += count

    def print_summary(self):
        self.stdout.write(self.style.SUCCESS("Seed data testing operasional selesai."))
        for label in sorted(self.counts.keys()):
            self.stdout.write(f"- {label}: {self.counts[label]}")
        if self.warnings:
            self.stdout.write(self.style.WARNING("Catatan:"))
            for warning in self.warnings:
                self.stdout.write(f"- {warning}")
        self.stdout.write("")
        self.stdout.write("Cara pakai:")
        self.stdout.write("  python manage.py seed_operational_test_data")
        self.stdout.write("  python manage.py seed_operational_test_data --scale 2 --months 6")
        self.stdout.write(
            "  python manage.py seed_operational_test_data --clear-test-data --confirm CLEAR_TEST_DATA"
        )
