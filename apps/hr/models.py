"""
==========================================================================
 HR MODELS - Human Resources (SDM / Sumber Daya Manusia)
==========================================================================
 File ini berisi 6 model untuk modul HR:

 1. Departemen → Divisi/bagian perusahaan (IT, Finance, Marketing, dll)
 2. Jabatan → Posisi/role karyawan (Staff, Supervisor, Manager)
 3. Karyawan → Data master karyawan
 4. FotoWajah → Foto untuk absensi face recognition
 5. PengaturanAbsensi → Konfigurasi jam kerja, lokasi, hari kerja
 6. Absensi → Record kehadiran harian karyawan
 7. Penggajian → Slip gaji bulanan (pendapatan - potongan = gaji bersih)

 HIERARKI ORGANISASI:
 ┌────────────┐
 │ Departemen │ (contoh: IT, Finance)
 │  ├── Jabatan 1 (Staff → gaji 5jt)
 │  ├── Jabatan 2 (Supervisor → gaji 8jt)
 │  └── Jabatan 3 (Manager → gaji 12jt)
 └────────────┘
       │
       └──→ Karyawan → Absensi → Penggajian

 Koneksi:
 - django.contrib.auth.models.User → Karyawan bisa terhubung ke akun user
 - apps/hr/views.py → View CRUD untuk semua model HR
 - apps/dashboard/views.py → Statistik karyawan di dashboard
==========================================================================
"""

from django.db import models                # Django ORM — framework untuk mendefinisikan tabel database sebagai class Python
from django.contrib.auth.models import User  # Model User bawaan Django — menyimpan data akun login (username, password, email)
from decimal import Decimal                  # Tipe data Decimal — untuk perhitungan uang yang presisi (tidak ada pembulatan float)


# ╔══════════════════════════════════════════════════════════════╗
# ║                     DEPARTEMEN                                ║
# ╚══════════════════════════════════════════════════════════════╝

