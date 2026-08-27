from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.core.models import RolePermission


@receiver([post_save, post_delete], sender=RolePermission)
def invalidate_role_permission_cache(sender, instance, **kwargs):
    if instance and instance.role:
        from apps.core.cache_utils import invalidate_role_permissions_cache
        invalidate_role_permissions_cache(instance.role)
