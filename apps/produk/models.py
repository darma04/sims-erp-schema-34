"""
==========================================================================
 PRODUK MODELS - Model Data Produk, Kategori, Satuan, Gudang, Stok
==========================================================================
 File ini berisi 5 model database untuk manajemen produk:

 1. Kategori → Pengelompokan produk (contoh: Makanan, Minuman, Elektronik)
 2. Satuan → Unit pengukuran (contoh: pcs, kg, liter, box)
 3. Produk → Data master produk (nama, SKU, harga, gambar)
 4. Gudang → Lokasi penyimpanan barang
 5. Stok → Jumlah produk per gudang (relasi many-to-many)

 Hubungan antar model:
   Kategori ←(FK)── Produk ──(FK)→ Satuan
                       │
                       ├──(FK)→ Gudang (cabang)
                       │
                       └──(via Stok)→ Gudang (stok per gudang)

   Stok = Produk + Gudang + Jumlah (unique_together)

 Koneksi ke modul lain:
 - apps/inventory/models.py → TransferStok, AdjustmentStok mengubah Stok
 - apps/pembelian/models.py → PurchaseOrder menambah Stok
 - apps/penjualan/models.py → SalesOrder mengurangi Stok
 - apps/pos/models.py → Transaksi POS mengurangi Stok
 - apps/laporan/ → Laporan Produk dan Laporan Stok membaca data ini

 ⚠ PENTING: Stok diupdate dari 5 sumber berbeda!
 Update stok = TransferStok + AdjustmentStok + PO + SO + POS
==========================================================================
"""

# Import dari framework Django
from django.db import models               # Django ORM untuk definisi model
# Import dari framework Django
from django.contrib.auth.models import User  # Model User bawaan Django
from apps.core.validators import validate_image_file
import uuid                                 # Modul untuk generate ID unik


class Kategori(models.Model):
    """
    Model untuk KATEGORI produk.

    Contoh data: Makanan, Minuman, Elektronik, Bahan Bangunan
    Digunakan untuk mengelompokkan produk di halaman Daftar Produk.

    Relasi:
    - ForeignKey ke User (dibuat_oleh) → siapa yang membuat kategori ini
    - Reverse relation: kategori.produk.all() → semua produk di kategori ini
    """
    nama = models.CharField(max_length=100, verbose_name="Nama Kategori")
    # deskripsi — Teks panjang
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # Tracking: siapa dan kapan membuat
    dibuat_oleh = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,   # Jika user dihapus → set null (jangan hapus kategori)
        null=True,
        related_name='kategori_dibuat'  # user.kategori_dibuat.all() → semua kategori yang dibuat user
    )
    # dibuat_pada — Tanggal & waktu
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    # diupdate_pada — Tanggal & waktu
    diupdate_pada = models.DateTimeField(auto_now=True)      # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Kategori"
        verbose_name_plural = "Kategori"
        ordering = ['nama']  # Urutan default: A-Z berdasarkan nama

    def __str__(self):
        """Representasi string: nama kategori (untuk dropdown, admin, dll)"""
        return self.nama


class Satuan(models.Model):
    """
    Model untuk SATUAN / unit pengukuran produk.

    Contoh data:
    | nama    | singkatan |
    |---------|-----------|
    | Pieces  | pcs       |
    | Kilogram| kg        |
    | Liter   | ltr       |
    | Box     | box       |

    Satuan digunakan di halaman Daftar Produk dan laporan stok.
    """
    # Nama satuan lengkap — contoh: 'Kilogram', 'Pieces', 'Liter'
    nama = models.CharField(max_length=50, verbose_name="Nama Satuan")

    # Singkatan untuk ditampilkan di label stok — contoh: 'kg', 'pcs', 'ltr'
    singkatan = models.CharField(max_length=10, verbose_name="Singkatan")

    # Kapan satuan ini dibuat — hanya auto_now_add (tidak perlu tracking update)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model Satuan."""
        verbose_name = "Satuan"            # Nama tampilan singular di Django Admin
        verbose_name_plural = "Satuan"     # Nama tampilan plural
        ordering = ['nama']                # Urutan default A-Z

    def __str__(self):
        """
        Representasi string satuan untuk dropdown dan tampilan admin.
        Format: 'Kilogram (kg)'
        """
        return f"{self.nama} ({self.singkatan})"


