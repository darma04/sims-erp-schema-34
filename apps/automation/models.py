"""
==========================================================================
 AUTOMATION MODELS - Model Sistem Notifikasi Telegram Otomatis
==========================================================================
 File ini berisi 3 model untuk sistem notifikasi Telegram:

 1. PengaturanTelegram (Singleton Pattern)
    - Menyimpan konfigurasi bot: token, chat_id, toggle notifikasi
    - Singleton = hanya 1 record (pk=1 selalu)
    - Alasan: Pengaturan bot Telegram hanya perlu 1 konfigurasi global
    - Toggle per jenis transaksi: POS, SO, PO, Biaya bisa on/off masing²

 2. TemplatePesan
    - Template pesan notifikasi per jenis transaksi
    - Menggunakan placeholder {{variabel}} yang di-render saat kirim
    - Default template otomatis dibuat jika belum ada (get_template())
    - Admin bisa edit template via Django Admin tanpa ubah kode

 3. LogNotifikasi
    - Riwayat pengiriman notifikasi (sukses/gagal)
    - Untuk monitoring dan debugging pengiriman pesan
    - Menyimpan: pesan yang dikirim, respons API, error message

 Alur kerja notifikasi:
 ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  ┌──────────┐
 │ User membuat │→│ views.py      │→│ signals.py       │→│ telegram  │
 │ transaksi    │  │ save data     │  │ siapkan data     │  │ _service  │
 └──────────────┘  └───────────────┘  │ panggil kirim    │  │ kirim API│
                                      └──────────────────┘  └──────────┘

 Terhubung dengan:
 - signals.py → Memformat data transaksi untuk notifikasi
 - telegram_service.py → Mengirim pesan via Telegram Bot API
 - views.py → Halaman pengaturan dan log notifikasi
 - admin.py → Mendaftarkan model ke Django Admin
==========================================================================
"""

# Import Django ORM base class
from django.db import models


