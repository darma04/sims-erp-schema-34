from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("akuntansi", "0001_initial"),
        ("produk", "0006_produk_metode_pembayaran"),
        ("pos", "0007_add_satuan_transaksi_jumlah_konversi_to_postransactionitem"),
    ]

    operations = [
        migrations.CreateModel(
            name="KasBankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kode", models.CharField(max_length=30, unique=True, verbose_name="Kode Akun Kas/Bank")),
                ("nama", models.CharField(max_length=120, verbose_name="Nama Akun Kas/Bank")),
                (
                    "tipe",
                    models.CharField(
                        choices=[
                            ("kas", "Kas"),
                            ("bank", "Bank"),
                            ("qris", "QRIS"),
                            ("ewallet", "E-Wallet"),
                            ("clearing", "Clearing"),
                        ],
                        default="kas",
                        max_length=20,
                        verbose_name="Tipe",
                    ),
                ),
                ("nomor_rekening", models.CharField(blank=True, max_length=80, null=True, verbose_name="Nomor Rekening")),
                ("nama_bank", models.CharField(blank=True, max_length=120, null=True, verbose_name="Nama Bank/Penyedia")),
                ("nama_pemilik", models.CharField(blank=True, max_length=120, null=True, verbose_name="Nama Pemilik")),
                ("saldo_awal", models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Saldo Awal")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("is_default", models.BooleanField(default=False, verbose_name="Default")),
                ("dibuat_pada", models.DateTimeField(auto_now_add=True)),
                ("diubah_pada", models.DateTimeField(auto_now=True)),
                (
                    "akun",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="kas_bank_accounts",
                        to="akuntansi.akun",
                        verbose_name="Akun CoA",
                    ),
                ),
                (
                    "dibuat_oleh",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_accounts_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Akun Kas/Bank",
                "verbose_name_plural": "Akun Kas/Bank",
                "ordering": ["kode"],
            },
        ),
        migrations.CreateModel(
            name="KasBankTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nomor", models.CharField(max_length=50, unique=True, verbose_name="Nomor Mutasi")),
                ("tanggal", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Tanggal")),
                (
                    "tipe",
                    models.CharField(
                        choices=[
                            ("masuk", "Masuk"),
                            ("keluar", "Keluar"),
                            ("transfer_masuk", "Transfer Masuk"),
                            ("transfer_keluar", "Transfer Keluar"),
                            ("penyesuaian_masuk", "Penyesuaian Masuk"),
                            ("penyesuaian_keluar", "Penyesuaian Keluar"),
                        ],
                        max_length=25,
                        verbose_name="Tipe Mutasi",
                    ),
                ),
                ("deskripsi", models.CharField(max_length=255, verbose_name="Deskripsi")),
                ("jumlah", models.DecimalField(decimal_places=2, max_digits=15, verbose_name="Jumlah")),
                ("sumber_app", models.CharField(blank=True, max_length=50, null=True, verbose_name="Sumber App")),
                ("sumber_model", models.CharField(blank=True, max_length=80, null=True, verbose_name="Sumber Model")),
                ("sumber_id", models.PositiveIntegerField(blank=True, null=True, verbose_name="ID Sumber")),
                ("sumber_ref", models.CharField(blank=True, max_length=80, null=True, verbose_name="Referensi Sumber")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Dibatalkan")],
                        default="draft",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                ("catatan", models.TextField(blank=True, null=True, verbose_name="Catatan")),
                ("dibuat_pada", models.DateTimeField(auto_now_add=True)),
                ("diubah_pada", models.DateTimeField(auto_now=True)),
                (
                    "akun_kas_bank",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mutasi",
                        to="kas_bank.kasbankaccount",
                        verbose_name="Akun Kas/Bank",
                    ),
                ),
                (
                    "akun_lawan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_mutasi_lawan",
                        to="akuntansi.akun",
                        verbose_name="Akun Lawan",
                    ),
                ),
                (
                    "cabang",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_mutasi",
                        to="produk.gudang",
                        verbose_name="Cabang/Gudang",
                    ),
                ),
                (
                    "dibuat_oleh",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_transactions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "jurnal_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_mutasi",
                        to="akuntansi.jurnalentry",
                        verbose_name="Jurnal",
                    ),
                ),
                (
                    "metode_pembayaran",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_mutasi",
                        to="pos.metodepembayaran",
                        verbose_name="Metode Pembayaran",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mutasi Kas/Bank",
                "verbose_name_plural": "Mutasi Kas/Bank",
                "ordering": ["-tanggal", "-id"],
            },
        ),
        migrations.CreateModel(
            name="KasBankTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nomor", models.CharField(max_length=50, unique=True, verbose_name="Nomor Transfer")),
                ("tanggal", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Tanggal")),
                ("jumlah", models.DecimalField(decimal_places=2, max_digits=15, verbose_name="Jumlah")),
                ("biaya_admin", models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Biaya Admin")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Dibatalkan")],
                        default="draft",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                ("catatan", models.TextField(blank=True, null=True, verbose_name="Catatan")),
                ("dibuat_pada", models.DateTimeField(auto_now_add=True)),
                ("diubah_pada", models.DateTimeField(auto_now=True)),
                (
                    "akun_biaya_admin",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_transfer_biaya_admin",
                        to="akuntansi.akun",
                        verbose_name="Akun Biaya Admin",
                    ),
                ),
                (
                    "cabang",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_transfer",
                        to="produk.gudang",
                        verbose_name="Cabang/Gudang",
                    ),
                ),
                (
                    "dari_akun",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transfer_keluar",
                        to="kas_bank.kasbankaccount",
                        verbose_name="Dari Akun",
                    ),
                ),
                (
                    "dibuat_oleh",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_transfers_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "jurnal_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_transfer",
                        to="akuntansi.jurnalentry",
                        verbose_name="Jurnal",
                    ),
                ),
                (
                    "ke_akun",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transfer_masuk",
                        to="kas_bank.kasbankaccount",
                        verbose_name="Ke Akun",
                    ),
                ),
            ],
            options={
                "verbose_name": "Transfer Kas/Bank",
                "verbose_name_plural": "Transfer Kas/Bank",
                "ordering": ["-tanggal", "-id"],
            },
        ),
        migrations.CreateModel(
            name="KasBankReconciliation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tanggal_mulai", models.DateField(verbose_name="Tanggal Mulai")),
                ("tanggal_akhir", models.DateField(verbose_name="Tanggal Akhir")),
                ("saldo_sistem", models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Saldo Sistem")),
                (
                    "saldo_statement",
                    models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Saldo Statement"),
                ),
                ("selisih", models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Selisih")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("reconciled", "Direkonsiliasi"), ("cancelled", "Dibatalkan")],
                        default="draft",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                ("catatan", models.TextField(blank=True, null=True, verbose_name="Catatan")),
                ("dibuat_pada", models.DateTimeField(auto_now_add=True)),
                ("diubah_pada", models.DateTimeField(auto_now=True)),
                (
                    "akun_kas_bank",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rekonsiliasi",
                        to="kas_bank.kasbankaccount",
                        verbose_name="Akun Kas/Bank",
                    ),
                ),
                (
                    "dibuat_oleh",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kas_bank_reconciliations_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Rekonsiliasi Kas/Bank",
                "verbose_name_plural": "Rekonsiliasi Kas/Bank",
                "ordering": ["-tanggal_akhir", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="kasbanktransaction",
            index=models.Index(fields=["sumber_app", "sumber_model", "sumber_id"], name="kas_bank_ka_sumber__5b5482_idx"),
        ),
        migrations.AddIndex(
            model_name="kasbanktransaction",
            index=models.Index(fields=["tanggal", "status"], name="kas_bank_ka_tanggal_ad7343_idx"),
        ),
    ]
