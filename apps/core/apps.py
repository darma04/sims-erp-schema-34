"""
==========================================================================
 CORE APP CONFIG - Konfigurasi Aplikasi Inti Sistem
==========================================================================
 File ini mengkonfigurasi modul Core — fondasi dari seluruh sistem ERP.

 Fungsi modul:
 - Sistem permission (RBAC — Role-Based Access Control)
 - Mixin permission untuk Class-Based Views
 - Context processor untuk menyuntikkan permission ke template
 - Custom template tags (permission_tags, core_tags, currency_filters)
 - Cache utilities untuk optimasi performa

 Terhubung dengan:
 - models.py → RolePermission (tabel permission per role per modul)
 - permissions.py → Logika pengecekan hak akses
 - mixins.py → Mixin class untuk views (SubModulePermissionMixin, dll)
 - context_processors.py → Menyuntikkan can_view/can_create/dll ke template
 - templatetags/ → Custom template tags untuk pengecekan permission
==========================================================================
"""
from django.apps import AppConfig  # Base class untuk konfigurasi app


class CoreConfig(AppConfig):
    """
    Konfigurasi aplikasi Core.

    Atribut:
    - default_auto_field: Tipe field ID otomatis (BigAutoField = integer 64-bit)
    - name: Nama modul Python lengkap (harus 'apps.core' karena ada di subfolder apps/)
    - verbose_name: Nama yang ditampilkan di admin panel
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'   # Path modul Python (folder apps/core/)
    verbose_name = 'Core'  # Nama yang ditampilkan di Django admin

    def ready(self):
        """Register signal invalidasi cache tampilan untuk data operasional."""
        from apps.core.cache_invalidation import register_data_cache_invalidation_signals
        register_data_cache_invalidation_signals()
