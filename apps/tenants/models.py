"""
==========================================================================
 TENANTS MODELS — Model Routing Multi-Tenant (Isolated Schema)
==========================================================================
 Model ini BUKAN pengganti CLS (Central License Server).
 Ini hanya 'peta routing' agar django-tenants tahu:
 subdomain X → arahkan ke schema X di PostgreSQL.

 Data klien yang sebenarnya (lisensi, durasi, pembayaran)
 tetap dikelola 100% oleh CLS.

 Koneksi:
 - config/settings.py → TENANT_MODEL & TENANT_DOMAIN_MODEL
 - django_tenants middleware → Membaca model ini untuk routing
 - CLS API → Membuat record baru di sini saat generate license
==========================================================================
"""
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class TenantClient(TenantMixin):
    """
    Peta routing tenant.
    Setiap record mewakili 1 perusahaan/klien.
    Field 'schema_name' otomatis disediakan oleh TenantMixin.
    """
    nama = models.CharField(max_length=150, verbose_name="Nama Perusahaan")
    created_at = models.DateTimeField(auto_now_add=True)

    # Otomatis buat schema PostgreSQL saat save()
    auto_create_schema = True

    def __str__(self):
        return f"{self.nama} ({self.schema_name})"

    class Meta:
        verbose_name = "Tenant (Klien)"
        verbose_name_plural = "Tenant (Klien)"


class TenantDomain(DomainMixin):
    """
    Menyimpan domain/subdomain untuk setiap tenant.
    Contoh: toko-budi.erp-anda.com → schema 'toko_budi'
    """

    def __str__(self):
        return self.domain

    class Meta:
        verbose_name = "Domain Tenant"
        verbose_name_plural = "Domain Tenant"
