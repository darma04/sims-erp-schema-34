"""
==========================================================================
 TENANT PROVISIONING API — Endpoint Internal untuk CLS
==========================================================================
 API ini HANYA boleh diakses oleh CLS (Central License Server).
 Dilindungi oleh API Key di header Authorization.

 Endpoints:
 - GET    /api/internal/tenants/                → Daftar semua tenant
 - POST   /api/internal/tenants/                → Buat tenant baru
 - GET    /api/internal/tenants/<schema_name>/   → Detail 1 tenant
 - DELETE /api/internal/tenants/<schema_name>/   → Hapus tenant + schema
==========================================================================
"""
import os
import json
import string
import secrets
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.contrib.auth.models import User

from .models import TenantClient, TenantDomain

import logging

logger = logging.getLogger(__name__)



# ==========================================================================
#  API KEY AUTHENTICATION
# ==========================================================================

def require_internal_api_key(view_func):
    """
    Decorator: Hanya izinkan request dengan API Key yang valid.
    Header: Authorization: Bearer <SAAS_INTERNAL_API_KEY>
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = os.environ.get('SAAS_INTERNAL_API_KEY', '')
        if not api_key:
            return JsonResponse(
                {"status": "error", "message": "Server belum dikonfigurasi (API key kosong)."},
                status=500
            )

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse(
                {"status": "error", "message": "Authorization header tidak valid."},
                status=401
            )

        provided_key = auth_header[7:]  # Strip "Bearer "
        if provided_key != api_key:
            return JsonResponse(
                {"status": "error", "message": "API Key tidak valid."},
                status=403
            )

        return view_func(request, *args, **kwargs)
    return wrapper


# ==========================================================================
#  HELPER: Generate Random Password
# ==========================================================================

def generate_password(length=10):
    """Generate password acak yang mudah dibaca (tanpa karakter ambigu)."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


# ==========================================================================
#  API ENDPOINTS
# ==========================================================================

@csrf_exempt
@require_internal_api_key
@require_http_methods(["GET", "POST"])
def tenant_list_create(request):
    """
    GET  → Daftar semua tenant (kecuali public).
    POST → Buat tenant baru + domain + superuser.
    """
    if request.method == "GET":
        tenants = TenantClient.objects.exclude(schema_name='public').order_by('-created_at')
        data = []
        for t in tenants:
            domains = list(t.domains.values_list('domain', flat=True))
            data.append({
                "id": t.id,
                "nama": t.nama,
                "schema_name": t.schema_name,
                "domains": domains,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })
        return JsonResponse({"status": "success", "count": len(data), "tenants": data})

    # === POST: Buat tenant baru ===
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Format JSON tidak valid."},
            status=400
        )

    nama = body.get('nama', '').strip()
    schema_name = body.get('schema_name', '').strip()
    domain = body.get('domain', '').strip()

    # Validasi
    if not nama:
        return JsonResponse({"status": "error", "message": "Field 'nama' wajib diisi."}, status=400)
    if not schema_name:
        return JsonResponse({"status": "error", "message": "Field 'schema_name' wajib diisi."}, status=400)
    if not domain:
        return JsonResponse({"status": "error", "message": "Field 'domain' wajib diisi."}, status=400)

    # Validasi schema_name (hanya huruf kecil, angka, underscore)
    import re
    if not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
        return JsonResponse({
            "status": "error",
            "message": "schema_name hanya boleh huruf kecil, angka, dan underscore. Harus diawali huruf."
        }, status=400)

    # Cek duplikat
    if TenantClient.objects.filter(schema_name=schema_name).exists():
        return JsonResponse({"status": "error", "message": f"Schema '{schema_name}' sudah ada."}, status=409)
    if TenantDomain.objects.filter(domain=domain).exists():
        return JsonResponse({"status": "error", "message": f"Domain '{domain}' sudah digunakan."}, status=409)

    try:
        # 1. Buat tenant (auto_create_schema=True → PostgreSQL buat schema + tabel)
        tenant = TenantClient(schema_name=schema_name, nama=nama)
        tenant.save()

        # 2. Buat domain
        TenantDomain.objects.create(tenant=tenant, domain=domain, is_primary=True)

        # 3. Buat superuser di schema baru
        admin_password = generate_password(10)
        connection.set_tenant(tenant)
        superuser = User.objects.create_superuser(
            username='admin',
            email=f'admin@{domain}',
            password=admin_password
        )

        # PENTING: Reset koneksi ke public schema setelah operasi tenant
        # Mencegah data leak — request berikutnya di thread yang sama
        # bisa masih menggunakan schema tenant jika tidak di-reset
        connection.set_schema_to_public()

        return JsonResponse({
            "status": "success",
            "message": f"Tenant '{nama}' berhasil dibuat.",
            "data": {
                "id": tenant.id,
                "nama": tenant.nama,
                "schema_name": tenant.schema_name,
                "domain": domain,
                "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                "superuser": {
                    "username": "admin",
                    "password": admin_password,
                    "email": superuser.email,
                }
            }
        }, status=201)

    except Exception as e:
        # Pastikan selalu reset ke public meskipun terjadi error
        try:
            connection.set_schema_to_public()
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        return JsonResponse(
            {"status": "error", "message": f"Gagal membuat tenant: {str(e)}"},
            status=500
        )


@csrf_exempt
@require_internal_api_key
@require_http_methods(["GET", "DELETE"])
def tenant_detail_delete(request, schema_name):
    """
    GET    → Detail 1 tenant.
    DELETE → Hapus tenant + schema PostgreSQL.
    """
    try:
        tenant = TenantClient.objects.get(schema_name=schema_name)
    except TenantClient.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": f"Tenant '{schema_name}' tidak ditemukan."},
            status=404
        )

    if schema_name == 'public':
        return JsonResponse(
            {"status": "error", "message": "Schema 'public' tidak boleh dihapus."},
            status=403
        )

    if request.method == "GET":
        domains = list(tenant.domains.values_list('domain', flat=True))

        # Hitung jumlah tabel di schema
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s;",
                [schema_name]
            )
            table_count = cursor.fetchone()[0]

        # Hitung jumlah user dan ambil data superuser di schema
        user_count = 0
        superusers = []
        try:
            connection.set_tenant(tenant)
            user_count = User.objects.count()
            su_list = User.objects.filter(is_superuser=True).values(
                'id', 'username', 'email', 'date_joined', 'is_active'
            )
            superusers = [
                {
                    'id': su['id'],
                    'username': su['username'],
                    'email': su['email'],
                    'is_active': su['is_active'],
                    'date_joined': su['date_joined'].isoformat() if su['date_joined'] else None,
                }
                for su in su_list
            ]
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        finally:
            # PENTING: Selalu reset ke public schema setelah query tenant
            try:
                connection.set_schema_to_public()
            except Exception as e:
                logger.warning("Error tidak terduga: %s", e)

        return JsonResponse({
            "status": "success",
            "data": {
                "id": tenant.id,
                "nama": tenant.nama,
                "schema_name": tenant.schema_name,
                "domains": domains,
                "table_count": table_count,
                "user_count": user_count,
                "superusers": superusers,
                "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
            }
        })

    # === DELETE ===
    try:
        tenant.delete(force_drop=True)
        return JsonResponse({
            "status": "success",
            "message": f"Tenant '{schema_name}' dan semua datanya berhasil dihapus."
        })
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": f"Gagal menghapus tenant: {str(e)}"},
            status=500
        )
