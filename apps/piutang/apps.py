from django.apps import AppConfig


class PiutangConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.piutang'
    verbose_name = 'Piutang (Accounts Receivable)'

    def ready(self):
        """Import signals saat aplikasi ready — monitoring jurnal piutang."""
        import apps.piutang.signals  # noqa: F401
