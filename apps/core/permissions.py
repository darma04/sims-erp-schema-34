# CORE PERMISSIONS SYSTEM - HYBRID RBAC
import os
from functools import wraps
import warnings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages

SUB_MODULE_TO_SLUG = {
    'kategori': 'kategori',
    'satuan': 'satuan',
    'import': 'import',
    'produk_import': 'import',
    'stok': 'stok',
    'gudang': 'gudang',
    'penyesuaian': 'penyesuaian',
    'transfer': 'transfer',
    'minimum': 'minimum',
    'opname': 'opname',
    'supplier': 'supplier',
    'po': 'po',
    'penerimaan': 'penerimaan',
    'faktur': 'faktur',
    'retur': 'retur',
    'purchase_order_import': 'import',
    'pelanggan': 'pelanggan',
    'penawaran': 'penawaran',
    'so': 'so',
    'pengiriman': 'pengiriman',
    'dashboard': 'dashboard',
    'akun': 'akun',
    'mutasi': 'mutasi',
    'rekonsiliasi': 'rekonsiliasi',
    'daftar_piutang': 'list',
    'aging_piutang': 'aging',
    'daftar_hutang': 'list',
    'aging_hutang': 'aging',
    'list': 'list',
    'aging': 'aging',
    'daftar_aset': 'list',
    'penyusutan': 'penyusutan',
    'faktur_pajak': 'list',
    'rekap_ppn': 'rekap',
    'setting_pajak': 'setting',
    'rekap': 'rekap',
    'setting': 'setting',
    'pengaturan_telegram': 'pengaturan',
    'template_pesan': 'template',
    'log_notifikasi': 'log',
    'pengaturan': 'pengaturan',
    'template': 'template',
    'log': 'log',
    'daftar_reimburse': 'list',
    'pengajuan': 'pengajuan',
    'approval': 'approval',
    'coa': 'coa',
    'jurnal': 'jurnal',
    'buku_besar': 'buku-besar',
    'periode': 'periode',
    'panduan': 'panduan',
    'neraca': 'neraca',
    'laba_rugi': 'laba-rugi',
    'arus_kas': 'arus-kas',
    'trial_balance': 'trial-balance',
}

SUBMODULE_ALIAS_MAP = {
    'produk_import': 'import',
    'purchase_order_import': 'import',
    'daftar_aset': 'list',
    'daftar_hutang': 'list',
    'aging_hutang': 'aging',
    'daftar_piutang': 'list',
    'aging_piutang': 'aging',
    'faktur_pajak': 'list',
    'rekap_ppn': 'rekap',
    'setting_pajak': 'setting',
    'pengaturan_telegram': 'pengaturan',
    'template_pesan': 'template',
    'log_notifikasi': 'log',
    'daftar_approval': 'list',
}

SUPERUSER_ROLE_CODES = {'SUPERUSER'}


def get_user_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'SUPERUSER'
    try:
        role = str(user.profile.role or '').strip()
        if not role:
            return 'USER'
        role_upper = role.upper()
        # Exact match untuk role standar — AMAN, tidak potong role kustom
        # Role standar: SUPERUSER, ADMIN, KASIR, PENGELOLA, USER
        STANDARD_ROLES = {'SUPERUSER', 'ADMIN', 'KASIR', 'PENGELOLA', 'USER'}
        if role_upper in STANDARD_ROLES:
            return role_upper
        # Role kustom — kembalikan UTUH, jangan dipotong
        return role_upper
    except Exception:
        return 'USER'


