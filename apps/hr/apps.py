"""
==========================================================================
 HR APPS - Konfigurasi aplikasi Django untuk modul HR (SDM)
==========================================================================
"""
from django.apps import AppConfig

class HrConfig(AppConfig):
    """Konfigurasi aplikasi HR (Human Resources / Manajemen SDM)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hr'
    verbose_name = 'Manajemen HR'

    def ready(self):
        """Import signals saat aplikasi ready — auto-jurnal penggajian."""
        import apps.hr.signals  # noqa: F401
