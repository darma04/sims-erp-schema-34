from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class KasBankAccount(models.Model):
    TIPE_CHOICES = [
        ("kas", "Kas"),
        ("bank", "Bank"),
        ("qris", "QRIS"),
        ("ewallet", "E-Wallet"),
        ("clearing", "Clearing"),
    ]

    kode = models.CharField(max_length=30, unique=True, verbose_name="Kode Akun Kas/Bank")
    nama = models.CharField(max_length=120, verbose_name="Nama Akun Kas/Bank")
    tipe = models.CharField(max_length=20, choices=TIPE_CHOICES, default="kas", verbose_name="Tipe")
    akun = models.ForeignKey(
        "akuntansi.Akun",
        on_delete=models.PROTECT,
        related_name="kas_bank_accounts",
        verbose_name="Akun CoA",
    )
    nomor_rekening = models.CharField(max_length=80, blank=True, null=True, verbose_name="Nomor Rekening")
    nama_bank = models.CharField(max_length=120, blank=True, null=True, verbose_name="Nama Bank/Penyedia")
    nama_pemilik = models.CharField(max_length=120, blank=True, null=True, verbose_name="Nama Pemilik")
    saldo_awal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo Awal")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    is_default = models.BooleanField(default=False, verbose_name="Default")
    dibuat_oleh = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="kas_bank_accounts_created"
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akun Kas/Bank"
        verbose_name_plural = "Akun Kas/Bank"
        ordering = ["kode"]
        indexes = [
            models.Index(fields=["tipe", "aktif"], name="kb_acc_tipe_aktif_idx"),
            models.Index(fields=["aktif", "is_default"], name="kb_acc_default_idx"),
        ]

    def __str__(self):
        return f"{self.kode} - {self.nama}"

    @property
    def total_masuk(self):
        total = self.mutasi.filter(tipe__in=["masuk", "transfer_masuk", "penyesuaian_masuk"], status="posted").aggregate(
            total=models.Sum("jumlah")
        )["total"]
        return total or Decimal("0")

    @property
    def total_keluar(self):
        total = self.mutasi.filter(tipe__in=["keluar", "transfer_keluar", "penyesuaian_keluar"], status="posted").aggregate(
            total=models.Sum("jumlah")
        )["total"]
        return total or Decimal("0")

    @property
    def saldo_terhitung(self):
        return self.saldo_awal + self.total_masuk - self.total_keluar


