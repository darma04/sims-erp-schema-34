"""
==========================================================================
 PAJAK MODELS - Tax Engine (PPN / e-Faktur)
==========================================================================
 Model:
 1. SettingPajak  → Konfigurasi tarif PPN, NPWP perusahaan
 2. FakturPajak  → Faktur pajak masukan & keluaran
==========================================================================
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class SettingPajak(models.Model):
    """
    Konfigurasi pajak perusahaan — singleton (hanya 1 record).
    """
    tarif_ppn = models.DecimalField(
        max_digits=5, decimal_places=2, default=11.00,
        verbose_name="Tarif PPN (%)",
        help_text="Tarif PPN Indonesia saat ini: 11%"
    )
    npwp = models.CharField(max_length=30, blank=True, default='', verbose_name="NPWP Perusahaan")
    nama_pkp = models.CharField(max_length=200, blank=True, default='', verbose_name="Nama PKP")
    alamat_pkp = models.TextField(blank=True, default='', verbose_name="Alamat PKP")
    is_pkp = models.BooleanField(default=False, verbose_name="Terdaftar PKP?",
                                  help_text="Jika PKP, wajib pungut PPN")

    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Setting Pajak"
        verbose_name_plural = "Setting Pajak"

    def __str__(self):
        return f"Setting PPN: {self.tarif_ppn}%"

    @classmethod
    def get_setting(cls):
        """Ambil/buat setting pajak (singleton)."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FakturPajak(models.Model):
    """
    Model FAKTUR PAJAK — untuk pencatatan PPN masukan & keluaran.

    PPN Masukan = PPN yang kita bayar ke supplier (saat beli)
    PPN Keluaran = PPN yang kita pungut dari customer (saat jual)
    Setor PPN = PPN Keluaran - PPN Masukan (jika positif → setor ke negara)
    """

    TIPE_CHOICES = [
        ('masukan', 'PPN Masukan (Pembelian)'),
        ('keluaran', 'PPN Keluaran (Penjualan)'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Disetujui'),
        ('reported', 'Dilaporkan'),
        ('batal', 'Dibatalkan'),
    ]

    # Identitas
    nomor_seri = models.CharField(max_length=50, unique=True, verbose_name="Nomor Seri Faktur")
    tipe = models.CharField(max_length=10, choices=TIPE_CHOICES, verbose_name="Tipe Faktur")
    tanggal = models.DateField(verbose_name="Tanggal Faktur", default=timezone.now)

    # Nilai
    dpp = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="DPP (Dasar Pengenaan Pajak)")
    tarif_ppn = models.DecimalField(max_digits=5, decimal_places=2, default=11.00, verbose_name="Tarif PPN (%)")
    ppn = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="PPN")

    # Lawan transaksi
    nama_lawan = models.CharField(max_length=200, verbose_name="Nama Lawan Transaksi")
    npwp_lawan = models.CharField(max_length=30, blank=True, default='', verbose_name="NPWP Lawan")

    # Referensi ke SO/PO
    sales_order = models.ForeignKey(
        'penjualan.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='faktur_pajak_set', verbose_name="Sales Order"
    )
    purchase_order = models.ForeignKey(
        'pembelian.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='faktur_pajak_set', verbose_name="Purchase Order"
    )
    pos_transaction = models.ForeignKey(
        'pos.POSTransaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='faktur_pajak_set', verbose_name="Transaksi POS"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name="Status")
    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dibuat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Faktur Pajak"
        verbose_name_plural = "Faktur Pajak"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'tipe', 'status'], name='tax_faktur_tgl_type_idx'),
            models.Index(fields=['sales_order', 'tipe'], name='tax_faktur_so_type_idx'),
            models.Index(fields=['purchase_order', 'tipe'], name='tax_faktur_po_type_idx'),
            models.Index(fields=['pos_transaction', 'tipe'], name='tax_faktur_pos_type_idx'),
        ]

    def __str__(self):
        return f"{self.nomor_seri} - {self.get_tipe_display()}"

    def save(self, *args, **kwargs):
        # Auto-calc PPN
        self.ppn = self.dpp * self.tarif_ppn / Decimal('100')
        super().save(*args, **kwargs)

    @property
    def total(self):
        return self.dpp + self.ppn


