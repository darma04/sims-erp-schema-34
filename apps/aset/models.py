"""
==========================================================================
 ASET TETAP MODELS - Fixed Asset Management
==========================================================================
 Model:
 1. AsetTetap      → Master data aset (peralatan, kendaraan, bangunan)
 2. Penyusutan     → Pencatatan depresiasi bulanan
 3. DisposalAset   → Penjualan / penghapusan aset
==========================================================================
"""

from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class AsetTetap(models.Model):
    """
    Model ASET TETAP — harta perusahaan jangka panjang (>1 tahun).

    PSAK 16: Aset Tetap diakui sebesar harga perolehan dan disusutkan
    selama umur ekonomisnya. Nilai Buku = Harga Perolehan - Akumulasi Penyusutan.
    """

    KATEGORI_CHOICES = [
        ('peralatan', 'Peralatan'),
        ('kendaraan', 'Kendaraan'),
        ('bangunan', 'Bangunan'),
        ('tanah', 'Tanah'),
        ('mesin', 'Mesin'),
        ('inventaris', 'Inventaris Kantor'),
        ('lainnya', 'Lainnya'),
    ]

    METODE_PENYUSUTAN_CHOICES = [
        ('garis_lurus', 'Garis Lurus (Straight-Line)'),
        ('saldo_menurun', 'Saldo Menurun Ganda (Double-Declining)'),
    ]

    STATUS_CHOICES = [
        ('aktif', 'Aktif'),
        ('dijual', 'Dijual'),
        ('dihapuskan', 'Dihapuskan'),
        ('rusak', 'Rusak/Tidak Terpakai'),
    ]

    # Identitas
    kode = models.CharField(max_length=30, unique=True, verbose_name="Kode Aset")
    nama = models.CharField(max_length=200, verbose_name="Nama Aset")
    kategori = models.CharField(max_length=20, choices=KATEGORI_CHOICES, verbose_name="Kategori")
    deskripsi = models.TextField(blank=True, default='', verbose_name="Deskripsi")

    # Relasi ke CoA (akun aset di neraca)
    akun_aset = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT,
        related_name='aset_tetap_set', verbose_name="Akun Aset (CoA)",
        null=True, blank=True,
        help_text="Akun neraca untuk aset ini (misal: 1-4000 Peralatan)"
    )

    # Nilai aset
    harga_perolehan = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Harga Perolehan")
    nilai_residu = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Nilai Residu",
                                        help_text="Estimasi nilai saat habis umur ekonomis")
    umur_ekonomis = models.IntegerField(verbose_name="Umur Ekonomis (Bulan)",
                                         help_text="Lama pemakaian dalam bulan")

    # Tanggal
    tanggal_perolehan = models.DateField(verbose_name="Tanggal Perolehan")

    # Penyusutan
    metode_penyusutan = models.CharField(
        max_length=20, choices=METODE_PENYUSUTAN_CHOICES, default='garis_lurus',
        verbose_name="Metode Penyusutan"
    )

    # Pembelian
    supplier = models.ForeignKey(
        'pembelian.Supplier', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Supplier"
    )

    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aktif', verbose_name="Status")

    # Cabang
    cabang = models.ForeignKey(
        'produk.Gudang', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='aset_tetap_set', verbose_name="Cabang/Lokasi"
    )

    # Relasi ke Jurnal (untuk tracking jurnal penyusutan)
    jurnal_penyusutan = models.ForeignKey(
        'akuntansi.JurnalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='penyusutan_aset',
        verbose_name="Jurnal Penyusutan",
        help_text="Jurnal otomatis untuk penyusutan bulanan"
    )

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dibuat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Aset Tetap"
        verbose_name_plural = "Aset Tetap"
        ordering = ['-tanggal_perolehan']
        indexes = [
            models.Index(fields=['status', 'tanggal_perolehan'], name='asset_status_tgl_idx'),
            models.Index(fields=['cabang', 'status'], name='asset_cabang_status_idx'),
            models.Index(fields=['supplier', 'status'], name='asset_supplier_status_idx'),
            models.Index(fields=['kategori', 'status'], name='asset_kategori_status_idx'),
        ]

    def __str__(self):
        return f"{self.kode} - {self.nama}"

    def save(self, *args, **kwargs):
        if not self.kode:
            self.kode = self.generate_kode()
        super().save(*args, **kwargs)

    def generate_kode(self):
        prefix_map = {
            'peralatan': 'AST-EQ', 'kendaraan': 'AST-VH', 'bangunan': 'AST-BG',
            'tanah': 'AST-TN', 'mesin': 'AST-MC', 'inventaris': 'AST-IV', 'lainnya': 'AST-XX',
        }
        prefix = prefix_map.get(self.kategori, 'AST-XX')
        with transaction.atomic():
            last = AsetTetap.objects.select_for_update().filter(
                kode__startswith=prefix
            ).order_by('-kode').first()
            if last:
                try:
                    last_num = int(last.kode.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = AsetTetap.objects.filter(kode__startswith=prefix).count() + 1
            else:
                new_num = 1
            kode = f"{prefix}-{new_num:04d}"
            while AsetTetap.objects.filter(kode=kode).exists():
                new_num += 1
                kode = f"{prefix}-{new_num:04d}"
        return kode

    @property
    def akumulasi_penyusutan(self):
        """Total akumulasi penyusutan dari semua record."""
        return self.penyusutan_set.aggregate(
            total=models.Sum('jumlah')
        )['total'] or Decimal('0')

    @property
    def nilai_buku(self):
        """Nilai Buku = Harga Perolehan - Akumulasi Penyusutan."""
        return self.harga_perolehan - self.akumulasi_penyusutan

    @property
    def penyusutan_per_bulan(self):
        """Hitung penyusutan per bulan berdasarkan metode."""
        if self.umur_ekonomis <= 0:
            return Decimal('0')
        if self.metode_penyusutan == 'garis_lurus':
            return (self.harga_perolehan - self.nilai_residu) / self.umur_ekonomis
        elif self.metode_penyusutan == 'saldo_menurun':
            rate = Decimal('2') / Decimal(str(self.umur_ekonomis))
            return self.nilai_buku * rate
        return Decimal('0')

    @property
    def persentase_penyusutan(self):
        """Persentase penyusutan terhadap harga perolehan."""
        if self.harga_perolehan <= 0:
            return 0
        return round(float(self.akumulasi_penyusutan / self.harga_perolehan * 100), 1)

    @property
    def sisa_umur_bulan(self):
        """Sisa umur ekonomis dalam bulan."""
        total_penyusutan = self.penyusutan_set.count()
        return max(0, self.umur_ekonomis - total_penyusutan)


class Penyusutan(models.Model):
    """
    Model PENYUSUTAN — depresiasi bulanan aset tetap.

    Setiap record = 1 bulan penyusutan.
    Jurnal: D:Beban Penyusutan (6-4000) K:Akumulasi Penyusutan (1-4100)
    """

    aset = models.ForeignKey(AsetTetap, on_delete=models.CASCADE,
                              related_name='penyusutan_set', verbose_name="Aset")
    bulan = models.IntegerField(verbose_name="Bulan (1-12)")
    tahun = models.IntegerField(verbose_name="Tahun")
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah Penyusutan")
    akumulasi = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                     verbose_name="Akumulasi s/d Bulan Ini")

    # Jurnal otomatis
    jurnal = models.ForeignKey(
        'akuntansi.JurnalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Jurnal Entry"
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Penyusutan"
        verbose_name_plural = "Penyusutan"
        ordering = ['-tahun', '-bulan']
        unique_together = ['aset', 'bulan', 'tahun']
        indexes = [
            models.Index(fields=['tahun', 'bulan'], name='depr_year_month_idx'),
            models.Index(fields=['aset', 'tahun'], name='depr_asset_year_idx'),
        ]

    def __str__(self):
        return f"Penyusutan {self.aset.kode} - {self.bulan:02d}/{self.tahun}"


class DisposalAset(models.Model):
    """
    Model DISPOSAL ASET — penjualan atau penghapusan aset tetap.

    Jika dijual > nilai buku → Laba disposal (Pendapatan Lain-lain)
    Jika dijual < nilai buku → Rugi disposal (Beban Lain-lain)
    """

    TIPE_CHOICES = [
        ('jual', 'Dijual'),
        ('hapus', 'Dihapuskan'),
    ]

    aset = models.ForeignKey(AsetTetap, on_delete=models.CASCADE,
                              related_name='disposal_set', verbose_name="Aset")
    tipe = models.CharField(max_length=10, choices=TIPE_CHOICES, verbose_name="Tipe Disposal")
    tanggal = models.DateField(verbose_name="Tanggal Disposal")
    harga_jual = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                      verbose_name="Harga Jual",
                                      help_text="0 jika dihapuskan")
    nilai_buku_saat_disposal = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                                     verbose_name="Nilai Buku saat Disposal")
    laba_rugi = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                     verbose_name="Laba/Rugi Disposal",
                                     help_text="Positif=Laba, Negatif=Rugi")
    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    jurnal = models.ForeignKey(
        'akuntansi.JurnalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Jurnal Entry"
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Disposal Aset"
        verbose_name_plural = "Disposal Aset"
        ordering = ['-tanggal']
        indexes = [
            models.Index(fields=['tanggal', 'tipe'], name='asset_disp_tgl_type_idx'),
            models.Index(fields=['aset', 'tanggal'], name='asset_disp_asset_tgl_idx'),
        ]

    def __str__(self):
        return f"Disposal {self.aset.kode} - {self.get_tipe_display()}"

    def save(self, *args, **kwargs):
        self.laba_rugi = self.harga_jual - self.nilai_buku_saat_disposal
        super().save(*args, **kwargs)
