"""
==========================================================================
 PENJUALAN MODELS - Sales Order (SO) & Customer
==========================================================================
 File ini berisi 3 model untuk manajemen penjualan:

 1. Customer → Data pelanggan
 2. SalesOrder → Dokumen penjualan barang
 3. SalesOrderItem → Detail produk dalam SO

 ALUR SALES ORDER:
 ┌──────┐   ┌────────────┐   ┌──────────┐   ┌──────────┐
 │Draft │──→│ Confirmed  │──→│ Delivered│──→│ Completed│
 └──────┘   └────────────┘   └──────────┘   └──────────┘
                  │
             Kurangi Stok (-)

 Saat confirm_order:
 1. Validasi status harus 'draft'
 2. Validasi stok cukup di gudang
 3. Kurangi stok untuk setiap item
 4. Log ke activity_log

 Koneksi:
 - apps/produk/models.py → Produk, Gudang, Stok
 - apps/activity_log/stock_signals.py → log_sales_stock_out()
==========================================================================
"""

from decimal import Decimal

from django.db import models, transaction    # Django ORM + atomic transaction
from django.contrib.auth.models import User  # Model User bawaan Django (akun login)
from apps.produk.models import Produk, Gudang, Stok  # Import model dari modul Produk untuk relasi FK


class Customer(models.Model):
    """
    Model untuk DATA PELANGGAN / customer.

    Contoh data:
    | kode   | nama           | telepon     |
    |--------|----------------|-------------|
    | CUS-01 | Toko Sejahtera | 08123456789 |
    | CUS-02 | CV Makmur      | 08234567890 |
    """
    # Kode unik pelanggan — contoh: 'CUS-01', 'CUS-TOKO-JAYA'
    # unique=True memastikan tidak ada duplikat kode customer
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Customer")

    # Nama lengkap pelanggan/perusahaan — contoh: 'Toko Sejahtera'
    nama = models.CharField(max_length=200, verbose_name="Nama Customer")

    # Nomor telepon pelanggan — untuk komunikasi & pengiriman
    telepon = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telepon")

    # Email pelanggan — EmailField otomatis validasi format email
    email = models.EmailField(blank=True, null=True, verbose_name="Email")

    # Alamat lengkap — textarea untuk alamat pengiriman
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")

    # Flag aktif — customer nonaktif tidak muncul di dropdown saat buat SO
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model Customer."""
        verbose_name = "Customer"          # Nama singular
        verbose_name_plural = "Customers"  # Nama plural
        ordering = ['nama']                # Urutan default A-Z
        indexes = [
            models.Index(fields=['aktif', 'nama'], name='sales_cust_aktif_idx'),
        ]

    def __str__(self):
        """Representasi: 'CUS-01 - Toko Sejahtera'"""
        return f"{self.kode} - {self.nama}"


class SalesOrder(models.Model):
    """
    Model untuk SALES ORDER (SO) — dokumen penjualan barang.

    Setiap SO memiliki:
    - Nomor unik (auto-generate: SO/2024/01/0001)
    - Customer (jual ke siapa)
    - Gudang sumber (stok diambil dari gudang mana)
    - Status workflow (draft → confirmed → delivered → completed)
    - Items (daftar produk yang dijual)
    - Diskon dan pajak

    Perbedaan dengan POS:
    - SO = penjualan B2B (bisnis ke bisnis), ada workflow
    - POS = penjualan retail (langsung bayar, langsung potong stok)
    """

    # ===== STATUS WORKFLOW =====
    # Alur: draft → confirmed (stok berkurang) → delivered → completed
    STATUS_CHOICES = [
        ('draft', 'Draft'),              # Baru dibuat, belum dikonfirmasi
        ('confirmed', 'Dikonfirmasi'),   # Stok sudah dikurangi dari gudang
        ('delivered', 'Dikirim'),         # Barang sedang dikirim ke customer
        ('completed', 'Selesai'),        # Transaksi selesai (barang sampai)
        ('cancelled', 'Dibatalkan'),     # SO dibatalkan
    ]

    # ===== IDENTITAS SO =====
    # Nomor SO unik — auto-generate format: SO/2024/01/0001
    nomor_so = models.CharField(max_length=50, unique=True, verbose_name="Nomor SO")

    # Tanggal SO — DateTimeField yang bisa diedit user
    tanggal = models.DateTimeField(verbose_name="Tanggal")

    # ===== RELASI =====
    # Customer — pelanggan yang membeli (WAJIB, berbeda dengan POS yang opsional)
    # on_delete=PROTECT → customer tidak bisa dihapus jika masih ada SO
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_orders', verbose_name="Customer")

    # Gudang sumber — stok diambil dari gudang mana
    gudang = models.ForeignKey(Gudang, on_delete=models.PROTECT, related_name='sales_orders', verbose_name="Gudang")

    # Status workflow SO
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    # ===== KOMPONEN HARGA =====
    # subtotal = jumlah semua item sebelum diskon/pajak
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")
    # diskon = potongan harga keseluruhan SO
    diskon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Diskon")
    # pajak = PPN atau pajak lainnya
    pajak = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Pajak")
    # biaya_pengiriman = ongkir/biaya kirim yang ditagihkan ke customer
    biaya_pengiriman = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Biaya Pengiriman/Ongkir")
    # total = subtotal - diskon + biaya_pengiriman + pajak (dihitung otomatis)
    total_harga = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total Harga")

    # Catatan opsional — info tambahan
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    # Siapa yang membuat SO ini
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='so_dibuat')

    # ===== METODE PEMBAYARAN =====
    # FK ke MetodePembayaran di modul POS — untuk tracking pembayaran SO
    # Saat SO dikonfirmasi/selesai, nominal masuk ke saldo metode pembayaran ini
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',          # String reference ke model di app 'pos'
        on_delete=models.SET_NULL,       # Metode dihapus → SO tetap ada
        null=True, blank=True,
        related_name='sales_orders',     # metode.sales_orders.all()
        verbose_name="Metode Pembayaran"
    )

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model SalesOrder."""
        verbose_name = "Sales Order"           # Nama singular
        verbose_name_plural = "Sales Orders"   # Nama plural
        ordering = ['-dibuat_pada']            # Terbaru di atas
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='sales_so_tgl_status_idx'),
            models.Index(fields=['customer', 'status'], name='sales_so_cust_status_idx'),
            models.Index(fields=['gudang', 'tanggal'], name='sales_so_gdg_tgl_idx'),
            models.Index(fields=['metode_pembayaran', 'status'], name='sales_so_pay_status_idx'),
        ]

    # ===== STATE MACHINE =====
    # Transisi status yang valid — digunakan oleh transition_status()
    VALID_TRANSITIONS = {
        'draft': ['confirmed', 'cancelled'],
        'confirmed': ['delivered', 'cancelled'],
        'delivered': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
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
        """Representasi: 'SO/2024/01/0001 - Toko Sejahtera'"""
        return f"{self.nomor_so} - {self.customer.nama}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor SO dan hitung total.

        Alur:
        1. Cek apakah record baru atau update
        2. Auto-generate nomor SO jika field kosong
        3. Set tanggal default ke sekarang untuk SO baru
        4. Hitung total hanya saat update (items belum ada saat create)
        5. Simpan ke database
        """
        from django.utils import timezone
        is_new = self.pk is None  # Cek apakah ini SO baru

        # Auto-generate nomor SO hanya jika field kosong
        if not self.nomor_so:
            self.nomor_so = self.generate_nomor()

        # Set tanggal default untuk SO baru
        if is_new and not self.tanggal:
            self.tanggal = timezone.now()

        # Hitung total hanya saat update (SO sudah punya items)
        if not is_new:
            self.calculate_total()

        super().save(*args, **kwargs)  # Simpan ke database

    def generate_nomor(self):
        """
        Generate nomor SO otomatis (per BULAN).

        Format: SO/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: SO/2024/01/0001, SO/2024/01/0002

        Algoritma:
        1. Buat prefix berdasarkan tahun+bulan → 'SO/2024/01'
        2. Cari SO terakhir dengan prefix yang sama
        3. Increment nomor urut +1
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor SO — contoh 'SO/2024/01/0001'
        """
        from datetime import datetime
        today = datetime.now()
        # Format prefix: SO/2024/01 (per bulan)
        prefix = f"SO/{today.year}/{today.month:02d}"

        # Cari SO terakhir BULAN INI
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_so = SalesOrder.objects.select_for_update().filter(
            nomor_so__startswith=prefix     # Filter SO bulan ini
        ).order_by('-nomor_so').first()     # Ambil yang nomor terbesar

        if last_so:
            try:
                # Parse nomor urut dari SO terakhir
                last_number = int(last_so.nomor_so.split('/')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah SO + 1
                new_number = SalesOrder.objects.filter(
                    nomor_so__startswith=prefix
                ).count() + 1
        else:
            new_number = 1

        # Format dengan zero-padding 4 digit
        # Loop untuk memastikan nomor yang dihasilkan benar-benar unik
        nomor = f"{prefix}/{new_number:04d}"
        while SalesOrder.objects.filter(nomor_so=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor

    def calculate_total(self):
        """
        Hitung total harga SO dari semua items.

        Formula: total_harga = subtotal - diskon + biaya_pengiriman + pajak
        (Berbeda dengan PO yang tidak ada diskon)

        Catatan: Method ini TIDAK memanggil save() — hanya mengubah field di memory.
        """
        # Hitung subtotal dari semua item SO
        self.subtotal = sum(item.subtotal for item in self.items.all())
        if self.diskon > self.subtotal:
            self.diskon = self.subtotal
        # Total = subtotal - diskon + ongkir + pajak
        self.total_harga = self.subtotal - self.diskon + self.biaya_pengiriman + self.pajak

    @property
    def dpp_pajak(self):
        """Dasar pengenaan pajak SO: subtotal setelah diskon plus ongkir."""
        return max(
            (self.subtotal or Decimal('0')) - (self.diskon or Decimal('0')) + (self.biaya_pengiriman or Decimal('0')),
            Decimal('0')
        )

    @property
    def nilai_pajak(self):
        """Nilai pajak dalam Rupiah."""
        return self.pajak or Decimal('0')

    def confirm_order(self, user=None):
        """
        Konfirmasi order — kurangi stok dari gudang sumber.

        Alur:
        1. VALIDASI STATUS: Hanya SO dengan status 'draft' yang bisa dikonfirmasi
        2. VALIDASI STOK: Cek ketersediaan stok untuk SETIAP item
        3. PROSES: Kurangi stok di gudang untuk setiap item
        4. UPDATE STATUS: Ubah status SO menjadi 'confirmed'
        5. LOG: Catat ke activity_log untuk audit trail

        Args:
            user: User yang melakukan konfirmasi (opsional, untuk logging)

        Raises:
            ValueError: Jika status bukan 'draft'
            ValueError: Jika stok tidak mencukupi untuk salah satu item
            ValueError: Jika produk tidak ada stok di gudang yang dipilih

        PENTING: Berbeda dengan POS yang langsung potong stok,
        SO memvalidasi ketersediaan stok terlebih dahulu!
        """
        # LANGKAH 1: Validasi status
        if self.status != 'draft':
            raise ValueError("Hanya order dengan status Draft yang bisa dikonfirmasi")

        # Seluruh proses dalam atomic transaction + select_for_update()
        # untuk mencegah race condition saat multiple user confirm bersamaan
        with transaction.atomic():
            # LANGKAH 2 & 3: Validasi dan kurangi stok (dalam satu atomic block)
            for item in self.items.select_related('produk'):
                try:
                    # Lock baris stok untuk mencegah concurrent read/write
                    stok = Stok.objects.select_for_update().get(
                        produk=item.produk, gudang=self.gudang
                    )

                    # Gunakan jumlah_konversi (dalam satuan dasar) untuk stok
                    qty_stok = item.jumlah_konversi if item.jumlah_konversi else item.jumlah

                    # Cek apakah stok mencukupi
                    if stok.jumlah < qty_stok:
                        raise ValueError(f"Stok {item.produk.nama} tidak mencukupi")

                    # Kurangi stok sesuai quantity dalam satuan dasar
                    stok.jumlah -= qty_stok
                    stok.save()  # Simpan perubahan stok

                    # Update cabang produk ke gudang dengan stok terbanyak
                    stok_terbanyak = Stok.objects.filter(
                        produk=item.produk, jumlah__gt=0
                    ).order_by('-jumlah').first()

                    if stok_terbanyak and item.produk.cabang != stok_terbanyak.gudang:
                        item.produk.cabang = stok_terbanyak.gudang
                        item.produk.save(update_fields=['cabang'])

                except Stok.DoesNotExist:
                    # Produk tidak punya record stok di gudang ini
                    raise ValueError(f"Stok {item.produk.nama} tidak ditemukan di gudang {self.gudang.nama}")

            # LANGKAH 4: Update status menjadi 'confirmed'
            self.status = 'confirmed'
            self.save()

        # LANGKAH 5: Log stok keluar (opsional, di luar atomic agar tidak rollback)
        if user:
            try:
                from apps.activity_log.stock_signals import log_sales_stock_out
                log_sales_stock_out(self, user)
            except Exception as e:
                pass  # Jangan break operasi utama


class SalesOrderItem(models.Model):
    """
    Model untuk DETAIL ITEM dalam Sales Order.

    Setiap SO memiliki 1 atau lebih item (produk yang dijual).
    Subtotal per item = (jumlah × harga_satuan) - diskon.

    Contoh:
    | produk        | jumlah | harga_satuan | diskon | subtotal |
    |---------------|--------|--------------|--------|----------|
    | Laptop Asus   | 2      | 8,000,000    | 500,000| 15,500,000|
    | Mouse Logi    | 5      | 150,000      | 0      | 750,000  |

    Relasi:
    - FK ke SalesOrder → SO induk (parent)
    - FK ke Produk → produk yang dijual
    """

    # Relasi ke SO induk — CASCADE berarti item terhapus jika SO dihapus
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items', verbose_name="Sales Order")

    # Produk yang dijual — PROTECT agar produk tidak bisa dihapus jika ada di SO
    produk = models.ForeignKey(Produk, on_delete=models.PROTECT, verbose_name="Produk")

    # Jumlah yang dijual — Decimal untuk mendukung satuan pecahan
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Harga per unit saat transaksi — disimpan terpisah agar tidak berubah
    harga_satuan = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Harga Satuan")

    # Diskon per item — potongan harga untuk item ini
    diskon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Diskon")

    # Subtotal per item — dihitung otomatis: (jumlah × harga_satuan) - diskon
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")

    # Satuan transaksi — satuan yang digunakan saat transaksi (bisa berbeda dari satuan produk)
    satuan_transaksi = models.ForeignKey(
        'produk.Satuan', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Satuan Transaksi",
        help_text="Kosongkan jika menggunakan satuan asli produk"
    )

    # Jumlah setelah konversi ke satuan dasar produk
    jumlah_konversi = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        verbose_name="Jumlah (Satuan Dasar)",
        help_text="Jumlah dalam satuan dasar produk, dihitung otomatis"
    )

    # Snapshot HPP saat transaksi dibuat agar laporan lama tidak berubah
    hpp_satuan = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="HPP Satuan"
    )
    hpp_subtotal = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Subtotal HPP"
    )

    # Catatan opsional per item
    catatan = models.CharField(max_length=200, blank=True, null=True, verbose_name="Catatan")

    class Meta:
        """Konfigurasi metadata model SalesOrderItem."""
        verbose_name = "Item SO"
        verbose_name_plural = "Item SO"
        indexes = [
            models.Index(fields=['produk', 'sales_order'], name='sales_item_prod_so_idx'),
        ]

    def __str__(self):
        """Representasi: 'Laptop Asus - 2'"""
        return f"{self.produk.nama} - {self.jumlah}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-calculate subtotal, jumlah_konversi, dan update total SO.
        """
        # LANGKAH 1: Hitung subtotal per item
        self.subtotal = (self.jumlah * self.harga_satuan) - self.diskon

        # LANGKAH 2: Hitung jumlah_konversi jika satuan transaksi berbeda
        if self.satuan_transaksi and self.produk and self.satuan_transaksi != self.produk.satuan:
            from apps.produk.models import KonversiSatuan
            satuan_produk = self.produk.satuan
            satuan_trx = self.satuan_transaksi

            # Cari konversi: dari satuan produk ke satuan transaksi
            konversi = KonversiSatuan.objects.filter(
                dari_satuan=satuan_produk, ke_satuan=satuan_trx, produk=self.produk
            ).first() or KonversiSatuan.objects.filter(
                dari_satuan=satuan_produk, ke_satuan=satuan_trx, produk__isnull=True
            ).first()

            if konversi:
                self.jumlah_konversi = self.jumlah / konversi.faktor_konversi
            else:
                # Arah sebaliknya
                konversi_balik = KonversiSatuan.objects.filter(
                    dari_satuan=satuan_trx, ke_satuan=satuan_produk, produk=self.produk
                ).first() or KonversiSatuan.objects.filter(
                    dari_satuan=satuan_trx, ke_satuan=satuan_produk, produk__isnull=True
                ).first()
                if konversi_balik:
                    self.jumlah_konversi = self.jumlah * konversi_balik.faktor_konversi
                else:
                    self.jumlah_konversi = self.jumlah
        else:
            self.jumlah_konversi = self.jumlah

        qty_stok = self.jumlah_konversi or self.jumlah
        if self.produk_id and self.hpp_satuan == Decimal('0'):
            self.hpp_satuan = self.produk.harga_beli or Decimal('0')
        self.hpp_subtotal = qty_stok * (self.hpp_satuan or Decimal('0'))

        # LANGKAH 3: Simpan item ke database
        super().save(*args, **kwargs)

        # LANGKAH 4: Update total SO induk
        if self.sales_order_id:
            self.sales_order.calculate_total()
            self.sales_order.save()
