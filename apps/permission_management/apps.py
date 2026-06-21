from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_seed_permissions_first_run(sender, **kwargs):
    """Seed permission default hanya saat DB masih kosong (first run)."""
    from django.core.management import call_command
    from apps.core.models import RolePermission
    if not RolePermission.objects.exists():
        call_command('seed_permissions')


class PermissionManagementConfig(AppConfig):
    """Konfigurasi aplikasi Permission Management."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.permission_management'
    verbose_name = 'Permission Management'

    def ready(self):
        post_migrate.connect(auto_seed_permissions_first_run, sender=self)
