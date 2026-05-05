"""
==========================================================================
 AUTH MODELS - Model Profile User
==========================================================================
 File ini mendefinisikan model Profile yang memperluas (extend) model
 User bawaan Django dengan informasi tambahan.

 Mengapa perlu Profile terpisah?
 - Model User bawaan Django hanya punya: username, email, password,
   first_name, last_name, is_staff, is_superuser, is_active
 - Kita butuh field tambahan: role, avatar, phone, token verifikasi
 - Cara terbaik: buat Profile dengan OneToOneField ke User
   (setiap User punya tepat 1 Profile, dan sebaliknya)

 Koneksi:
 - django.contrib.auth.models.User → Model User bawaan Django (parent)
 - apps/core/models.py → RolePermission (menggunakan role dari Profile)
 - apps/core/permissions.py → get_user_role() membaca profile.role
 - auth/admin.py → Profile didaftarkan di admin panel
 - Signal post_save → Otomatis membuat Profile saat User baru dibuat
==========================================================================
"""

from django.db import models                    # Django ORM untuk definisi model database
from django.contrib.auth.models import User      # Model User bawaan Django
from django.db.models.signals import post_save   # Signal yang terpicu SETELAH model disimpan
from django.dispatch import receiver             # Decorator untuk menghubungkan signal ke fungsi


class Profile(models.Model):
    """
    Model Profile - Memperluas data User bawaan Django.

    Relasi:
    - OneToOneField ke User → Setiap user punya tepat 1 profile
    - Diakses dari user: user.profile (karena related_name='profile')
    - Diakses dari profile: profile.user

    Field utama:
    - role → Menentukan hak akses (SUPERUSER/ADMIN/USER/KASIR)
    - email_token → Token untuk verifikasi email saat registrasi
    - forget_password_token → Token untuk reset password
    - avatar → Foto profil user
    """

    # ==================== PILIHAN ROLE (Static) ====================
    # Daftar role bawaan — untuk backward compatibility
    # Role dinamis bisa ditambah melalui RolePermission
    ROLE_CHOICES = [
        ('SUPERUSER', 'Superuser - Full Access'),    # Akses penuh, bypass semua permission
        ('ADMIN', 'Admin - Limited Access'),          # Admin dengan akses terbatas
        ('USER', 'User - Read & Create Only'),        # User biasa: baca & buat data
        ('KASIR', 'Kasir - POS Access Only'),         # Kasir: hanya akses modul POS
    ]

    # ==================== FIELD RELASI ====================
    # OneToOneField: Setiap User hanya bisa punya 1 Profile
    # on_delete=CASCADE: Jika User dihapus, Profile ikut terhapus
    # related_name='profile': Akses dari user → user.profile
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # ==================== FIELD DATA ====================
    # Email unik — digunakan untuk login alternatif dan komunikasi
    email = models.EmailField(max_length=100, unique=True)

    # Role user — menentukan hak akses di seluruh sistem
    # max_length=50: Cukup untuk nama role kustom yang panjang
    # choices=[]: Kosong agar bisa menerima APAPUN (role dinamis dari database)
    # Default 'USER' untuk user baru
    role = models.CharField(
        max_length=50,
        choices=[],           # Dynamic choices — menerima semua nilai
        default='USER',
        verbose_name="Role",
        help_text="User role for access control"
    )

    @classmethod
    def get_role_choices(cls):
        """
        Mendapatkan daftar role yang tersedia, termasuk role dinamis.

        Memanggil RolePermission.get_all_roles() untuk mengambil
        semua role yang terdaftar di database (bukan hardcoded).

        Return: List of tuples [('ADMIN', 'Admin'), ('KASIR', 'Kasir'), ...]
        """
        from apps.core.models import RolePermission
        return RolePermission.get_all_roles()

    # ==================== FIELD TOKEN & VERIFIKASI ====================
    # Token untuk verifikasi email — dikirim via email saat registrasi
    # Format: UUID (contoh: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890')
    email_token = models.CharField(max_length=100, blank=True, null=True)

    # Token untuk reset password — dikirim via email saat lupa password
    forget_password_token = models.CharField(max_length=100, blank=True, null=True)

    # Waktu kadaluarsa token reset password (biasanya 24 jam setelah request)
    forget_password_token_expiration = models.DateTimeField(blank=True, null=True)

    # Status apakah email sudah diverifikasi
    # False saat pertama registrasi, True setelah klik link verifikasi
    is_verified = models.BooleanField(default=False)

    # ==================== FIELD PROFIL ====================
    # Foto profil user — disimpan di folder media/avatars/
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Foto Profil")

    # Nomor telepon user (opsional)
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Nomor Telepon")

    # ==================== FIELD TRACKING ====================
    # Tanggal pembuatan profile — otomatis diisi saat pertama disimpan
    created_at = models.DateTimeField(auto_now_add=True)

    # ==================== METHOD ====================
    def save(self, *args, **kwargs):
        """
        Override method save untuk normalisasi role.

        Sebelum menyimpan ke database:
        1. Hapus spasi di awal/akhir role (strip)
        2. Ubah ke UPPERCASE (contoh: 'admin' → 'ADMIN')

        Ini memastikan konsistensi data role di database
        sehingga pengecekan permission tidak case-sensitive.
        """
        if self.role:
            self.role = self.role.strip().upper()
        super().save(*args, **kwargs)

    def get_role_display(self):
        """
        Mendapatkan nama role yang mudah dibaca manusia.

        Contoh:
        - 'SUPERUSER' → 'Superuser - Full Access'
        - 'STAFF_GUDANG' → 'Staff Gudang' (dari format otomatis)

        Langkah:
        1. Ambil semua role dari RolePermission.get_all_roles()
        2. Cari role user saat ini di daftar tersebut
        3. Jika tidak ketemu → format otomatis: ganti '_' dengan spasi, capitalize
        """
        from apps.core.models import RolePermission
        all_roles = dict(RolePermission.get_all_roles())
        return all_roles.get(self.role, self.role.replace('_', ' ').title())

    def __str__(self):
        """Representasi string Profile — menampilkan username"""
        return self.user.username

    def get_avatar_url(self):
        """
        Mendapatkan URL foto profil.

        Jika user sudah upload avatar → kembalikan URL file yang diupload
        Jika belum → kembalikan avatar default (gambar bawaan)
        """
        if self.avatar:
            return self.avatar.url
        return '/static/img/avatars/1.png'  # Avatar default

    # ==================== SIGNAL: Auto-create Profile ====================
    @receiver(post_save, sender=User)
    def create_profile(sender, instance, created, **kwargs):
        """
        Signal handler — OTOMATIS dipanggil setiap kali User disimpan.

        Cara kerja signal post_save:
        1. User.objects.create_user() dipanggil (misal: saat registrasi)
        2. Django mengirimkan signal post_save
        3. Fungsi ini menangkap signal dan cek: apakah User baru dibuat?
        4. Jika ya (created=True) → buat Profile baru untuk User tersebut

        Parameter signal:
        - sender: Model yang mengirim signal (User)
        - instance: Object User yang baru disimpan
        - created: True jika ini CREATE baru, False jika UPDATE
        - kwargs: Argumen tambahan

        Kenapa pakai signal?
        - Agar Profile SELALU dibuat saat User baru, tanpa perlu
          menambahkan kode di setiap tempat User dibuat
        - DRY (Don't Repeat Yourself)
        """
        if created:
            Profile.objects.get_or_create(user=instance, defaults={'email': instance.email})

    # ==================== META ====================
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