class Departemen(models.Model):
    """
    Model untuk DEPARTEMEN / divisi perusahaan.

    Departemen adalah unit organisasi tertinggi dalam hierarki HR.
    Contoh departemen: IT, Finance, Marketing, Warehouse, HR, dll.

    Relasi:
    - Departemen (1) → (N) Jabatan — satu departemen punya banyak jabatan
    - Departemen (1) → (N) Karyawan — satu departemen punya banyak karyawan
    - Departemen → Kepala (FK ke Karyawan) — setiap departemen punya 1 kepala

    Contoh data:
    | kode  | nama      | kepala_departemen |
    |-------|-----------|-------------------|
    | IT    | IT        | Budi Santoso      |
    | FIN   | Finance   | Siti Nurhaliza    |
    | MKT   | Marketing | None (kosong)     |
    """

    # Kode unik departemen — digunakan sebagai identifier pendek
    # unique=True berarti tidak boleh ada 2 departemen dengan kode yang sama
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Departemen")

    # Nama lengkap departemen — ditampilkan di UI dan laporan
    nama = models.CharField(max_length=100, verbose_name="Nama Departemen")

    # Deskripsi tugas/fungsi departemen — opsional (blank=True, null=True)
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # Kepala departemen — relasi ke model Karyawan
    # Menggunakan string 'Karyawan' (bukan class langsung) karena model Karyawan
    # didefinisikan SETELAH Departemen di file ini (forward reference)
    # on_delete=SET_NULL → jika karyawan dihapus, field ini jadi NULL (bukan error)
    # related_name='departemen_dipimpin' → akses balik: karyawan.departemen_dipimpin.all()
    kepala_departemen = models.ForeignKey(
        'Karyawan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departemen_dipimpin',
        verbose_name="Kepala Departemen"
    )

    # Flag aktif/nonaktif — departemen nonaktif tidak muncul di dropdown
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp otomatis — auto_now_add=True: diisi saat pertama kali dibuat
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    # auto_now=True: diupdate otomatis setiap kali record disimpan
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata model Departemen."""
        verbose_name = "Departemen"              # Nama singular di admin
        verbose_name_plural = "Departemen"       # Nama plural di admin
        ordering = ['nama']                      # Default urutan: A-Z berdasarkan nama

    def __str__(self):
        """
        Representasi string — dipanggil saat print() atau ditampilkan di dropdown.
        Format: 'IT - Information Technology'
        """
        return f"{self.kode} - {self.nama}"

    @property
    def jumlah_karyawan(self):
        """
        Property untuk menghitung jumlah karyawan AKTIF di departemen ini.

        Cara kerja:
        - self.karyawan_set → reverse relation dari FK Karyawan.departemen
        - .filter(aktif=True) → hanya karyawan yang masih aktif
        - .count() → hitung jumlahnya (SQL COUNT)

        Digunakan di: template list departemen untuk menampilkan badge jumlah karyawan

        Return: Integer — jumlah karyawan aktif (contoh: 15)
        """
        return self.karyawan_set.filter(aktif=True).count()


# ╔══════════════════════════════════════════════════════════════╗
# ║                      JABATAN                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class Jabatan(models.Model):
    """
    Model untuk JABATAN / posisi karyawan dalam organisasi.

    Jabatan menentukan:
    - Posisi karyawan dalam hierarki (Staff → Supervisor → Manager → Director → Executive)
    - Gaji pokok default yang diberikan saat karyawan baru ditambahkan
    - Tunjangan jabatan yang melekat pada posisi tersebut

    Relasi:
    - Jabatan (N) → (1) Departemen — setiap jabatan milik 1 departemen
    - Jabatan (1) → (N) Karyawan — 1 jabatan bisa dipegang banyak karyawan

    Contoh data:
    | kode     | nama              | departemen | level      | gaji_pokok |
    |----------|-------------------|------------|------------|------------|
    | IT-STF   | Staff IT          | IT         | staff      | 5,000,000  |
    | IT-SPV   | Supervisor IT     | IT         | supervisor | 8,000,000  |
    | FIN-MGR  | Manager Finance   | Finance    | manager    | 12,000,000 |
    """

    # Level jabatan — menentukan hierarki posisi dalam organisasi
    # Digunakan untuk urutan tampilan dan laporan organisasi
    LEVEL_CHOICES = [
        ('staff', 'Staff'),              # Level terendah — pelaksana tugas harian
        ('supervisor', 'Supervisor'),    # Mengawasi staff di bawahnya
        ('manager', 'Manager'),          # Mengelola tim dan departemen
        ('director', 'Director'),        # Pengambil keputusan strategis divisi
        ('executive', 'Executive'),      # Level tertinggi — C-level (CEO, CFO, dll)
    ]

    # Kode unik jabatan — contoh: 'IT-STF', 'FIN-MGR'
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Jabatan")

    # Nama lengkap jabatan — contoh: 'Staff IT', 'Manager Finance'
    nama = models.CharField(max_length=100, verbose_name="Nama Jabatan")

    # Relasi ke Departemen — setiap jabatan harus terikat ke 1 departemen
    # on_delete=PROTECT → departemen TIDAK BISA dihapus selama masih punya jabatan
    # Ini mencegah kehilangan data jabatan secara tidak sengaja
    departemen = models.ForeignKey(
        Departemen,
        on_delete=models.PROTECT,
        related_name='jabatan_set',       # departemen.jabatan_set.all() → semua jabatan di departemen
        verbose_name="Departemen"
    )

    # Level hierarki — menggunakan choices agar hanya bisa pilih dari daftar valid
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='staff', verbose_name="Level")

    # Gaji pokok default — otomatis dipakai saat karyawan baru ditambahkan ke jabatan ini
    # max_digits=15, decimal_places=2 → mendukung hingga 9,999,999,999,999.99
    gaji_pokok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Gaji Pokok")

    # Tunjangan jabatan — kompensasi tambahan berdasarkan posisi
    tunjangan_jabatan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Jabatan")

    # Deskripsi tugas dan tanggung jawab jabatan — opsional
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi Tugas")

    # Flag aktif — jabatan nonaktif tidak muncul di dropdown saat tambah karyawan
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp tracking — kapan record dibuat dan terakhir diubah
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat pertama kali dibuat
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis setiap kali disimpan

    class Meta:
        """Konfigurasi metadata model Jabatan."""
        verbose_name = "Jabatan"                              # Nama singular
        verbose_name_plural = "Jabatan"                       # Nama plural
        ordering = ['departemen', 'level', 'nama']            # Urutan: departemen → level → nama

    def __str__(self):
        """
        Representasi string jabatan.
        Format: 'IT-STF - Staff IT'
        Digunakan di dropdown, admin, dan log.
        """
        return f"{self.kode} - {self.nama}"

    @property
    def jumlah_karyawan(self):
        """
        Property untuk menghitung jumlah karyawan AKTIF di jabatan ini.

        Cara kerja: Query reverse relation karyawan_set, filter aktif=True, hitung total.
        Digunakan di template list jabatan untuk badge jumlah.

        Return: Integer — jumlah karyawan aktif
        """
        return self.karyawan_set.filter(aktif=True).count()


# ╔══════════════════════════════════════════════════════════════╗
# ║                     KARYAWAN                                   ║
# ╚══════════════════════════════════════════════════════════════╝

class Karyawan(models.Model):
    """
    Model master KARYAWAN — entitas utama modul HR.

    Setiap karyawan memiliki:
    - NIK unik (auto-generate: EMP20240001)
    - Data pribadi (nama, email, telepon, alamat, dll)
    - Data organisasi (jabatan, departemen)
    - Data kepegawaian (tanggal masuk/keluar, status)
    - Gaji pokok (default dari jabatan)
    - Link ke akun User Django (opsional)

    Status karyawan: aktif → cuti → resign/phk
    """

    STATUS_CHOICES = [
        ('aktif', 'Aktif'),
        ('cuti', 'Cuti'),
        ('resign', 'Resign'),
        ('phk', 'PHK'),
    ]

    JENIS_KELAMIN_CHOICES = [
        ('L', 'Laki-laki'),
        ('P', 'Perempuan'),
    ]

    # ===== DATA PRIBADI =====
    nik = models.CharField(max_length=20, unique=True, verbose_name="NIK Karyawan")
    nama = models.CharField(max_length=200, verbose_name="Nama Lengkap")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    telepon = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telepon")
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")
    tempat_lahir = models.CharField(max_length=100, blank=True, null=True, verbose_name="Tempat Lahir")
    tanggal_lahir = models.DateField(blank=True, null=True, verbose_name="Tanggal Lahir")
    jenis_kelamin = models.CharField(max_length=1, choices=JENIS_KELAMIN_CHOICES, default='L', verbose_name="Jenis Kelamin")
    foto = models.ImageField(upload_to='hr/karyawan/', blank=True, null=True, verbose_name="Foto Karyawan")

    # ===== ORGANISASI =====
    jabatan = models.ForeignKey(
        Jabatan,
        on_delete=models.PROTECT,
        related_name='karyawan_set',       # jabatan.karyawan_set.all()
        verbose_name="Jabatan"
    )
    departemen = models.ForeignKey(
        Departemen,
        on_delete=models.PROTECT,
        related_name='karyawan_set',       # departemen.karyawan_set.all()
        verbose_name="Departemen"
    )

    # ===== CABANG =====
    # FK ke Gudang (cabang) — menentukan di cabang mana karyawan bekerja
    # Digunakan untuk menentukan pengaturan absensi yang berlaku (lokasi, jam kerja, radius)
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hr_karyawan_set',
        verbose_name="Cabang"
    )

    # ===== KEPEGAWAIAN =====
    tanggal_masuk = models.DateField(verbose_name="Tanggal Masuk")
    tanggal_keluar = models.DateField(blank=True, null=True, verbose_name="Tanggal Keluar")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aktif', verbose_name="Status")

    # ===== GAJI =====
    gaji_pokok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Gaji Pokok")

    # ===== LINK KE USER ACCOUNT (OPSIONAL) =====
    # OneToOneField berarti 1 karyawan = 1 akun user
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='karyawan',           # user.karyawan → data karyawan user ini
        verbose_name="Akun User"
    )

    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # ===== TRACKING =====
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='karyawan_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata model Karyawan — urutan default A-Z berdasarkan nama."""
        verbose_name = "Karyawan"
        verbose_name_plural = "Karyawan"
        ordering = ['nama']

    def __str__(self):
        """Representasi string karyawan: 'EMP20240001 - Budi Santoso' — untuk admin dan dropdown."""
        return f"{self.nik} - {self.nama}"

    def save(self, *args, **kwargs):
        """
        Override method save() Django — dipanggil setiap kali record karyawan disimpan.

        Langkah-langkah:
        1. Cek apakah NIK sudah diisi → jika belum, generate otomatis
        2. Cek apakah gaji_pokok sudah diisi → jika belum, ambil default dari jabatan
        3. Panggil super().save() → simpan ke database

        DIPERBAIKI: Dibungkus transaction.atomic() agar generate_nik() + save()
        berjalan dalam satu transaksi — mencegah race condition NIK duplikat.
        """
        from django.db import transaction
        with transaction.atomic():
            # LANGKAH 1: Auto-generate NIK jika field masih kosong
            if not self.nik:
                self.nik = self.generate_nik()

            # LANGKAH 2: Default gaji dari jabatan jika belum diisi
            if not self.gaji_pokok and self.jabatan:
                self.gaji_pokok = self.jabatan.gaji_pokok

            # LANGKAH 3: Simpan ke database
            super().save(*args, **kwargs)

    def generate_nik(self):
        """
        Generate NIK (Nomor Induk Karyawan) secara otomatis.

        Format: EMP{TAHUN}{NOMOR_URUT_4_DIGIT}
        Contoh: EMP20240001, EMP20240002, EMP20250001

        Algoritma:
        1. Buat prefix berdasarkan tahun sekarang → 'EMP2024'
        2. Cari karyawan terakhir dengan prefix yang sama
        3. Ambil 4 digit terakhir dari NIK terakhir → increment + 1
        4. Jika belum ada karyawan → mulai dari 0001

        Return: String NIK — contoh 'EMP20240001'
        """
        from datetime import datetime
        today = datetime.now()
        prefix = f"EMP{today.year}"   # Prefix berdasarkan tahun: 'EMP2024'

        # Cari karyawan dengan NIK paling besar yang dimulai dengan prefix ini
        # DIPERBAIKI: select_for_update() mencegah race condition saat concurrent create
        last_karyawan = Karyawan.objects.select_for_update().filter(
            nik__startswith=prefix
        ).order_by('-nik').first()

        if last_karyawan:
            try:
                # Ambil 4 digit terakhir dan konversi ke integer
                last_number = int(last_karyawan.nik[-4:])
                new_number = last_number + 1
            except (ValueError, IndexError):
                # DIPERBAIKI: bare except → except spesifik
                # Jika format NIK tidak standar (gagal parse), mulai dari 1
                new_number = 1
        else:
            # Belum ada karyawan di tahun ini → mulai dari 1
            new_number = 1

        # Format dengan zero-padding 4 digit: 1 → '0001', 42 → '0042'
        return f"{prefix}{new_number:04d}"


