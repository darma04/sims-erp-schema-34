"""
==========================================================================
 SERVICE CENTER MODELS - Model Data Service Elektronik
==========================================================================
 File ini berisi model database untuk manajemen service elektronik:

 1. Pelanggan → Data pelanggan yang membawa perangkat untuk di-service
 2. Perangkat → Jenis perangkat (HP Android, iPhone, TV, Laptop, dll)
 3. OrderService → Dokumen utama penerimaan & pelacakan service
 4. ItemService → Detail layanan/perbaikan per order
 5. RiwayatStatus → Log perubahan status order service

 ALUR SERVICE:
 ┌──────────┐   ┌──────────┐   ┌─────────────────┐   ┌────────────┐
 │ Diterima │──→│ Diagnosa │──→│ Menunggu        │──→│ Dikerjakan │
 └──────────┘   └──────────┘   │ Konfirmasi      │   └────────────┘
                                └─────────────────┘         │
                                       │                    ▼
                                       │              ┌──────────┐
                                       │              │  Selesai  │
                                       │              └──────────┘
                                       │                    │
                                       ▼                    ▼
                                ┌─────────────┐     ┌──────────┐
                                │ Dibatalkan  │     │  Diambil  │
                                └─────────────┘     └──────────┘
==========================================================================
"""

import uuid

from django.db import models
from django.contrib.auth.models import User


