from django.db.models.signals import post_save
from django.dispatch import receiver
from auth.models import Profile


@receiver(post_save, sender=Profile)
def invalidate_cache_on_role_change(sender, instance, created, **kwargs):
    if not created:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.role != instance.role:
                from apps.core.cache_utils import invalidate_user_permissions_cache
                invalidate_user_permissions_cache(instance.user_id)
        except sender.DoesNotExist:
            pass