class PembayaranPPN(models.Model):
    """
    Model PEMBAYARAN PPN — pelunasan setor/restitusi PPN bulanan.

    Setiap record merepresentasikan satu kali setor (atau penerimaan restitusi)
    PPN ke kas negara. Saat dibuat:

      - Jika tipe=setor (PPN Keluaran > Masukan):
            D: 2-2000 PPN Keluaran          Σ keluaran
            D: ─                            ─
              K: 1-1500 PPN Masukan         Σ masukan
              K: Kas/Bank                    selisih (jumlah_setor)
      - Jika tipe=restitusi (PPN Masukan > Keluaran):
            D: 2-2000 PPN Keluaran          Σ keluaran
            D: Kas/Bank (atau 1-2500 piutang restitusi) selisih
              K: 1-1500 PPN Masukan         Σ masukan

    Semua FakturPajak periode tersebut akan otomatis dimark sebagai 'reported'.
    """

    TIPE_CHOICES = [
        ('setor', 'Setor (Kurang Bayar)'),
        ('restitusi', 'Restitusi (Lebih Bayar)'),
    ]

    nomor = models.CharField(max_length=50, unique=True, verbose_name="Nomor Setor")
    tipe = models.CharField(max_length=15, choices=TIPE_CHOICES, default='setor', verbose_name="Tipe")

    # Periode pelaporan
    masa_bulan = models.IntegerField(verbose_name="Masa Bulan", help_text="1-12")
    masa_tahun = models.IntegerField(verbose_name="Masa Tahun")

    # Total PPN periode
    total_ppn_keluaran = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total PPN Keluaran")
    total_ppn_masukan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total PPN Masukan")
    jumlah_setor = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Setor / Restitusi")

    # Tanggal & metode pembayaran
    tanggal_setor = models.DateField(default=timezone.now, verbose_name="Tanggal Setor")
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Metode Pembayaran"
    )
    nomor_bukti = models.CharField(max_length=80, blank=True, default='',
                                    verbose_name="No. Bukti / NTPN",
                                    help_text="Nomor bukti setor pajak (NTPN) jika ada")

    # Jurnal otomatis
    jurnal = models.ForeignKey(
        'akuntansi.JurnalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pembayaran_ppn',
        verbose_name="Jurnal Entry"
    )

    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dibuat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pembayaran PPN"
        verbose_name_plural = "Pembayaran PPN"
        ordering = ['-tanggal_setor', '-dibuat_pada']
        unique_together = ['masa_bulan', 'masa_tahun']
        indexes = [
            models.Index(fields=['masa_tahun', 'masa_bulan'], name='tax_ppn_masa_idx'),
            models.Index(fields=['tanggal_setor', 'tipe'], name='tax_ppn_tgl_type_idx'),
            models.Index(fields=['metode_pembayaran', 'tanggal_setor'], name='tax_ppn_metode_tgl_idx'),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.masa_bulan:02d}/{self.masa_tahun}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self.generate_nomor()
        selisih = (self.total_ppn_keluaran or Decimal('0')) - (self.total_ppn_masukan or Decimal('0'))
        if selisih > 0:
            self.tipe = 'setor'
            self.jumlah_setor = selisih
        elif selisih < 0:
            self.tipe = 'restitusi'
            self.jumlah_setor = abs(selisih)
        else:
            self.jumlah_setor = Decimal('0')
        super().save(*args, **kwargs)

    def generate_nomor(self):
        prefix = f"PPN/{self.masa_tahun}/{self.masa_bulan:02d}"
        # Cek apakah sudah ada record dengan periode ini (unique_together)
        if PembayaranPPN.objects.filter(masa_bulan=self.masa_bulan, masa_tahun=self.masa_tahun).exists():
            return f"{prefix}/REV"
        return f"{prefix}/0001"
