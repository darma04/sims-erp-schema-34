"""
==========================================================================
 INVENTORY MODELS - Transfer Stok & Adjustment Stok
==========================================================================
 File ini berisi 3 model untuk manajemen inventory/gudang:

 1. TransferStok → Pemindahan barang antar gudang
 2. TransferStokItem → Detail produk yang ditransfer
 3. AdjustmentStok → Koreksi stok manual (stock opname)

 ALUR TRANSFER STOK:
 ┌──────────┐    ┌───────────┐    ┌───────────┐    ┌──────────┐
 │  Draft   │───→│ Submitted │───→│ Approved  │───→│ Completed│
 └──────────┘    └───────────┘    └───────────┘    └──────────┘
      │               │                                  │
      └───────────────┴──── Cancelled ◄──────────────────┘

 Saat approve/complete:
 1. Validasi stok gudang asal cukup
 2. Kurangi stok gudang asal
 3. Tambah stok gudang tujuan
 4. Log ke activity_log

 ALUR ADJUSTMENT STOK:
 - Tipe 'in' → Tambah stok (barang ditemukan, bonus, dll)
 - Tipe 'out' → Kurangi stok (rusak, hilang, kadaluarsa)
 - Langsung update stok saat save (tanpa approval)

 Koneksi:
 - apps/produk/models.py → Produk, Gudang, Stok (data master)
 - apps/activity_log/stock_signals.py → Log perubahan stok
 - apps/inventory/views.py → View CRUD untuk transfer dan adjustment
==========================================================================
"""

from django.db import models, transaction, OperationalError   # Django ORM + atomic + lock error
from django.contrib.auth.models import User  # Model User bawaan Django
from apps.produk.models import Produk, Gudang, Stok  # Model master produk


# ╔══════════════════════════════════════════════════════════════╗
# ║              TRANSFER STOK ANTAR GUDANG                       ║
# ╚══════════════════════════════════════════════════════════════╝

