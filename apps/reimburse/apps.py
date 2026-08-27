from django.apps import AppConfig


class ReimburseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.reimburse'
    verbose_name = 'Reimburse'

    def ready(self):
        import apps.reimburse.signals
