"""
==========================================================================
 FRAUD DETECTION MODELS — Model Database Deteksi Kecurangan
==========================================================================
 File ini berisi 3 model utama:

 1. FraudRule       → Pengaturan pencegahan fraud (singleton, hanya 1 record)
 2. FraudAlert      → Log anomali/kecurangan yang terdeteksi otomatis
 3. CashReconciliation → Rekonsiliasi kas kasir (blind cash closing)

 Hubungan antar model:
 ┌─────────────────┐     ┌──────────────────┐
 │   FraudRule     │     │  FraudAlert      │
 │  (Singleton)    │     │  FK → User       │
 │                 │     │  FK → Activity   │
 │  Batas diskon   │     │  Jenis anomali   │
 │  Blokir hapus   │     │  Severity level  │
 │  Jam operasional│     │  Status review   │
 └─────────────────┘     └──────────────────┘
                         ┌──────────────────┐
                         │CashReconciliation│
                         │  FK → User(kasir)│
                         │  FK → Gudang     │
                         │  FK → User(revwr)│
                         │  Expected vs     │
                         │  Actual amount   │
                         └──────────────────┘

 Relasi dengan model lain:
 - FraudAlert.activity     → FK ke activity_log.UserActivity
 - FraudAlert.user_terkait → FK ke auth.User (pelaku)
 - FraudAlert.reviewed_by  → FK ke auth.User (reviewer)
 - CashReconciliation.kasir → FK ke auth.User
 - CashReconciliation.gudang → FK ke produk.Gudang
 - CashReconciliation.reviewed_by → FK ke auth.User

 Catatan penting:
 - FraudRule menggunakan pola Singleton (pk selalu = 1)
 - FraudAlert dibuat otomatis oleh signals.py saat anomali terdeteksi
 - CashReconciliation.discrepancy dihitung otomatis di method save()

 Konvensi penamaan field tanggal:
 - Modul ini menggunakan konvensi English (created_at, updated_at) untuk
   timestamp tracking, berbeda dengan modul inti yang menggunakan konvensi
   Indonesian (dibuat_pada, diupdate_pada, tanggal). Hal ini dipertahankan
   untuk konsistensi internal modul ini.
==========================================================================
"""

# Import dari framework Django — ORM (Object-Relational Mapping)
from django.db import models
# Import model User bawaan Django — digunakan untuk relasi FK ke user
from django.contrib.auth.models import User


# ╔══════════════════════════════════════════════════════════════╗
# ║        MODEL 1: FRAUD RULE — Pengaturan Fraud (Singleton)  ║
# ╚══════════════════════════════════════════════════════════════╝

