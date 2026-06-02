from django.apps import AppConfig


class KasBankConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kas_bank"
    verbose_name = "Kas & Bank / Treasury"

    def ready(self):
        """Import signals saat aplikasi ready — auto-jurnal mutasi & transfer."""
        import apps.kas_bank.signals  # noqa: F401
