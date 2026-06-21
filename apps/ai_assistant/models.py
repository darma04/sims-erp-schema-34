"""
==========================================================================
 AI ASSISTANT MODELS - Konfigurasi, Riwayat Chat & Feedback
==========================================================================
 File ini mendefinisikan 3 model database untuk modul AI Assistant:

 1. AIAssistantConfig — Model Singleton untuk konfigurasi provider AI
    - Menyimpan: provider (Gemini/OpenAI/Groq), API key, model name,
      temperature, max tokens, system prompt, status aktif
    - Singleton: hanya ada 1 record di database (pk=1 selalu)
    - Diakses via: AIAssistantConfig.load() dari views.py
    - Kenapa singleton? Karena pengaturan AI bersifat global,
      berlaku untuk SEMUA user, bukan per-user config

 2. ChatHistory — Riwayat percakapan per user (context memory)
    - Menyimpan: pesan user & respons AI secara bergantian
    - Mendukung multi-user: setiap user punya riwayat sendiri
    - Digunakan untuk context memory (AI ingat percakapan sebelumnya)
    - Field 'intent' mencatat intent yang terdeteksi (penjualan, stok, dll)
    - Field 'source' mencatat sumber AI (gemini, openai, groq)

 3. ChatFeedback — Feedback 👍/👎 dari user untuk setiap respons AI
    - User bisa beri feedback positif/negatif untuk respons AI
    - Feedback terhubung ke ChatHistory via ForeignKey (opsional)
    - Digunakan untuk analisa kualitas respons AI

 Terhubung dengan:
 - views.py → ai_chat_api() menggunakan ChatHistory & AIAssistantConfig
 - admin.py → Mendaftarkan ketiga model ke Django Admin
 - intents.py → Menggunakan data dari model lain (Produk, SO, POS, dll)
 - templatetags/ai_tags.py → Mengambil ai_name dari AIAssistantConfig

 Konvensi penamaan field tanggal:
 - Modul ini menggunakan konvensi English (created_at, updated_at) untuk
   timestamp tracking, berbeda dengan modul inti yang menggunakan konvensi
   Indonesian (dibuat_pada, diupdate_pada, tanggal). Hal ini dipertahankan
   untuk konsistensi internal modul ini.
==========================================================================
"""

# Import modul Django yang diperlukan
from django.db import models        # Base class untuk semua model Django
from django.conf import settings    # Untuk mengakses AUTH_USER_MODEL (model User kustom)


