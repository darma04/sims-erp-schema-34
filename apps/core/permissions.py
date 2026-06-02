"""
==========================================================================
 CORE PERMISSIONS - Fungsi Utilitas Pengecekan Hak Akses
==========================================================================
 File ini berisi fungsi-fungsi untuk mengecek hak akses user.
 Semua permission 100% diambil dari database (RolePermission model).
 Tidak ada fallback hardcoded — jika tidak ada config di DB, akses DITOLAK.

 Fungsi utama:
 - get_user_role(user) → Mendapatkan role user
 - has_permission(user, action, module, sub_module) → Cek hak akses
 - get_accessible_submodules(user, module) → Sub-modul yang bisa dilihat
 - role_required(*roles) → Decorator untuk membatasi akses berdasarkan role
 - permission_required(action, module) → Decorator untuk membatasi akses

 Alur pengecekan permission:
 1. Ambil role user dari Profile
 2. Jika SUPERUSER → izinkan semua (bypass)
 3. Jika bukan → query RolePermission di database
 4. Cek field yang sesuai (can_view, can_create, dll)
 5. Jika tidak ada record → akses DITOLAK

 Koneksi:
 - auth/models.py → Profile.role (sumber role user)
 - apps/core/models.py → RolePermission (sumber data permission)
 - apps/core/mixins.py → Mixin yang memanggil has_permission()
 - apps/core/context_processors.py → PermissionChecker yang membungkus ini
 - Semua views → Menggunakan mixin/decorator dari file ini
==========================================================================
"""

from functools import wraps                     # Untuk decorator yang mempertahankan metadata fungsi
# Import dari framework Django
from django.core.exceptions import PermissionDenied  # Exception 403 Forbidden
# Import dari framework Django
from django.shortcuts import redirect           # Fungsi redirect ke URL lain
# Import dari framework Django
from django.contrib import messages              # Framework pesan flash


SUPERUSER_ROLE_CODES = {'SUPERUSER', 'PEMILIK'}


def get_user_role(user):
    """
    Mendapatkan role user dari Profile-nya.

    Hierarki:
    1. Jika user tidak login → return None
    2. Jika user.is_superuser (superuser Django) → return 'SUPERUSER'
    3. Jika user punya profile → return profile.role (UPPERCASE)
    4. Jika gagal (profile belum ada) → return 'USER' (default)

    Parameter:
    - user: Object User Django (dari request.user)

    Return: String role (UPPERCASE) atau None jika belum login

    Kenapa is_superuser dicek terpisah?
    - is_superuser adalah flag di model User bawaan Django
    - User yang dibuat via createsuperuser otomatis punya is_superuser=True
    - Ini berbeda dengan role 'SUPERUSER' di Profile → keduanya dianggap sama
    """
    if not user.is_authenticated:
        return None

    # Superuser Django (dari createsuperuser command) → selalu SUPERUSER
    if user.is_superuser:
        return 'SUPERUSER'

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Ambil role dari Profile (via relasi OneToOne: user.profile)
        role = user.profile.role
        role = role.upper() if role else 'USER'
        if role in SUPERUSER_ROLE_CODES:
            return 'SUPERUSER'
        return role
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception:
        # Jika profile belum ada (error), default ke 'USER'
        return 'USER'


def is_superuser_role(user):
    """True jika user adalah Django superuser atau role bisnis full-access."""
    return get_user_role(user) == 'SUPERUSER'


