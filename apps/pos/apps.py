"""
==========================================================================
 POS APPS - Konfigurasi aplikasi Django untuk modul POS/Kasir
==========================================================================
"""
from django.apps import AppConfig

class PosConfig(AppConfig):
    """Konfigurasi aplikasi POS (Point of Sale / Kasir)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pos'
    verbose_name = 'POS/Kasir'
    
    def ready(self):
        """Import signals saat aplikasi ready."""
        import apps.pos.signals  # noqa: F401