def is_superuser_role(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or get_user_role(user) == 'SUPERUSER'


def has_permission(user, action, module=None, sub_module=None):
    if not user or not user.is_authenticated:
        return False

    role = get_user_role(user)

    if not role:
        return False

    # Superuser selalu punya semua akses (bypass)
    if user.is_superuser or role == 'SUPERUSER':
        return True

    if module:
        try:
            module_normalized = module.replace('-', '_').lower()

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

            perms_cache = _get_role_permissions_cache(role)

            if sub_module:
                sub_clean = sub_module.lower()
                sub_clean = SUBMODULE_ALIAS_MAP.get(sub_clean, sub_clean)
                sub_key = (module_normalized, sub_clean)
                
                # Cek permission di sub-module dulu
                if sub_key in perms_cache:
                    sub_perm = perms_cache[sub_key].get(perm_field, False)
                    if sub_perm:
                        return True
                    # Jika sub-module tidak punya permission ini,
                    # FALLBACK ke module-level (module inherit CRUD ke sub-module)
                    # kecuali untuk View — View harus eksplisit di sub-module
                    if perm_field != 'can_view':
                        mod_key = (module_normalized, None)
                        if mod_key in perms_cache:
                            return perms_cache[mod_key].get(perm_field, False)
                        return False
                    # Untuk View, jika sub-module tidak punya can_view, cek raw key
                
                raw_key = (module_normalized, sub_module.lower())
                if raw_key in perms_cache and raw_key != sub_key:
                    raw_perm = perms_cache[raw_key].get(perm_field, False)
                    if raw_perm:
                        return True
                    if perm_field != 'can_view':
                        mod_key = (module_normalized, None)
                        if mod_key in perms_cache:
                            return perms_cache[mod_key].get(perm_field, False)
                        return False
                
                mod_key = (module_normalized, None)
                if mod_key in perms_cache:
                    return perms_cache[mod_key].get(perm_field, False)
                return False

            mod_key = (module_normalized, None)
            if mod_key in perms_cache and perms_cache[mod_key].get(perm_field, False):
                return True

            for (mod, sub), perm_dict in perms_cache.items():
                if mod == module_normalized and sub is not None and perm_dict.get(perm_field, False):
                    return True

            return False

        except Exception:
            return False

    return False


def has_exact_submodule_permission(user, action, module, sub_module):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or get_user_role(user) == 'SUPERUSER':
        return True
    try:
        role = get_user_role(user)
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
    from django.core.cache import cache
    from apps.core.cache_utils import get_role_permissions_cache_key, normalize_role_code

    role = normalize_role_code(role)
    cache_key = get_role_permissions_cache_key(role)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from apps.core.models import RolePermission
    perms_dict = {}

    exact_qs = RolePermission.objects.filter(role__iexact=role)
    if exact_qs.exists():
        all_perms = exact_qs
    else:
        all_perms = RolePermission.objects.filter(role__istartswith=role)

    for p in all_perms.order_by().values('module', 'sub_module', 'can_view', 'can_create', 'can_edit', 'can_delete'):
        mod = p['module'].lower() if p['module'] else ''
        sub = p['sub_module'].lower() if p['sub_module'] else None
        key = (mod, sub)
        perms_dict[key] = {
            'can_view': p['can_view'],
            'can_create': p['can_create'],
            'can_edit': p['can_edit'],
            'can_delete': p['can_delete'],
        }

    cache.set(cache_key, perms_dict, 300)
    return perms_dict


def get_accessible_submodules(user, module):
    if not user or not user.is_authenticated:
        return []

    role = get_user_role(user)

    from apps.core.models import RolePermission
    module_normalized = module.replace('-', '_').lower()

    # Ambil semua default submodules untuk modul ini (dari choices & sidebar json)
    subs_from_choices = [
        RolePermission.SUB_MODULE_TO_SLUG.get(sub_code, sub_code)
        for sub_code, _ in RolePermission.SUB_MODULE_CHOICES.get(module_normalized, [])
    ]
    subs_from_json = get_all_submodules_from_menu(module)
    all_default_subs = list(dict.fromkeys(subs_from_choices + subs_from_json))

    if user.is_superuser or role == 'SUPERUSER':
        if not all_default_subs and module_normalized:
            all_default_subs = ['list', 'import', 'kategori', 'satuan', 'stok', 'gudang', 'penyesuaian', 'transfer', 'minimum', 'opname', 'supplier', 'po', 'penerimaan', 'faktur', 'retur', 'pelanggan', 'penawaran', 'so', 'pengiriman', 'dashboard', 'akun', 'mutasi', 'rekonsiliasi', 'aging', 'penyusutan', 'rekap', 'setting', 'pengaturan', 'template', 'log', 'pengajuan', 'approval', 'coa', 'jurnal', 'buku-besar', 'periode', 'panduan', 'neraca', 'laba-rugi', 'arus-kas', 'trial-balance']
        return all_default_subs

    try:
        perms_cache = _get_role_permissions_cache(role)

        module_has_view = perms_cache.get((module_normalized, None), {}).get('can_view', False)

        explicit_view_subs = []

        # Hanya konfigurasi yang dapat dipetakan ke submenu sidebar yang boleh
        # membatasi submenu. Data legacy dapat menyimpan kode sub-modul yang
        # tidak lagi ada di menu (mis. ``reimburse``); jika ikut dianggap
        # eksplisit, seluruh submenu yang valid akan hilang dari sidebar.
        sidebar_subs = set(subs_from_json)
        has_explicit_sub_config = any(
            mod == module_normalized
            and sub is not None
            and (
                not sidebar_subs
                or RolePermission.SUB_MODULE_TO_SLUG.get(sub, sub) in sidebar_subs
            )
            for (mod, sub) in perms_cache.keys()
        )

        for (mod, sub), perms in perms_cache.items():
            if mod == module_normalized and sub is not None:
                slug = RolePermission.SUB_MODULE_TO_SLUG.get(sub, sub)
                if perms.get('can_view', False):
                    if slug and slug not in explicit_view_subs:
                        explicit_view_subs.append(slug)

        if sidebar_subs:
            explicit_view_subs = [
                slug for slug in explicit_view_subs if slug in sidebar_subs
            ]

        if module_has_view:
            if has_explicit_sub_config:
                # Ada konfigurasi sub-module eksplisit → gunakan HANYA yang dicentang
                # (user sudah mengatur sub-menu mana yang boleh tampil)
                return explicit_view_subs
            else:
                # Tidak ada konfigurasi sub-module → backward compat:
                # semua sub-module default tampil (role lama sebelum fitur sub-menu)
                return all_default_subs
        else:
            # Module tidak dapat view → hanya yang eksplisit dicentang (seharusnya kosong)
            return explicit_view_subs

    except Exception:
        return []



_menu_cache = None


def get_all_submodules_from_menu(module):
    global _menu_cache
    if _menu_cache is None:
        _menu_cache = _load_vertical_menu_json()

    module_normalized = module.replace('-', '_').lower()
    slug_mapping = {
        'user_management': 'users',
        'kas_bank': 'kas-bank',
        'laporan_keuangan': 'laporan-keuangan',
        'rekonsiliasi_keuangan': 'rekonsiliasi-keuangan',
        'access_control': 'access-control',
        'activity_log': 'activity-log',
        'ai_assistant': 'ai-assistant',
        'fraud_detection': 'fraud-detection',
        'service_center': 'service-center',
    }
    menu_slug = slug_mapping.get(module_normalized, module_normalized.replace('_', '-'))

    # Known prefixes — harus IDENTIK dengan extract_submodule di permission_tags.py
    known_prefixes = [
        'kas-bank-',
        'laporan-keuangan-',
        'access-control-',
        'activity-log-',
        'fraud-detection-',
        'service-center-',
    ]

    def _extract(raw_slug):
        """Ekstrak sub-name dari slug, konsisten dengan extract_submodule template filter."""
        if not raw_slug:
            return ''
        slug_lower = raw_slug.lower().strip()
        for prefix in known_prefixes:
            if slug_lower.startswith(prefix):
                result = slug_lower[len(prefix):]
                for component in prefix.strip('-').split('-'):
                    comp_prefix = component + '-'
                    if result.startswith(comp_prefix):
                        result = result[len(comp_prefix):]
                return result
        parts = slug_lower.split('-')
        if len(parts) > 1:
            return '-'.join(parts[1:])
        return slug_lower

    submodules = []
    for item in _menu_cache:
        if item.get('slug') == menu_slug and 'submenu' in item:
            for sub in item['submenu']:
                raw_slug = sub.get('slug', '')
                sub_name = _extract(raw_slug)
                if sub_name and sub_name not in submodules:
                    submodules.append(sub_name)

    return submodules


def _load_vertical_menu_json():
    import json
    from django.conf import settings
    menu_path = os.path.join(
        settings.BASE_DIR,
        'templates', 'layout', 'partials', 'menu', 'vertical', 'json', 'vertical_menu.json'
    )
    if not os.path.exists(menu_path):
        return []
    try:
        with open(menu_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('menu', [])
    except Exception:
        return []


def role_required(*roles):
    """[DEPRECATED] Gunakan @permission_required sebagai gantinya."""
    warnings.warn(
        "role_required sudah tidak digunakan. Gunakan @permission_required.",
        DeprecationWarning,
        stacklevel=2
    )
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            user_role = get_user_role(request.user)
            if user_role == 'SUPERUSER' or user_role in [r.upper() for r in roles]:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied('Anda tidak memiliki akses ke halaman ini.')
        return wrapper
    return decorator


def permission_required(action, module, sub_module=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if has_permission(request.user, action, module, sub_module):
                return view_func(request, *args, **kwargs)
            else:
                action_labels = {
                    'create': 'membuat',
                    'read': 'melihat',
                    'update': 'mengubah',
                    'delete': 'menghapus'
                }
                action_label = action_labels.get(action, action)
                messages.error(request, f'Anda tidak memiliki izin untuk {action_label} data ini.')
                return redirect('dashboard:index')
        return wrapper
    return decorator


def can_user_edit(user, module=None):
    return has_permission(user, 'update', module)


def can_user_delete(user, module=None):
    return has_permission(user, 'delete', module)


def can_user_create(user, module=None):
    return has_permission(user, 'create', module)