class KonversiSatuan(models.Model):
    """
    Model untuk KONVERSI antar satuan.

    Mendukung 2 jenis konversi:
    1. Global (produk=None) — berlaku untuk semua produk
       Contoh: 1 Kilogram = 1000 Gram (berlaku universal)
    2. Per-Produk (produk=set) — override khusus per produk
       Contoh: 1 Karton Indomie = 40 pcs, tapi 1 Karton Aqua = 24 pcs

    Contoh data global:
    | dari_satuan | ke_satuan | faktor | produk |
    |-------------|-----------|--------|--------|
    | Kilogram    | Gram      | 1000   | None   |
    | Karton      | PCS       | 24     | None   |

    Contoh data per-produk:
    | dari_satuan | ke_satuan | faktor | produk        |
    |-------------|-----------|--------|---------------|
    | Karton      | PCS       | 40     | Indomie       |
    | Karton      | PCS       | 48     | Aqua 600ml    |
    """

    # Satuan asal — satuan "besar" (contoh: Kilogram, Karton, Liter)
    dari_satuan = models.ForeignKey(
        Satuan,
        on_delete=models.CASCADE,
        related_name='konversi_dari',
        verbose_name="Dari Satuan"
    )

    # Satuan tujuan — satuan "kecil" (contoh: Gram, PCS, ML)
    ke_satuan = models.ForeignKey(
        Satuan,
        on_delete=models.CASCADE,
        related_name='konversi_ke',
        verbose_name="Ke Satuan"
    )

    # Faktor konversi: 1 dari_satuan = faktor × ke_satuan
    # Contoh: 1 kg = 1000 gram → faktor = 1000
    faktor_konversi = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name="Faktor Konversi",
        help_text="1 [dari_satuan] = ? [ke_satuan]"
    )

    # Opsional: override per produk — jika null, berlaku global
    produk = models.ForeignKey(
        'Produk',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='konversi_satuan',
        verbose_name="Produk (Opsional)",
        help_text="Kosongkan untuk konversi global, isi untuk override per produk"
    )

    # dibuat_pada — Tanggal & waktu
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konversi Satuan"
        verbose_name_plural = "Konversi Satuan"
        ordering = ['dari_satuan', 'ke_satuan']
        # Unik per kombinasi: dari + ke + produk
        unique_together = ['dari_satuan', 'ke_satuan', 'produk']

    # Representasi string objek (untuk admin/debugging)
    def __str__(self):
        produk_label = f" [{self.produk.nama}]" if self.produk else ""
        return f"1 {self.dari_satuan.singkatan} = {self.faktor_konversi} {self.ke_satuan.singkatan}{produk_label}"

    @classmethod
    def get_konversi_untuk_produk(cls, produk):
        """
        Ambil semua konversi yang tersedia untuk produk tertentu.

        Prioritas:
        1. Konversi per-produk (override) — cek dulu
        2. Konversi global (produk=None) — fallback

        Return: list of dict [{satuan_id, satuan_nama, singkatan, faktor, arah}]
        arah: 'turun' (kg→gram) atau 'naik' (gram→kg)
        """
        satuan_produk = produk.satuan
        hasil = []

        # Cari konversi dimana satuan produk = dari_satuan (turun: kg→gram)
        konversi_turun = cls.objects.filter(dari_satuan=satuan_produk)
        # Cari konversi dimana satuan produk = ke_satuan (naik: gram→kg)
        konversi_naik = cls.objects.filter(ke_satuan=satuan_produk)

        # Proses konversi "turun" (dari satuan produk ke satuan lebih kecil)
        processed = set()
        for k in konversi_turun.filter(produk=produk):
            # Override per produk
            hasil.append({
                'satuan_id': k.ke_satuan.id,
                'satuan_nama': k.ke_satuan.nama,
                'singkatan': k.ke_satuan.singkatan,
                'faktor': float(k.faktor_konversi),
                'arah': 'turun',
            })
            processed.add(k.ke_satuan.id)

        for k in konversi_turun.filter(produk__isnull=True):
            if k.ke_satuan.id not in processed:
                hasil.append({
                    'satuan_id': k.ke_satuan.id,
                    'satuan_nama': k.ke_satuan.nama,
                    'singkatan': k.ke_satuan.singkatan,
                    'faktor': float(k.faktor_konversi),
                    'arah': 'turun',
                })

        # Proses konversi "naik" (dari satuan lebih besar ke satuan produk)
        processed_naik = set()
        for k in konversi_naik.filter(produk=produk):
            hasil.append({
                'satuan_id': k.dari_satuan.id,
                'satuan_nama': k.dari_satuan.nama,
                'singkatan': k.dari_satuan.singkatan,
                'faktor': float(k.faktor_konversi),
                'arah': 'naik',
            })
            processed_naik.add(k.dari_satuan.id)

        for k in konversi_naik.filter(produk__isnull=True):
            if k.dari_satuan.id not in processed_naik:
                hasil.append({
                    'satuan_id': k.dari_satuan.id,
                    'satuan_nama': k.dari_satuan.nama,
                    'singkatan': k.dari_satuan.singkatan,
                    'faktor': float(k.faktor_konversi),
                    'arah': 'naik',
                })

        return hasil


