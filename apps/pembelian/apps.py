"""
==========================================================================
 PEMBELIAN APPS - Konfigurasi aplikasi Django untuk modul Pembelian
==========================================================================
"""

from django.apps import AppConfig


class PembelianConfig(AppConfig):
    """Konfigurasi aplikasi Pembelian (Purchase Module)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pembelian'
    verbose_name = 'Pembelian'
    
    def ready(self):
        """Import signals saat aplikasi ready."""
        import apps.pembelian.signals  # noqa: F401
