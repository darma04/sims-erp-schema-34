"""
==========================================================================
 AUTH APPS - Konfigurasi Aplikasi Auth
==========================================================================
 File ini mengkonfigurasi aplikasi 'auth' sebagai Django App.

 Kenapa label='accounts'?
 - Django sudah punya app bawaan bernama 'django.contrib.auth'
 - Nama app kita juga 'auth' → KONFLIK!
 - Solusi: Gunakan label='accounts' sebagai identitas unik di Django
 - Di database, tabel akan bernama 'accounts_profile' bukan 'auth_profile'

 Koneksi:
 - config/settings.py → INSTALLED_APPS: "auth.apps.AuthConfig"
 - auth/models.py → Model Profile (tabel: accounts_profile)
 - auth/admin.py → Admin registration
==========================================================================
"""

from django.apps import AppConfig  # Base class untuk konfigurasi app


class AuthConfig(AppConfig):
    """
    Konfigurasi aplikasi Auth.

    Atribut:
    - default_auto_field: Tipe field ID otomatis (BigAutoField = integer 64-bit)
    - name: Nama modul Python (harus sesuai dengan nama folder)
    - label: Label unik untuk menghindari konflik dengan django.contrib.auth
    """
    default_auto_field = 'django.db.models.BigAutoField'  # Tipe ID otomatis
    name = 'auth'       # Nama modul Python (folder 'auth/')
    label = 'accounts'  # Label unik di Django (menghindari konflik dengan 'django.contrib.auth')

    def ready(self):
        import auth.signals  # lazy import