class Produk(models.Model):
    """
    Model UTAMA — Data master produk.

    Setiap produk memiliki:
    - SKU unik (auto-generate jika kosong)
    - Barcode opsional
    - Harga beli dan harga jual
    - Gambar opsional
    - Terkait ke Kategori dan Satuan

    Property penting:
    - stok_total → Total stok di SEMUA gudang

    Relasi:
    - FK ke Kategori → kategori produk
    - FK ke Satuan → unit pengukuran
    - FK ke Gudang (cabang) → gudang default / cabang
    - Reverse: produk.stok_set.all() → stok di semua gudang
    """

    # ===== IDENTITAS PRODUK =====
    sku = models.CharField(
        max_length=50,
        unique=True,             # SKU harus unik di seluruh database
        verbose_name="SKU"       # Stock Keeping Unit — kode unik produk
    )
    # barcode — Teks pendek
    barcode = models.CharField(max_length=100, blank=True, null=True, verbose_name="Barcode")
    # nama — Teks pendek
    nama = models.CharField(max_length=200, verbose_name="Nama Produk")
    # deskripsi — Teks panjang
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # ===== RELASI KE MODEL LAIN =====
    kategori = models.ForeignKey(
        Kategori,
        on_delete=models.SET_NULL,   # Kategori dihapus → produk tetap ada (kategori=null)
        null=True,
        related_name='produk',        # kategori.produk.all() → semua produk di kategori
        verbose_name="Kategori"
    )
    # satuan — Relasi FK
    satuan = models.ForeignKey(
        Satuan,
        on_delete=models.PROTECT,    # Satuan TIDAK BISA dihapus jika masih dipakai produk
        related_name='produk',
        verbose_name="Satuan"
    )

    # Cabang / gudang default produk
    cabang = models.ForeignKey(
        'Gudang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produk_cabang',
        verbose_name="Cabang"
    )

    # ===== HARGA =====
    harga_beli = models.DecimalField(
        max_digits=15,           # Max 15 digit total (contoh: 999,999,999,999.99)
        decimal_places=2,        # 2 digit desimal
        default=0,
        verbose_name="Harga Beli"
    )
    # harga_jual — Angka desimal
    harga_jual = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Harga Jual")

    # ===== GAMBAR =====
    gambar = models.ImageField(
        upload_to='produk/',     # Disimpan di MEDIA_ROOT/produk/
        blank=True,
        null=True,
        verbose_name="Gambar Produk",
        validators=[validate_image_file]
    )

    # ===== TIPE PRODUK (SIMS) =====
    TIPE_CHOICES = [
        ('produk', 'Produk'),
        ('sparepart', 'Sparepart'),
    ]
    tipe = models.CharField(
        max_length=15,
        choices=TIPE_CHOICES,
        default='produk',
        verbose_name='Tipe',
        help_text='Produk untuk penjualan umum, Sparepart untuk service center'
    )

    # ===== STATUS =====
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # ===== PPN =====
    # Flag apakah produk ini dikenakan PPN saat transaksi
    # True = kena PPN (default), False = bebas PPN (makanan pokok, dll)
    kena_ppn = models.BooleanField(
        default=True,
        verbose_name="Kena PPN",
        help_text="Jika dicentang, produk ini akan dikenakan PPN saat transaksi"
    )

    # ===== METODE PEMBAYARAN =====
    # FK ke MetodePembayaran — metode pembayaran saat menambahkan produk
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='produk_set',
        verbose_name="Metode Pembayaran"
    )

    # ===== TRACKING =====
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='produk_dibuat')
    # dibuat_pada — Tanggal & waktu
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    # diupdate_pada — Tanggal & waktu
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Produk"
        verbose_name_plural = "Produk"
        ordering = ['-dibuat_pada']  # Terbaru di atas
        indexes = [
            models.Index(fields=['aktif', 'dibuat_pada'], name='prd_aktif_created_idx'),
            models.Index(fields=['kategori', 'aktif'], name='prd_kat_aktif_idx'),
            models.Index(fields=['cabang', 'aktif'], name='prd_cabang_aktif_idx'),
            models.Index(fields=['metode_pembayaran', 'aktif'], name='prd_pay_aktif_idx'),
        ]

    def __str__(self):
        """Representasi: 'PRD-00001 - Produk ABC'"""
        return f"{self.sku} - {self.nama}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate SKU jika kosong.

        Alur:
        1. Cek apakah field SKU masih kosong (belum diisi user)
        2. Jika kosong → generate SKU otomatis berdasarkan kategori (dalam atomic transaction)
        3. Simpan ke database via super().save()

        DIPERBAIKI: Dibungkus transaction.atomic() agar generate_sku() + save()
        berjalan dalam satu transaksi — mencegah race condition SKU duplikat.
        """
        from django.db import transaction
        with transaction.atomic():
            if not self.sku:
                # Auto-generate SKU hanya jika field kosong
                # Jika user sudah mengisi SKU manual, biarkan apa adanya
                self.sku = self.generate_sku()
            super().save(*args, **kwargs)  # Simpan semua field ke database

    def generate_sku(self):
        """
        Generate SKU (Stock Keeping Unit) otomatis berdasarkan kategori produk.

        Format: {PREFIKS}-{NOMOR_URUT_5_DIGIT}
        - Prefiks: 3 huruf pertama dari nama kategori (uppercase)
        - Nomor urut: 5 digit, sequential, dimulai dari 00001

        Contoh:
        - Kategori "Makanan"  → MAK-00001, MAK-00002, MAK-00003
        - Kategori "Minuman"  → MIN-00001, MIN-00002
        - Kategori None (kosong) → PRD-00001, PRD-00002

        Algoritma:
        1. Tentukan prefix dari nama kategori (atau 'PRD' jika tanpa kategori)
        2. Query produk terakhir dengan prefix yang sama
        3. Ambil nomor urut terakhir, increment +1
        4. Return SKU baru dengan zero-padding 5 digit

        Return: String SKU — contoh 'MAK-00001'
        """
        # LANGKAH 1: Tentukan prefix berdasarkan kategori
        prefix = "PRD"  # Default prefix jika produk belum punya kategori
        if self.kategori:
            # Ambil 3 huruf pertama dari nama kategori, ubah ke uppercase
            # Contoh: 'Makanan' → 'Mak' → 'MAK'
            prefix = self.kategori.nama[:3].upper()

        # LANGKAH 2: Cari produk terakhir dengan prefix yang sama
        # DIPERBAIKI: select_for_update() mencegah race condition saat concurrent create
        # sku__startswith=prefix → filter SKU yang dimulai dengan prefix ini
        # order_by('-sku') → urutkan descending agar yang terbesar di atas
        # .first() → ambil 1 record pertama (yang terbesar)
        last_product = Produk.objects.select_for_update().filter(
            sku__startswith=prefix
        ).order_by('-sku').first()

        if last_product:
            try:
                # LANGKAH 3: Parse nomor urut dari SKU terakhir
                # Contoh: 'MAK-00005'.split('-') → ['MAK', '00005'] → [-1] → '00005' → int = 5
                last_number = int(last_product.sku.split('-')[-1])
                new_number = last_number + 1  # Increment: 5 → 6
            except (ValueError, IndexError):
                # DIPERBAIKI: bare except → except spesifik
                # Jika format SKU tidak standar (gagal parse), mulai dari 1
                new_number = 1
        else:
            # Belum ada produk dengan prefix ini → mulai dari 1
            new_number = 1

        # LANGKAH 4: Format SKU dengan zero-padding 5 digit
        # :05d → 1 jadi '00001', 42 jadi '00042', 999 jadi '00999'
        return f"{prefix}-{new_number:05d}"

    @property
    def stok_total(self):
        """
        Property untuk menghitung TOTAL stok produk ini di SEMUA gudang.

        Cara kerja:
        1. self.stok_set → reverse relation ke model Stok (dari FK produk)
        2. .aggregate(Sum('jumlah')) → SQL: SELECT SUM(jumlah) FROM stok WHERE produk_id=self.id
        3. ['jumlah__sum'] → ambil hasil aggregate (bisa None jika tidak ada record)
        4. 'or 0' → jika None, kembalikan 0 (agar tidak error di template)

        Contoh:
        - Gudang A: 100, Gudang B: 50, Gudang C: 30 → stok_total = 180
        - Tidak ada stok → stok_total = 0

        Digunakan di: template daftar produk, dashboard, laporan stok

        Return: Decimal atau Integer — total stok di semua gudang
        """
        return self.stok_set.aggregate(models.Sum('jumlah'))['jumlah__sum'] or 0

    def get_total_stok(self):
        """
        Method backward compatibility — memanggil property stok_total.

        Method ini ada untuk menjaga kompatibilitas dengan kode lama
        yang memanggil produk.get_total_stok() sebelum property stok_total dibuat.
        """
        return self.stok_total


class Gudang(models.Model):
    """
    Model untuk GUDANG / lokasi penyimpanan barang.

    Contoh data:
    | kode      | nama           | pajak_persen |
    |-----------|----------------|--------------|
    | GD-001    | Gudang Utama   | 11.00        |
    | GD-002    | Gudang Cabang  | 0.00         |

    Gudang juga berfungsi sebagai "Cabang" di beberapa konteks.
    """
    # Kode unik gudang — contoh: 'GD-001', 'GD-CABANG-JKT'
    # unique=True memastikan tidak ada duplikat kode gudang
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Gudang")

    # Nama gudang yang ditampilkan di UI — contoh: 'Gudang Utama Jakarta'
    nama = models.CharField(max_length=100, verbose_name="Nama Gudang")

    # Alamat fisik gudang — opsional, untuk referensi pengiriman
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")

    # Persentase pajak yang berlaku di gudang/cabang ini
    # Digunakan untuk menghitung pajak otomatis saat transaksi POS
    # max_digits=5, decimal_places=2 → range 0.00 s/d 999.99
    # Contoh: 11.00 = PPN 11%, 0.00 = tanpa pajak
    pajak_persen = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Pajak (%)"
    )

    # Flag aktif — gudang nonaktif tidak muncul di dropdown transfer/PO/SO
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # ===== METODE PEMBAYARAN DEFAULT =====
    # FK ke MetodePembayaran — metode pembayaran default untuk cabang ini
    # Setiap cabang bisa punya metode pembayaran berbeda (Cash, Transfer, dll)
    metode_pembayaran_default = models.ForeignKey(
        'pos.MetodePembayaran',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='gudang_default',
        verbose_name="Metode Pembayaran Default"
    )

    # Timestamp pembuatan gudang
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model Gudang."""
        verbose_name = "Gudang"            # Nama singular
        verbose_name_plural = "Gudang"     # Nama plural
        ordering = ['nama']                # Urutan default A-Z
        indexes = [
            models.Index(fields=['aktif', 'nama'], name='gudang_aktif_nama_idx'),
        ]

    def __str__(self):
        """
        Representasi string gudang untuk dropdown dan admin.
        Format: 'GD-001 - Gudang Utama'
        """
        return f"{self.kode} - {self.nama}"

    def get_tarif_ppn(self):
        """
        Ambil tarif PPN efektif untuk cabang/gudang ini.

        Hierarki:
        1. Gudang.pajak_persen → jika > 0, gunakan nilai ini
        2. PengaturanPerusahaan.pajak_default → fallback jika gudang belum diset

        Return: Decimal — tarif PPN dalam persen (contoh: 11.00)
        Dipakai oleh: SalesOrderCreate/UpdateView, POSIndexView,
        PurchaseOrder views (untuk auto-hitung pajak di form).
        """
        if self.pajak_persen and self.pajak_persen > 0:
            return self.pajak_persen
        # Fallback ke pengaturan perusahaan
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            setting = PengaturanPerusahaan.load()
            return setting.pajak_default or 0
        except Exception:
            return 0