# ╔══════════════════════════════════════════════════════════════╗
# ║                   FOTO WAJAH (FACE RECOGNITION)               ║
# ╚══════════════════════════════════════════════════════════════╝

class FotoWajah(models.Model):
    """
    Model untuk FOTO WAJAH karyawan — digunakan untuk absensi face recognition.

    Setiap karyawan bisa punya beberapa foto wajah dari sudut berbeda.
    Field 'encoding' menyimpan vector face encoding untuk perbandingan.
    """
    karyawan = models.ForeignKey(
        Karyawan,
        on_delete=models.CASCADE,          # Karyawan dihapus → foto ikut terhapus
        related_name='foto_wajah_set',
        verbose_name="Karyawan"
    )
    foto = models.ImageField(upload_to='hr/wajah/', verbose_name="Foto Wajah")
    encoding = models.TextField(blank=True, null=True, verbose_name="Face Encoding")  # Vector encoding
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model FotoWajah — terbaru di atas."""
        verbose_name = "Foto Wajah"
        verbose_name_plural = "Foto Wajah"
        ordering = ['-dibuat_pada']

    def __str__(self):
        """Representasi string: 'Foto Budi Santoso - 2024-01-15 08:00:00' — untuk admin."""
        return f"Foto {self.karyawan.nama} - {self.dibuat_pada}"


# ╔══════════════════════════════════════════════════════════════╗
# ║                  PENGATURAN ABSENSI                           ║
# ╚══════════════════════════════════════════════════════════════╝

class PengaturanAbsensi(models.Model):
    """
    Model untuk KONFIGURASI ABSENSI perusahaan.

    Mengatur:
    - Jam masuk/pulang dan toleransi terlambat
    - Hari kerja (Senin-Jumat, atau kustom)
    - Zona waktu (WIB/WITA/WIT)
    - Lokasi kantor (latitude, longitude, radius)
    - Fitur wajib (foto, lokasi, face recognition)
    - Jam lembur

    ⚠ PENTING: Hanya 1 pengaturan yang aktif di satu waktu!
    Saat mengaktifkan satu, yang lain otomatis dinonaktifkan (singleton-like).
    """

    HARI_CHOICES = [
        (0, 'Senin'), (1, 'Selasa'), (2, 'Rabu'), (3, 'Kamis'),
        (4, 'Jumat'), (5, 'Sabtu'), (6, 'Minggu'),
    ]

    ZONA_WAKTU_CHOICES = [
        ('Asia/Jakarta', 'WIB (Jakarta)'),
        ('Asia/Makassar', 'WITA (Makassar)'),
        ('Asia/Jayapura', 'WIT (Jayapura)'),
    ]

    # ===== IDENTITAS =====
    nama = models.CharField(max_length=100, default='Pengaturan Default', verbose_name="Nama Pengaturan")
    aktif = models.BooleanField(default=True, verbose_name="Aktif (Gunakan Pengaturan Ini)")

    # ===== CABANG =====
    # FK ke Gudang (cabang) — pengaturan absensi per cabang
    # Jika null → pengaturan default (berlaku untuk karyawan tanpa cabang)
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pengaturan_absensi_set',
        verbose_name="Cabang",
        help_text="Kosongkan untuk pengaturan default (berlaku untuk karyawan tanpa cabang)"
    )

    # ===== JAM KERJA =====
    jam_masuk = models.TimeField(default='08:00:00', verbose_name="Jam Masuk")
    jam_pulang = models.TimeField(default='17:00:00', verbose_name="Jam Pulang")
    toleransi_terlambat = models.PositiveIntegerField(default=15, verbose_name="Toleransi Terlambat (menit)")

    # ===== HARI KERJA =====
    # Disimpan sebagai string CSV: "0,1,2,3,4" = Senin s/d Jumat
    hari_kerja = models.CharField(
        max_length=50,
        default='0,1,2,3,4',
        verbose_name="Hari Kerja",
        help_text="Format: 0=Senin, 1=Selasa, dst. Contoh: 0,1,2,3,4 untuk Senin-Jumat"
    )

    # ===== LOKASI & ZONA WAKTU =====
    zona_waktu = models.CharField(max_length=50, choices=ZONA_WAKTU_CHOICES, default='Asia/Jakarta', verbose_name="Zona Waktu")
    nama_lokasi = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nama Lokasi Kantor")
    alamat_lokasi = models.TextField(blank=True, null=True, verbose_name="Alamat Kantor")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True, verbose_name="Longitude")
    radius_lokasi = models.PositiveIntegerField(
        default=100,
        verbose_name="Radius Lokasi (meter)",
        help_text="Radius maksimal untuk absensi dari lokasi kantor"
    )

    # ===== FITUR ABSENSI =====
    wajib_foto = models.BooleanField(default=True, verbose_name="Wajib Foto Saat Absen")
    wajib_lokasi = models.BooleanField(default=False, verbose_name="Wajib Dalam Lokasi")
    wajib_face_recognition = models.BooleanField(default=False, verbose_name="Wajib Face Recognition")

    # ===== JAM LEMBUR =====
    mulai_lembur_setelah = models.TimeField(
        default='18:00:00',
        verbose_name="Lembur Dimulai Setelah",
        help_text="Jam mulai dihitung lembur"
    )

    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata — pengaturan aktif ditampilkan paling atas."""
        verbose_name = "Pengaturan Absensi"
        verbose_name_plural = "Pengaturan Absensi"
        ordering = ['-aktif', '-diupdate_pada']

    def __str__(self):
        """Representasi string: 'Pengaturan Default (✓ Aktif)' — menampilkan status aktif/nonaktif."""
        status = "✓ Aktif" if self.aktif else "Nonaktif"
        return f"{self.nama} ({status})"

    def save(self, *args, **kwargs):
        """
        Override save() — implementasi singleton-per-cabang behavior.

        Logika:
        - Jika record ini diaktifkan (self.aktif = True)
        - Maka NONAKTIFKAN pengaturan lain UNTUK CABANG YANG SAMA
        - Ini memastikan hanya 1 pengaturan aktif per cabang

        Multi-cabang:
        - Cabang A bisa punya pengaturan aktif sendiri
        - Cabang B bisa punya pengaturan aktif sendiri
        - Pengaturan default (cabang=None) berlaku untuk karyawan tanpa cabang
        """
        if self.aktif:
            # Nonaktifkan pengaturan lain UNTUK CABANG YANG SAMA saja
            # Jika cabang=None → nonaktifkan yang cabang=None juga
            PengaturanAbsensi.objects.filter(
                cabang=self.cabang
            ).exclude(pk=self.pk).update(aktif=False)
        super().save(*args, **kwargs)  # Simpan record ini ke database

    @property
    def hari_kerja_list(self):
        """
        Konversi string hari kerja dari database ke list integer Python.

        Contoh: '0,1,2,3,4' → [0, 1, 2, 3, 4]
        Mapping: 0=Senin, 1=Selasa, 2=Rabu, 3=Kamis, 4=Jumat, 5=Sabtu, 6=Minggu

        Kenapa disimpan sebagai string?
        - Django tidak punya field array untuk database sederhana (SQLite)
        - String CSV adalah cara paling sederhana menyimpan list angka

        Return: List of integers — contoh [0, 1, 2, 3, 4]
        """
        if self.hari_kerja:
            # split(',') → pecah string menjadi list: ['0','1','2','3','4']
            # isdigit() → filter hanya yang berupa angka (keamanan)
            # int(h) → konversi string ke integer
            return [int(h) for h in self.hari_kerja.split(',') if h.isdigit()]
        return []  # Kembalikan list kosong jika field kosong

    @property
    def hari_kerja_display(self):
        """
        Konversi nomor hari ke nama hari untuk ditampilkan di UI.

        Contoh: [0, 1, 2, 3, 4] → ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']

        Return: List of strings — nama-nama hari kerja
        """
        hari_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
        # List comprehension: untuk setiap nomor hari, ambil nama dari daftar
        # Filter i < 7 untuk keamanan (agar tidak IndexError)
        return [hari_names[i] for i in self.hari_kerja_list if i < 7]

    @classmethod
    def get_active(cls, cabang=None):
        """
        Class method untuk mendapatkan pengaturan absensi yang sedang AKTIF.

        Multi-cabang:
        1. Jika cabang diberikan → cari pengaturan khusus cabang tersebut
        2. Jika tidak ditemukan → fallback ke pengaturan default (cabang=None)
        3. Jika cabang=None → langsung ambil pengaturan default

        Dipanggil dari views saat karyawan melakukan absensi:
            pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)

        Return: Instance PengaturanAbsensi yang aktif, atau None jika tidak ada
        """
        if cabang:
            # Cari pengaturan khusus untuk cabang ini
            pengaturan = cls.objects.filter(aktif=True, cabang=cabang).first()
            if pengaturan:
                return pengaturan
        # Fallback: pengaturan default (tanpa cabang / global)
        return cls.objects.filter(aktif=True, cabang__isnull=True).first()


