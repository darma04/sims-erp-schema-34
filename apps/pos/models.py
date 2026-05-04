"""
==========================================================================
 POS MODELS - Point of Sale (Kasir) & Metode Pembayaran
==========================================================================
 File ini berisi 3 model untuk modul POS (Point of Sale):

 1. MetodePembayaran → Cara bayar (Cash, Transfer, QRIS, dll)
 2. POSTransaction → Transaksi penjualan kasir
 3. POSTransactionItem → Detail produk dalam transaksi

 ALUR POS (berbeda dengan SO — lebih sederhana):
 Kasir pilih produk → Input pembayaran → Simpan transaksi → Stok berkurang

 Perbedaan POS vs Sales Order (SO):
 ┌─────────────┬────────────────────┬────────────────────┐
 │             │ POS                │ Sales Order (SO)   │
 ├─────────────┼────────────────────┼────────────────────┤
 │ Tipe        │ B2C (retail)       │ B2B (grosir)       │
 │ Workflow    │ Langsung (1 step)  │ Multi-step         │
 │ Stok        │ Langsung dikurangi │ Dikurangi saat     │
 │             │                    │ confirm             │
 │ Pembayaran  │ Langsung           │ Bisa bertahap      │
 │ Customer    │ Opsional (walk-in) │ Wajib              │
 └─────────────┴────────────────────┴────────────────────┘

 Koneksi:
 - apps/produk/models.py → Produk, Gudang, Stok
 - apps/pembelian/models.py → PO juga pakai MetodePembayaran
 - apps/biaya/models.py → TransaksiBiaya juga pakai MetodePembayaran
 - apps/pos/views.py → View untuk halaman kasir
==========================================================================
"""

from django.db import models, transaction    # Django ORM + atomic transaction
from django.contrib.auth.models import User  # Model User bawaan Django (akun login)
from apps.produk.models import Produk, Gudang, Stok  # Import model dari modul Produk untuk relasi FK