def has_permission(user, action, module=None, sub_module=None):
    """
    Fungsi INTI — Mengecek apakah user punya hak akses untuk aksi tertentu.

    Parameter:
    - user: Object User Django
    - action: Jenis aksi — 'create', 'read'/'view', 'update'/'write', 'delete'
    - module: Nama modul (contoh: 'produk', 'inventory', 'access-control')
    - sub_module: Nama sub-modul opsional (contoh: 'kategori', 'gudang')

    Return: True jika diizinkan, False jika ditolak

    OPTIMASI: Semua permission untuk sebuah role di-load sekali dari DB
    dan di-cache selama 30 detik. Satu page load hanya 1 DB query,
    bukan 20-40+ query seperti sebelumnya.
    """
    role = get_user_role(user)

    if not role:
        return False

    # Superuser selalu punya semua akses (tidak bisa dibatasi)
    if role == 'SUPERUSER':
        return True

    # Semua role lain → cek di cache permission
    if module:
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            # Normalisasi: 'access-control' → 'access_control' (sesuai format di DB)
            module_normalized = module.replace('-', '_').lower()

            # Mapping aksi ke field database
            action_map = {
                'add': 'can_create',
                'create': 'can_create',
                'read': 'can_view',
                'view': 'can_view',
                'edit': 'can_edit',
                'update': 'can_edit',
                'write': 'can_edit',
                'delete': 'can_delete',
                'del': 'can_delete',
                'remove': 'can_delete'
            }
            perm_field = action_map.get(action)
            if not perm_field:
                return False

            # Ambil cache permission (1 query per role, di-cache 30 detik)
            perms_cache = _get_role_permissions_cache(role)

            # ===== CEK SUB-MODULE DULU (lebih spesifik) =====
            if sub_module:
                sub_key = (module_normalized, sub_module.lower())
                if sub_key in perms_cache:
                    sub_value = perms_cache[sub_key].get(perm_field, False)
                    if sub_value:
                        return True
                    # Sub-modul ada tapi permission False →
                    # fallback ke module level (karena UI hanya set can_view untuk sub-modul)

            # ===== CEK MODULE LEVEL (fallback) =====
            mod_key = (module_normalized, None)
            if mod_key in perms_cache:
                return perms_cache[mod_key].get(perm_field, False)

            # ===== FALLBACK SUB-MODULE =====
            # Jika user mengecek level modul, tapi database hanya punya record level sub-modul
            # (karena checkbox UI hanya ada di level sub-modul), anggap True jika ADA minimal
            # 1 sub-modul di modul ini yang memiliki permission tersebut.
            if not sub_module:
                for (mod, sub), perm_dict in perms_cache.items():
                    if mod == module_normalized and sub is not None and perm_dict.get(perm_field, False):
                        return True

            # Tidak ada permission record → DITOLAK
            return False

        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            return False

    return False


def has_exact_submodule_permission(user, action, module, sub_module):
    """
    Cek permission sub-module tanpa fallback ke module-level.
    Dipakai untuk tombol/fitur global yang harus bisa disembunyikan eksplisit
    dari Add/Edit Role Permission.
    """
    role = get_user_role(user)

    if not role:
        return False

    if role == 'SUPERUSER':
        return True

    if not module or not sub_module:
        return False

    try:
        module_normalized = module.replace('-', '_').lower()
        sub_module_normalized = sub_module.replace('-', '_').lower()
        action_map = {
            'add': 'can_create',
            'create': 'can_create',
            'read': 'can_view',
            'view': 'can_view',
            'edit': 'can_edit',
            'update': 'can_edit',
            'write': 'can_edit',
            'delete': 'can_delete',
            'del': 'can_delete',
            'remove': 'can_delete',
        }
        perm_field = action_map.get(action)
        if not perm_field:
            return False

        perms_cache = _get_role_permissions_cache(role)
        return perms_cache.get((module_normalized, sub_module_normalized), {}).get(perm_field, False)
    except Exception:
        return False