class PengaturanTelegram(models.Model):
    """
    Model konfigurasi bot Telegram menggunakan Singleton Pattern.

    Singleton Pattern:
    - Hanya boleh ada 1 record di database (pk=1 selalu)
    - save() memaksa pk=1 → update record yang ada
    - load() mengambil record pk=1, buat jika belum ada

    Kenapa Singleton?
    - Bot Telegram hanya 1 (1 token bot, 1 chat ID tujuan)
    - Tidak perlu banyak konfigurasi berbeda
    - Menyederhanakan akses dari mana saja: PengaturanTelegram.load()

    Diakses dari:
    - views.py → Halaman pengaturan Telegram (form edit)
    - telegram_service.py → Ambil bot_token dan chat_id untuk kirim pesan
    """

    # ═══ FIELD: Bot Token ═══
    # Token unik yang didapat dari @BotFather di Telegram
    # Format: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890"
    # Tanpa token ini, bot tidak bisa mengirim pesan
    bot_token = models.CharField(
        max_length=200,
        blank=True,                # Boleh kosong (bot belum dikonfigurasi)
        verbose_name="Bot Token",
        help_text="Token dari @BotFather, contoh: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    )

    # ═══ FIELD: Chat ID ═══
    # ID tujuan pengiriman notifikasi (bisa grup atau personal)
    # Untuk mengetahui Chat ID: kirim pesan ke @userinfobot di Telegram
    # Grup ID biasanya negatif: -1001234567890
    # Personal ID positif: 123456789
    chat_id = models.CharField(
        max_length=100,
        blank=True,                # Boleh kosong sebelum di-setup
        verbose_name="Chat ID",
        help_text="Chat ID tujuan (grup atau personal). Gunakan @userinfobot untuk mengetahui Chat ID"
    )

    # ═══ FIELD: Status Aktif ═══
    # Master toggle: jika False, SEMUA notifikasi tidak dikirim
    # Meskipun toggle per jenis masih True
    aktif = models.BooleanField(
        default=False,             # Default nonaktif sampai bot_token & chat_id diisi
        verbose_name="Aktif"
    )

    # ═══ FIELD: Toggle per Jenis Transaksi ═══
    # Masing-masing bisa di-on/off secara terpisah
    # Default True → aktif saat master toggle diaktifkan
    # Alasan toggle terpisah: admin mungkin hanya mau notifikasi POS saja

    # Notifikasi saat transaksi POS baru (kasir checkout)
    notif_pos = models.BooleanField(
        default=True,
        verbose_name="Notifikasi Transaksi POS"
    )

    # Notifikasi saat Sales Order baru dibuat
    notif_sales_order = models.BooleanField(
        default=True,
        verbose_name="Notifikasi Sales Order"
    )

    # Notifikasi saat Purchase Order baru dibuat
    notif_purchase_order = models.BooleanField(
        default=True,
        verbose_name="Notifikasi Purchase Order"
    )

    # Notifikasi saat transaksi biaya baru dicatat
    notif_biaya = models.BooleanField(
        default=True,
        verbose_name="Notifikasi Transaksi Biaya"
    )

    # Notifikasi saat slip gaji baru dibuat/dibayar
    notif_penggajian = models.BooleanField(
        default=True,
        verbose_name="Notifikasi Slip Gaji"
    )

    # Toggle kirim PDF — jika True, setiap notifikasi juga mengirim file PDF
    kirim_pdf = models.BooleanField(
        default=True,
        verbose_name="Kirim PDF Otomatis",
        help_text="Jika aktif, setiap notifikasi juga akan mengirim file PDF dokumen ke Telegram"
    )

    # ═══ FIELD: System Prompt Bot Telegram ═══
    # Instruksi kustom untuk mengatur perilaku AI chatbot di Telegram
    # Jika kosong, akan menggunakan system prompt default dari telegram_bot.py
    system_prompt_bot = models.TextField(
        blank=True,
        default='',
        verbose_name="System Prompt Bot AI",
        help_text="Instruksi tambahan untuk mengatur perilaku AI chatbot Telegram. Kosongkan untuk menggunakan default."
    )

    # ═══ FIELD: Timestamp ═══
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Kapan pertama kali dibuat
    diupdate_pada = models.DateTimeField(auto_now=True)     # Kapan terakhir diupdate

    class Meta:
        """
        Metadata model Django:
        - verbose_name: Label yang muncul di Django Admin
        - verbose_name_plural: Label jamak (sama karena singleton)
        """
        verbose_name = "Pengaturan Telegram"
        verbose_name_plural = "Pengaturan Telegram"

    def __str__(self):
        """
        Representasi string: "Pengaturan Telegram (Aktif)" atau "(Nonaktif)"
        Digunakan di Django Admin list dan dropdown.
        """
        return f"Pengaturan Telegram ({'Aktif' if self.aktif else 'Nonaktif'})"

    def save(self, *args, **kwargs):
        """
        Override save() untuk implementasi Singleton Pattern.
        Memaksa pk=1 sehingga hanya ada 1 record di database.
        - Jika pk=1 ada → UPDATE
        - Jika pk=1 belum ada → CREATE dengan pk=1
        """
        self.pk = 1  # Paksa primary key = 1 (singleton)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """
        Class method untuk memuat konfigurasi Telegram.

        Cara kerja:
        - get_or_create(pk=1): ambil record pk=1, buat jika belum ada
        - Jika baru dibuat: semua field kosong/default (bot belum aktif)

        Penggunaan:
            config = PengaturanTelegram.load()
            if config.aktif:
                kirim_pesan(config.bot_token, config.chat_id, ...)
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class TemplatePesan(models.Model):
    """
    Template pesan notifikasi Telegram untuk setiap jenis transaksi.

    Cara kerja template:
    1. Setiap jenis transaksi (POS, SO, PO, Biaya) punya 1 template
    2. Template berisi teks dengan placeholder {{variabel}}
    3. Saat kirim notifikasi, placeholder diganti dengan data aktual
    4. Contoh: "No: {{nomor_transaksi}}" → "No: TRX-20260306-001"

    Kenapa disimpan di database (bukan hardcode)?
    - Admin bisa edit format pesan tanpa ubah kode Python
    - Bisa tambah/hapus informasi yang ditampilkan di notifikasi
    - Bisa disable template tertentu tanpa matikan semua notifikasi

    Diakses dari:
    - telegram_service.py → get_template() untuk ambil format pesan
    - views.py → Admin bisa edit template via halaman pengaturan
    - admin.py → Bisa edit langsung di Django Admin
    """

    # ═══ CHOICES: Jenis Transaksi ═══
    # 4 jenis transaksi yang mendukung notifikasi Telegram
    JENIS_CHOICES = [
        ('pos', 'Transaksi POS'),           # Penjualan kasir langsung
        ('sales_order', 'Sales Order'),      # Penjualan via Sales Order
        ('purchase_order', 'Purchase Order'),# Pembelian dari supplier
        ('biaya', 'Transaksi Biaya'),        # Pencatatan biaya operasional
        ('penggajian', 'Slip Gaji'),         # Slip gaji karyawan
    ]

    # ═══ FIELD: Jenis Transaksi ═══
    # unique=True → setiap jenis hanya punya 1 template
    # Contoh: tidak boleh ada 2 template untuk 'pos'
    jenis = models.CharField(
        max_length=30,
        choices=JENIS_CHOICES,
        unique=True,               # Satu template per jenis transaksi
        verbose_name="Jenis Transaksi"
    )

    # ═══ FIELD: Nama Template ═══
    # Label deskriptif untuk template (ditampilkan di admin)
    # Contoh: "Template Transaksi POS", "Template Sales Order"
    nama = models.CharField(
        max_length=100,
        verbose_name="Nama Template"
    )

    # ═══ FIELD: Template Pesan ═══
    # Teks template dengan placeholder dalam format {{variabel}}
    # Placeholder yang tersedia berbeda per jenis transaksi
    # POS: {{nomor_transaksi}}, {{kasir}}, {{detail_items}}, {{total}}, dll
    # SO: {{nomor_so}}, {{customer}}, {{detail_items}}, {{total}}, dll
    # PO: {{nomor_po}}, {{supplier}}, {{detail_items}}, {{total}}, dll
    # Biaya: {{nomor_transaksi}}, {{kategori}}, {{jumlah}}, {{deskripsi}}, dll
    template_pesan = models.TextField(
        verbose_name="Template Pesan",
        help_text="Gunakan variabel dalam kurung kurawal ganda, contoh: {{nomor_transaksi}}"
    )

    # ═══ FIELD: Status Aktif ═══
    # Jika False, template tidak digunakan → notifikasi jenis ini tidak terkirim
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif"
    )

    # ═══ FIELD: Timestamp ═══
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Kapan template dibuat
    diupdate_pada = models.DateTimeField(auto_now=True)     # Kapan template terakhir diedit

    class Meta:
        """
        Metadata:
        - ordering: urutkan berdasarkan jenis transaksi (A-Z)
        """
        verbose_name = "Template Pesan"
        verbose_name_plural = "Template Pesan"
        ordering = ['jenis']  # Urut: biaya, pos, purchase_order, sales_order

    def __str__(self):
        """
        Representasi string: "Transaksi POS - Template Transaksi POS"
        get_jenis_display() mengkonversi 'pos' → 'Transaksi POS'
        """
        return f"{self.get_jenis_display()} - {self.nama}"

    @classmethod
    def get_template(cls, jenis):
        """
        Mengambil template pesan berdasarkan jenis transaksi.

        Cara kerja:
        - get_or_create() → ambil template dari DB
        - Jika belum ada → buat dengan default template dari _get_default_template()
        - Ini memastikan template SELALU tersedia tanpa setup manual

        Parameter:
            jenis (str): 'pos', 'sales_order', 'purchase_order', atau 'biaya'

        Return:
            TemplatePesan: instance template yang bisa dipakai

        Contoh:
            template = TemplatePesan.get_template('pos')
            pesan = template.template_pesan  # "🛒 *TRANSAKSI POS BARU*..."
        """
        obj, created = cls.objects.get_or_create(
            jenis=jenis,
            defaults={
                'nama': f'Template {dict(cls.JENIS_CHOICES).get(jenis, jenis)}',
                'template_pesan': cls._get_default_template(jenis),
                'aktif': True,
            }
        )
        return obj

    @classmethod
    def _get_default_template(cls, jenis):
        """
        Mendapatkan template default untuk setiap jenis transaksi.

        Template default dibuat dengan format:
        - Emoji header untuk identifikasi visual di Telegram
        - Garis pemisah (━━━) untuk keterbacaan
        - Placeholder {{variabel}} yang akan diganti data aktual
        - Format Markdown Telegram (*bold* untuk judul dan total)

        Parameter:
            jenis (str): Jenis transaksi ('pos', 'sales_order', dll)

        Return:
            str: String template default dengan placeholder

        Kenapa method ini private (_)?
        - Hanya dipanggil internal oleh get_template()
        - Tidak perlu diakses dari luar class
        """
        templates = {
            # ═══ Template POS ═══
            # Placeholder: nomor_transaksi, tanggal, kasir, gudang,
            # detail_items, subtotal, diskon, total, metode_pembayaran, status
            'pos': (
                "🛒 *TRANSAKSI POS BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_transaksi}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "👤 Kasir: {{kasir}}\n"
                "🏪 Gudang: {{gudang}}\n"
                "━━━━━━━━━━━━━━━\n"
                "{{detail_items}}\n"
                "━━━━━━━━━━━━━━━\n"
                "💰 Subtotal: Rp {{subtotal}}\n"
                "🏷️ Diskon: Rp {{diskon}}\n"
                "💵 *Total: Rp {{total}}*\n"
                "💳 Pembayaran: {{metode_pembayaran}}\n"
                "📊 Status: {{status}}"
            ),

            # ═══ Template Sales Order ═══
            # Placeholder: nomor_so, tanggal, customer, gudang,
            # detail_items, subtotal, diskon, total, status
            'sales_order': (
                "📦 *SALES ORDER BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_so}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "👤 Customer: {{customer}}\n"
                "🏪 Gudang: {{gudang}}\n"
                "━━━━━━━━━━━━━━━\n"
                "{{detail_items}}\n"
                "━━━━━━━━━━━━━━━\n"
                "💰 Subtotal: Rp {{subtotal}}\n"
                "🏷️ Diskon: Rp {{diskon}}\n"
                "💵 *Total: Rp {{total}}*\n"
                "📊 Status: {{status}}"
            ),

            # ═══ Template Purchase Order ═══
            # Placeholder: nomor_po, tanggal, supplier, gudang,
            # detail_items, subtotal, total, status
            'purchase_order': (
                "🛒 *PURCHASE ORDER BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_po}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "🏢 Supplier: {{supplier}}\n"
                "🏪 Gudang: {{gudang}}\n"
                "━━━━━━━━━━━━━━━\n"
                "{{detail_items}}\n"
                "━━━━━━━━━━━━━━━\n"
                "💰 Subtotal: Rp {{subtotal}}\n"
                "💵 *Total: Rp {{total}}*\n"
                "📊 Status: {{status}}"
            ),

            # ═══ Template Biaya ═══
            'biaya': (
                "💸 *TRANSAKSI BIAYA BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_transaksi}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "📂 Kategori: {{kategori}}\n"
                "💰 Jumlah: Rp {{jumlah}}\n"
                "📝 Deskripsi: {{deskripsi}}\n"
                "📊 Status: {{status}}\n"
                "👤 Dibuat oleh: {{dibuat_oleh}}"
            ),

            # ═══ Template Slip Gaji ═══
            'penggajian': (
                "💼 *SLIP GAJI KARYAWAN*\n"
                "━━━━━━━━━━━━━━━\n"
                "👤 Karyawan: {{nama_karyawan}}\n"
                "🏢 Jabatan: {{jabatan}}\n"
                "📅 Periode: {{periode}}\n"
                "━━━━━━━━━━━━━━━\n"
                "💰 Gaji Pokok: Rp {{gaji_pokok}}\n"
                "➕ Total Tunjangan: Rp {{tunjangan}}\n"
                "➖ Total Potongan: Rp {{potongan}}\n"
                "━━━━━━━━━━━━━━━\n"
                "💵 *Gaji Bersih: Rp {{gaji_bersih}}*\n"
                "📊 Status: {{status}}"
            ),
        }
        # Jika jenis tidak dikenali, gunakan template minimal
        return templates.get(jenis, "{{nomor_transaksi}} - {{total}}")