class TransferStok(models.Model):
    """
    Model untuk TRANSFER STOK antar gudang.

    Contoh use case:
    - Pindahkan 100 pcs Produk A dari Gudang Utama ke Gudang Cabang
    - Pengiriman barang dari pusat ke toko

    Setiap transfer memiliki:
    - Nomor unik (auto-generate: TRF/2024/01/0001)
    - Gudang asal dan gudang tujuan
    - Status workflow (draft → submitted → approved → completed)
    - Items (daftar produk yang ditransfer)
    """

    # Status workflow — alur kerja transfer
    STATUS_CHOICES = [
        ('draft', 'Draft'),           # Baru dibuat, belum diajukan
        ('submitted', 'Diajukan'),    # Sudah diajukan ke atasan
        ('approved', 'Disetujui'),    # Sudah disetujui
        ('completed', 'Selesai'),     # Transfer selesai, stok sudah berubah
        ('cancelled', 'Dibatalkan'),  # Dibatalkan
    ]

    # Nomor transfer unik — auto-generate format: TRF/2024/01/0001
    nomor_transfer = models.CharField(max_length=50, unique=True, verbose_name="Nomor Transfer")

    # Tanggal transfer — otomatis diisi saat pertama kali dibuat
    tanggal = models.DateTimeField(auto_now_add=True, verbose_name="Tanggal")

    # Gudang asal dan tujuan — menggunakan PROTECT agar gudang tidak bisa dihapus
    # jika masih ada transfer yang merujuk ke gudang tersebut
    gudang_asal = models.ForeignKey(
        Gudang, on_delete=models.PROTECT,
        related_name='transfer_keluar',   # gudang.transfer_keluar.all() → transfer dari gudang ini
        verbose_name="Gudang Asal"
    )
    gudang_tujuan = models.ForeignKey(
        Gudang, on_delete=models.PROTECT,
        related_name='transfer_masuk',    # gudang.transfer_masuk.all() → transfer ke gudang ini
        verbose_name="Gudang Tujuan"
    )

    # Status workflow transfer
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    # Catatan opsional — info tambahan tentang transfer ini
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    # ===== TRACKING PENGGUNA =====
    # Siapa yang membuat transfer ini
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transfer_dibuat')
    # Siapa yang menyetujui transfer (diisi saat approve)
    disetujui_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfer_disetujui')

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model TransferStok."""
        verbose_name = "Transfer Stok"         # Nama singular
        verbose_name_plural = "Transfer Stok"  # Nama plural
        ordering = ['-dibuat_pada']            # Terbaru di atas
        indexes = [
            models.Index(fields=['status', 'dibuat_pada'], name='inv_trf_status_created_idx'),
            models.Index(fields=['gudang_asal', 'status'], name='inv_trf_asal_status_idx'),
            models.Index(fields=['gudang_tujuan', 'status'], name='inv_trf_tujuan_status_idx'),
        ]

    def __str__(self):
        """Representasi: 'TRF/2024/01/0001 - Gudang A → Gudang B'"""
        return f"{self.nomor_transfer} - {self.gudang_asal} → {self.gudang_tujuan}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor transfer.

        Catatan: Stok TIDAK diupdate di sini — stok diupdate di method approve().
        Ini karena transfer harus melalui proses persetujuan terlebih dahulu.
        """
        if not self.nomor_transfer:
            # Generate nomor otomatis hanya jika field kosong
            self.nomor_transfer = self.generate_nomor()
        super().save(*args, **kwargs)  # Simpan ke database

    def generate_nomor(self):
        """
        Generate nomor transfer otomatis (per BULAN).

        Format: TRF/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: TRF/2024/01/0001, TRF/2024/01/0002

        Algoritma (sama dengan pola di PO/SO/EXP):
        1. Buat prefix berdasarkan tahun+bulan → 'TRF/2024/01'
        2. Cari transfer terakhir dengan prefix yang sama
        3. Increment nomor urut +1
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor transfer — contoh 'TRF/2024/01/0001'
        """
        from django.utils import timezone
        today = timezone.now()
        # Format prefix: TRF/2024/01 (per bulan)
        prefix = f"TRF/{today.year}/{today.month:02d}"

        # Cari transfer terakhir BULAN INI
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_transfer = TransferStok.objects.select_for_update().filter(
            nomor_transfer__startswith=prefix  # Filter transfer bulan ini
        ).order_by('-nomor_transfer').first()  # Ambil yang nomor terbesar

        if last_transfer:
            try:
                # Parse nomor urut dari transfer terakhir
                last_number = int(last_transfer.nomor_transfer.split('/')[-1])
                new_number = last_number + 1  # Increment
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah transfer + 1
                new_number = TransferStok.objects.filter(
                    nomor_transfer__startswith=prefix
                ).count() + 1
        else:
            new_number = 1  # Transfer pertama bulan ini

        # Format dengan zero-padding 4 digit
        # Loop untuk memastikan nomor yang dihasilkan benar-benar unik
        nomor = f"{prefix}/{new_number:04d}"
        while TransferStok.objects.filter(nomor_transfer=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor

    def approve(self, user):
        """
        Approve dan proses transfer stok antar gudang.

        Ini adalah method UTAMA yang mengubah stok. Alur:
        1. VALIDASI STATUS: Hanya transfer draft/submitted yang bisa di-approve
        2. VALIDASI STOK (TAHAP 1): Cek ketersediaan stok di gudang asal
           untuk SEMUA item sebelum memproses (all-or-nothing)
        3. PROSES TRANSFER (TAHAP 2): Untuk setiap item:
           a. Kurangi stok di gudang asal
           b. Tambah stok di gudang tujuan (buat record jika belum ada)
        4. UPDATE STATUS: Ubah status menjadi 'completed'
        5. LOG: Catat ke activity_log untuk audit trail

        Kenapa validasi terpisah dari proses?
        - TAHAP 1 memvalidasi SEMUA item terlebih dahulu
        - Jika 1 item stoknya kurang, TIDAK ADA item yang diproses
        - Ini mencegah transfer parsial (setengah jadi)

        Args:
            user: User yang melakukan approval

        Raises:
            ValueError: Jika status tidak valid
            ValueError: Jika stok tidak mencukupi di gudang asal
            ValueError: Jika produk tidak ada stok di gudang asal
        """
        # VALIDASI: Hanya bisa approve dari status draft atau submitted
        if self.status not in ['draft', 'submitted']:
            raise ValueError(f"Transfer dengan status '{self.get_status_display()}' tidak bisa diapprove")

        # Seluruh proses dalam atomic transaction + select_for_update()
        # untuk mencegah race condition saat multiple user approve bersamaan
        with transaction.atomic():
            # TAHAP 1: Validasi ketersediaan stok di gudang asal (cek semua dulu)
            # select_for_update(nowait=True) mengunci baris stok, gagal cepat jika terkunci
            for item in self.items.select_related('produk'):
                try:
                    # Lock baris stok untuk mencegah concurrent read/write
                    stok_asal = Stok.objects.select_for_update(nowait=True).get(
                        produk=item.produk, gudang=self.gudang_asal
                    )
                    # Cek apakah stok mencukupi untuk di-transfer
                    if stok_asal.jumlah < item.jumlah:
                        raise ValueError(
                            f"Stok {item.produk.nama} di {self.gudang_asal.nama} tidak mencukupi. "
                            f"Tersedia: {stok_asal.jumlah}, Dibutuhkan: {item.jumlah}"
                        )
                except Stok.DoesNotExist:
                    raise ValueError(
                        f"Stok {item.produk.nama} tidak ditemukan di {self.gudang_asal.nama}"
                    )

            # TAHAP 2: Proses transfer stok (semua telah tervalidasi)
            # Stok sudah di-lock oleh select_for_update() di atas
            for item in self.items.select_related('produk'):
                # 2a. Kurangi stok di gudang asal (sudah ter-lock)
                stok_asal = Stok.objects.select_for_update().get(
                    produk=item.produk, gudang=self.gudang_asal
                )
                stok_asal.jumlah -= item.jumlah  # Kurangi sesuai qty transfer
                stok_asal.save()  # Simpan perubahan

                # 2b. Tambah stok di gudang tujuan
                # get_or_create + select_for_update: lock baris atau buat baru
                stok_tujuan, created = Stok.objects.select_for_update().get_or_create(
                    produk=item.produk,
                    gudang=self.gudang_tujuan,
                    defaults={'jumlah': 0}     # Default jumlah 0 jika baru dibuat
                )
                stok_tujuan.jumlah += item.jumlah  # Tambah sesuai qty transfer
                stok_tujuan.save()  # Simpan perubahan

                # 2c. Update cabang produk ke gudang dengan stok terbanyak
                # Jika stok di gudang asal habis, pindahkan cabang produk
                # ke gudang yang memiliki stok paling banyak
                produk = item.produk
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak:
                    # Update cabang ke gudang dengan stok terbanyak
                    if produk.cabang != stok_terbanyak.gudang:
                        produk.cabang = stok_terbanyak.gudang
                        produk.save(update_fields=['cabang'])

            # Update status dan catat siapa yang approve
            self.status = 'completed'
            self.disetujui_oleh = user
            self.save()

        # TAHAP 3: Log ke activity_log (opsional, tidak boleh gagalkan operasi utama)
        try:
            from apps.activity_log.stock_signals import log_transfer_stock
            log_transfer_stock(self, user)
        except Exception as e:
            pass  # Jangan break operasi utama jika logging gagal


class TransferStokItem(models.Model):
    """
    Detail item yang ditransfer antar gudang.
    Setiap TransferStok memiliki 1 atau lebih item.

    Contoh: Transfer TRF/2024/01/0001 berisi:
    - 50 pcs Produk A
    - 30 kg Produk B

    Relasi:
    - FK ke TransferStok → transfer induk (parent)
    - FK ke Produk → produk yang ditransfer
    """

    # Relasi ke transfer induk — CASCADE berarti item terhapus jika transfer dihapus
    # related_name='items' → transfer.items.all() untuk mendapatkan semua item
    transfer = models.ForeignKey(
        TransferStok, on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Transfer"
    )

    # Produk yang ditransfer — PROTECT agar produk tidak bisa dihapus jika ada di transfer
    produk = models.ForeignKey(Produk, on_delete=models.PROTECT, verbose_name="Produk")

    # Jumlah yang ditransfer — Decimal untuk mendukung satuan pecahan
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Catatan opsional per item — info tambahan
    catatan = models.CharField(max_length=200, blank=True, null=True, verbose_name="Catatan")

    class Meta:
        """Konfigurasi metadata model TransferStokItem."""
        verbose_name = "Item Transfer"
        verbose_name_plural = "Item Transfer"
        indexes = [
            models.Index(fields=['produk', 'transfer'], name='inv_item_prod_trf_idx'),
        ]

    def __str__(self):
        """Representasi: 'Produk A - 50'"""
        return f"{self.produk.nama} - {self.jumlah}"


# ╔══════════════════════════════════════════════════════════════╗
# ║            ADJUSTMENT STOK (STOCK OPNAME)                     ║
# ╚══════════════════════════════════════════════════════════════╝

class AdjustmentStok(models.Model):
    """
    Model untuk PENYESUAIAN STOK (stock opname / koreksi manual).

    Kapan digunakan:
    - Barang rusak/hilang → tipe 'out' (kurangi stok)
    - Barang ditemukan/bonus → tipe 'in' (tambah stok)
    - Hasil stock opname tidak sesuai → koreksi manual

    ⚠ PENTING: Stok langsung berubah saat save() pertama!
    Tidak ada workflow approval untuk adjustment.
    """

    # Tipe adjustment: tambah atau kurang
    TIPE_CHOICES = [
        ('in', 'Penambahan'),    # Stok bertambah
        ('out', 'Pengurangan'),  # Stok berkurang
    ]

    # Nomor adjustment unik — auto-generate format: ADJ/2024/01/0001
    nomor_adjustment = models.CharField(max_length=50, unique=True, verbose_name="Nomor Adjustment")

    # Tanggal adjustment — otomatis diisi saat pertama kali dibuat
    tanggal = models.DateTimeField(auto_now_add=True, verbose_name="Tanggal")

    # Produk yang di-adjust — PROTECT agar produk tidak bisa dihapus
    produk = models.ForeignKey(Produk, on_delete=models.PROTECT, verbose_name="Produk")

    # Gudang tempat adjustment — stok di gudang mana yang berubah
    gudang = models.ForeignKey(Gudang, on_delete=models.PROTECT, verbose_name="Gudang")

    # Tipe adjustment: 'in' untuk tambah, 'out' untuk kurang
    tipe = models.CharField(max_length=10, choices=TIPE_CHOICES, verbose_name="Tipe")

    # Jumlah yang ditambah atau dikurangi
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Alasan adjustment — WAJIB diisi untuk audit trail
    # Tidak ada blank=True, artinya selalu required
    # Contoh: 'Barang rusak karena bocor', 'Hasil stock opname', 'Bonus dari supplier'
    alasan = models.TextField(verbose_name="Alasan")

    # Siapa yang membuat adjustment
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    # Timestamp pembuatan
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model AdjustmentStok."""
        verbose_name = "Adjustment Stok"           # Nama singular
        verbose_name_plural = "Adjustment Stok"    # Nama plural
        ordering = ['-dibuat_pada']                # Terbaru di atas
        indexes = [
            models.Index(fields=['tanggal', 'tipe'], name='inv_adj_tgl_tipe_idx'),
            models.Index(fields=['produk', 'gudang'], name='inv_adj_prod_gdg_idx'),
            models.Index(fields=['gudang', 'tanggal'], name='inv_adj_gdg_tgl_idx'),
        ]

    def __str__(self):
        """Representasi: 'ADJ/2024/01/0001 - Produk ABC'"""
        return f"{self.nomor_adjustment} - {self.produk.nama}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor dan update stok.

        ⚠ PENTING: Stok langsung berubah saat adjustment BARU disimpan!
        Tidak ada workflow approval untuk adjustment — perubahan langsung terjadi.

        Alur:
        1. Generate nomor adjustment jika kosong
        2. Capture stok sebelum perubahan (untuk audit log)
        3. Simpan record adjustment ke database
        4. Update stok (tambah/kurang berdasarkan tipe)
        5. Log ke activity_log

        Kenapa cek is_new?
        - Stok hanya diupdate saat CREATE (record baru)
        - Saat EDIT, stok TIDAK diupdate lagi (mencegah double update)
        """
        # Cek apakah record baru (belum pernah disimpan)
        is_new = self.pk is None

        # Auto-generate nomor adjustment
        if not self.nomor_adjustment:
            self.nomor_adjustment = self.generate_nomor()

        # Seluruh proses dalam atomic transaction untuk mencegah race condition
        with transaction.atomic():
            # Capture stok SEBELUM perubahan (untuk audit log)
            # Ini harus dilakukan SEBELUM save() dan update stok
            stok_before = 0
            if is_new:
                try:
                    # select_for_update(nowait=True) → gagal cepat jika terkunci
                    existing_stok = Stok.objects.select_for_update(nowait=True).get(
                        produk=self.produk, gudang=self.gudang
                    )
                    stok_before = existing_stok.jumlah  # Simpan jumlah stok saat ini
                except Stok.DoesNotExist:
                    stok_before = 0  # Belum ada record stok
                except OperationalError:
                    raise ValueError(
                        f"Stok {self.produk.nama} sedang diproses pengguna lain. Coba lagi."
                    )

            # Simpan record adjustment ke database
            super().save(*args, **kwargs)

            # Update stok HANYA jika record baru (hindari double update saat edit)
            if is_new:
                # get_or_create + select_for_update(nowait=True): lock baris stok
                stok, _ = Stok.objects.select_for_update(nowait=True).get_or_create(
                    produk=self.produk,
                    gudang=self.gudang,
                    defaults={'jumlah': 0}     # Default 0 jika baru dibuat
                )

                # Update jumlah stok berdasarkan tipe adjustment
                if self.tipe == 'in':
                    stok.jumlah += self.jumlah  # Tipe 'in' → Tambah stok
                else:
                    # Validasi: cegah stok negatif saat adjustment keluar
                    if stok.jumlah < self.jumlah:
                        raise ValueError(
                            f"Stok {self.produk.nama} di {self.gudang.nama} tidak mencukupi. "
                            f"Tersedia: {stok.jumlah}, Dibutuhkan: {self.jumlah}"
                        )
                    stok.jumlah -= self.jumlah  # Tipe 'out' → Kurangi stok

                stok.save()  # Simpan perubahan stok ke database

                # Update cabang produk ke gudang dengan stok terbanyak
                stok_terbanyak = Stok.objects.filter(
                    produk=self.produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak:
                    if self.produk.cabang != stok_terbanyak.gudang:
                        self.produk.cabang = stok_terbanyak.gudang
                        self.produk.save(update_fields=['cabang'])

        # Log adjustment ke activity_log (opsional, di luar atomic agar tidak rollback)
        if is_new:
            try:
                from apps.activity_log.stock_signals import log_adjustment_stock
                # Kirim stok sebelum perubahan untuk perbandingan di log
                log_adjustment_stock(self, self.dibuat_oleh, stok_before)
            except Exception as e:
                pass  # Jangan break operasi utama

    def generate_nomor(self):
        """
        Generate nomor adjustment otomatis (per BULAN).

        Format: ADJ/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: ADJ/2024/01/0001, ADJ/2024/01/0002

        Algoritma (sama dengan pola di TRF/PO/SO/EXP):
        1. Buat prefix berdasarkan tahun+bulan
        2. Cari adjustment terakhir bulan ini
        3. Increment nomor urut +1
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor adjustment — contoh 'ADJ/2024/01/0001'
        """
        from django.utils import timezone
        today = timezone.now()
        # Format prefix: ADJ/2024/01 (per bulan)
        prefix = f"ADJ/{today.year}/{today.month:02d}"

        # Cari adjustment terakhir BULAN INI
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_adj = AdjustmentStok.objects.select_for_update().filter(
            nomor_adjustment__startswith=prefix  # Filter adjustment bulan ini
        ).order_by('-nomor_adjustment').first()  # Ambil yang nomor terbesar

        if last_adj:
            try:
                # Parse nomor urut dari adjustment terakhir
                last_number = int(last_adj.nomor_adjustment.split('/')[-1])
                new_number = last_number + 1  # Increment
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah adjustment + 1
                new_number = AdjustmentStok.objects.filter(
                    nomor_adjustment__startswith=prefix
                ).count() + 1
        else:
            new_number = 1  # Adjustment pertama bulan ini

        # Format dengan zero-padding 4 digit
        # Loop untuk memastikan nomor yang dihasilkan benar-benar unik
        nomor = f"{prefix}/{new_number:04d}"
        while AdjustmentStok.objects.filter(nomor_adjustment=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor
