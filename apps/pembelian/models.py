"""
==========================================================================
 PEMBELIAN MODELS - Purchase Order (PO) & Supplier
==========================================================================
 File ini berisi 3 model untuk manajemen pembelian barang:

 1. Supplier → Data pemasok/vendor
 2. PurchaseOrder → Dokumen pembelian barang
 3. PurchaseOrderItem → Detail produk dalam PO

 ALUR PURCHASE ORDER:
 ┌──────┐   ┌───────────┐   ┌──────────┐   ┌──────────┐
 │Draft │──→│ Submitted │──→│ Approved │──→│ Received │
 └──────┘   └───────────┘   └──────────┘   └──────────┘
                                                │
                                           Update Stok (+)

 Saat status → 'received' (receive_goods):
 1. Validasi status harus 'approved'
 2. Tambah stok di gudang tujuan untuk setiap item
 3. Log ke activity_log

 Koneksi:
 - apps/produk/models.py → Produk, Gudang, Stok
 - apps/pos/models.py → MetodePembayaran (FK untuk pembayaran PO)
 - apps/activity_log/stock_signals.py → log_purchase_stock_in()
 - apps/pembelian/views.py → View CRUD untuk PO
==========================================================================
"""

from django.db import models, transaction   # Django ORM + atomic transaction
from django.contrib.auth.models import User  # Model User bawaan
from apps.produk.models import Produk, Gudang, Stok  # Model master produk


class Supplier(models.Model):
    """
    Model untuk DATA SUPPLIER / pemasok barang.

    Contoh data:
    | kode   | nama            | kontak     | telepon      |
    |--------|-----------------|------------|--------------|
    | SUP-01 | PT Maju Jaya    | Budi       | 08123456789  |
    | SUP-02 | CV Sentosa      | Andi       | 08234567890  |
    """
    # Kode unik supplier — contoh: 'SUP-01', 'SUP-JAYA'
    # unique=True memastikan tidak ada duplikat kode supplier
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode Supplier")

    # Nama lengkap supplier/vendor — contoh: 'PT Maju Jaya'
    nama = models.CharField(max_length=200, verbose_name="Nama Supplier")

    # Contact person — nama orang yang bisa dihubungi di perusahaan supplier
    kontak = models.CharField(max_length=100, blank=True, null=True, verbose_name="Kontak Person")

    # Nomor telepon supplier — untuk komunikasi order/pengiriman
    telepon = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telepon")

    # Email supplier — untuk kirim PO atau korespondensi
    # EmailField secara otomatis memvalidasi format email
    email = models.EmailField(blank=True, null=True, verbose_name="Email")

    # Alamat lengkap supplier — textarea untuk alamat panjang
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")

    # Flag aktif — supplier nonaktif tidak muncul di dropdown saat buat PO
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model Supplier."""
        verbose_name = "Supplier"          # Nama singular
        verbose_name_plural = "Supplier"   # Nama plural
        ordering = ['nama']                # Urutan default A-Z
        indexes = [
            models.Index(fields=['aktif', 'nama'], name='purch_sup_aktif_idx'),
        ]

    def __str__(self):
        """Representasi: 'SUP-01 - PT Maju Jaya'"""
        return f"{self.kode} - {self.nama}"


class PurchaseOrder(models.Model):
    """
    Model untuk PURCHASE ORDER (PO) — dokumen pembelian barang.

    Setiap PO memiliki:
    - Nomor unik (auto-generate: PO/2024/01/0001)
    - Supplier (dari mana beli)
    - Gudang tujuan (barang masuk ke gudang mana)
    - Status workflow (draft → submitted → approved → received)
    - Items (daftar produk yang dibeli)
    - Metode pembayaran (Cash, Transfer, dll)

    Property:
    - grand_total → subtotal + pajak
    - nilai_pajak → total_harga - subtotal
    """

    # ===== STATUS WORKFLOW =====
    # Alur: draft → submitted → approved → received (stok bertambah)
    STATUS_CHOICES = [
        ('draft', 'Draft'),              # Baru dibuat, belum diajukan
        ('submitted', 'Diajukan'),       # Sudah diajukan untuk persetujuan
        ('approved', 'Disetujui'),       # Disetujui manager
        ('received', 'Diterima'),        # Barang sudah diterima di gudang → stok bertambah
        ('cancelled', 'Dibatalkan'),     # PO dibatalkan
    ]

    # ===== IDENTITAS PO =====
    # Nomor PO unik — auto-generate format: PO/2024/01/0001
    nomor_po = models.CharField(max_length=50, unique=True, verbose_name="Nomor PO")

    # Tanggal PO — DateTimeField yang bisa diedit user (bukan auto_now_add)
    # Ini berbeda dari POS yang tanggalnya otomatis saat create
    tanggal = models.DateTimeField(verbose_name="Tanggal")

    # ===== RELASI =====
    # Supplier — dari mana barang dibeli
    # on_delete=PROTECT → supplier tidak bisa dihapus jika masih ada PO
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders', verbose_name="Supplier")

    # Gudang tujuan — barang akan masuk ke gudang mana
    gudang = models.ForeignKey(Gudang, on_delete=models.PROTECT, related_name='purchase_orders', verbose_name="Gudang Tujuan")

    # Status workflow PO
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    # ===== KOMPONEN HARGA =====
    # subtotal = jumlah semua item sebelum pajak
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")
    # pajak = PPN atau pajak lainnya (bisa diisi manual)
    pajak = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Pajak")
    # biaya_pengiriman = ongkir/biaya kirim dari supplier/ekspedisi
    biaya_pengiriman = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Biaya Pengiriman/Ongkir")
    # total = subtotal + biaya_pengiriman + pajak (dihitung otomatis)
    total_harga = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total Harga")

    # Catatan opsional — info tambahan untuk supplier atau internal
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    # ===== TRACKING PENGGUNA =====
    # Siapa yang membuat PO ini
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='po_dibuat')
    # Siapa yang menyetujui PO ini (diisi saat approve)
    disetujui_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='po_disetujui')

    # ===== METODE PEMBAYARAN =====
    # FK ke MetodePembayaran di modul POS — cross-module relation
    # Tracking pembayaran PO dilakukan lewat metode mana (Cash/Transfer)
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran',          # String reference ke model di app 'pos'
        on_delete=models.SET_NULL,       # Metode dihapus → PO tetap ada
        null=True, blank=True,
        related_name='purchase_orders',  # metode.purchase_orders.all()
        verbose_name="Metode Pembayaran"
    )

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model PurchaseOrder."""
        verbose_name = "Purchase Order"            # Nama singular
        verbose_name_plural = "Purchase Orders"    # Nama plural
        ordering = ['-dibuat_pada']                # Terbaru di atas
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='purch_po_tgl_status_idx'),
            models.Index(fields=['supplier', 'status'], name='purch_po_sup_status_idx'),
            models.Index(fields=['gudang', 'tanggal'], name='purch_po_gdg_tgl_idx'),
            models.Index(fields=['metode_pembayaran', 'status'], name='purch_po_pay_status_idx'),
        ]

    # ===== STATE MACHINE =====
    # Transisi status yang valid — digunakan oleh transition_status()
    VALID_TRANSITIONS = {
        'draft': ['submitted', 'cancelled'],
        'submitted': ['approved', 'cancelled'],
        'approved': ['received', 'cancelled'],
        'received': ['cancelled'],
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
        """Representasi: 'PO/2024/01/0001 - PT Maju Jaya'"""
        return f"{self.nomor_po} - {self.supplier.nama}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor PO dan hitung total.

        Alur:
        1. Cek apakah record baru atau update
        2. Auto-generate nomor PO jika field kosong
        3. Set tanggal default ke sekarang untuk PO baru (jika belum diisi)
        4. Hitung total hanya saat update (bukan create, karena items belum ada)
        5. Simpan ke database
        """
        from django.utils import timezone
        is_new = self.pk is None  # Cek apakah ini PO baru

        # Auto-generate nomor PO hanya jika field kosong
        if not self.nomor_po:
            self.nomor_po = self.generate_nomor()

        # Set tanggal default untuk PO baru yang belum punya tanggal
        # Menggunakan timezone.now() agar aware timezone (bukan datetime.now())
        if is_new and not self.tanggal:
            self.tanggal = timezone.now()

        # Hitung total hanya saat update (PO sudah punya items)
        # Saat create pertama kali, items belum ada → skip calculate
        if not is_new:
            self.calculate_total()

        super().save(*args, **kwargs)  # Simpan ke database

    def generate_nomor(self):
        """
        Generate nomor PO otomatis (per BULAN).

        Format: PO/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: PO/2024/01/0001, PO/2024/01/0002

        Algoritma:
        1. Buat prefix berdasarkan tahun+bulan → 'PO/2024/01'
        2. Cari PO terakhir dengan prefix yang sama
        3. Increment nomor urut +1
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor PO — contoh 'PO/2024/01/0001'
        """
        from datetime import datetime
        today = datetime.now()
        # Format prefix: PO/2024/01 (per bulan)
        prefix = f"PO/{today.year}/{today.month:02d}"

        # Cari PO terakhir BULAN INI
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_po = PurchaseOrder.objects.select_for_update().filter(
            nomor_po__startswith=prefix     # Filter PO bulan ini
        ).order_by('-nomor_po').first()     # Ambil yang nomor terbesar

        if last_po:
            try:
                # Parse nomor urut dari PO terakhir
                # Contoh: 'PO/2024/01/0005'.split('/') → [-1] = '0005' → int = 5
                last_number = int(last_po.nomor_po.split('/')[-1])
                new_number = last_number + 1  # Increment: 5 → 6
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah PO + 1
                new_number = PurchaseOrder.objects.filter(
                    nomor_po__startswith=prefix
                ).count() + 1
        else:
            new_number = 1  # PO pertama bulan ini

        # Format dengan zero-padding 4 digit: 1 → '0001'
        # Loop untuk memastikan nomor yang dihasilkan benar-benar unik
        nomor = f"{prefix}/{new_number:04d}"
        while PurchaseOrder.objects.filter(nomor_po=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor

    def calculate_total(self):
        """
        Hitung total harga PO dari semua items.

        Formula: total_harga = subtotal + biaya_pengiriman + pajak
        (Berbeda dengan SO/POS yang punya diskon, PO tidak ada diskon)

        Catatan: Method ini TIDAK memanggil save() — hanya mengubah field di memory.
        """
        # Hitung subtotal dari semua item PO
        self.subtotal = sum(item.subtotal for item in self.items.all())
        # Total = subtotal + ongkir + pajak (PO tidak ada diskon keseluruhan)
        self.total_harga = self.subtotal + self.biaya_pengiriman + self.pajak

    @property
    def grand_total(self):
        """
        Property alias untuk total_harga.
        Digunakan di template: {{ po.grand_total }}

        Return: Decimal — total harga termasuk pajak
        """
        return self.total_harga

    @property
    def nilai_pajak(self):
        """
        Property untuk menghitung nilai pajak dalam Rupiah.
        Selisih antara total harga dan subtotal.

        Return: Decimal — nilai pajak (contoh: Rp 1.100.000)
        """
        from decimal import Decimal
        return self.pajak or Decimal('0')

    @property
    def dpp_pajak(self):
        """Dasar pengenaan pajak PO: subtotal plus ongkir."""
        from decimal import Decimal
        return (self.subtotal or Decimal('0')) + (self.biaya_pengiriman or Decimal('0'))

    def receive_goods(self, user):
        """
        Terima barang — update stok di gudang tujuan saat barang tiba.

        Alur:
        1. VALIDASI: Status harus 'approved' (sudah disetujui)
        2. PROSES: Untuk setiap item PO:
           a. Cari/buat record stok (produk + gudang tujuan)
           b. Tambah jumlah stok sesuai qty yang diterima
        3. UPDATE: Ubah status PO menjadi 'received'
        4. LOG: Catat ke activity_log untuk audit trail

        Args:
            user: User yang melakukan penerimaan barang

        Raises:
            ValueError: Jika PO belum disetujui (status ≠ 'approved')

        Contoh:
        - PO berisi 100 pcs Produk A
        - Gudang tujuan = Gudang Utama
        - Setelah receive: Stok Produk A di Gudang Utama +100
        """
        # LANGKAH 1: Validasi status
        if self.status != 'approved':
            raise ValueError("PO harus disetujui terlebih dahulu")

        # Seluruh proses dalam atomic transaction + select_for_update()
        # untuk mencegah race condition saat multiple user receive bersamaan
        with transaction.atomic():
            # LANGKAH 2: Tambah stok untuk setiap item PO
            for item in self.items.select_related('produk'):
                # Lock baris stok untuk mencegah concurrent write
                stok, _ = Stok.objects.select_for_update().get_or_create(
                    produk=item.produk,
                    gudang=self.gudang,
                    defaults={'jumlah': 0}
                )
                # Gunakan jumlah_konversi (satuan dasar) untuk update stok
                qty_stok = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
                stok.jumlah += qty_stok
                stok.save()

                # Update cabang produk ke gudang dengan stok terbanyak
                produk = item.produk
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                    produk.cabang = stok_terbanyak.gudang
                    produk.save(update_fields=['cabang'])

            # LANGKAH 3: Update status PO menjadi 'received'
            self.status = 'received'
            self.save()

        # LANGKAH 4: Log stok masuk ke activity_log (opsional)
        # Try-except agar error di logging tidak menggagalkan operasi utama
        try:
            from apps.activity_log.stock_signals import log_purchase_stock_in
            log_purchase_stock_in(self, user)
        except Exception as e:
            pass  # Jangan break operasi utama jika logging gagal


class PurchaseOrderItem(models.Model):
    """
    Model untuk DETAIL ITEM dalam Purchase Order.

    Setiap PO memiliki 1 atau lebih item (produk yang dibeli).
    Subtotal dihitung otomatis: jumlah × harga_satuan.
    Saat item disimpan, total PO induk otomatis di-update.

    Contoh:
    | produk           | jumlah | harga_satuan | subtotal   |
    |------------------|--------|--------------|------------|
    | Indomie Goreng   | 100    | 2,800        | 280,000    |
    | Aqua 600ml       | 50     | 3,500        | 175,000    |

    Relasi:
    - FK ke PurchaseOrder → PO induk (parent)
    - FK ke Produk → produk yang dibeli
    """

    # Relasi ke PO induk — CASCADE berarti item terhapus jika PO dihapus
    # related_name='items' → po.items.all() untuk mendapatkan semua item
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items', verbose_name="Purchase Order")

    # Produk yang dibeli — PROTECT agar produk tidak bisa dihapus jika ada di PO
    produk = models.ForeignKey(Produk, on_delete=models.PROTECT, verbose_name="Produk")

    # Jumlah yang dibeli — Decimal untuk mendukung satuan pecahan
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Harga per unit — harga beli dari supplier
    harga_satuan = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Harga Satuan")

    # Subtotal per item — dihitung otomatis: jumlah × harga_satuan
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")

    # Satuan transaksi — satuan yang digunakan saat PO (bisa berbeda dari satuan produk)
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

    # Catatan opsional per item
    catatan = models.CharField(max_length=200, blank=True, null=True, verbose_name="Catatan")

    class Meta:
        """Konfigurasi metadata model PurchaseOrderItem."""
        verbose_name = "Item PO"
        verbose_name_plural = "Item PO"
        indexes = [
            models.Index(fields=['produk', 'purchase_order'], name='purch_item_prod_po_idx'),
        ]

    def __str__(self):
        """Representasi: 'Indomie Goreng - 100'"""
        return f"{self.produk.nama} - {self.jumlah}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-calculate subtotal, jumlah_konversi, dan update total PO.
        """
        # LANGKAH 1: Hitung subtotal (qty × harga)
        self.subtotal = self.jumlah * self.harga_satuan

        # LANGKAH 2: Hitung jumlah_konversi jika satuan transaksi berbeda
        if self.satuan_transaksi and self.produk and self.satuan_transaksi != self.produk.satuan:
            from apps.produk.models import KonversiSatuan
            satuan_produk = self.produk.satuan
            satuan_trx = self.satuan_transaksi

            konversi = KonversiSatuan.objects.filter(
                dari_satuan=satuan_produk, ke_satuan=satuan_trx, produk=self.produk
            ).first() or KonversiSatuan.objects.filter(
                dari_satuan=satuan_produk, ke_satuan=satuan_trx, produk__isnull=True
            ).first()

            if konversi:
                self.jumlah_konversi = self.jumlah / konversi.faktor_konversi
            else:
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

        # LANGKAH 3: Simpan item ke database
        super().save(*args, **kwargs)

        # LANGKAH 4: Update total PO induk
        if self.purchase_order_id:
            self.purchase_order.calculate_total()
            self.purchase_order.save()