def _get_role_permissions_cache(role):
    """
    Load SEMUA permissions untuk sebuah role dalam 1 query dan cache.

    Return: Dictionary {(module, sub_module): {can_view, can_create, can_edit, can_delete}}
    Cache TTL: 5 menit, dengan versioned invalidation saat permission role berubah.
    """
    from django.core.cache import cache
    from apps.core.cache_utils import get_role_permissions_cache_key, normalize_role_code

    role = normalize_role_code(role)
    cache_key = get_role_permissions_cache_key(role)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Import dari modul internal proyek
    from apps.core.models import RolePermission
    perms_dict = {}

    # Satu query untuk SEMUA permission role ini
    all_perms = RolePermission.objects.filter(
        role__iexact=role
    ).order_by().values('module', 'sub_module', 'can_view', 'can_create', 'can_edit', 'can_delete')

    for p in all_perms:
        mod = p['module'].lower() if p['module'] else ''
        sub = p['sub_module'].lower() if p['sub_module'] else None
        key = (mod, sub)
        perms_dict[key] = {
            'can_view': p['can_view'],
            'can_create': p['can_create'],
            'can_edit': p['can_edit'],
            'can_delete': p['can_delete'],
        }

    cache.set(cache_key, perms_dict, 300)  # Cache 5 menit, aman karena invalidasi berbasis versi
    return perms_dict


def get_accessible_submodules(user, module):
    """
    Mendapatkan daftar sub-modul yang bisa DILIHAT user dalam sebuah modul.
    Digunakan untuk MEMFILTER sidebar (menyembunyikan submenu yang tidak diizinkan).

    OPTIMASI: Menggunakan cache permission yang sama, tanpa query tambahan.
    """
    role = get_user_role(user)

    if not role:
        return []

    # Superuser bisa lihat SEMUA sub-modules
    if role == 'SUPERUSER':
        from apps.core.models import RolePermission
        module_normalized = module.replace('-', '_').lower()
        return [
            RolePermission.SUB_MODULE_TO_SLUG.get(sub_code, sub_code)
            for sub_code, _ in RolePermission.SUB_MODULE_CHOICES.get(module_normalized, [])
        ]

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Import dari modul internal proyek
        from apps.core.models import RolePermission

        # Normalisasi nama modul
        module_normalized = module.replace('-', '_').lower()

        # Ambil dari cache (sama dengan has_permission, tidak ada query baru)
        perms_cache = _get_role_permissions_cache(role)

        result = []
        for (mod, sub), perms in perms_cache.items():
            if mod == module_normalized and sub is not None and perms.get('can_view', False):
                # Konversi kode database ke slug menu
                slug = RolePermission.SUB_MODULE_TO_SLUG.get(sub, sub)
                if slug and slug not in result:
                    result.append(slug)

        return result

    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_accessible_submodules for user {user.username}, module {module}: {e}")
        return []


# Cache untuk data menu JSON (dibaca sekali dari disk, tidak perlu baca ulang)
# v2: Reset cache setelah fix duplikat slug "laporan" → "laporan-keuangan"
_menu_cache = None


def get_all_submodules_from_menu(module):
    """
    Mendapatkan SEMUA sub-modul untuk sebuah modul dari file vertical_menu.json.
    Digunakan untuk superuser yang bisa melihat semua sub-modul.

    OPTIMASI: File JSON hanya dibaca SEKALI dari disk dan di-cache di memori.
    """
    global _menu_cache
    import json
    import os
    # Import dari framework Django
    from django.conf import settings

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Reverse mapping: DB module → menu slug
        MODULE_TO_SLUG = {
            'user_management': 'users',
            'laporan_keuangan': 'laporan-keuangan',
        }

        # Cache menu data di memori (baca file hanya sekali)
        if _menu_cache is None:
            menu_path = os.path.join(
                settings.BASE_DIR,
                'templates/layout/partials/menu/vertical/json/vertical_menu.json'
            )
            with open(menu_path, 'r', encoding='utf-8') as f:
                _menu_cache = json.load(f)

        # Cari modul di menu (normalisasi dash dan underscore)
        module_norm = module.lower().replace('-', '_')
        menu_slug_norm = MODULE_TO_SLUG.get(module_norm, module_norm)

        for item in _menu_cache.get('menu', []):
            item_slug_norm = item.get('slug', '').lower().replace('-', '_')
            if (item_slug_norm == module_norm or item_slug_norm == menu_slug_norm) and 'submenu' in item:
                # Ekstrak slug sub-modul dari submenu
                subs = []
                for sub_item in item['submenu']:
                    sub_slug = sub_item.get('slug', '')
                    if '-' in sub_slug:
                        sub_name = sub_slug.split('-', 1)[1]
                    else:
                        sub_name = sub_slug

                    sub_name_lower = sub_name.lower()
                    if sub_name_lower not in subs:
                        subs.append(sub_name_lower)
                return subs

        return []

    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error reading vertical_menu.json for module {module}: {e}")
        return []