# ╔══════════════════════════════════════════════════════════════╗
# ║                      ABSENSI                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class Absensi(models.Model):
    """
    Model untuk RECORD ABSENSI / kehadiran karyawan harian.

    Setiap record = 1 karyawan + 1 tanggal (unique_together).
    Menyimpan:
    - Jam masuk dan jam keluar
    - Status kehadiran (hadir/terlambat/izin/sakit/alpha/cuti/libur)
    - Foto absensi (untuk face recognition)
    - Lokasi GPS saat absen
    - Persentase kemiripan wajah
    """

    STATUS_CHOICES = [
        ('hadir', 'Hadir'),
        ('terlambat', 'Terlambat'),
        ('izin', 'Izin'),
        ('sakit', 'Sakit'),
        ('alpha', 'Alpha'),       # Tidak hadir tanpa keterangan
        ('cuti', 'Cuti'),
        ('libur', 'Libur'),
    ]

    karyawan = models.ForeignKey(
        Karyawan,
        on_delete=models.CASCADE,
        related_name='absensi_set',        # karyawan.absensi_set.all()
        verbose_name="Karyawan"
    )
    tanggal = models.DateField(verbose_name="Tanggal")
    jam_masuk = models.TimeField(blank=True, null=True, verbose_name="Jam Masuk")
    jam_keluar = models.TimeField(blank=True, null=True, verbose_name="Jam Keluar")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='hadir', verbose_name="Status")

    # Face recognition — persentase kemiripan wajah
    persentase_kemiripan = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True, verbose_name="Persentase Kemiripan")

    # Foto absensi (bukti kehadiran)
    foto_masuk = models.ImageField(upload_to='hr/absensi/', blank=True, null=True, verbose_name="Foto Masuk")
    foto_keluar = models.ImageField(upload_to='hr/absensi/', blank=True, null=True, verbose_name="Foto Keluar")

    # Lokasi GPS
    lokasi_masuk = models.CharField(max_length=255, blank=True, null=True, verbose_name="Lokasi Masuk")
    lokasi_keluar = models.CharField(max_length=255, blank=True, null=True, verbose_name="Lokasi Keluar")

    # Jarak dari kantor saat absen (dalam meter)
    jarak_masuk = models.DecimalField(max_digits=10, decimal_places=1, blank=True, null=True, verbose_name="Jarak Masuk (m)")
    jarak_keluar = models.DecimalField(max_digits=10, decimal_places=1, blank=True, null=True, verbose_name="Jarak Keluar (m)")

    # ===== CABANG & PENGATURAN =====
    # Mencatat cabang dan pengaturan yang digunakan saat absensi dilakukan
    # Ini penting untuk audit trail dan laporan per cabang
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='absensi_set',
        verbose_name="Cabang"
    )
    pengaturan_snapshot = models.ForeignKey(
        PengaturanAbsensi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='absensi_set',
        verbose_name="Pengaturan yang Digunakan"
    )

    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata — 1 record per karyawan per hari, diurutkan terbaru dulu."""
        verbose_name = "Absensi"
        verbose_name_plural = "Absensi"
        ordering = ['-tanggal', 'karyawan']
        unique_together = ['karyawan', 'tanggal']  # 1 record per karyawan per hari

    def __str__(self):
        """Representasi string: 'Budi Santoso - 2024-01-15 (hadir)' — untuk admin dan log."""
        return f"{self.karyawan.nama} - {self.tanggal} ({self.status})"

    @property
    def durasi_kerja(self):
        """
        Property untuk menghitung durasi kerja karyawan dalam satuan JAM.

        DIPERBAIKI: Menangani shift malam (jam_keluar < jam_masuk)
        dengan menambahkan 1 hari ke jam_keluar.

        Contoh normal: masuk 08:00, keluar 17:00 → durasi = 9.0 jam
        Contoh shift malam: masuk 22:00, keluar 06:00 → durasi = 8.0 jam

        Return: Float — durasi kerja dalam jam, atau 0 jika data tidak lengkap
        """
        if self.jam_masuk and self.jam_keluar:
            from datetime import datetime, timedelta

            masuk = datetime.combine(self.tanggal, self.jam_masuk)
            keluar = datetime.combine(self.tanggal, self.jam_keluar)

            # DIPERBAIKI: Handle shift malam — jika keluar lebih awal dari masuk,
            # artinya karyawan pulang keesokan harinya
            if keluar < masuk:
                keluar += timedelta(days=1)

            durasi = keluar - masuk
            return durasi.total_seconds() / 3600
        return 0  # Kembalikan 0 jika jam masuk/keluar belum diisi


# ╔══════════════════════════════════════════════════════════════╗
# ║                     PENGGAJIAN                                ║
# ╚══════════════════════════════════════════════════════════════╝

class Penggajian(models.Model):
    """
    Model untuk SLIP GAJI karyawan bulanan.

    Rumus:
    Total Pendapatan = Gaji Pokok + Tunjangan(5 jenis) + Lembur + Bonus
    Total Potongan = BPJS Kesehatan + BPJS TK + PPh 21 + Potongan Lainnya
    Gaji Bersih = Total Pendapatan - Total Potongan

    ⚠ PENTING: unique_together = ['karyawan', 'periode_bulan', 'periode_tahun']
    → 1 karyawan hanya bisa punya 1 slip gaji per bulan per tahun
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('diproses', 'Diproses'),
        ('dibayar', 'Dibayar'),
        ('batal', 'Batal'),
    ]

    karyawan = models.ForeignKey(
        Karyawan,
        on_delete=models.PROTECT,          # Karyawan tidak bisa dihapus jika ada slip gaji
        related_name='penggajian_set',
        verbose_name="Karyawan"
    )
    periode_bulan = models.PositiveIntegerField(verbose_name="Bulan")   # 1-12
    periode_tahun = models.PositiveIntegerField(verbose_name="Tahun")   # 2024, 2025, dst

    # ===== KOMPONEN PENDAPATAN =====
    gaji_pokok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Gaji Pokok")
    tunjangan_jabatan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Jabatan")
    tunjangan_makan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Makan")
    tunjangan_transport = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Transport")
    tunjangan_lainnya = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Lainnya")
    lembur = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Lembur")
    bonus = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Bonus")

    # ===== KOMPONEN POTONGAN =====
    potongan_bpjs_kesehatan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="BPJS Kesehatan")
    potongan_bpjs_ketenagakerjaan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="BPJS Ketenagakerjaan")
    potongan_pph21 = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="PPh 21")
    potongan_lainnya = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Potongan Lainnya")

    # ===== TOTAL (dihitung otomatis) =====
    total_pendapatan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total Pendapatan")
    total_potongan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total Potongan")
    gaji_bersih = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Gaji Bersih")

    # ===== STATUS & TRACKING =====
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")
    tanggal_bayar = models.DateField(blank=True, null=True, verbose_name="Tanggal Bayar")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='penggajian_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata — 1 slip gaji per karyawan per bulan, urutan terbaru dulu."""
        verbose_name = "Penggajian"
        verbose_name_plural = "Penggajian"
        ordering = ['-periode_tahun', '-periode_bulan', 'karyawan']
        unique_together = ['karyawan', 'periode_bulan', 'periode_tahun']

    def __str__(self):
        """Representasi string: 'Budi Santoso - 1/2024' — untuk admin dan laporan slip gaji."""
        return f"{self.karyawan.nama} - {self.periode_bulan}/{self.periode_tahun}"

    def save(self, *args, **kwargs):
        """
        Override save() — otomatis hitung total sebelum menyimpan ke database.

        Alur:
        1. Panggil calculate_total() → hitung total_pendapatan, total_potongan, gaji_bersih
        2. Panggil super().save() → simpan semua field ke database

        Kenapa hitung di save() bukan di form?
        - Agar konsisten: total SELALU dihitung ulang setiap kali disimpan
        - Meskipun data diubah langsung via admin/script, total tetap benar
        """
        self.calculate_total()     # Hitung ulang semua total
        super().save(*args, **kwargs)  # Simpan ke database

    def calculate_total(self):
        """
        Menghitung total pendapatan, potongan, dan gaji bersih.

        Formula perhitungan:
        ┌─────────────────────────────────────────────────────────────────┐
        │ Total Pendapatan = Gaji Pokok                                  │
        │                  + Tunjangan Jabatan                           │
        │                  + Tunjangan Makan                             │
        │                  + Tunjangan Transport                         │
        │                  + Tunjangan Lainnya                           │
        │                  + Lembur                                      │
        │                  + Bonus                                       │
        ├─────────────────────────────────────────────────────────────────┤
        │ Total Potongan   = BPJS Kesehatan                              │
        │                  + BPJS Ketenagakerjaan                        │
        │                  + PPh 21 (Pajak Penghasilan)                   │
        │                  + Potongan Lainnya                             │
        ├─────────────────────────────────────────────────────────────────┤
        │ Gaji Bersih      = Total Pendapatan - Total Potongan           │
        └─────────────────────────────────────────────────────────────────┘

        Contoh:
        Pendapatan: 5jt + 500rb + 300rb + 200rb + 0 + 100rb + 0 = 6.1jt
        Potongan: 100rb + 50rb + 150rb + 0 = 300rb
        Gaji Bersih: 6.1jt - 300rb = 5.8jt
        """
        # KOMPONEN PENDAPATAN — semua sumber penghasilan karyawan
        self.total_pendapatan = (
            self.gaji_pokok +              # Gaji pokok bulanan
            self.tunjangan_jabatan +       # Tunjangan berdasarkan posisi/jabatan
            self.tunjangan_makan +         # Uang makan harian × hari kerja
            self.tunjangan_transport +     # Uang transport/bensin
            self.tunjangan_lainnya +       # Tunjangan lain (kesehatan, komunikasi, dll)
            self.lembur +                  # Upah lembur (jam lembur × tarif per jam)
            self.bonus                     # Bonus kinerja/prestasi (opsional)
        )

        # KOMPONEN POTONGAN — semua pengurangan dari gaji bruto
        self.total_potongan = (
            self.potongan_bpjs_kesehatan +         # Iuran BPJS Kesehatan (wajib)
            self.potongan_bpjs_ketenagakerjaan +   # Iuran BPJS Ketenagakerjaan (wajib)
            self.potongan_pph21 +                  # Pajak Penghasilan Pasal 21
            self.potongan_lainnya                  # Potongan lain (pinjaman, dll)
        )

        # GAJI BERSIH — yang diterima karyawan (take-home pay)
        self.gaji_bersih = self.total_pendapatan - self.total_potongan

    @property
    def periode(self):
        """
        Property untuk mendapatkan nama periode gaji dalam format yang mudah dibaca.

        Konversi: bulan=1, tahun=2024 → 'Januari 2024'
        Mapping: Index 0 dikosongkan karena bulan dimulai dari 1 (bukan 0)

        Digunakan di: template slip gaji dan laporan penggajian

        Return: String — contoh 'Januari 2024', 'Desember 2025'
        """
        # Index 0 dikosongkan ('') karena bulan dimulai dari 1
        bulan_names = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                       'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
        return f"{bulan_names[self.periode_bulan]} {self.periode_tahun}"

    @property
    def total_tunjangan(self):
        """
        Property untuk menghitung total tunjangan karyawan.

        Total = Tunjangan Jabatan + Tunjangan Makan + Tunjangan Transport
                + Tunjangan Lainnya + Lembur + Bonus

        Return: Decimal — total tunjangan
        """
        return (
            self.tunjangan_jabatan +
            self.tunjangan_makan +
            self.tunjangan_transport +
            self.tunjangan_lainnya +
            self.lembur +
            self.bonus
        )
