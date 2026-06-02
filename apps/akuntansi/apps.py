"""
==========================================================================
 AKUNTANSI APPS - Konfigurasi aplikasi Django untuk modul Akuntansi
==========================================================================
"""
from django.apps import AppConfig


class AkuntansiConfig(AppConfig):
    """Konfigurasi aplikasi Akuntansi (Core Accounting Engine)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.akuntansi'
    verbose_name = 'Akuntansi'