class Stok(models.Model):
    """
    Model untuk STOK produk per gudang.

    Ini adalah tabel penghubung (junction table) antara Produk dan Gudang.
    Setiap record menunjukkan berapa jumlah produk tertentu di gudang tertentu.

    Contoh data:
    | produk      | gudang       | jumlah |
    |-------------|-------------|--------|
    | PRD-00001   | Gudang Utama | 150.00 |
    | PRD-00001   | Gudang Cabang| 50.00  |
    | PRD-00002   | Gudang Utama | 0.00   |

    ⚠ PENTING: unique_together = ['produk', 'gudang']
    → 1 produk hanya bisa punya 1 record stok per gudang

    Stok diupdate oleh:
    - TransferStok → Memindahkan stok antar gudang
    - AdjustmentStok → Koreksi stok manual
    - PurchaseOrder → Menambah stok saat barang masuk
    - SalesOrder → Mengurangi stok saat barang keluar
    - Transaksi POS → Mengurangi stok saat penjualan kasir
    """
    # Relasi ke Produk — produk mana yang disimpan di gudang ini
    # on_delete=CASCADE → produk dihapus → record stok ikut terhapus
    # Ini logis karena stok tanpa produk tidak ada artinya
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='stok_set',       # produk.stok_set.all() → stok di semua gudang
        verbose_name="Produk"
    )

    # Relasi ke Gudang — di gudang mana produk ini disimpan
    # on_delete=CASCADE → gudang dihapus → record stok ikut terhapus
    gudang = models.ForeignKey(
        Gudang,
        on_delete=models.CASCADE,
        related_name='stok_set',       # gudang.stok_set.all() → semua stok di gudang ini
        verbose_name="Gudang"
    )

    # Jumlah stok — berapa banyak produk di gudang ini
    # Decimal untuk mendukung satuan pecahan (contoh: 2.5 kg)
    # max_digits=15, decimal_places=2 → mendukung hingga 9,999,999,999,999.99
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah")

    # Kapan terakhir stok diupdate — otomatis setiap kali disimpan
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata model Stok."""
        verbose_name = "Stok"              # Nama singular
        verbose_name_plural = "Stok"       # Nama plural
        # unique_together memastikan hanya 1 record per kombinasi produk + gudang
        # Ini mencegah duplikasi: tidak boleh ada 2 record stok untuk
        # produk yang sama di gudang yang sama
        unique_together = ['produk', 'gudang']
        ordering = ['produk', 'gudang']    # Urutan: produk → gudang
        indexes = [
            models.Index(fields=['gudang', 'produk'], name='stok_gudang_produk_idx'),
        ]

    def __str__(self):
        """
        Representasi string stok untuk admin dan debugging.
        Format: 'Produk ABC - Gudang Utama: 150.00 pcs'
        Menyertakan nama produk, nama gudang, jumlah, dan satuan
        """
        return f"{self.produk.nama} - {self.gudang.nama}: {self.jumlah} {self.produk.satuan.singkatan}"