class LogNotifikasi(models.Model):
    """
    Log riwayat pengiriman notifikasi Telegram (sukses/gagal).

    Fungsi:
    1. Monitoring — admin bisa lihat notifikasi mana yang terkirim/gagal
    2. Debugging — jika gagal, error_message menunjukkan penyebabnya
    3. Audit Trail — riwayat lengkap notifikasi yang pernah dikirim

    Alur data:
    1. telegram_service.py mencoba kirim pesan via Telegram API
    2. Jika sukses → buat LogNotifikasi(status='sukses')
    3. Jika gagal → buat LogNotifikasi(status='gagal', error_message=...)
    4. Admin bisa lihat log di halaman /automation/telegram/ atau Django Admin

    Terhubung dengan:
    - telegram_service.py → Membuat record log setelah kirim pesan
    - views.py → Menampilkan log di halaman pengaturan Telegram
    """

    # ═══ CHOICES: Status Pengiriman ═══
    STATUS_CHOICES = [
        ('sukses', 'Sukses'),  # Pesan berhasil terkirim ke Telegram
        ('gagal', 'Gagal'),    # Pesan gagal terkirim (error API/network)
    ]

    # Menggunakan JENIS_CHOICES yang sama dengan TemplatePesan
    # Agar konsisten: 'pos', 'sales_order', 'purchase_order', 'biaya'
    JENIS_CHOICES = TemplatePesan.JENIS_CHOICES

    # ═══ FIELD: Jenis Transaksi ═══
    # Jenis transaksi yang memicu notifikasi ini
    jenis_transaksi = models.CharField(
        max_length=30,
        choices=JENIS_CHOICES,
        verbose_name="Jenis Transaksi"
    )

    # ═══ FIELD: Nomor Referensi ═══
    # Nomor unik transaksi (contoh: TRX-20260306-001, SO-2026-0088)
    # Berguna untuk trace: "notifikasi ini untuk transaksi mana?"
    nomor_referensi = models.CharField(
        max_length=100,
        verbose_name="Nomor Referensi"
    )

    # ═══ FIELD: Pesan yang Dikirim ═══
    # Isi pesan final yang dikirim ke Telegram (setelah placeholder diganti)
    # Disimpan sebagai bukti: "pesan apa yang persis dikirim?"
    pesan = models.TextField(
        verbose_name="Pesan yang Dikirim"
    )

    # ═══ FIELD: Status ═══
    # 'sukses' atau 'gagal' — hasil pengiriman
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        verbose_name="Status"
    )

    # ═══ FIELD: Respons API ═══
    # Body respons dari Telegram API (JSON string)
    # Berguna untuk debugging: response code, message_id, dll
    # null/blank jika gagal sebelum mendapat respons (network error)
    respons = models.TextField(
        blank=True,
        null=True,
        verbose_name="Respons API"
    )

    # ═══ FIELD: Pesan Error ═══
    # Detail error jika pengiriman gagal
    # Contoh: "401 Unauthorized" (token salah), "400 Bad Request" (chat_id salah)
    # null/blank jika pengiriman sukses
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="Pesan Error"
    )

    # ═══ FIELD: Timestamp ═══
    # Waktu pengiriman notifikasi
    dikirim_pada = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Dikirim Pada"
    )

    class Meta:
        """
        Metadata:
        - ordering: terbaru di atas → admin langsung lihat log terbaru
        """
        verbose_name = "Log Notifikasi"
        verbose_name_plural = "Log Notifikasi"
        ordering = ['-dikirim_pada']  # Terbaru di atas

    def __str__(self):
        """
        Representasi string: "[sukses] pos - TRX-20260306-001"
        Memberikan informasi status, jenis, dan nomor referensi sekaligus.
        """
        return f"[{self.status}] {self.jenis_transaksi} - {self.nomor_referensi}"
