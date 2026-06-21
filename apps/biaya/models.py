"""
==========================================================================
 BIAYA MODELS - Manajemen Biaya / Pengeluaran Operasional
==========================================================================
 File ini berisi 2 model untuk pencatatan biaya/expense:

 1. KategoriBiaya → Pengelompokan biaya (Listrik, Gaji, Sewa, dll)
 2. TransaksiBiaya → Record pengeluaran (expense record)

 ALUR TRANSAKSI BIAYA:
 ┌──────┐   ┌───────────┐   ┌──────────┐
 │Draft │──→│ Submitted │──→│ Approved │  → Uang keluar
 └──────┘   └───────────┘   └──────────┘
                                │
                           ┌──────────┐
                           │ Rejected │  → Ditolak
                           └──────────┘

 Koneksi:
 - apps/pos/models.py → MetodePembayaran (FK untuk pembayaran biaya)
 - apps/dashboard/views.py → Menampilkan total biaya di dashboard
 - apps/laporan/ → Laporan biaya
==========================================================================
"""

from django.db import models                # Django ORM untuk mendefinisikan model/tabel database
from django.contrib.auth.models import User  # Model User bawaan Django (akun login)
from apps.core.validators import validate_expense_proof


class KategoriBiaya(models.Model):
    """
    Model untuk KATEGORI BIAYA / pengelompokan expense.

    Contoh: Listrik, Gaji Karyawan, Sewa Gedung, Transportasi, Internet, dll.
    """
    # Nama kategori biaya — contoh: 'Listrik', 'Gaji Karyawan', 'Sewa Gedung'
    nama = models.CharField(max_length=100, verbose_name="Nama Kategori")

    # Deskripsi opsional — penjelasan detail tentang kategori ini
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # FK ke Akun CoA — akun beban spesifik untuk kategori ini
    # Jika kosong, fallback ke akun 6-9000 (Beban Operasional Lainnya)
    akun_beban = models.ForeignKey(
        'akuntansi.Akun',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kategori_biaya',
        verbose_name="Akun Beban (CoA)",
        help_text="Akun CoA spesifik untuk kategori ini. Kosong = fallback ke 6-9000"
    )

    # Flag aktif — kategori nonaktif tidak muncul di dropdown saat buat transaksi biaya
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp kapan kategori ini dibuat — auto_now_add hanya diisi sekali saat create
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model KategoriBiaya."""
        verbose_name = "Kategori Biaya"            # Nama singular di Django Admin
        verbose_name_plural = "Kategori Biaya"     # Nama plural di Django Admin
        ordering = ['nama']                        # Urutan default A-Z berdasarkan nama
        indexes = [
            models.Index(fields=['aktif', 'nama'], name='biaya_kat_aktif_idx'),
        ]

    def __str__(self):
        """Representasi string — nama kategori (contoh: 'Listrik')."""
        return self.nama


class TransaksiBiaya(models.Model):
    """
    Model untuk TRANSAKSI BIAYA / pengeluaran operasional.

    Setiap transaksi biaya memiliki:
    - Nomor unik (auto-generate: EXP/2024/01/0001)
    - Kategori biaya (Listrik, Gaji, dll)
    - Jumlah uang yang dikeluarkan
    - Status workflow (draft → submitted → approved/rejected)
    - Bukti (foto/PDF bon/kwitansi)
    - Metode pembayaran (Cash, Transfer, dll)
    """

    # ===== STATUS WORKFLOW =====
    # Status menentukan alur persetujuan biaya:
    # draft → submitted → approved (uang keluar) ATAU rejected (ditolak)
    STATUS_CHOICES = [
        ('draft', 'Draft'),              # Baru dibuat, belum diajukan
        ('submitted', 'Diajukan'),       # Sudah diajukan, menunggu persetujuan
        ('approved', 'Disetujui'),       # Disetujui manager → uang keluar dari kas
        ('rejected', 'Ditolak'),         # Ditolak manager → tidak ada pengeluaran
        ('cancelled', 'Dibatalkan'),     # Dibatalkan setelah approved → reversal jurnal
    ]

    # ===== IDENTITAS TRANSAKSI =====
    # Nomor transaksi unik — auto-generate format: EXP/2024/01/0001
    nomor_transaksi = models.CharField(max_length=50, unique=True, verbose_name="Nomor Transaksi")

    # Tanggal pengeluaran — DateField (bukan DateTimeField) karena hanya perlu tanggal
    # Berbeda dengan POS yang pakai DateTimeField karena butuh waktu detail
    tanggal = models.DateField(verbose_name="Tanggal")

    # Kategori biaya — FK ke KategoriBiaya (contoh: Listrik, Gaji)
    # on_delete=PROTECT → kategori tidak bisa dihapus jika masih ada transaksi
    kategori = models.ForeignKey(KategoriBiaya, on_delete=models.PROTECT, related_name='transaksi', verbose_name="Kategori")

    # Nominal pengeluaran — berapa uang yang dikeluarkan
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Deskripsi wajib — penjelasan detail tentang biaya ini
    # Tidak ada blank=True, artinya deskripsi WAJIB diisi (required field)
    deskripsi = models.TextField(verbose_name="Deskripsi")

    bukti = models.FileField(upload_to='biaya/', blank=True, null=True, verbose_name="Bukti (Foto/PDF)", validators=[validate_expense_proof])

    # Status workflow — mengikuti alur persetujuan (lihat STATUS_CHOICES di atas)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    # ===== TRACKING PENGGUNA =====
    # Siapa yang membuat transaksi biaya ini
    # on_delete=SET_NULL → jika user dihapus, transaksi tetap ada (creator=null)
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='biaya_dibuat')

    # Siapa yang menyetujui biaya ini (diisi saat status berubah ke 'approved')
    # Opsional — hanya diisi saat ada approval
    disetujui_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='biaya_disetujui')

    # Siapa yang membatalkan biaya ini (diisi saat status berubah ke 'cancelled')
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='biaya_dibatalkan',
        verbose_name="Dibatalkan Oleh"
    )

    # Tanggal pembatalan (diisi saat status berubah ke 'cancelled')
    cancelled_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Tanggal Pembatalan"
    )

    # ===== METODE PEMBAYARAN =====
    # FK ke MetodePembayaran di modul POS — cross-module relation
    # Menggunakan string 'pos.MetodePembayaran' karena model ada di app lain
    # Ini memungkinkan tracking dari metode mana uang dikeluarkan
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',          # String reference ke model di app 'pos'
        on_delete=models.SET_NULL,       # Metode dihapus → transaksi tetap ada
        null=True, blank=True,
        related_name='transaksi_biaya',  # metode.transaksi_biaya.all() → semua biaya via metode ini
        verbose_name="Metode Pembayaran"
    )

    # ===== CABANG / GUDANG =====
    # FK ke Gudang (cabang) — biaya bisa dikaitkan ke cabang tertentu
    # Setiap cabang memiliki biayanya masing-masing
    cabang = models.ForeignKey(
        'produk.Gudang',                 # String reference ke model Gudang di app 'produk'
        on_delete=models.SET_NULL,       # Gudang dihapus → transaksi tetap ada
        null=True, blank=True,
        related_name='transaksi_biaya',  # gudang.transaksi_biaya.all() → semua biaya di cabang ini
        verbose_name="Cabang"
    )

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model TransaksiBiaya."""
        verbose_name = "Transaksi Biaya"           # Nama singular
        verbose_name_plural = "Transaksi Biaya"    # Nama plural
        # Urutan: tanggal terbaru → kemudian dibuat terbaru
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='biaya_trx_tgl_status_idx'),
            models.Index(fields=['kategori', 'status'], name='biaya_trx_kat_status_idx'),
            models.Index(fields=['cabang', 'tanggal'], name='biaya_trx_cbg_tgl_idx'),
            models.Index(fields=['metode_pembayaran', 'status'], name='biaya_trx_pay_status_idx'),
        ]

    # ===== STATE MACHINE =====
    # Transisi status yang valid — digunakan oleh transition_status()
    VALID_TRANSITIONS = {
        'draft': ['submitted'],
        'submitted': ['approved', 'rejected'],
        'approved': ['cancelled'],
        'rejected': ['draft'],
        'cancelled': [],  # terminal state
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
        """
        Representasi string transaksi untuk admin/debugging.
        Format: 'EXP/2024/01/0001 - Listrik - Rp 500,000'
        :,.0f → format angka dengan separator ribuan tanpa desimal
        """
        return f"{self.nomor_transaksi} - {self.kategori.nama} - Rp {self.jumlah:,.0f}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor transaksi.

        Alur:
        1. Cek apakah nomor_transaksi sudah diisi atau belum
        2. Jika belum → generate nomor otomatis
        3. Simpan ke database via super().save()

        DIPERBAIKI: Dibungkus transaction.atomic() agar select_for_update()
        di generate_nomor() efektif — lock baru dilepas setelah save selesai.
        """
        from django.db import transaction
        with transaction.atomic():
            if not self.nomor_transaksi:
                # Generate nomor otomatis hanya jika field kosong
                self.nomor_transaksi = self.generate_nomor()
            super().save(*args, **kwargs)  # Simpan semua field ke database

    def generate_nomor(self):
        """
        Generate nomor transaksi biaya otomatis (per BULAN).

        Format: EXP/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: EXP/2024/01/0001, EXP/2024/01/0002

        Algoritma (sama dengan pola di PO/SO):
        1. Buat prefix berdasarkan tahun+bulan → 'EXP/2024/01'
        2. Cari transaksi terakhir dengan prefix yang sama
        3. Parse dan increment nomor urut
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor transaksi — contoh 'EXP/2024/01/0001'
        """
        from django.utils import timezone
        today = timezone.now()
        # Format prefix: EXP/2024/01 (per bulan, bukan per hari seperti POS)
        prefix = f"EXP/{today.year}/{today.month:02d}"

        # Cari transaksi biaya terakhir BULAN INI
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_exp = TransaksiBiaya.objects.select_for_update().filter(
            nomor_transaksi__startswith=prefix  # Filter transaksi bulan ini
        ).order_by('-nomor_transaksi').first()  # Ambil yang nomor terbesar

        if last_exp:
            try:
                # Parse nomor urut dari nomor terakhir
                # Contoh: 'EXP/2024/01/0005'.split('/') → [-1] = '0005' → int = 5
                last_number = int(last_exp.nomor_transaksi.split('/')[-1])
                new_number = last_number + 1  # Increment: 5 → 6
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah transaksi + 1
                # Mencegah IntegrityError jika nomor 0001 sudah ada
                new_number = TransaksiBiaya.objects.filter(
                    nomor_transaksi__startswith=prefix
                ).count() + 1
        else:
            new_number = 1  # Transaksi biaya pertama bulan ini

        # Format dengan zero-padding 4 digit: 1 → '0001'
        # Tambahan: loop untuk memastikan nomor yang dihasilkan benar-benar unik
        nomor = f"{prefix}/{new_number:04d}"
        while TransaksiBiaya.objects.filter(nomor_transaksi=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor
