"""
==========================================================================
 SERVICE CENTER APPS - Konfigurasi Aplikasi Service Center
==========================================================================
 Konfigurasi Django app untuk modul Service Center Elektronik.
 Modul ini menangani penerimaan, perbaikan, dan pengelolaan
 service perangkat elektronik (HP, TV, Laptop, dll).
==========================================================================
"""
from django.apps import AppConfig


class ServiceCenterConfig(AppConfig):
    """Konfigurasi aplikasi Service Center Elektronik."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.service_center'
    verbose_name = 'Service Center'

    def ready(self):
        """Import signals saat aplikasi ready."""
        import apps.service_center.signals  # noqa: F401