class FraudRule(models.Model):
    """
    ══════════════════════════════════════════════════════
    Pengaturan Pencegahan Fraud (Singleton Pattern).
    ══════════════════════════════════════════════════════
    Model ini HANYA boleh memiliki 1 record (pk=1).
    Digunakan untuk mengkonfigurasi aturan keamanan fraud di seluruh sistem.

    Kenapa Singleton?
    → Karena pengaturan fraud berlaku global untuk seluruh toko/cabang.
      Tidak perlu banyak record, cukup 1 yang berlaku untuk semua.

    Cara akses:
    → FraudRule.load()  → Buat default otomatis jika belum ada

    Terhubung dengan:
    → signals.py     — Setiap signal membaca FraudRule.load() untuk cek aturan
    → views.py       — FraudSettingsView menampilkan & menyimpan perubahan
    → pengaturan/views.py — reset_data() menghapus saat reset sistem
    """

    # =================================================================
    # FIELD 1: block_delete_paid — Blokir Hapus Transaksi Lunas
    # =================================================================
    # Jika aktif (True), user TIDAK BISA menghapus transaksi SO/PO/POS
    # yang sudah berstatus 'paid'/'confirmed'/'completed'.
    # Ini mencegah kecurangan dimana kasir menghapus transaksi setelah
    # uang masuk (menggelapkan uang).
    # Signal: detect_hapus_lunas() di signals.py akan raise Exception
    # jika flag ini = True dan user mencoba delete data lunas.
    block_delete_paid = models.BooleanField(
        default=False,
        verbose_name="Blokir Hapus Data Lunas",
        help_text="Jika aktif, transaksi SO/PO/POS berstatus lunas tidak bisa dihapus."
    )

    # =================================================================
    # FIELD 2: block_negative_stock — Blokir Stok Minus
    # =================================================================
    # Jika aktif (True), transaksi POS akan ditolak jika stok produk
    # tidak mencukupi (stok < qty yang diminta).
    # Ini mencegah overselling yang bisa menyebabkan kerugian.
    # Signal: blokir_stok_minus_pos() di signals.py akan raise Exception
    # jika flag ini = True dan stok < qty.
    block_negative_stock = models.BooleanField(
        default=False,
        verbose_name="Blokir Stok Minus",
        help_text="Jika aktif, transaksi POS ditolak jika stok tidak mencukupi."
    )

    # =================================================================
    # FIELD 3: max_discount_percent — Batas Maksimal Diskon (%)
    # =================================================================
    # Kasir hanya boleh memberi diskon sampai batas ini.
    # Jika kasir memberi diskon > batas, sistem otomatis buat FraudAlert
    # dengan jenis 'diskon_besar' dan severity 'high'.
    # Default: 100% (tidak ada batas) — admin harus set sesuai kebijakan.
    # Contoh: set 30% artinya kasir max diskon 30% dari subtotal.
    # Signal: detect_diskon_berlebihan() di signals.py cek field ini.
    max_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=100.00,
        verbose_name="Batas Maksimal Diskon (%)",
        help_text="Persentase maksimal diskon yang boleh diberikan kasir. Default 100% (tanpa batas)."
    )

    # =================================================================
    # FIELD 4-5: Jam Operasional (mulai & selesai)
    # =================================================================
    # Digunakan untuk mendeteksi transaksi diluar jam operasional.
    # Jika ada transaksi POS/SO/PO dibuat di luar rentang jam ini,
    # sistem otomatis buat FraudAlert jenis 'diluar_jam'.
    # Signal: detect_transaksi_diluar_jam() di signals.py cek field ini.
    jam_operasional_mulai = models.TimeField(
        default="07:00",
        verbose_name="Jam Operasional Mulai",
        help_text="Waktu mulai jam operasional toko."
    )
    jam_operasional_selesai = models.TimeField(
        default="22:00",
        verbose_name="Jam Operasional Selesai",
        help_text="Waktu selesai jam operasional toko."
    )

    # =================================================================
    # FIELD 6: max_sparepart_qty — Batas Maksimal Sparepart per Item
    # =================================================================
    max_sparepart_qty = models.DecimalField(
        max_digits=10, decimal_places=2, default=10.00,
        verbose_name="Batas Maksimal Qty Sparepart",
        help_text="Batas maksimal jumlah sparepart per item service. Default 10."
    )

    # =================================================================
    # FIELD 7: max_transaction_amount — Batas Transaksi Mencurigakan
    # =================================================================
    max_transaction_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=10000000.00,
        verbose_name="Batas Transaksi Mencurigakan (Rp)",
        help_text="Jika nilai transaksi melebihi batas ini, buat FraudAlert. Default Rp 10.000.000."
    )

    # =================================================================
    # FIELD 8: min_margin_percent — Margin Minimal untuk Alert
    # =================================================================
    min_margin_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        verbose_name="Margin Minimal (%)",
        help_text="Jika margin keuntungan di bawah % ini, buat FraudAlert. Default 0% (tanpa alert)."
    )

    # =================================================================
    # FIELD 9-10: Tracking — Siapa & kapan terakhir mengubah pengaturan
    # =================================================================
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Diubah Oleh"
    )

    class Meta:
        verbose_name = "Pengaturan Fraud"
        verbose_name_plural = "Pengaturan Fraud"

    def __str__(self):
        return "Pengaturan Fraud Detection"

    @classmethod
    def load(cls):
        """
        Load singleton FraudRule.
        ─────────────────────────
        Menggunakan get_or_create(pk=1) agar:
        - Jika record belum ada → otomatis buat dengan default values
        - Jika sudah ada → langsung return record yang ada
        Ini memastikan FraudRule selalu ada dan tidak perlu setup manual.
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        """
        Override save() untuk memaksa pk = 1.
        ──────────────────────────────────────
        Apapun pk yang di-assign, selalu di-set ke 1.
        Ini menjamin hanya ada 1 record FraudRule di database (Singleton).
        """
        self.pk = 1
        super().save(*args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
# ║        MODEL 2: FRAUD ALERT — Log Anomali Kecurangan       ║
# ╚══════════════════════════════════════════════════════════════╝

class FraudAlert(models.Model):
    """
    ══════════════════════════════════════════════════════
    Log Anomali Kecurangan yang Terdeteksi.
    ══════════════════════════════════════════════════════
    Setiap record = 1 anomali yang terdeteksi oleh sistem.
    Record dibuat otomatis oleh signals.py saat event mencurigakan terjadi.

    Alur hidup (lifecycle) setiap FraudAlert:
    1. PENDING   → Baru terdeteksi, belum ada tindakan
    2. INVESTIGATED → Sedang diselidiki oleh owner/SPV
    3. CLEARED   → Ternyata aman/wajar (false positive)
    4. REJECTED  → Terbukti fraud, perlu tindak lanjut

    Terhubung dengan:
    → signals.py              — Signal otomatis buat record ini
    → views.py                — FraudAlertListView, DetailView menampilkan
    → views.py                — fraud_alert_update_status() mengubah status
    → ai_assistant/intents.py — _gather_fraud_detection() mengumpulkan statistik
    → pengaturan/views.py     — ManajemenDataView menampilkan count-nya
    """

    # =================================================================
    # CHOICES — Pilihan dropdown untuk setiap field kategori
    # =================================================================

    # Jenis anomali yang bisa terdeteksi oleh sistem
    JENIS_CHOICES = [
        ('hapus_lunas', 'Hapus Data Lunas'),           # Hapus transaksi yang sudah lunas
        ('diskon_besar', 'Diskon Berlebihan'),          # Diskon melebihi batas FraudRule
        ('po_markup', 'PO Mark-Up Harga'),              # Harga PO lebih tinggi dari normal
        ('stok_minus', 'Stok Minus'),                   # Percobaan jual stok yang tidak ada
        ('diluar_jam', 'Aktivitas Diluar Jam'),         # Transaksi di luar jam operasional
        ('adjustment_besar', 'Adjustment Stok Besar'),  # Adjustment qty > 50 atau nominal > 1 juta
        ('void_transaksi', 'Void Transaksi'),           # Void/batal transaksi
        ('lainnya', 'Lainnya'),                         # Catch-all untuk jenis lain
    ]

    # Tingkat keparahan anomali (menentukan prioritas penanganan)
    SEVERITY_CHOICES = [
        ('low', 'Rendah'),       # Info — tidak mendesak
        ('medium', 'Sedang'),    # Perlu perhatian dalam 1-3 hari
        ('high', 'Tinggi'),      # Perlu segera ditangani
        ('critical', 'Kritis'),  # EMERGENCY — harus segera diinvestigasi
    ]

    # Status tindak lanjut oleh owner/SPV/manajer
    STATUS_CHOICES = [
        ('pending', 'Menunggu Review'),        # Belum ada tindakan
        ('investigated', 'Sedang Diinvestigasi'),  # Sedang diperiksa
        ('cleared', 'Aman / Wajar'),           # False positive — bukan fraud
        ('rejected', 'Terbukti Fraud'),        # Benar fraud — perlu sanksi
    ]

    # =================================================================
    # FIELD: Relasi ke Activity Log
    # =================================================================
    # FK ke UserActivity — menghubungkan anomali dengan log aktivitas
    # yang memicu anomali tersebut. Bisa null jika anomali dibuat manual.
    # SET_NULL karena jika log dihapus, alert-nya masih tetap ada.
    activity = models.ForeignKey(
        'activity_log.UserActivity',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Log Aktivitas Terkait",
        related_name="fraud_alerts"
    )

    # =================================================================
    # FIELD: Data Anomali Utama
    # =================================================================

    # Jenis anomali — dari JENIS_CHOICES di atas
    jenis = models.CharField(
        max_length=30, choices=JENIS_CHOICES,
        verbose_name="Jenis Anomali"
    )
    # Tingkat keparahan — dari SEVERITY_CHOICES
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default='medium',
        verbose_name="Tingkat Keparahan"
    )
    # Status tindak lanjut — dari STATUS_CHOICES (default: pending)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        verbose_name="Status"
    )

    # =================================================================
    # FIELD: Detail Anomali
    # =================================================================

    # Deskripsi lengkap anomali yang terdeteksi
    # Diisi otomatis oleh signal dengan format f-string
    deskripsi = models.TextField(
        verbose_name="Deskripsi Anomali",
        help_text="Penjelasan detail anomali yang terdeteksi."
    )
    # User yang melakukan aksi mencurigakan (kasir/karyawan)
    # SET_NULL karena jika user dihapus, record anomali masih perlu dipertahankan
    user_terkait = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="User Terkait",
        related_name="fraud_alerts_terkait"
    )
    # Nominal rupiah terkait anomali (contoh: nominal diskon, nominal transaksi)
    nominal = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Nominal Terkait (Rp)"
    )

    # =================================================================
    # FIELD: Data Referensi — untuk menautkan kembali ke record asli
    # =================================================================

    # Nama model yang memicu anomali (contoh: 'POSTransaction', 'SalesOrder')
    model_name = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Model/Modul"
    )
    # ID objek terkait (contoh: nomor_transaksi POS, nomor_so)
    object_id = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="ID Objek"
    )
    # Snapshot data JSON — menyimpan data sebelum/sesudah perubahan
    # untuk keperluan forensik/investigasi (evidence)
    data_snapshot = models.JSONField(
        default=dict, blank=True,
        verbose_name="Snapshot Data",
        help_text="Data JSON sebelum/sesudah perubahan."
    )

    # =================================================================
    # FIELD: Tindak Lanjut oleh Owner/SPV
    # =================================================================

    # Catatan dari owner/SPV saat mereview anomali
    catatan_owner = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan Owner/SPV"
    )
    # User yang mereview anomali (biasanya owner/manajer/SPV)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Direview Oleh",
        related_name="fraud_alerts_reviewed"
    )
    # Tanggal review dilakukan
    reviewed_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Tanggal Review"
    )

    # =================================================================
    # FIELD: Tracking — kapan dibuat & terakhir diupdate
    # =================================================================
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Tanggal Terdeteksi")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fraud Alert"
        verbose_name_plural = "Fraud Alerts"
        ordering = ['-created_at']  # Terbaru dulu

    def __str__(self):
        """Format display: [Tinggi] Hapus Data Lunas - 21/03/2026 14:30"""
        return f"[{self.get_severity_display()}] {self.get_jenis_display()} - {self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '-'}"


# ╔══════════════════════════════════════════════════════════════╗
# ║     MODEL 3: CASH RECONCILIATION — Rekonsiliasi Kas        ║
# ╚══════════════════════════════════════════════════════════════╝

class CashReconciliation(models.Model):
    """
    ══════════════════════════════════════════════════════
    Rekonsiliasi Kas Kasir (Blind Cash Closing).
    ══════════════════════════════════════════════════════
    Fitur untuk memverifikasi uang fisik di laci kas kasir vs
    jumlah yang dicatat sistem (POS). Disebut "blind" karena kasir
    TIDAK melihat jumlah sistem saat menginput uang fisik.

    Alur operasional:
    1. Kasir selesai shift → klik "Tutup Shift"
    2. Kasir hitung uang fisik di laci → input ke sistem
    3. Sistem otomatis bandingkan: fisik vs POS cash transactions
    4. Jika selisih negatif > Rp 10.000 → otomatis buat FraudAlert
    5. Manajer/SPV review → approve, catatan, atau biaya kerugian

    Kenapa "Blind"?
    → Kasir tidak boleh lihat jumlah sistem sebelum input uang fisik.
      Ini mencegah kasir "menyesuaikan" angka agar cocok.

    Status lifecycle:
    - open     → Shift sedang berjalan (belum tutup)
    - closed   → Shift ditutup, uang fisik sudah diinput
    - reviewed → Manajer/SPV sudah mereview & menyetujui

    Terhubung dengan:
    → views.py (CashReconciliationCreateView) — create record + hitung expected
    → views.py (cash_recon_edit)              — edit uang fisik
    → views.py (cash_recon_review)            — review + tindak lanjut
    → pos.POSTransaction                      — sumber data expected_amount
    → biaya.TransaksiBiaya                    — pengeluaran cash dikurangi
    → produk.Gudang                           — cabang/outlet terkait
    """

    # Status lifecycle rekonsiliasi kas
    STATUS_CHOICES = [
        ('open', 'Shift Berjalan'),     # Shift aktif, belum tutup
        ('closed', 'Shift Ditutup'),    # Sudah tutup, menunggu review
        ('reviewed', 'Sudah Direview'), # Manajer sudah tindak lanjut
    ]

    # =================================================================
    # FIELD: Relasi ke User (Kasir)
    # =================================================================
    # FK ke User — kasir yang melakukan tutup shift
    # CASCADE karena jika user dihapus, data rekonsiliasi-nya juga dihapus
    kasir = models.ForeignKey(
        User, on_delete=models.CASCADE,
        verbose_name="Kasir",
        related_name="cash_reconciliations"
    )

    # =================================================================
    # FIELD: Relasi ke Gudang (Cabang/Outlet)
    # =================================================================
    # FK ke Gudang — cabang/outlet tempat kasir bekerja
    # SET_NULL karena jika gudang dihapus, data rekonsiliasi masih diperlukan
    gudang = models.ForeignKey(
        'produk.Gudang', on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Cabang/Gudang"
    )

    # =================================================================
    # FIELD: Waktu Shift
    # =================================================================
    shift_start = models.DateTimeField(verbose_name="Mulai Shift")  # Jam mulai shift kasir
    shift_end = models.DateTimeField(                                # Jam akhir shift kasir
        null=True, blank=True,
        verbose_name="Akhir Shift"
    )

    # =================================================================
    # FIELD: Nominal Uang
    # =================================================================

    # Expected = total penjualan cash POS - pengeluaran cash dari laci
    # Dihitung otomatis saat create di CashReconciliationCreateView.post()
    expected_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Uang Seharusnya (Sistem)",
        help_text="Nominal uang yang seharusnya ada berdasarkan transaksi POS."
    )
    # Actual = uang fisik yang dihitung kasir di laci kas
    actual_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Uang Fisik (Input Kasir)",
        help_text="Nominal uang fisik yang dilaporkan kasir saat tutup shift."
    )
    # Discrepancy = actual - expected (dihitung otomatis di save())
    # Positif → uang lebih (overage) — bisa karena kembalian kurang
    # Negatif → uang kurang (shortage) — MASALAH, indikasi fraud
    discrepancy = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Selisih (Rp)",
        help_text="Selisih antara uang fisik dan uang sistem. Positif = lebih, Negatif = kurang."
    )

    # =================================================================
    # FIELD: Catatan & Status
    # =================================================================
    catatan = models.TextField(
        blank=True, null=True,
        verbose_name="Catatan"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='open',
        verbose_name="Status"
    )
    # User yang mereview (biasanya manajer/SPV)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Direview Oleh",
        related_name="cash_reviews"
    )

    # =================================================================
    # FIELD: Tracking timestamps
    # =================================================================
    created_at = models.DateTimeField(auto_now_add=True)  # Otomatis saat record dibuat
    updated_at = models.DateTimeField(auto_now=True)      # Otomatis saat record diupdate

    class Meta:
        verbose_name = "Rekonsiliasi Kas"
        verbose_name_plural = "Rekonsiliasi Kas"
        ordering = ['-shift_start']  # Shift terbaru dulu

    def __str__(self):
        """Format: Kas Ahmad Kasir - 21/03/2026"""
        return f"Kas {self.kasir.get_full_name() or self.kasir.username} - {self.shift_start.strftime('%d/%m/%Y') if self.shift_start else '-'}"

    def save(self, *args, **kwargs):
        """
        Override save() untuk menghitung selisih (discrepancy) otomatis.
        ───────────────────────────────────────────────────────────────
        Rumus: discrepancy = actual_amount - expected_amount
        - Positif → uang di laci lebih dari yang seharusnya
        - Negatif → uang di laci kurang dari yang seharusnya (indikasi masalah)

        Kenapa otomatis di save()?
        → Agar selisih selalu akurat saat uang fisik diubah (edit).
          Tanpa ini, admin harus hitung manual setiap kali edit.
        """
        self.discrepancy = self.actual_amount - self.expected_amount
        super().save(*args, **kwargs)
