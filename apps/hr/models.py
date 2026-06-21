"""
==========================================================================
 HR MODELS - Human Resources (SDM / Sumber Daya Manusia)
==========================================================================
 File ini berisi 6 model untuk modul HR:

 1. Departemen â†’ Divisi/bagian perusahaan (IT, Finance, Marketing, dll)
 2. Jabatan â†’ Posisi/role karyawan (Staff, Supervisor, Manager)
 3. Karyawan â†’ Data master karyawan
 4. FotoWajah â†’ Foto untuk absensi face recognition
 5. PengaturanAbsensi â†’ Konfigurasi jam kerja, lokasi, hari kerja
 6. Absensi â†’ Record kehadiran harian karyawan
 7. Penggajian â†’ Slip gaji bulanan (pendapatan - potongan = gaji bersih)

 HIERARKI ORGANISASI:
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ Departemen â”‚ (contoh: IT, Finance)
 â”‚  â”œâ”€â”€ Jabatan 1 (Staff â†’ gaji 5jt)
 â”‚  â”œâ”€â”€ Jabatan 2 (Supervisor â†’ gaji 8jt)
 â”‚  â””â”€â”€ Jabatan 3 (Manager â†’ gaji 12jt)
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
       â”‚
       â””â”€â”€â†’ Karyawan â†’ Absensi â†’ Penggajian

 Koneksi:
 - django.contrib.auth.models.User â†’ Karyawan bisa terhubung ke akun user
 - apps/hr/views.py â†’ View CRUD untuk semua model HR
 - apps/dashboard/views.py â†’ Statistik karyawan di dashboard
==========================================================================
"""

from django.db import models                # Django ORM â€” framework untuk mendefinisikan tabel database sebagai class Python
from django.contrib.auth.models import User  # Model User bawaan Django â€” menyimpan data akun login (username, password, email)
from decimal import Decimal                  # Tipe data Decimal â€” untuk perhitungan uang yang presisi (tidak ada pembulatan float)
from apps.core.validators import validate_image_file


# â•”â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â•—
# â•‘                     DEPARTEMEN                                â•‘
# â•šâ• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• â• 

