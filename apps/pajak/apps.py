from django.apps import AppConfig


class PajakConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pajak'
    verbose_name = 'Pajak (Tax Engine)'

    def ready(self):
        """Import signals saat aplikasi ready — auto-jurnal PPN."""
        import apps.pajak.signals  # noqa: F401
