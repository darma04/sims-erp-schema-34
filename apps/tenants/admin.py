from django.contrib import admin
from .models import TenantClient, TenantDomain


@admin.register(TenantClient)
class TenantClientAdmin(admin.ModelAdmin):
    list_display = ('nama', 'schema_name', 'created_at')


@admin.register(TenantDomain)
class TenantDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