class Departemen(models.Model):
    """
    Model untuk DEPARTEMEN / divisi perusahaan.

    Departemen adalah unit organisasi tertinggi dalam hierarki HR.
    Contoh departemen: IT, Finance, Marketing, Warehouse, HR, dll.

    Relasi:
    - Departemen (1) â†’ (N) Jabatan â€” satu departemen punya banyak jabatan
    - Departemen (1) â†’ (N) Karyawan â€” satu departemen punya banyak karyawan
    - Departemen â†’ Kepala (FK ke Karyawan) â€” setiap departemen punya 1 kepala

    Contoh data:
    | kode  | nama      | kepala_departemen |
    |-------|-----------|-------------------|
    | IT    | IT        | Budi Santoso      |
    | FIN   | Finance   | Siti Nurhaliza    |
    | MKT   | Marketing | None (kosong)     |
    """

    # Kode unik departemen â€” digunakan sebagai identifier pendek
    # unique=True berarti tidak boleh ada 2 departemen dengan kode yang sama
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Departemen")

    # Nama lengkap departemen â€” ditampilkan di UI dan laporan
    nama = models.CharField(max_length=100, verbose_name="Nama Departemen")

    # Deskripsi tugas/fungsi departemen â€” opsional (blank=True, null=True)
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # Kepala departemen â€” relasi ke model Karyawan
    # Menggunakan string 'Karyawan' (bukan class langsung) karena model Karyawan
    # didefinisikan SETELAH Departemen di file ini (forward reference)
    # on_delete=SET_NULL â†’ jika karyawan dihapus, field ini jadi NULL (bukan error)
    # related_name='departemen_dipimpin' â†’ akses balik: karyawan.departemen_dipimpin.all()
    kepala_departemen = models.ForeignKey(
        'Karyawan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departemen_dipimpin',
        verbose_name="Kepala Departemen"
    )

    # Flag aktif/nonaktif â€” departemen nonaktif tidak muncul di dropdown
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp otomatis â€” auto_now_add=True: diisi saat pertama kali dibuat
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
        Representasi string â€” dipanggil saat print() atau ditampilkan di dropdown.
        Format: 'IT - Information Technology'
        """
        return f"{self.kode} - {self.nama}"

    @property
    def jumlah_karyawan(self):
        """
        Property untuk menghitung jumlah karyawan AKTIF di departemen ini.

        Cara kerja:
        - self.karyawan_set â†’ reverse relation dari FK Karyawan.departemen
        - .filter(aktif=True) â†’ hanya karyawan yang masih aktif
        - .count() â†’ hitung jumlahnya (SQL COUNT)

        Digunakan di: template list departemen untuk menampilkan badge jumlah karyawan

        Return: Integer â€” jumlah karyawan aktif (contoh: 15)
        """
        return self.karyawan_set.filter(aktif=True).count()


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                      JABATAN                                  â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Jabatan(models.Model):
    """
    Model untuk JABATAN / posisi karyawan dalam organisasi.

    Jabatan menentukan:
    - Posisi karyawan dalam hierarki (Staff â†’ Supervisor â†’ Manager â†’ Director â†’ Executive)
    - Gaji pokok default yang diberikan saat karyawan baru ditambahkan
    - Tunjangan jabatan yang melekat pada posisi tersebut

    Relasi:
    - Jabatan (N) â†’ (1) Departemen â€” setiap jabatan milik 1 departemen
    - Jabatan (1) â†’ (N) Karyawan â€” 1 jabatan bisa dipegang banyak karyawan

    Contoh data:
    | kode     | nama              | departemen | level      | gaji_pokok |
    |----------|-------------------|------------|------------|------------|
    | IT-STF   | Staff IT          | IT         | staff      | 5,000,000  |
    | IT-SPV   | Supervisor IT     | IT         | supervisor | 8,000,000  |
    | FIN-MGR  | Manager Finance   | Finance    | manager    | 12,000,000 |
    """

    # Level jabatan â€” menentukan hierarki posisi dalam organisasi
    # Digunakan untuk urutan tampilan dan laporan organisasi
    LEVEL_CHOICES = [
        ('staff', 'Staff'),              # Level terendah â€” pelaksana tugas harian
        ('supervisor', 'Supervisor'),    # Mengawasi staff di bawahnya
        ('manager', 'Manager'),          # Mengelola tim dan departemen
        ('director', 'Director'),        # Pengambil keputusan strategis divisi
        ('executive', 'Executive'),      # Level tertinggi â€” C-level (CEO, CFO, dll)
    ]

    # Kode unik jabatan â€” contoh: 'IT-STF', 'FIN-MGR'
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Jabatan")

    # Nama lengkap jabatan â€” contoh: 'Staff IT', 'Manager Finance'
    nama = models.CharField(max_length=100, verbose_name="Nama Jabatan")

    # Relasi ke Departemen â€” setiap jabatan harus terikat ke 1 departemen
    # on_delete=PROTECT â†’ departemen TIDAK BISA dihapus selama masih punya jabatan
    # Ini mencegah kehilangan data jabatan secara tidak sengaja
    departemen = models.ForeignKey(
        Departemen,
        on_delete=models.PROTECT,
        related_name='jabatan_set',       # departemen.jabatan_set.all() â†’ semua jabatan di departemen
        verbose_name="Departemen"
    )

    # Level hierarki â€” menggunakan choices agar hanya bisa pilih dari daftar valid
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='staff', verbose_name="Level")

    # Gaji pokok default â€” otomatis dipakai saat karyawan baru ditambahkan ke jabatan ini
    # max_digits=15, decimal_places=2 â†’ mendukung hingga 9,999,999,999,999.99
    gaji_pokok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Gaji Pokok")

    # Tunjangan jabatan â€” kompensasi tambahan berdasarkan posisi
    tunjangan_jabatan = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Tunjangan Jabatan")

    # Deskripsi tugas dan tanggung jawab jabatan â€” opsional
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi Tugas")

    # Flag aktif â€” jabatan nonaktif tidak muncul di dropdown saat tambah karyawan
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp tracking â€” kapan record dibuat dan terakhir diubah
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat pertama kali dibuat
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis setiap kali disimpan

    class Meta:
        """Konfigurasi metadata model Jabatan."""
        verbose_name = "Jabatan"                              # Nama singular
        verbose_name_plural = "Jabatan"                       # Nama plural
        ordering = ['departemen', 'level', 'nama']            # Urutan: departemen â†’ level â†’ nama

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

        Return: Integer â€” jumlah karyawan aktif
        """
        return self.karyawan_set.filter(aktif=True).count()


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                     KARYAWAN                                   â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Karyawan(models.Model):
    """
    Model master KARYAWAN â€” entitas utama modul HR.

    Setiap karyawan memiliki:
    - NIK unik (auto-generate: EMP20240001)
    - Data pribadi (nama, email, telepon, alamat, dll)
    - Data organisasi (jabatan, departemen)
    - Data kepegawaian (tanggal masuk/keluar, status)
    - Gaji pokok (default dari jabatan)
    - Link ke akun User Django (opsional)

    Status karyawan: aktif â†’ cuti â†’ resign/phk
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
    foto = models.ImageField(upload_to='hr/karyawan/', blank=True, null=True, verbose_name="Foto Karyawan", validators=[validate_image_file])

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
    # FK ke Gudang (cabang) â€” menentukan di cabang mana karyawan bekerja
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
        related_name='karyawan',           # user.karyawan â†’ data karyawan user ini
        verbose_name="Akun User"
    )

    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # ===== TRACKING =====
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='karyawan_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata model Karyawan â€” urutan default A-Z berdasarkan nama."""
        verbose_name = "Karyawan"
        verbose_name_plural = "Karyawan"
        ordering = ['nama']
        indexes = [
            models.Index(fields=['aktif', 'status'], name='hr_emp_aktif_status_idx'),
            models.Index(fields=['departemen', 'aktif'], name='hr_emp_dept_aktif_idx'),
            models.Index(fields=['jabatan', 'aktif'], name='hr_emp_jabatan_aktif_idx'),
            models.Index(fields=['cabang', 'aktif'], name='hr_emp_cabang_aktif_idx'),
        ]

    def __str__(self):
        """Representasi string karyawan: 'EMP20240001 - Budi Santoso' â€” untuk admin dan dropdown."""
        return f"{self.nik} - {self.nama}"

    def save(self, *args, **kwargs):
        """
        Override method save() Django â€” dipanggil setiap kali record karyawan disimpan.

        Langkah-langkah:
        1. Cek apakah NIK sudah diisi â†’ jika belum, generate otomatis
        2. Cek apakah gaji_pokok sudah diisi â†’ jika belum, ambil default dari jabatan
        3. Panggil super().save() â†’ simpan ke database

        DIPERBAIKI: Dibungkus transaction.atomic() agar generate_nik() + save()
        berjalan dalam satu transaksi â€” mencegah race condition NIK duplikat.
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
        1. Buat prefix berdasarkan tahun sekarang â†’ 'EMP2024'
        2. Cari karyawan terakhir dengan prefix yang sama
        3. Ambil 4 digit terakhir dari NIK terakhir â†’ increment + 1
        4. Jika belum ada karyawan â†’ mulai dari 0001

        Return: String NIK â€” contoh 'EMP20240001'
        """
        from django.utils import timezone
        today = timezone.now()
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
                # DIPERBAIKI: bare except â†’ except spesifik
                # Jika format NIK tidak standar (gagal parse), mulai dari 1
                new_number = 1
        else:
            # Belum ada karyawan di tahun ini â†’ mulai dari 1
            new_number = 1

        # Format dengan zero-padding 4 digit: 1 â†’ '0001', 42 â†’ '0042'
        return f"{prefix}{new_number:04d}"


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                   FOTO WAJAH (FACE RECOGNITION)               â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class FotoWajah(models.Model):
    """
    Model untuk FOTO WAJAH karyawan â€” digunakan untuk absensi face recognition.

    Setiap karyawan bisa punya beberapa foto wajah dari sudut berbeda.
    Field 'encoding' menyimpan vector face encoding untuk perbandingan.
    """
    karyawan = models.ForeignKey(
        Karyawan,
        on_delete=models.CASCADE,          # Karyawan dihapus â†’ foto ikut terhapus
        related_name='foto_wajah_set',
        verbose_name="Karyawan"
    )
    foto = models.ImageField(upload_to='hr/wajah/', verbose_name="Foto Wajah", validators=[validate_image_file])
    encoding = models.TextField(blank=True, null=True, verbose_name="Face Encoding")  # Vector encoding
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model FotoWajah â€” terbaru di atas."""
        verbose_name = "Foto Wajah"
        verbose_name_plural = "Foto Wajah"
        ordering = ['-dibuat_pada']

    def __str__(self):
        """Representasi string: 'Foto Budi Santoso - 2024-01-15 08:00:00' â€” untuk admin."""
        return f"Foto {self.karyawan.nama} - {self.dibuat_pada}"


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                  PENGATURAN ABSENSI                           â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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

    âš  PENTING: Hanya 1 pengaturan yang aktif di satu waktu!
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
    # FK ke Gudang (cabang) â€” pengaturan absensi per cabang
    # Jika null â†’ pengaturan default (berlaku untuk karyawan tanpa cabang)
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
        """Konfigurasi metadata â€” pengaturan aktif ditampilkan paling atas."""
        verbose_name = "Pengaturan Absensi"
        verbose_name_plural = "Pengaturan Absensi"
        ordering = ['-aktif', '-diupdate_pada']

    def __str__(self):
        """Representasi string: 'Pengaturan Default (âœ“ Aktif)' â€” menampilkan status aktif/nonaktif."""
        status = "âœ“ Aktif" if self.aktif else "Nonaktif"
        return f"{self.nama} ({status})"

    def save(self, *args, **kwargs):
        """
        Override save() â€” implementasi singleton-per-cabang behavior.

        Logika:
        - Jika record ini diaktifkan (self.aktif = True)
        - Maka NONAKTIFKAN pengaturan lain UNTUK CABANG YANG SAMA
        - Ini memastikan hanya 1 pengaturan aktif per cabang

        Multi-cabang:
        - Cabang A bisa punya pengaturan aktif sendiri
        - Cabang B bisa punya pengaturan aktif sendiri
        - Pengaturan default (cabang=None) berlaku untuk karyawan tanpa cabang
        """
        from django.db import transaction

        with transaction.atomic():
            if self.aktif:
            # Nonaktifkan pengaturan lain UNTUK CABANG YANG SAMA saja
            # Jika cabang=None â†’ nonaktifkan yang cabang=None juga
                PengaturanAbsensi.objects.filter(
                    cabang=self.cabang
                ).exclude(pk=self.pk).update(aktif=False)
            super().save(*args, **kwargs)  # Simpan record ini ke database

    @property
    def hari_kerja_list(self):
        """
        Konversi string hari kerja dari database ke list integer Python.

        Contoh: '0,1,2,3,4' â†’ [0, 1, 2, 3, 4]
        Mapping: 0=Senin, 1=Selasa, 2=Rabu, 3=Kamis, 4=Jumat, 5=Sabtu, 6=Minggu

        Kenapa disimpan sebagai string?
        - Django tidak punya field array untuk database sederhana (SQLite)
        - String CSV adalah cara paling sederhana menyimpan list angka

        Return: List of integers â€” contoh [0, 1, 2, 3, 4]
        """
        if self.hari_kerja:
            # split(',') â†’ pecah string menjadi list: ['0','1','2','3','4']
            # isdigit() â†’ filter hanya yang berupa angka (keamanan)
            # int(h) â†’ konversi string ke integer
            return [int(h) for h in self.hari_kerja.split(',') if h.isdigit()]
        return []  # Kembalikan list kosong jika field kosong

    @property
    def hari_kerja_display(self):
        """
        Konversi nomor hari ke nama hari untuk ditampilkan di UI.

        Contoh: [0, 1, 2, 3, 4] â†’ ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']

        Return: List of strings â€” nama-nama hari kerja
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
        1. Jika cabang diberikan â†’ cari pengaturan khusus cabang tersebut
        2. Jika tidak ditemukan â†’ fallback ke pengaturan default (cabang=None)
        3. Jika cabang=None â†’ langsung ambil pengaturan default

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


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                      ABSENSI                                  â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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

    # Face recognition â€” persentase kemiripan wajah
    persentase_kemiripan = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True, verbose_name="Persentase Kemiripan")

    # Foto absensi (bukti kehadiran)
    foto_masuk = models.ImageField(upload_to='hr/absensi/', blank=True, null=True, verbose_name="Foto Masuk", validators=[validate_image_file])
    foto_keluar = models.ImageField(upload_to='hr/absensi/', blank=True, null=True, verbose_name="Foto Keluar", validators=[validate_image_file])

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
        """Konfigurasi metadata â€” 1 record per karyawan per hari, diurutkan terbaru dulu."""
        verbose_name = "Absensi"
        verbose_name_plural = "Absensi"
        ordering = ['-tanggal', 'karyawan']
        unique_together = ['karyawan', 'tanggal']  # 1 record per karyawan per hari
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='hr_abs_tgl_status_idx'),
            models.Index(fields=['cabang', 'tanggal'], name='hr_abs_cabang_tgl_idx'),
        ]

    def __str__(self):
        """Representasi string: 'Budi Santoso - 2024-01-15 (hadir)' â€” untuk admin dan log."""
        return f"{self.karyawan.nama} - {self.tanggal} ({self.status})"

    @property
    def durasi_kerja(self):
        """
        Property untuk menghitung durasi kerja karyawan dalam satuan JAM.

        DIPERBAIKI: Menangani shift malam (jam_keluar < jam_masuk)
        dengan menambahkan 1 hari ke jam_keluar.

        Contoh normal: masuk 08:00, keluar 17:00 â†’ durasi = 9.0 jam
        Contoh shift malam: masuk 22:00, keluar 06:00 â†’ durasi = 8.0 jam

        Return: Float â€” durasi kerja dalam jam, atau 0 jika data tidak lengkap
        """
        if self.jam_masuk and self.jam_keluar:
            from datetime import datetime, timedelta

            masuk = datetime.combine(self.tanggal, self.jam_masuk)
            keluar = datetime.combine(self.tanggal, self.jam_keluar)

            # DIPERBAIKI: Handle shift malam â€” jika keluar lebih awal dari masuk,
            # artinya karyawan pulang keesokan harinya
            if keluar < masuk:
                keluar += timedelta(days=1)

            durasi = keluar - masuk
            return durasi.total_seconds() / 3600
        return 0  # Kembalikan 0 jika jam masuk/keluar belum diisi


