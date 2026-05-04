"""
==========================================================================
 CUSTOM TENANT ROUTER — Wrapper TenantSyncRouter + SQLite Fallback
==========================================================================
 Router ini membungkus django_tenants.routers.TenantSyncRouter agar
 kompatibel dengan SQLite mode (development tanpa PostgreSQL).

 Saat PostgreSQL → delegasi ke TenantSyncRouter (multi-tenant routing)
 Saat SQLite → izinkan semua migrasi (single-tenant, tanpa schema)
==========================================================================
"""
from django_tenants.routers import TenantSyncRouter


class SafeTenantSyncRouter(TenantSyncRouter):
    """
    TenantSyncRouter yang aman untuk digunakan dengan SQLite.
    Saat database engine bukan django_tenants PostgreSQL backend,
    router ini akan mem-bypass logic schema_name dan mengizinkan
    semua migrasi secara normal.
    """

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        from django.db import connections

        connection = connections[db]

        # Jika backend bukan django_tenants (misal: SQLite),
        # izinkan semua migrasi tanpa schema routing
        if not hasattr(connection, 'schema_name'):
            return None

        # Jika PostgreSQL backend django_tenants, gunakan logic asli
        return super().allow_migrate(db, app_label, model_name=model_name, **hints)