def role_required(*allowed_roles):
    """
    Decorator untuk membatasi akses view berdasarkan role.

    Cara pakai:
        @role_required('SUPERUSER', 'ADMIN')
        # Fungsi my_view
        def my_view(request):
            ...

    Alur:
    1. Ambil role user
    2. Jika role ada di daftar yang diizinkan → lanjutkan ke view
    3. Jika tidak → tampilkan pesan error dan redirect ke dashboard

    Apa itu Decorator?
    - Fungsi yang membungkus fungsi lain
    - Menambahkan logika sebelum/sesudah fungsi asli dijalankan
    - @role_required('ADMIN') = role_required('ADMIN')(my_view)
    """
    def decorator(view_func):
        """Fungsi decorator — membungkus view function."""
        @wraps(view_func)  # Mempertahankan nama dan docstring fungsi asli
        def wrapper(request, *args, **kwargs):
            """Fungsi wrapper — logika pengecekan sebelum view dijalankan."""
            user_role = get_user_role(request.user)
            if user_role in allowed_roles:
                # Role diizinkan → jalankan view
                return view_func(request, *args, **kwargs)
            else:
                # Role tidak diizinkan → tampilkan pesan error
                messages.error(request, 'Anda tidak memiliki akses untuk halaman ini.')
                # Redirect ke halaman tujuan
                return redirect('dashboard:index')
        return wrapper
    return decorator


def permission_required(action, module=None):
    """
    Decorator untuk membatasi akses view berdasarkan permission spesifik.

    Cara pakai:
        @permission_required('create', 'produk')
        # Fungsi add_product
        def add_product(request):
            ...

    Alur:
    1. Cek has_permission(user, action, module)
    2. Jika True → lanjutkan ke view
    3. Jika False → tampilkan pesan error dan redirect

    Perbedaan dengan role_required:
    - role_required: cek APAKAH user punya role tertentu
    - permission_required: cek APAKAH user punya AKSI tertentu di MODUL tertentu
    - permission_required lebih granular dan fleksibel
    """
    def decorator(view_func):
        """Fungsi decorator — membungkus view function."""
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            """Fungsi wrapper — logika pengecekan sebelum view dijalankan."""
            if has_permission(request.user, action, module):
                return view_func(request, *args, **kwargs)
            else:
                # Pesan error dengan label aksi dalam Bahasa Indonesia
                action_labels = {
                    'create': 'membuat',
                    'read': 'melihat',
                    'update': 'mengubah',
                    'delete': 'menghapus'
                }
                action_label = action_labels.get(action, action)
                # Tampilkan pesan error ke user
                messages.error(request, f'Anda tidak memiliki izin untuk {action_label} data ini.')
                # Redirect ke halaman tujuan
                return redirect('dashboard:index')
        return wrapper
    return decorator


def can_user_edit(user, module=None):
    """
    Fungsi helper — cek apakah user bisa EDIT data di modul tertentu.
    Digunakan di template: {% if user|can_user_edit:'produk' %}
    """
    return has_permission(user, 'update', module)


def can_user_delete(user, module=None):
    """
    Fungsi helper — cek apakah user bisa DELETE data di modul tertentu.
    Digunakan di template: {% if user|can_user_delete:'produk' %}
    """
    return has_permission(user, 'delete', module)


def can_user_create(user, module=None):
    """
    Fungsi helper — cek apakah user bisa CREATE data di modul tertentu.
    Digunakan di template: {% if user|can_user_create:'produk' %}
    """
    return has_permission(user, 'create', module)
