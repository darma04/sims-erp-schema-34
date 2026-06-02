"""
==========================================================================
 BIAYA APPS - Konfigurasi aplikasi Django untuk modul Biaya
==========================================================================
"""
from django.apps import AppConfig

class BiayaConfig(AppConfig):
    """Konfigurasi aplikasi Biaya (Expense Management)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.biaya'
    verbose_name = 'Biaya'

    def ready(self):
        """Import signals saat aplikasi ready."""
        import apps.biaya.signals  # noqa: F401
