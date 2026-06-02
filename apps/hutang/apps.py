from django.apps import AppConfig


class HutangConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hutang'
    verbose_name = 'Hutang (Accounts Payable)'

    def ready(self):
        """Import signals saat aplikasi ready — monitoring jurnal hutang."""
        import apps.hutang.signals  # noqa: F401