class AIAssistantConfig(models.Model):
    """
    Model Singleton untuk menyimpan konfigurasi AI Chat Assistant.

    Singleton Pattern:
    - Hanya boleh ada 1 record di database (pk=1)
    - Method save() memaksa pk=1 → update, bukan create baru
    - Method load() mengambil record pk=1, buat default jika belum ada
    - Ini memastikan seluruh sistem menggunakan konfigurasi yang SAMA

    Diakses dari:
    - views.py → AIAssistantConfig.load() untuk mendapatkan config
    - admin.py → Admin bisa edit config via Django Admin panel
    - templatetags/ai_tags.py → Mengambil config.ai_name untuk header chat

    Provider yang didukung:
    - Google Gemini: gemini-2.0-flash (gratis tier awal)
    - OpenAI ChatGPT: gpt-4o-mini (berbayar)
    - Groq: llama-3.3-70b-versatile (GRATIS, 14.400 req/hari)
    """

    # ═══ CHOICES ═══
    # Daftar provider AI yang didukung sistem
    # Tuple format: (value_di_db, label_tampilan_di_form)
    PROVIDER_CHOICES = (
        ('gemini', 'Google Gemini'),      # Google AI Studio → SDK google.genai
        ('openai', 'OpenAI ChatGPT'),     # OpenAI Platform → REST API urllib
        ('groq', 'Groq (Gratis)'),        # Groq Console → REST API OpenAI-compatible
    )

    # ═══ FIELD: Provider AI ═══
    # Menentukan provider mana yang dipakai untuk memanggil API
    # Default 'groq' karena GRATIS dan performanya bagus
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default='groq',
        verbose_name="Provider AI"
    )

    # ═══ FIELD: API Key ═══
    # Kunci autentikasi untuk mengakses API provider
    # Blank/default '' → belum dikonfigurasi (fitur AI tidak aktif)
    # Max 500 karakter → cukup untuk semua jenis API key
    api_key = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name="API Key",
        help_text="API Key dari Google AI Studio, OpenAI Platform, atau Groq Console"
    )

    # ═══ FIELD: Nama Model AI ═══
    # Model spesifik yang digunakan untuk generate respons
    # Default: llama-3.3-70b-versatile (model terbaik Groq yang gratis)
    # Contoh lain: gemini-2.0-flash, gpt-4o-mini, mixtral-8x7b-32768
    model_name = models.CharField(
        max_length=100,
        default='llama-3.3-70b-versatile',
        verbose_name="Model AI",
        help_text="Contoh: gemini-2.0-flash, gpt-4o-mini, llama-3.3-70b-versatile"
    )

    # ═══ FIELD: Status Aktif ═══
    # Toggle on/off fitur AI secara keseluruhan
    # False → widget chat tidak muncul, API endpoint menolak request
    aktif = models.BooleanField(
        default=True,
        verbose_name="Status Aktif",
        help_text="Aktifkan/nonaktifkan fitur AI Chat"
    )

    # ═══ FIELD: Nama AI ═══
    # Nama yang ditampilkan di header widget chat
    # Bisa di-custom oleh admin (misal: "Asisten Bisnis", "ERP Bot")
    # Diambil via templatetag get_ai_name di template chat
    ai_name = models.CharField(
        max_length=100,
        default='AI Assistant',
        verbose_name="Nama AI",
        help_text="Nama yang ditampilkan di header chat AI"
    )

    # ═══ FIELD: Max Tokens ═══
    # Batas maksimal panjang respons AI (dalam token)
    # 1 token ≈ 4 karakter bahasa Inggris, ≈ 2-3 karakter Indonesia
    # 1024 token ≈ 500-700 kata respons
    # Semakin besar → respons lebih panjang, tapi lebih lambat & mahal
    max_tokens = models.IntegerField(
        default=1024,
        verbose_name="Max Tokens",
        help_text="Batas maksimal token respons AI"
    )

    # ═══ FIELD: Temperature ═══
    # Parameter kreativitas AI (0.0 sampai 1.0)
    # 0.0 = deterministik, respons selalu sama untuk pertanyaan sama
    # 0.7 = seimbang antara akurat dan kreatif (default)
    # 1.0 = sangat kreatif, bisa jadi tidak akurat
    temperature = models.FloatField(
        default=0.7,
        verbose_name="Temperature",
        help_text="Kreativitas AI (0.0 = fokus, 1.0 = kreatif)"
    )

    # ═══ FIELD: System Prompt Tambahan ═══
    # Instruksi tambahan untuk AI yang ditambahkan ke SYSTEM_PROMPT utama
    # Opsional: jika kosong, hanya SYSTEM_PROMPT default dari views.py yang dipakai
    # Contoh: "Selalu jawab dalam format bullet point", "Fokus ke analisa keuangan"
    system_prompt = models.TextField(
        blank=True,
        default='',
        verbose_name="System Prompt Tambahan",
        help_text="Instruksi tambahan untuk AI (opsional)"
    )

    # ═══ FIELD: Timestamp ═══
    # auto_now_add = diisi otomatis saat record PERTAMA KALI dibuat
    # auto_now = diisi otomatis SETIAP KALI record disimpan (update)
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Kapan config pertama dibuat
    diupdate_pada = models.DateTimeField(auto_now=True)     # Kapan config terakhir diubah

    class Meta:
        """
        Metadata model untuk Django Admin dan ORM.
        - verbose_name: Label tunggal (ditampilkan di admin)
        - verbose_name_plural: Label jamak (sama karena singleton)
        """
        verbose_name = "Pengaturan AI Assistant"
        verbose_name_plural = "Pengaturan AI Assistant"

    def __str__(self):
        """
        Representasi string model di Django Admin, dropdown, dan log.
        Contoh output: "AI Assistant (Groq (Gratis))"
        get_provider_display() mengkonversi 'groq' → 'Groq (Gratis)'
        """
        return f"AI Assistant ({self.get_provider_display()})"

    def save(self, *args, **kwargs):
        """
        Override save() untuk implementasi Singleton Pattern.

        Cara kerja:
        - Paksa self.pk = 1 sebelum save
        - Jika pk=1 sudah ada → UPDATE record yang ada
        - Jika pk=1 belum ada → CREATE record baru dengan pk=1
        - Efek: TIDAK PERNAH ada lebih dari 1 record

        Kenapa singleton?
        - Konfigurasi AI bersifat global (berlaku untuk semua user)
        - Tidak perlu menyimpan banyak konfigurasi berbeda
        - Menyederhanakan akses: cukup load() tanpa parameter
        """
        self.pk = 1  # Paksa primary key = 1 (singleton)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """
        Class method untuk memuat konfigurasi AI dari database.

        Cara kerja:
        - get_or_create(pk=1): ambil record pk=1, buat jika belum ada
        - Jika baru dibuat (created=True): semua field pakai default values
        - Return: instance AIAssistantConfig

        Penggunaan di views.py:
            config = AIAssistantConfig.load()
            provider = config.provider      # 'groq'
            api_key = config.api_key        # 'gsk_...'
            model = config.model_name       # 'llama-3.3-70b-versatile'
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class ChatHistory(models.Model):
    """
    Model untuk menyimpan riwayat chat per user.

    Fungsi utama:
    1. Context Memory → AI bisa ingat percakapan sebelumnya
       Saat user bertanya lagi, 10 pesan terakhir dikirim ke AI
       sebagai konteks, sehingga AI bisa melanjutkan pembahasan
    2. Multi-User → Setiap user punya riwayat chat terpisah
       User A dan User B tidak bisa melihat chat satu sama lain
    3. Analitik → Bisa menganalisa intent yang paling sering ditanya

    Alur data:
    1. User kirim pesan → views.py simpan ChatHistory(role='user')
    2. AI generate respons → views.py simpan ChatHistory(role='assistant')
    3. Pesan tersimpan bergantian: user, assistant, user, assistant...
    4. Saat load konteks: ambil 10 pesan terakhir berurutan

    Terhubung dengan:
    - views.py → ai_chat_api() menyimpan & memuat riwayat
    - views.py → chat_history_api() mengembalikan riwayat ke frontend
    - views.py → clear_history() menghapus semua riwayat user
    - ChatFeedback → Feedback terhubung ke pesan spesifik
    """

    # ═══ CHOICES ═══
    # Role untuk setiap pesan dalam percakapan
    ROLE_CHOICES = (
        ('user', 'User'),              # Pesan dari pengguna manusia
        ('assistant', 'AI Assistant'),  # Respons dari AI
    )

    # ═══ FIELD: User (Foreign Key) ═══
    # Setiap pesan dimiliki oleh SATU user
    # CASCADE: jika user dihapus, semua chat history-nya ikut terhapus
    # related_name: user.ai_chat_history.all() untuk akses dari User model
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,       # Mengacu ke model User aktif (bisa kustom)
        on_delete=models.CASCADE,       # Hapus riwayat saat user dihapus
        related_name='ai_chat_history', # Akses balik: user.ai_chat_history.all()
        verbose_name="User"
    )

    # ═══ FIELD: Role ═══
    # Menandai apakah pesan ini dari user atau dari AI
    # Penting untuk merekonstruksi percakapan secara bergantian
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        verbose_name="Role"
    )

    # ═══ FIELD: Pesan ═══
    # Isi pesan (bisa panjang, terutama respons AI yang detail)
    # TextField tanpa max_length → unlimited di database
    message = models.TextField(
        verbose_name="Pesan"
    )

    # ═══ FIELD: Intent Terdeteksi ═══
    # Intent yang terdeteksi dari pesan user (dari intents.py)
    # Contoh: 'penjualan', 'stok', 'biaya', 'keuntungan', 'karyawan'
    # Kosong jika tidak terdeteksi atau jika role='assistant'
    # Berguna untuk analisa: "intent apa yang paling sering ditanya?"
    intent = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name="Intent Terdeteksi"
    )

    # ═══ FIELD: Sumber AI ═══
    # Mencatat provider AI mana yang generate respons ini
    # Contoh: 'gemini', 'openai', 'groq', atau 'fallback'
    # Berguna untuk tracking: provider mana yang paling sering dipakai
    source = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name="Sumber AI"
    )

    # ═══ FIELD: Timestamp ═══
    # auto_now_add: diisi otomatis saat record dibuat
    # Digunakan untuk mengurutkan percakapan secara kronologis
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Waktu"
    )

    class Meta:
        """
        Metadata model:
        - ordering: urutkan berdasarkan waktu (lama → baru) agar percakapan runtut
        - indexes: index gabungan (user + created_at desc) untuk query cepat
          Kenapa index ini? Karena query paling sering:
          ChatHistory.objects.filter(user=user).order_by('-created_at')[:10]
        """
        verbose_name = "Riwayat Chat"
        verbose_name_plural = "Riwayat Chat"
        ordering = ['created_at']       # Urut kronologis (lama dulu)
        indexes = [
            # Index untuk mempercepat query filter per user + sort by waktu
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        """
        Representasi string: "[role] preview pesan..."
        Pesan dipotong 50 karakter pertama + '...' jika terlalu panjang
        Contoh: "[user] Berapa penjualan bulan ini?"
        Contoh: "[assistant] Berikut ringkasan penjualan bulan ini..."
        """
        preview = self.message[:50] + '...' if len(self.message) > 50 else self.message
        return f"[{self.role}] {preview}"


class ChatFeedback(models.Model):
    """
    Model untuk menyimpan feedback user terhadap respons AI.

    Fungsi:
    - User bisa klik 👍 (bagus) atau 👎 (kurang) pada setiap respons AI
    - Data feedback digunakan untuk:
      1. Evaluasi kualitas respons AI secara keseluruhan
      2. Identifikasi topik/intent yang kualitas responsnya rendah
      3. Bahan pertimbangan tuning parameter (temperature, system prompt)

    Alur data:
    1. AI menampilkan respons di widget chat
    2. Di bawah respons ada tombol 👍 dan 👎
    3. User klik salah satu → AJAX POST ke /ai/feedback/
    4. views.py → ChatFeedback.objects.create(...)
    5. Admin bisa lihat semua feedback di Django Admin

    Terhubung dengan:
    - views.py → chat_feedback() menyimpan feedback baru
    - ChatHistory → FK opsional ke pesan yang di-feedback
    - admin.py → ChatFeedbackAdmin menampilkan di admin panel
    """

    # ═══ CHOICES ═══
    # Jenis feedback yang bisa diberikan user
    FEEDBACK_CHOICES = (
        ('up', '👍 Bagus'),     # Respons AI memuaskan / akurat
        ('down', '👎 Kurang'),  # Respons AI kurang tepat / tidak membantu
    )

    # ═══ FIELD: User (FK) ═══
    # User yang memberikan feedback
    # Satu user bisa memberi banyak feedback (untuk respons berbeda)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,         # Hapus feedback saat user dihapus
        related_name='ai_chat_feedback',  # user.ai_chat_feedback.all()
        verbose_name="User"
    )

    # ═══ FIELD: Chat (FK, Opsional) ═══
    # Referensi ke pesan ChatHistory yang di-feedback
    # null=True, blank=True → feedback bisa tanpa referensi ke chat spesifik
    # Kenapa opsional? Karena frontend mungkin tidak selalu punya chat ID
    # (misal: feedback dikirim sebelum pesan tersimpan ke DB)
    chat = models.ForeignKey(
        ChatHistory,
        on_delete=models.CASCADE,  # Hapus feedback jika chat dihapus
        related_name='feedback',   # chat.feedback.all() untuk akses dari ChatHistory
        verbose_name="Chat",
        null=True,                 # Boleh NULL di database
        blank=True,                # Boleh kosong di form
    )

    # ═══ FIELD: Feedback ═══
    # Nilai feedback: 'up' (👍) atau 'down' (👎)
    # max_length=4 cukup untuk 'up' (2) dan 'down' (4)
    feedback = models.CharField(
        max_length=4,
        choices=FEEDBACK_CHOICES,
        verbose_name="Feedback"
    )

    # ═══ FIELD: Teks Pesan AI ═══
    # Salinan teks pesan AI yang di-feedback
    # Berguna untuk review admin tanpa harus JOIN ke ChatHistory
    # Juga sebagai backup jika ChatHistory terhapus
    message_text = models.TextField(
        blank=True,
        default='',
        verbose_name="Teks Pesan AI"
    )

    # ═══ FIELD: Timestamp ═══
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Waktu"
    )

    class Meta:
        """
        Metadata:
        - ordering: terbaru dulu (untuk admin melihat feedback terbaru di atas)
        """
        verbose_name = "Feedback Chat"
        verbose_name_plural = "Feedback Chat"
        ordering = ['-created_at']  # Terbaru di atas

    def __str__(self):
        """
        Representasi string: "👍 Bagus oleh admin"
        get_feedback_display() mengkonversi 'up' → '👍 Bagus'
        """
        return f"{self.get_feedback_display()} oleh {self.user}"