class Pelanggan(models.Model):
    """
    Model untuk DATA PELANGGAN service center.

    Menyimpan informasi pelanggan yang membawa perangkat elektronik
    untuk diperbaiki. Setiap pelanggan memiliki kode unik (auto-generate).

    Contoh data:
    | kode      | nama           | telepon      |
    |-----------|----------------|--------------|
    | PLG-00001 | Budi Santoso   | 081234567890 |
    | PLG-00002 | Siti Aminah    | 085678901234 |
    """
    # Kode unik pelanggan — auto-generate format: PLG-00001
    kode = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Kode Pelanggan"
    )
    # Nama lengkap pelanggan
    nama = models.CharField(max_length=200, verbose_name="Nama Pelanggan")
    # Nomor telepon — penting untuk notifikasi status service
    telepon = models.CharField(max_length=20, verbose_name="No. Telepon")
    # Email opsional
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    # Alamat lengkap pelanggan
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")
    # Status aktif
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    # Timestamps
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pelanggan"
        verbose_name_plural = "Pelanggan"
        ordering = ['nama']

    def __str__(self):
        return f"{self.kode} - {self.nama}"

    def save(self, *args, **kwargs):
        """Auto-generate kode pelanggan jika kosong."""
        if not self.kode:
            self.kode = self.generate_kode()
        super().save(*args, **kwargs)

    def generate_kode(self):
        """Generate kode pelanggan otomatis: PLG-00001, PLG-00002, dst."""
        prefix = "PLG"
        last = Pelanggan.objects.filter(
            kode__startswith=prefix
        ).order_by('-kode').first()

        if last:
            try:
                last_number = int(last.kode.split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{prefix}-{new_number:05d}"


class Perangkat(models.Model):
    """
    Model untuk JENIS PERANGKAT yang bisa di-service.

    Contoh data:
    | nama           | deskripsi                        |
    |----------------|----------------------------------|
    | HP Android     | Smartphone berbasis Android      |
    | iPhone         | Smartphone Apple iOS             |
    | TV LED/LCD     | Televisi LED atau LCD            |
    | Laptop         | Notebook / Laptop                |
    | Tablet         | Tablet Android / iPad            |
    | Mesin Cuci     | Mesin cuci berbagai merek        |
    """
    nama = models.CharField(max_length=100, verbose_name="Nama Jenis Perangkat")
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")
    # Icon untuk tampilan (Remix Icon class)
    icon = models.CharField(
        max_length=50,
        default='ri-smartphone-line',
        verbose_name="Icon",
        help_text="Class icon Remix Icon, contoh: ri-smartphone-line"
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jenis Perangkat"
        verbose_name_plural = "Jenis Perangkat"
        ordering = ['nama']

    def __str__(self):
        return self.nama


class KategoriService(models.Model):
    """
    Model untuk KATEGORI LAYANAN SERVICE.

    Mengelompokkan jenis-jenis layanan service ke dalam kategori besar.

    Contoh data:
    | nama      | deskripsi                          |
    |-----------|------------------------------------|
    | Hardware  | Perbaikan komponen fisik perangkat |
    | Software  | Perbaikan software / firmware      |
    | Cleaning  | Pembersihan dan perawatan          |
    | Aksesoris | Penggantian dan pemasangan part    |
    """
    nama = models.CharField(max_length=100, unique=True, verbose_name="Nama Kategori")
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")
    icon = models.CharField(
        max_length=50,
        default='ri-tools-line',
        verbose_name="Icon",
        help_text="Class icon Remix Icon"
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kategori Service"
        verbose_name_plural = "Kategori Service"
        ordering = ['nama']

    def __str__(self):
        return self.nama


class JenisService(models.Model):
    """
    Model untuk JENIS LAYANAN SERVICE spesifik.

    Menyimpan daftar layanan standar yang tersedia beserta harga standar.
    Terhubung ke KategoriService.

    Contoh data:
    | kategori  | nama           | harga_standar |
    |-----------|----------------|---------------|
    | Hardware  | Ganti LCD      | 250000        |
    | Hardware  | Ganti Baterai  | 100000        |
    | Software  | Flash ROM      | 75000         |
    | Software  | Install Ulang  | 50000         |
    | Cleaning  | Cleaning Full  | 50000         |
    """
    kategori = models.ForeignKey(
        KategoriService,
        on_delete=models.PROTECT,
        related_name='jenis_services',
        verbose_name="Kategori"
    )
    nama = models.CharField(max_length=200, verbose_name="Nama Layanan")
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")
    foto = models.ImageField(
        upload_to='service_center/jenis/',
        blank=True, null=True,
        verbose_name="Foto Layanan",
        help_text="Foto/gambar untuk jenis layanan ini"
    )
    harga_standar = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Harga Standar (Rp)"
    )
    estimasi_waktu = models.CharField(
        max_length=50,
        blank=True, null=True,
        verbose_name="Estimasi Waktu",
        help_text="Contoh: 1-2 jam, 1 hari"
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Jenis Service"
        verbose_name_plural = "Jenis Service"
        ordering = ['kategori', 'nama']

    def __str__(self):
        return f"{self.kategori.nama} — {self.nama} (Rp {self.harga_standar:,.0f})"


class OrderService(models.Model):
    """
    Model UTAMA — Dokumen penerimaan & pelacakan service.

    Setiap order service mencatat:
    - Siapa pelanggannya
    - Perangkat apa yang di-service
    - Keluhan dan kondisi fisik saat diterima
    - Status pengerjaan (workflow)
    - Biaya dan pembayaran

    Alur status:
    diterima → diagnosa → menunggu_konfirmasi → dikerjakan → selesai → diambil
                                 ↓
                            dibatalkan
    """

    # ===== STATUS WORKFLOW =====
    STATUS_CHOICES = [
        ('diterima', 'Diterima'),                    # Unit baru masuk / diterima
        ('diagnosa', 'Diagnosa'),                    # Sedang di-diagnosa oleh teknisi
        ('menunggu_konfirmasi', 'Menunggu Konfirmasi'),  # Menunggu persetujuan biaya dari pelanggan
        ('dikerjakan', 'Sedang Dikerjakan'),          # Sedang dalam proses perbaikan
        ('selesai', 'Selesai'),                      # Perbaikan selesai, siap diambil
        ('diambil', 'Sudah Diambil'),                # Pelanggan sudah mengambil unit
        ('dibatalkan', 'Dibatalkan'),                 # Service dibatalkan
    ]

    # ===== PRIORITAS =====
    PRIORITAS_CHOICES = [
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('express', 'Express'),
    ]

    # ===== STATUS PEMBAYARAN =====
    STATUS_BAYAR_CHOICES = [
        ('belum_bayar', 'Belum Bayar'),
        ('dp', 'DP (Uang Muka)'),
        ('lunas', 'Lunas'),
    ]

    # ===== IDENTITAS ORDER =====
    nomor_service = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nomor Service"
    )
    # Kode unik untuk tracking publik oleh pelanggan (UUID pendek)
    kode_unik = models.CharField(
        max_length=8,
        unique=True,
        blank=True,
        verbose_name="Kode Tracking",
        help_text="Kode unik untuk cek status oleh pelanggan"
    )
    tanggal_masuk = models.DateTimeField(verbose_name="Tanggal Masuk")

    # ===== RELASI KE PELANGGAN =====
    pelanggan = models.ForeignKey(
        Pelanggan,
        on_delete=models.PROTECT,
        related_name='order_services',
        verbose_name="Pelanggan"
    )

    # ===== DATA PERANGKAT =====
    jenis_perangkat = models.ForeignKey(
        Perangkat,
        on_delete=models.PROTECT,
        related_name='order_services',
        verbose_name="Jenis Perangkat"
    )
    merek = models.CharField(max_length=100, verbose_name="Merek")
    model_tipe = models.CharField(
        max_length=100,
        blank=True, null=True,
        verbose_name="Model / Tipe"
    )
    nomor_seri = models.CharField(
        max_length=100,
        blank=True, null=True,
        verbose_name="Nomor Seri / IMEI"
    )
    warna = models.CharField(
        max_length=50,
        blank=True, null=True,
        verbose_name="Warna"
    )

    # ===== KONDISI & KELUHAN =====
    keluhan = models.TextField(verbose_name="Keluhan Pelanggan")
    kondisi_fisik = models.TextField(
        blank=True, null=True,
        verbose_name="Kondisi Fisik",
        help_text="Deskripsi kondisi fisik perangkat saat diterima (lecet, retak, dll)"
    )
    kelengkapan = models.TextField(
        blank=True, null=True,
        verbose_name="Kelengkapan",
        help_text="Barang yang disertakan (charger, dus, SIM card, dll)"
    )
    password_perangkat = models.CharField(
        max_length=100,
        blank=True, null=True,
        verbose_name="Password / PIN Perangkat",
        help_text="Password lock screen jika diperlukan untuk diagnosa"
    )

    # ===== FOTO PERANGKAT =====
    gambar_perangkat = models.ImageField(
        upload_to='service_center/perangkat/',
        blank=True, null=True,
        verbose_name="Foto Perangkat"
    )

    # ===== STATUS & PRIORITAS =====
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default='diterima',
        verbose_name="Status"
    )
    prioritas = models.CharField(
        max_length=10,
        choices=PRIORITAS_CHOICES,
        default='normal',
        verbose_name="Prioritas"
    )

    # ===== BIAYA =====
    estimasi_biaya = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Estimasi Biaya"
    )
    biaya_akhir = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Biaya Akhir"
    )
    dp_bayar = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="DP / Uang Muka"
    )
    # PPN yang dikenakan — dihitung otomatis dari cabang/gudang
    pajak = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="PPN / Pajak (Rp)"
    )
    status_bayar = models.CharField(
        max_length=15,
        choices=STATUS_BAYAR_CHOICES,
        default='belum_bayar',
        verbose_name="Status Pembayaran"
    )
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Metode Pembayaran",
        related_name='order_services'
    )

    # ===== ESTIMASI & CATATAN =====
    estimasi_selesai = models.DateField(
        blank=True, null=True,
        verbose_name="Estimasi Selesai"
    )
    catatan_teknisi = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan Teknisi"
    )
    catatan_internal = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan Internal",
        help_text="Catatan internal yang tidak ditampilkan ke pelanggan"
    )

    # ===== CABANG / GUDANG =====
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='order_services',
        verbose_name="Cabang / Gudang",
        help_text="Cabang/gudang tempat order service ini ditangani"
    )

    # ===== PETUGAS =====
    teknisi = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='order_service_teknisi',
        verbose_name="Teknisi"
    )
    diterima_oleh = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='order_service_diterima',
        verbose_name="Diterima Oleh"
    )

    # ===== TANGGAL PENTING =====
    tanggal_selesai = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Tanggal Selesai"
    )
    tanggal_diambil = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Tanggal Diambil"
    )

    # ===== TIMESTAMPS =====
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Service"
        verbose_name_plural = "Order Service"
        ordering = ['-dibuat_pada']
        indexes = [
            models.Index(fields=['status', 'tanggal_masuk'], name='svc_order_status_tgl_idx'),
            models.Index(fields=['status_bayar', 'tanggal_masuk'], name='svc_order_bayar_tgl_idx'),
            models.Index(fields=['cabang', 'tanggal_masuk'], name='svc_order_cabang_tgl_idx'),
            models.Index(fields=['teknisi', 'status'], name='svc_order_teknisi_st_idx'),
            models.Index(fields=['pelanggan', 'tanggal_masuk'], name='svc_order_plg_tgl_idx'),
        ]

    def __str__(self):
        return f"{self.nomor_service} - {self.pelanggan.nama} ({self.merek})"

    def save(self, *args, **kwargs):
        """Auto-generate nomor service, kode unik, dan set tanggal masuk."""
        from django.utils import timezone

        is_new = self.pk is None

        if not self.nomor_service:
            self.nomor_service = self.generate_nomor()

        # Auto-generate kode unik untuk tracking publik
        if not self.kode_unik:
            self.kode_unik = self.generate_kode_unik()

        if is_new and not self.tanggal_masuk:
            self.tanggal_masuk = timezone.now()

        # Auto-update tanggal selesai saat status berubah ke 'selesai'
        if self.status == 'selesai' and not self.tanggal_selesai:
            self.tanggal_selesai = timezone.now()

        # Auto-update tanggal diambil saat status berubah ke 'diambil'
        if self.status == 'diambil' and not self.tanggal_diambil:
            self.tanggal_diambil = timezone.now()

        # Hitung biaya_akhir dari items layanan + sparepart
        # DIPERBAIKI: Skip recalculate jika hanya update status/status_bayar
        # agar tidak override biaya manual yang sudah diset via update_status form
        update_fields = kwargs.get('update_fields')
        status_only_update = update_fields and all(
            f in ['status', 'status_bayar', 'tanggal_selesai', 'tanggal_diambil', 'biaya_akhir']
            for f in update_fields
        )
        if not is_new and not status_only_update:
            total_layanan = sum(
                item.biaya for item in self.items.all()
            )
            total_sparepart = sum(
                sp.jumlah * sp.harga_satuan for sp in self.penggunaan_sparepart.all()
            )
            total = total_layanan + total_sparepart + self.pajak
            if total > 0:
                self.biaya_akhir = total

        super().save(*args, **kwargs)

    def generate_kode_unik(self):
        """Generate kode unik 8 karakter (huruf+angka) untuk tracking."""
        while True:
            kode = uuid.uuid4().hex[:8].upper()
            if not OrderService.objects.filter(kode_unik=kode).exists():
                return kode

    def generate_nomor(self):
        """Generate nomor service: SVC/2026/03/0001"""
        from datetime import datetime
        today = datetime.now()
        prefix = f"SVC/{today.year}/{today.month:02d}"

        last = OrderService.objects.filter(
            nomor_service__startswith=prefix
        ).order_by('-nomor_service').first()

        if last:
            try:
                last_number = int(last.nomor_service.split('/')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah order + 1
                new_number = OrderService.objects.filter(
                    nomor_service__startswith=prefix
                ).count() + 1
        else:
            new_number = 1

        # Tambahan: loop untuk memastikan nomor unik
        nomor = f"{prefix}/{new_number:04d}"
        while OrderService.objects.filter(nomor_service=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor

    @property
    def total_biaya(self):
        """Hitung total biaya DINAMIS dari layanan + sparepart + pajak."""
        total_layanan = sum(item.biaya for item in self.items.all())
        total_sparepart = sum(
            sp.jumlah * sp.harga_satuan for sp in self.penggunaan_sparepart.all()
        )
        return total_layanan + total_sparepart + self.pajak

    @property
    def sisa_bayar(self):
        """Hitung sisa pembayaran dari total_biaya (computed) - dp_bayar."""
        return max(self.total_biaya - self.dp_bayar, 0)

    @property
    def status_badge_class(self):
        """Return CSS class untuk badge status."""
        mapping = {
            'diterima': 'info',
            'diagnosa': 'warning',
            'menunggu_konfirmasi': 'primary',
            'dikerjakan': 'warning',
            'selesai': 'success',
            'diambil': 'secondary',
            'dibatalkan': 'danger',
        }
        return mapping.get(self.status, 'secondary')

    @property
    def prioritas_badge_class(self):
        """Return CSS class untuk badge prioritas."""
        mapping = {
            'normal': 'secondary',
            'urgent': 'warning',
            'express': 'danger',
        }
        return mapping.get(self.prioritas, 'secondary')


class ItemService(models.Model):
    """
    Model untuk DETAIL LAYANAN per order service.

    Setiap order bisa memiliki beberapa item perbaikan/layanan.

    Contoh:
    | order_service | nama_layanan     | biaya     |
    |---------------|------------------|-----------|
    | SVC/2026/03/1 | Ganti LCD        | 500,000   |
    | SVC/2026/03/1 | Ganti Baterai    | 150,000   |
    | SVC/2026/03/1 | Service Ringan   | 50,000    |
    """
    # Relasi ke order service induk
    order_service = models.ForeignKey(
        OrderService,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Order Service"
    )
    # Relasi opsional ke jenis service standar
    jenis_service = models.ForeignKey(
        JenisService,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='item_services',
        verbose_name="Jenis Service",
        help_text="Pilih dari daftar layanan standar, atau isi manual"
    )
    # Nama layanan/perbaikan
    nama_layanan = models.CharField(
        max_length=200,
        verbose_name="Nama Layanan / Perbaikan"
    )
    # Biaya untuk layanan ini
    biaya = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Biaya"
    )
    # Catatan opsional per item
    catatan = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan"
    )

    class Meta:
        verbose_name = "Item Service"
        verbose_name_plural = "Item Service"

    def __str__(self):
        return f"{self.nama_layanan} - Rp {self.biaya:,.0f}"