# â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
# â•‘                     PENGGAJIAN                                â•‘
# â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Penggajian(models.Model):
    """
    Model untuk SLIP GAJI karyawan bulanan.

    Rumus:
    Total Pendapatan = Gaji Pokok + Tunjangan(5 jenis) + Lembur + Bonus
    Total Potongan = BPJS Kesehatan + BPJS TK + PPh 21 + Potongan Lainnya
    Gaji Bersih = Total Pendapatan - Total Potongan

    âš  PENTING: unique_together = ['karyawan', 'periode_bulan', 'periode_tahun']
    â†’ 1 karyawan hanya bisa punya 1 slip gaji per bulan per tahun
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('diproses', 'Diproses'),
        ('dibayar', 'Dibayar'),
        ('batal', 'Batal'),
    ]

    karyawan = models.ForeignKey(
        Karyawan,
        on_delete=models.PROTECT,
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

    # ===== CABANG & METODE PEMBAYARAN =====
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penggajian_set',
        verbose_name="Cabang",
        help_text="Otomatis dari cabang karyawan jika tidak diisi"
    )
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penggajian_set',
        verbose_name="Metode Pembayaran",
        help_text="Metode pembayaran gaji (Kas/Transfer Bank)"
    )

    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='penggajian_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        """Konfigurasi metadata â€” 1 slip gaji per karyawan per bulan, urutan terbaru dulu."""
        verbose_name = "Penggajian"
        verbose_name_plural = "Penggajian"
        ordering = ['-periode_tahun', '-periode_bulan', 'karyawan']
        unique_together = ['karyawan', 'periode_bulan', 'periode_tahun']
        indexes = [
            models.Index(fields=['periode_tahun', 'periode_bulan', 'status'], name='hr_pay_period_status_idx'),
            models.Index(fields=['status', 'tanggal_bayar'], name='hr_pay_status_tgl_idx'),
        ]

    # ===== STATE MACHINE =====
    # Transisi status yang valid — digunakan oleh transition_status()
    VALID_TRANSITIONS = {
        'draft': ['diproses', 'batal'],
        'diproses': ['dibayar', 'batal'],
        'dibayar': ['batal'],
        'batal': [],
    }

    def transition_status(self, new_status, user=None):
        """
        Validasi dan set transisi status.
        TIDAK memanggil save() — caller harus save dalam transaction.atomic().
        Raises ValidationError jika transisi tidak valid.
        """
        from django.core.exceptions import ValidationError
        valid_targets = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in valid_targets:
            raise ValidationError(
                f"Transisi status tidak valid: '{self.get_status_display()}' → '{new_status}'. "
                f"Transisi yang diizinkan dari status '{self.status}': {valid_targets}"
            )
        self.status = new_status
        return self


    def __str__(self):
        """Representasi string: 'Budi Santoso - 1/2024' â€” untuk admin dan laporan slip gaji."""
        return f"{self.karyawan.nama} - {self.periode_bulan}/{self.periode_tahun}"

    def save(self, *args, **kwargs):
        """
        Override save() â€” otomatis hitung total sebelum menyimpan ke database.

        Alur:
        1. Panggil calculate_total() â†’ hitung total_pendapatan, total_potongan, gaji_bersih
        2. Panggil super().save() â†’ simpan semua field ke database

        Kenapa hitung di save() bukan di form?
        - Agar konsisten: total SELALU dihitung ulang setiap kali disimpan
        - Meskipun data diubah langsung via admin/script, total tetap benar
        """
        # Auto-set cabang dari karyawan jika belum diisi
        if not self.cabang_id and self.karyawan_id:
            self.cabang = self.karyawan.cabang
        self.calculate_total()     # Hitung ulang semua total
        super().save(*args, **kwargs)  # Simpan ke database

    def calculate_total(self):
        """
        Menghitung total pendapatan, potongan, dan gaji bersih.

        Formula perhitungan:
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚ Total Pendapatan = Gaji Pokok                                  â”‚
        â”‚                  + Tunjangan Jabatan                           â”‚
        â”‚                  + Tunjangan Makan                             â”‚
        â”‚                  + Tunjangan Transport                         â”‚
        â”‚                  + Tunjangan Lainnya                           â”‚
        â”‚                  + Lembur                                      â”‚
        â”‚                  + Bonus                                       â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚ Total Potongan   = BPJS Kesehatan                              â”‚
        â”‚                  + BPJS Ketenagakerjaan                        â”‚
        â”‚                  + PPh 21 (Pajak Penghasilan)                   â”‚
        â”‚                  + Potongan Lainnya                             â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚ Gaji Bersih      = Total Pendapatan - Total Potongan           â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

        Contoh:
        Pendapatan: 5jt + 500rb + 300rb + 200rb + 0 + 100rb + 0 = 6.1jt
        Potongan: 100rb + 50rb + 150rb + 0 = 300rb
        Gaji Bersih: 6.1jt - 300rb = 5.8jt
        """
        # KOMPONEN PENDAPATAN â€” semua sumber penghasilan karyawan
        self.total_pendapatan = (
            self.gaji_pokok +              # Gaji pokok bulanan
            self.tunjangan_jabatan +       # Tunjangan berdasarkan posisi/jabatan
            self.tunjangan_makan +         # Uang makan harian Ã— hari kerja
            self.tunjangan_transport +     # Uang transport/bensin
            self.tunjangan_lainnya +       # Tunjangan lain (kesehatan, komunikasi, dll)
            self.lembur +                  # Upah lembur (jam lembur Ã— tarif per jam)
            self.bonus                     # Bonus kinerja/prestasi (opsional)
        )

        # KOMPONEN POTONGAN â€” semua pengurangan dari gaji bruto
        self.total_potongan = (
            self.potongan_bpjs_kesehatan +         # Iuran BPJS Kesehatan (wajib)
            self.potongan_bpjs_ketenagakerjaan +   # Iuran BPJS Ketenagakerjaan (wajib)
            self.potongan_pph21 +                  # Pajak Penghasilan Pasal 21
            self.potongan_lainnya                  # Potongan lain (pinjaman, dll)
        )

        # GAJI BERSIH â€” yang diterima karyawan (take-home pay)
        self.gaji_bersih = self.total_pendapatan - self.total_potongan

    @property
    def periode(self):
        """
        Property untuk mendapatkan nama periode gaji dalam format yang mudah dibaca.

        Konversi: bulan=1, tahun=2024 â†’ 'Januari 2024'
        Mapping: Index 0 dikosongkan karena bulan dimulai dari 1 (bukan 0)

        Digunakan di: template slip gaji dan laporan penggajian

        Return: String â€” contoh 'Januari 2024', 'Desember 2025'
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

        Return: Decimal â€” total tunjangan
        """
        return (
            self.tunjangan_jabatan +
            self.tunjangan_makan +
            self.tunjangan_transport +
            self.tunjangan_lainnya +
            self.lembur +
            self.bonus
        )