class KasBankTransaction(models.Model):
    TIPE_CHOICES = [
        ("masuk", "Masuk"),
        ("keluar", "Keluar"),
        ("transfer_masuk", "Transfer Masuk"),
        ("transfer_keluar", "Transfer Keluar"),
        ("penyesuaian_masuk", "Penyesuaian Masuk"),
        ("penyesuaian_keluar", "Penyesuaian Keluar"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancelled", "Dibatalkan"),
    ]

    nomor = models.CharField(max_length=50, unique=True, verbose_name="Nomor Mutasi")
    tanggal = models.DateTimeField(default=timezone.now, verbose_name="Tanggal")
    akun_kas_bank = models.ForeignKey(
        KasBankAccount, on_delete=models.PROTECT, related_name="mutasi", verbose_name="Akun Kas/Bank"
    )
    tipe = models.CharField(max_length=25, choices=TIPE_CHOICES, verbose_name="Tipe Mutasi")
    deskripsi = models.CharField(max_length=255, verbose_name="Deskripsi")
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")
    akun_lawan = models.ForeignKey(
        "akuntansi.Akun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_mutasi_lawan",
        verbose_name="Akun Lawan",
    )
    cabang = models.ForeignKey(
        "produk.Gudang",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_mutasi",
        verbose_name="Cabang/Gudang",
    )
    metode_pembayaran = models.ForeignKey(
        "pos.MetodePembayaran",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_mutasi",
        verbose_name="Metode Pembayaran",
    )
    sumber_app = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sumber App")
    sumber_model = models.CharField(max_length=80, blank=True, null=True, verbose_name="Sumber Model")
    sumber_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="ID Sumber")
    sumber_ref = models.CharField(max_length=80, blank=True, null=True, verbose_name="Referensi Sumber")
    jurnal_entry = models.ForeignKey(
        "akuntansi.JurnalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_mutasi",
        verbose_name="Jurnal",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="kas_bank_transactions_created"
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mutasi Kas/Bank"
        verbose_name_plural = "Mutasi Kas/Bank"
        ordering = ["-tanggal", "-id"]
        indexes = [
            models.Index(fields=["sumber_app", "sumber_model", "sumber_id"]),
            models.Index(fields=["tanggal", "status"]),
            models.Index(fields=["akun_kas_bank", "status", "tanggal"], name="kb_mut_akun_status_idx"),
            models.Index(fields=["cabang", "tanggal"], name="kb_mut_cabang_tgl_idx"),
            models.Index(fields=["metode_pembayaran", "status", "tanggal"], name="kb_mut_metode_status_idx"),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.get_tipe_display()} - {self.jumlah:,.0f}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self.generate_nomor()
        super().save(*args, **kwargs)

    def generate_nomor(self):
        prefix = f"KB/{timezone.now().year}/{timezone.now().month:02d}"
        last = KasBankTransaction.objects.filter(nomor__startswith=prefix).order_by("-nomor").first()
        if last:
            try:
                number = int(last.nomor.split("/")[-1]) + 1
            except (ValueError, IndexError):
                number = KasBankTransaction.objects.filter(nomor__startswith=prefix).count() + 1
        else:
            number = 1
        nomor = f"{prefix}/{number:04d}"
        while KasBankTransaction.objects.filter(nomor=nomor).exists():
            number += 1
            nomor = f"{prefix}/{number:04d}"
        return nomor

    @property
    def is_debit_kas(self):
        return self.tipe in ["masuk", "transfer_masuk", "penyesuaian_masuk"]


class KasBankTransfer(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancelled", "Dibatalkan"),
    ]

    nomor = models.CharField(max_length=50, unique=True, verbose_name="Nomor Transfer")
    tanggal = models.DateTimeField(default=timezone.now, verbose_name="Tanggal")
    dari_akun = models.ForeignKey(
        KasBankAccount, on_delete=models.PROTECT, related_name="transfer_keluar", verbose_name="Dari Akun"
    )
    ke_akun = models.ForeignKey(
        KasBankAccount, on_delete=models.PROTECT, related_name="transfer_masuk", verbose_name="Ke Akun"
    )
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")
    biaya_admin = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Biaya Admin")
    akun_biaya_admin = models.ForeignKey(
        "akuntansi.Akun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_transfer_biaya_admin",
        verbose_name="Akun Biaya Admin",
    )
    cabang = models.ForeignKey(
        "produk.Gudang",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_transfer",
        verbose_name="Cabang/Gudang",
    )
    jurnal_entry = models.ForeignKey(
        "akuntansi.JurnalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kas_bank_transfer",
        verbose_name="Jurnal",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="kas_bank_transfers_created"
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transfer Kas/Bank"
        verbose_name_plural = "Transfer Kas/Bank"
        ordering = ["-tanggal", "-id"]
        indexes = [
            models.Index(fields=["status", "tanggal"], name="kb_trf_status_tgl_idx"),
            models.Index(fields=["dari_akun", "status"], name="kb_trf_dari_status_idx"),
            models.Index(fields=["ke_akun", "status"], name="kb_trf_ke_status_idx"),
            models.Index(fields=["cabang", "tanggal"], name="kb_trf_cabang_tgl_idx"),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.dari_akun} ke {self.ke_akun}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self.generate_nomor()
        super().save(*args, **kwargs)

    def generate_nomor(self):
        prefix = f"TRF/{timezone.now().year}/{timezone.now().month:02d}"
        last = KasBankTransfer.objects.filter(nomor__startswith=prefix).order_by("-nomor").first()
        if last:
            try:
                number = int(last.nomor.split("/")[-1]) + 1
            except (ValueError, IndexError):
                number = KasBankTransfer.objects.filter(nomor__startswith=prefix).count() + 1
        else:
            number = 1
        nomor = f"{prefix}/{number:04d}"
        while KasBankTransfer.objects.filter(nomor=nomor).exists():
            number += 1
            nomor = f"{prefix}/{number:04d}"
        return nomor


class KasBankReconciliation(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("reconciled", "Direkonsiliasi"),
        ("cancelled", "Dibatalkan"),
    ]

    akun_kas_bank = models.ForeignKey(
        KasBankAccount, on_delete=models.PROTECT, related_name="rekonsiliasi", verbose_name="Akun Kas/Bank"
    )
    tanggal_mulai = models.DateField(verbose_name="Tanggal Mulai")
    tanggal_akhir = models.DateField(verbose_name="Tanggal Akhir")
    saldo_sistem = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo Sistem")
    saldo_statement = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo Statement")
    selisih = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Selisih")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="kas_bank_reconciliations_created"
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rekonsiliasi Kas/Bank"
        verbose_name_plural = "Rekonsiliasi Kas/Bank"
        ordering = ["-tanggal_akhir", "-id"]
        indexes = [
            models.Index(fields=["akun_kas_bank", "status", "tanggal_akhir"], name="kb_rek_akun_status_idx"),
            models.Index(fields=["status", "tanggal_akhir"], name="kb_rek_status_tgl_idx"),
        ]

    def __str__(self):
        return f"{self.akun_kas_bank} - {self.tanggal_mulai} s/d {self.tanggal_akhir}"

    def save(self, *args, **kwargs):
        self.selisih = self.saldo_statement - self.saldo_sistem
        super().save(*args, **kwargs)