class RiwayatStatus(models.Model):
    """
    Model untuk LOG PERUBAHAN STATUS order service.

    Mencatat setiap perubahan status beserta catatan dan siapa
    yang melakukan perubahan — untuk audit trail.

    Contoh:
    | order   | dari      | ke         | diubah_oleh |
    |---------|-----------|------------|-------------|
    | SVC/001 | diterima  | diagnosa   | admin       |
    | SVC/001 | diagnosa  | dikerjakan | teknisi1    |
    """
    order_service = models.ForeignKey(
        OrderService,
        on_delete=models.CASCADE,
        related_name='riwayat_status',
        verbose_name="Order Service"
    )
    status_sebelum = models.CharField(
        max_length=25,
        verbose_name="Status Sebelum"
    )
    status_sesudah = models.CharField(
        max_length=25,
        verbose_name="Status Sesudah"
    )
    catatan = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan"
    )
    diubah_oleh = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Diubah Oleh"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Riwayat Status"
        verbose_name_plural = "Riwayat Status"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.order_service.nomor_service}: {self.status_sebelum} → {self.status_sesudah}"

    def get_status_display_sesudah(self):
        """Mendapatkan label status yang readable."""
        status_dict = dict(OrderService.STATUS_CHOICES)
        return status_dict.get(self.status_sesudah, self.status_sesudah)

    def get_status_display_sebelum(self):
        """Mendapatkan label status sebelum yang readable."""
        status_dict = dict(OrderService.STATUS_CHOICES)
        return status_dict.get(self.status_sebelum, self.status_sebelum)