class MetodePembayaran(models.Model):
    """
    Model untuk METODE PEMBAYARAN.

    Contoh data:
    | kode  | nama          | saldo        |
    |-------|---------------|--------------|
    | CASH  | Tunai         | 5,000,000    |
    | TRF   | Transfer Bank | 10,000,000   |
    | QRIS  | QRIS          | 2,000,000    |

    Model ini digunakan oleh:
    - POSTransaction → Pembayaran kasir
    - PurchaseOrder → Pembayaran PO ke supplier
    - TransaksiBiaya → Pembayaran biaya operasional
    """
    # Nama metode pembayaran yang ditampilkan di UI kasir — contoh: 'Tunai', 'Transfer Bank'
    nama = models.CharField(max_length=50, verbose_name="Nama Metode")

    # Nama pemilik rekening/akun — contoh: 'PT ABC', 'John Doe'
    nama_pemilik = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nama Pemilik")

    # Kode unik metode — digunakan sebagai identifier teknis
    # unique=True memastikan tidak ada duplikat — contoh: 'CASH', 'TRF', 'QRIS'
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode")

    # Deskripsi opsional — info tambahan tentang metode pembayaran
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # Gambar/logo metode pembayaran — ditampilkan di halaman kasir POS
    # Disimpan di MEDIA_ROOT/metode_pembayaran/ (contoh: qris_logo.png)
    gambar = models.ImageField(upload_to='metode_pembayaran/', blank=True, null=True, verbose_name="Gambar")

    # Saldo metode pembayaran — untuk tracking saldo kas/rekening
    # Contoh: Cash = 5jt, Bank BCA = 10jt
    # Diupdate otomatis saat ada transaksi POS masuk atau biaya keluar
    saldo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo")

    # Flag aktif — metode nonaktif tidak muncul di pilihan pembayaran kasir
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp tracking — kapan dibuat dan terakhir diubah
    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    diubah_pada = models.DateTimeField(auto_now=True, verbose_name="Diubah Pada")

    class Meta:
        """Konfigurasi metadata model MetodePembayaran."""
        verbose_name = "Metode Pembayaran"         # Nama singular di admin
        verbose_name_plural = "Metode Pembayaran"  # Nama plural di admin
        ordering = ['nama']                        # Urutan default A-Z berdasarkan nama

    def __str__(self):
        """Representasi string — nama metode (contoh: 'Tunai')."""
        return self.nama

    @property
    def total_pendapatan(self):
        """
        Hitung total PENDAPATAN dari semua sumber pemasukan.

        Sumber pendapatan:
        1. POSTransaction (status='paid') → penjualan retail kasir
        2. SalesOrder (status in confirmed/delivered/completed) → penjualan B2B
        3. OrderService (status_bayar='lunas') → service center

        Return: Decimal — total pendapatan
        """
        from django.db.models import Sum

        # Sumber 1: POS Transaction yang sudah lunas
        pos_total = self.postransaction_set.filter(
            status='paid'
        ).aggregate(total=Sum('total_harga'))['total'] or 0

        # Sumber 2: Sales Order yang sudah dikonfirmasi/dikirim/selesai
        so_total = self.sales_orders.filter(
            status__in=['confirmed', 'delivered', 'completed']
        ).aggregate(total=Sum('total_harga'))['total'] or 0

        # Sumber 3: Order Service yang sudah lunas
        sc_total = self.order_services.filter(
            status_bayar='lunas'
        ).aggregate(total=Sum('biaya_akhir'))['total'] or 0

        return pos_total + so_total + sc_total

    @property
    def total_pengeluaran(self):
        """
        Hitung total PENGELUARAN dari metode pembayaran ini.

        Pengeluaran berasal dari 3 sumber:
        1. TransaksiBiaya (biaya operasional) — yang statusnya 'approved'
        2. PurchaseOrder (pembelian ke supplier) — yang statusnya 'received'
        3. Produk (pembelian stok awal/import) — harga_beli × qty_historis

        DIPERBAIKI: Sumber 3 menggunakan qty_historis (stok + terjual + adj_out)
        bukan hanya stok_total, agar pengeluaran produk yang sudah terjual tetap terhitung.

        Return: Decimal — total pengeluaran
        """
        from django.db.models import Sum
        from decimal import Decimal
        from apps.penjualan.models import SalesOrderItem
        from apps.inventory.models import AdjustmentStok
        # Note: POSTransactionItem didefinisikan setelah MetodePembayaran, import dari modul pos
        import apps.pos.models as pos_models

        # Sumber 1: Total dari transaksi biaya (HANYA status 'approved')
        biaya_total = self.transaksi_biaya.filter(
            status='approved'
        ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')

        # Sumber 2: Total dari Purchase Order yang sudah diterima
        po_total = self.purchase_orders.filter(
            status='received'
        ).aggregate(total=Sum('total_harga'))['total'] or Decimal('0')

        # Sumber 3: Total pembelian produk/sparepart yang menggunakan metode ini
        # Menggunakan qty_historis (stok_saat_ini + terjual_so + terjual_pos + adj_out)
        produk_total = Decimal('0')
        try:
            for produk in self.produk_set.all():
                stok_saat_ini = produk.stok_total
                
                # Hitung qty terjual di SO
                qty_sold_so = SalesOrderItem.objects.filter(
                    produk=produk,
                    sales_order__status__in=['confirmed', 'delivered', 'completed']
                ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
                
                # Hitung qty terjual di POS (gunakan jumlah_konversi = satuan dasar)
                qty_sold_pos = pos_models.POSTransactionItem.objects.filter(
                    produk=produk,
                    transaction__status='paid'
                ).aggregate(total=Sum('jumlah_konversi'))['total'] or Decimal('0')
                
                # Hitung qty keluar di Adjustment
                qty_adj_out = AdjustmentStok.objects.filter(
                    produk=produk,
                    tipe='out'
                ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
                
                # Hitung qty terpakai di Service Center (yang sudah mengurangi stok)
                qty_sc_used = Decimal('0')
                try:
                    from apps.service_center.models import PenggunaanSparepart
                    qty_sc_used = PenggunaanSparepart.objects.filter(
                        produk=produk,
                        stok_dikurangi=True
                    ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
                except Exception:
                    pass
                
                qty_historis = stok_saat_ini + qty_sold_so + qty_sold_pos + qty_adj_out + qty_sc_used
                produk_total += produk.harga_beli * qty_historis
        except Exception:
            pass

        return biaya_total + po_total + produk_total

    @property
    def saldo_terhitung(self):
        """
        Saldo DINAMIS = saldo awal (manual) + total pendapatan - total pengeluaran.

        Saldo bisa NEGATIF jika pengeluaran melebihi pendapatan + saldo awal.
        Template menampilkan warna merah jika negatif, hijau jika positif.

        Return: Decimal — saldo terhitung (bisa negatif)
        """
        return self.saldo + self.total_pendapatan - self.total_pengeluaran

    @property
    def total_transaksi_count(self):
        """
        Hitung TOTAL TRANSAKSI dari semua sumber yang menggunakan metode pembayaran ini.

        Sumber:
        1. POSTransaction (semua status)
        2. SalesOrder (semua status)
        3. PurchaseOrder (semua status)
        4. TransaksiBiaya (semua status)
        5. OrderService (semua status)

        Return: int — jumlah total transaksi
        """
        pos_count = self.postransaction_set.count()
        so_count = self.sales_orders.count()
        po_count = self.purchase_orders.count()
        biaya_count = self.transaksi_biaya.count()
        sc_count = self.order_services.count()
        produk_count = self.produk_set.count()
        return pos_count + so_count + po_count + biaya_count + sc_count + produk_count


class POSTransaction(models.Model):
    """
    Model untuk TRANSAKSI POS / kasir.

    Setiap transaksi memiliki:
    - Nomor unik (auto-generate: POS/2024/01/01/0001 — per hari)
    - Kasir (user yang melakukan transaksi)
    - Gudang (stok diambil dari gudang mana)
    - Items (produk yang dibeli customer)
    - Pembayaran (metode, jumlah bayar, kembalian)
    - Status (draft/unpaid/paid/cancelled)
    """
    # Nomor transaksi unik — auto-generate format: POS/2024/01/15/0001
    # unique=True memastikan tidak ada duplikat nomor transaksi
    nomor_transaksi = models.CharField(max_length=50, unique=True, verbose_name="Nomor Transaksi")

    # Tanggal dan waktu transaksi — otomatis diisi saat pertama kali dibuat
    tanggal = models.DateTimeField(auto_now_add=True, verbose_name="Tanggal")

    # Kasir yang melakukan transaksi — wajib diisi
    # on_delete=PROTECT → user kasir tidak bisa dihapus jika punya transaksi
    kasir = models.ForeignKey(User, on_delete=models.PROTECT, related_name='pos_transactions', verbose_name="Kasir")

    # Gudang tempat stok diambil — menentukan gudang mana yang stoknya berkurang
    gudang = models.ForeignKey(Gudang, on_delete=models.PROTECT, related_name='pos_transactions', verbose_name="Gudang")

    # Customer terdaftar (opsional) — relasi ke model Customer di modul penjualan
    # Jika customer terdaftar dipilih, nama_customer akan otomatis diisi dari data customer
    customer = models.ForeignKey('penjualan.Customer', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='pos_transactions', verbose_name="Customer")

    # Customer opsional (walk-in customer tidak perlu registrasi)
    # blank=True berarti boleh kosong di form
    nama_customer = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nama Customer")

    # ===== KOMPONEN HARGA =====
    # subtotal = jumlah semua item sebelum diskon/pajak
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")
    # diskon = potongan harga keseluruhan transaksi
    diskon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Diskon")
    # pajak = PPN atau pajak lain yang dikenakan
    pajak = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Pajak")
    # total = subtotal - diskon + pajak (dihitung otomatis)
    total_harga = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total Harga")

    # ===== KOMPONEN PEMBAYARAN =====
    # metode pembayaran yang dipilih kasir (Cash, Transfer, QRIS)
    metode_pembayaran = models.ForeignKey(MetodePembayaran, on_delete=models.PROTECT, verbose_name="Metode Pembayaran", null=True, blank=True)
    # jumlah uang yang diberikan customer
    jumlah_bayar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Bayar")
    # kembalian = jumlah_bayar - total_harga (dihitung otomatis)
    kembalian = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Kembalian")

    # ===== STATUS TRANSAKSI =====
    STATUS_CHOICES = [
        ('draft', 'Draft'),              # Transaksi masih diedit (belum final)
        ('unpaid', 'Belum Lunas'),       # Customer belum bayar (hutang/piutang)
        ('paid', 'Lunas'),               # Default — transaksi selesai, stok sudah berkurang
        ('cancelled', 'Dibatalkan'),     # Transaksi dibatalkan (stok dikembalikan)
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='paid', verbose_name="Status")

    # Tanggal jatuh tempo — hanya untuk status 'unpaid' (customer bayar nanti)
    jatuh_tempo = models.DateField(blank=True, null=True, verbose_name="Jatuh Tempo")

    # Catatan opsional dari kasir
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model POSTransaction."""
        verbose_name = "Transaksi POS"             # Nama singular
        verbose_name_plural = "Transaksi POS"      # Nama plural
        ordering = ['-dibuat_pada']                # Terbaru di atas

    def __str__(self):
        """Representasi: 'POS/2024/01/15/0001 - 15/01/2024 14:30'"""
        return f"{self.nomor_transaksi} - {self.tanggal.strftime('%d/%m/%Y %H:%M')}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor transaksi dan hitung total.

        Alur:
        1. Cek apakah record baru (self.pk is None) atau update
        2. Generate nomor transaksi jika belum ada
        3. Hitung total HANYA saat update (bukan create)
           → Karena saat create pertama kali, items belum ada
           → Calculate dipanggil dari views.py setelah items dibuat
        4. Simpan ke database
        """
        # Cek apakah ini record baru (belum punya primary key di database)
        is_new = self.pk is None

        # Auto-generate nomor transaksi jika field masih kosong
        if not self.nomor_transaksi:
            self.nomor_transaksi = self.generate_nomor()

        # PENTING: Jangan calculate saat first save!
        # Alasan: items (produk yang dibeli) belum ada saat transaksi pertama kali dibuat
        # Views.py akan memanggil calculate_total() setelah semua items ditambahkan
        if not is_new:
            self.calculate_total()

        super().save(*args, **kwargs)  # Simpan ke database

    def generate_nomor(self):
        """
        Generate nomor transaksi POS secara otomatis (per HARI).

        Format: POS/{TAHUN}/{BULAN}/{HARI}/{NOMOR_URUT_4_DIGIT}
        Contoh: POS/2024/01/15/0001, POS/2024/01/15/0002

        ⚠ Berbeda dengan PO/SO yang per BULAN, POS menggunakan per HARI
        karena volume transaksi POS jauh lebih banyak (bisa puluhan per hari).

        Algoritma:
        1. Buat prefix berdasarkan tanggal hari ini → 'POS/2024/01/15'
        2. Cari transaksi terakhir hari ini dengan prefix yang sama
        3. Increment nomor urut +1
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor transaksi — contoh 'POS/2024/01/15/0001'
        """
        from datetime import datetime
        today = datetime.now()
        # Format prefix: POS/2024/01/15 (tahun/bulan/hari dengan zero-padding)
        prefix = f"POS/{today.year}/{today.month:02d}/{today.day:02d}"

        # Cari transaksi terakhir HARI INI dengan prefix yang sama
        # select_for_update() mencegah race condition nomor duplikat saat concurrent
        last_trx = POSTransaction.objects.select_for_update().filter(
            nomor_transaksi__startswith=prefix  # Filter transaksi hari ini
        ).order_by('-nomor_transaksi').first()  # Ambil yang nomor terbesar

        if last_trx:
            try:
                # Parse nomor urut dari transaksi terakhir
                # Contoh: 'POS/2024/01/15/0005'.split('/') → ['POS','2024','01','15','0005'] → [-1] = '0005'
                last_number = int(last_trx.nomor_transaksi.split('/')[-1])
                new_number = last_number + 1  # Increment: 5 → 6
            except (ValueError, IndexError):
                # DIPERBAIKI: fallback aman — hitung jumlah transaksi + 1
                new_number = POSTransaction.objects.filter(
                    nomor_transaksi__startswith=prefix
                ).count() + 1
        else:
            new_number = 1  # Transaksi pertama hari ini

        # Format dengan zero-padding 4 digit: 1 → '0001'
        # Tambahan: loop untuk memastikan nomor unik
        nomor = f"{prefix}/{new_number:04d}"
        while POSTransaction.objects.filter(nomor_transaksi=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor

    def calculate_total(self):
        """
        Hitung total harga transaksi dan kembalian.

        Formula:
        - subtotal = SUM(item.subtotal) dari semua item transaksi
        - total_harga = subtotal - diskon + pajak
        - kembalian = jumlah_bayar - total_harga

        Contoh:
        - Items: Rp 50.000 + Rp 30.000 = subtotal Rp 80.000
        - Diskon: Rp 5.000
        - Pajak: Rp 8.800 (PPN 11%)
        - Total: 80.000 - 5.000 + 8.800 = Rp 83.800
        - Bayar: Rp 100.000 → Kembalian: Rp 16.200

        ⚠ Method ini TIDAK memanggil save() — hanya mengubah field di memory.
        Pemanggil harus memanggil .save() sendiri setelah calculate_total().
        """
        # Hitung subtotal dari semua item: sum(jumlah × harga) per item
        self.subtotal = sum(item.subtotal for item in self.items.all())

        # Hitung total akhir: subtotal dikurangi diskon, ditambah pajak
        self.total_harga = self.subtotal - self.diskon + self.pajak

        # Hitung kembalian: uang bayar dikurangi total yang harus dibayar
        self.kembalian = self.jumlah_bayar - self.total_harga

    def update_stock(self):
        """
        Kurangi stok produk di gudang setelah transaksi POS selesai.

        Dipanggil dari views.py SETELAH transaksi dan items berhasil disimpan.
        TIDAK dipanggil otomatis dari save() — harus dipanggil manual.

        Alur per item:
        1. Ambil record stok produk di gudang transaksi
        2. Kurangi jumlah stok sesuai quantity yang dibeli
        3. Simpan perubahan stok

        DIPERBAIKI: Menggunakan select_for_update() + transaction.atomic()
        agar aman saat multiple kasir memproses transaksi bersamaan.

        ⚠ Jika produk belum ada stok di gudang ini, skip (tidak error).
        Ini bisa terjadi jika produk baru ditambahkan tapi stok belum diinput.
        """
        with transaction.atomic():
            for item in self.items.all():
                try:
                    # DIPERBAIKI: select_for_update() mencegah race condition
                    # Cari record stok: produk X di gudang Y (dengan row lock)
                    stok = Stok.objects.select_for_update().get(
                        produk=item.produk, gudang=self.gudang
                    )
                    # Kurangi jumlah stok sesuai quantity yang dijual
                    stok.jumlah -= item.jumlah
                    stok.save()  # Simpan perubahan stok ke database
                except Stok.DoesNotExist:
                    # Produk belum punya record stok di gudang ini → skip
                    # Tidak raise error agar transaksi tetap berhasil
                    pass


class POSTransactionItem(models.Model):
    """
    Model untuk DETAIL ITEM dalam transaksi POS.

    Setiap item merepresentasikan 1 produk yang dibeli dalam 1 transaksi.
    Subtotal per item = (jumlah × harga_satuan) - diskon

    Contoh:
    | produk        | jumlah | harga_satuan | diskon | subtotal |
    |---------------|--------|--------------|--------|----------|
    | Indomie       | 5      | 3,500        | 0      | 17,500   |
    | Aqua 600ml    | 2      | 4,000        | 500    | 7,500    |

    Relasi:
    - FK ke POSTransaction → transaksi induk (parent)
    - FK ke Produk → produk yang dibeli
    """

    # Relasi ke transaksi induk — on_delete=CASCADE berarti item ikut terhapus
    # jika transaksi dihapus (logis: item tanpa transaksi tidak berguna)
    # related_name='items' → transaksi.items.all() untuk mendapatkan semua item
    transaction = models.ForeignKey(POSTransaction, on_delete=models.CASCADE, related_name='items', verbose_name="Transaksi")

    # Produk yang dibeli — PROTECT agar produk tidak bisa dihapus jika ada di transaksi
    produk = models.ForeignKey(Produk, on_delete=models.PROTECT, verbose_name="Produk")

    # Jumlah yang dibeli — Decimal untuk mendukung satuan pecahan (contoh: 2.5 kg)
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Harga per unit saat transaksi — disimpan terpisah dari Produk.harga_jual
    # karena harga produk bisa berubah, tapi harga di transaksi lama harus tetap
    harga_satuan = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Harga Satuan")

    # Diskon per item — potongan harga untuk item ini saja
    diskon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Diskon")

    # Subtotal per item — dihitung otomatis: (jumlah × harga_satuan) - diskon
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Subtotal")

    # Satuan transaksi — satuan yang digunakan kasir saat transaksi (bisa berbeda dari satuan produk)
    # Contoh: produk dalam Kg, tapi kasir jual dalam Gram
    satuan_transaksi = models.ForeignKey(
        'produk.Satuan', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Satuan Transaksi",
        help_text="Kosongkan jika menggunakan satuan asli produk"
    )

    # Jumlah setelah konversi ke satuan dasar produk
    # Contoh: kasir jual 500 gram → jumlah=500, jumlah_konversi=0.5 (kg)
    # Digunakan untuk kalkulasi qty_historis di Laporan Keuangan & Metode Pembayaran
    jumlah_konversi = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        verbose_name="Jumlah (Satuan Dasar)",
        help_text="Jumlah dalam satuan dasar produk, dihitung otomatis"
    )

    class Meta:
        """Konfigurasi metadata model POSTransactionItem."""
        verbose_name = "Item Transaksi POS"
        verbose_name_plural = "Item Transaksi POS"

    def __str__(self):
        """Representasi: 'Indomie - 5'"""
        return f"{self.produk.nama} - {self.jumlah}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-calculate subtotal dan update total transaksi.

        Alur:
        1. Hitung subtotal item: (jumlah × harga_satuan) - diskon
        2. Simpan item ke database
        3. Recalculate total transaksi induk (parent)
        4. Simpan transaksi induk

        Kenapa update parent?
        - Karena perubahan di item mempengaruhi total keseluruhan transaksi
        - Ini memastikan total_harga transaksi selalu up-to-date
        """
        # LANGKAH 1: Hitung subtotal per item
        # Contoh: 5 × Rp 3.500 - Rp 0 = Rp 17.500
        self.subtotal = (self.jumlah * self.harga_satuan) - self.diskon

        # LANGKAH 2: Simpan item ke database
        super().save(*args, **kwargs)

        # LANGKAH 3: Update total transaksi induk
        # Cek transaction_id ada (untuk menghindari error saat item baru belum di-assign)
        if self.transaction_id:
            # Recalculate semua total di transaksi induk
            self.transaction.calculate_total()
            # Simpan transaksi induk dengan total yang sudah diupdate
            self.transaction.save()
