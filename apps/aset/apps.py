from django.apps import AppConfig


class AsetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.aset'
    verbose_name = 'Aset Tetap (Fixed Assets)'

    def ready(self):
        """Import signals saat aplikasi ready."""
        import apps.aset.signals  # noqa: F401