class PenggunaanSparepart(models.Model):
    """
    Model untuk PENGGUNAAN SPAREPART pada order service.

    Mencatat sparepart apa saja yang digunakan dalam perbaikan,
    jumlah, harga, dan dari gudang mana diambil.
    Otomatis mengurangi stok saat disimpan.

    Alur:
    1. Teknisi pilih sparepart dari dropdown (data dari model Produk)
    2. Tentukan jumlah dan gudang sumber
    3. Saat save → stok di gudang otomatis berkurang
    4. Harga sparepart masuk ke total biaya order service

    Relasi:
    - OrderService → Order service yang menggunakan sparepart
    - Produk → Sparepart yang digunakan (dari apps.produk)
    - Gudang → Gudang sumber stok (dari apps.produk)
    """
    order_service = models.ForeignKey(
        OrderService,
        on_delete=models.CASCADE,
        related_name='penggunaan_sparepart',
        verbose_name="Order Service"
    )
    produk = models.ForeignKey(
        'produk.Produk',
        on_delete=models.PROTECT,
        related_name='penggunaan_service',
        verbose_name="Sparepart"
    )
    gudang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.PROTECT,
        related_name='penggunaan_service',
        verbose_name="Gudang Sumber"
    )
    jumlah = models.DecimalField(
        max_digits=15, decimal_places=2, default=1,
        verbose_name="Jumlah"
    )
    harga_satuan = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Harga Satuan"
    )
    catatan = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Catatan"
    )
    stok_dikurangi = models.BooleanField(
        default=False,
        verbose_name="Stok Sudah Dikurangi",
        help_text="Flag apakah stok sudah dikurangi saat save"
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Penggunaan Sparepart"
        verbose_name_plural = "Penggunaan Sparepart"
        ordering = ['-dibuat_pada']
        indexes = [
            models.Index(fields=['produk', 'gudang'], name='svc_sp_prod_gdg_idx'),
            models.Index(fields=['order_service', 'produk'], name='svc_sp_order_prod_idx'),
        ]

    def __str__(self):
        return f"{self.produk.nama} x{self.jumlah} - {self.order_service.nomor_service}"

    @property
    def subtotal(self):
        """Hitung subtotal = jumlah × harga_satuan."""
        return self.jumlah * self.harga_satuan

    def kurangi_stok(self):
        """Kurangi stok sparepart dari gudang yang dipilih (thread-safe)."""
        if self.stok_dikurangi:
            return
        from apps.produk.models import Stok
        from django.db import transaction
        with transaction.atomic():
            stok, _ = Stok.objects.get_or_create(
                produk=self.produk,
                gudang=self.gudang,
                defaults={'jumlah': 0}
            )
            # Re-fetch dengan row lock untuk mencegah race condition
            stok = Stok.objects.select_for_update().get(pk=stok.pk)
            if stok.jumlah < self.jumlah:
                raise ValueError(
                    f"Stok {self.produk.nama} tidak mencukupi! "
                    f"Tersedia: {stok.jumlah}, dibutuhkan: {self.jumlah}"
                )
            stok.jumlah -= self.jumlah
            stok.save()
            self.stok_dikurangi = True
            self.save(update_fields=['stok_dikurangi'])

    def kembalikan_stok(self):
        """Kembalikan stok jika penggunaan dibatalkan/dihapus (thread-safe)."""
        if not self.stok_dikurangi:
            return
        from apps.produk.models import Stok
        from django.db import transaction
        with transaction.atomic():
            stok, _ = Stok.objects.get_or_create(
                produk=self.produk,
                gudang=self.gudang,
                defaults={'jumlah': 0}
            )
            # Re-fetch dengan row lock untuk mencegah race condition
            stok = Stok.objects.select_for_update().get(pk=stok.pk)
            stok.jumlah += self.jumlah
            stok.save()
            self.stok_dikurangi = False
            self.save(update_fields=['stok_dikurangi'])
