"""
==========================================================================
 CORE CONTEXT PROCESSORS - Penyuntik Permission ke Template
==========================================================================
 File ini berisi context processor yang menyediakan helper permission
 ke SEMUA template Django.

 Apa yang disuntikkan:
 - can_view → Cek akses VIEW    (contoh: {% if can_view.produk %})
 - can_create → Cek akses CREATE (contoh: {% if can_create.inventory %})
 - can_edit → Cek akses EDIT    (contoh: {% if can_edit.pembelian %})
 - can_delete → Cek akses DELETE (contoh: {% if can_delete.penjualan %})
 - accessible_subs → Sub-modul yang accessible (untuk sidebar filtering)
 - user_role → Role user saat ini ('ADMIN', 'KASIR', dll)
 - is_superuser → True/False apakah user adalah superuser

 Cara kerja PermissionChecker (magic class):
 - Menggunakan __getattr__() → atribut yang diakses menjadi nama modul
 - can_view.produk → PermissionChecker.__getattr__('produk')
                   → has_permission(user, 'read', 'produk')
 - can_view.produk.kategori → level kedua → has_permission(user, 'read', 'produk', 'kategori')

 Koneksi:
 - config/settings.py → Didaftarkan di TEMPLATES context_processors
 - apps/core/permissions.py → has_permission(), get_user_role(), get_accessible_submodules()
 - Semua template HTML → Menggunakan variabel can_view/can_create/dll
 - templates/layout/partials/menu/ → Sidebar menggunakan accessible_subs
==========================================================================
"""

# Import dari modul internal proyek
from apps.core.permissions import (
    has_exact_submodule_permission,
    has_permission,
    get_user_role,
    get_accessible_submodules,
)


class PermissionChecker:
    """
    Class "ajaib" untuk mengecek permission secara dinamis di template.

    Apa yang membuatnya "ajaib"?
    - Menggunakan __getattr__() → method Python yang dipanggil saat
      mengakses atribut yang TIDAK ADA di class
    - Contoh: can_view.produk → Python memanggil can_view.__getattr__('produk')
    - Ini memungkinkan pengecekan permission TANPA mendefinisikan setiap modul

    Level pengecekan:
    1. Level modul: can_view.produk → cek apakah role bisa view modul produk
    2. Level sub-modul: can_view.produk.kategori → cek view sub-modul kategori

    Normalisasi:
    - Dash → underscore: 'access-control' → 'access_control' (sesuai DB)
    - Di template Django, gunakan filter 'attr': {{ can_view|attr:'access-control' }}
    """

    # ═══ Mapping sidebar slug → database module code ═══
    # Beberapa menu di sidebar menggunakan slug yang BERBEDA dari kode modul di database.
    # Contoh: sidebar slug 'users' → database module 'user_management'
    # Mapping ini menjembatani perbedaan tersebut.
    SLUG_TO_MODULE = {
        'users': 'user_management',        # Manajemen User: slug 'users' → module 'user_management'
        'kas_bank': 'kas_bank',
        'kas-bank': 'kas_bank',
        'laporan_keuangan': 'laporan_keuangan',
        'laporan-keuangan': 'laporan_keuangan',
        'rekonsiliasi_keuangan': 'rekonsiliasi_keuangan',
        'rekonsiliasi-keuangan': 'rekonsiliasi_keuangan',
        'access_control': 'access_control',
        'access-control': 'access_control',
        'activity_log': 'activity_log',
        'activity-log': 'activity_log',
        'ai_assistant': 'ai_assistant',
        'ai-assistant': 'ai_assistant',
        'fraud_detection': 'fraud_detection',
        'fraud-detection': 'fraud_detection',
    }

    def __init__(self, user, action, module=None):
        """
        Inisialisasi PermissionChecker.

        Parameter:
        - user: Object User Django
        - action: Jenis aksi ('read', 'create', 'update', 'delete')
        - module: Nama modul (None untuk level pertama, diisi untuk level kedua)
        """
        self.user = user
        self.action = action
        self.module = module  # None = level modul, ada isi = level sub-modul

    def __getattr__(self, name):
        """
        Dipanggil saat mengakses atribut yang tidak ada.

        Alur 2 level:
        1. can_view.produk (module=None):
           → Return PermissionChecker baru yang tahu module='produk'
           → Ini memungkinkan chaining: can_view.produk.kategori

        2. can_view.produk.kategori (module='produk'):
           → Langsung cek has_permission(user, 'read', 'produk', 'kategori')
           → Return True/False
        """
        # Normalisasi nama: dash → underscore
        normalized = name.replace('-', '_').lower()

        # Terapkan slug→module mapping jika ada
        normalized = self.SLUG_TO_MODULE.get(normalized, normalized)

        if self.module:
            # Level 2: sub-module check (contoh: can_view.produk.kategori)
            return has_permission(self.user, self.action, self.module, normalized)
        else:
            # Level 1: module check → return checker baru untuk chaining
            return PermissionChecker(self.user, self.action, normalized)

    def __bool__(self):
        """
        Dipanggil saat PermissionChecker digunakan dalam kondisi boolean.

        Contoh: {% if can_view.produk %} → memanggil __bool__()
        Terjadi setelah __getattr__('produk') mengembalikan checker baru
        dengan module='produk'. Lalu template cek boolean → panggil __bool__()
        yang cek permission modul level.
        """
        if self.module:
            return has_permission(self.user, self.action, self.module)
        return False


class AccessibleSubsChecker:
    """
    Class untuk mengecek sub-modul mana yang accessible untuk sebuah modul.
    Digunakan untuk MEMFILTER submenu di sidebar.

    Cara pakai di template:
        {% if 'kategori' in accessible_subs.produk %}
            <li>Kategori</li>  <!-- Tampilkan submenu ini -->
        {% endif %}

    Menggunakan caching agar tidak query database berulang kali
    untuk modul yang sama dalam 1 request.
    """

    def __init__(self, user):
        """
        Inisialisasi checker.

        Parameter:
        - user: Object User Django

        _cache: Dictionary untuk menyimpan hasil query per modul
        Format: {'produk': ['kategori', 'list', 'tambah'], 'inventory': ['gudang', 'stok']}
        """
        self.user = user
        self._cache = {}  # Cache per request (bukan antar request)

    def __getattr__(self, module):
        """
        Mendapatkan list sub-modul yang accessible untuk modul tertentu.

        Dipanggil saat: accessible_subs.produk

        Return: List slug sub-modul ['kategori', 'satuan', 'list', 'tambah']

        Normalisasi: dash → underscore (access-control → access_control)
        Cache: Hasil disimpan agar tidak query ulang dalam 1 request
        """
        # Normalisasi nama modul
        normalized = module.replace('-', '_').lower()
        normalized = PermissionChecker.SLUG_TO_MODULE.get(normalized, normalized)

        # Cek cache dulu
        if normalized not in self._cache:
            # Cache miss → query database
            self._cache[normalized] = get_accessible_submodules(self.user, normalized)
        return self._cache[normalized]


def user_permissions(request):
    """
    Context processor UTAMA — Menyediakan helper permission ke SEMUA template.

    Fungsi ini didaftarkan di settings.py → TEMPLATES → context_processors.
    Dipanggil otomatis untuk SETIAP request.

    Data yang disuntikkan ke template:
    - user_role: String role user ('SUPERUSER', 'ADMIN', 'USER', 'KASIR')
    - can_view: PermissionChecker untuk cek akses VIEW
    - can_create: PermissionChecker untuk cek akses CREATE
    - can_edit: PermissionChecker untuk cek akses EDIT
    - can_delete: PermissionChecker untuk cek akses DELETE
    - accessible_subs: AccessibleSubsChecker untuk filtering sidebar
    - is_superuser: Boolean apakah user adalah superuser

    Contoh penggunaan di template:
    - {% if can_view.produk %} → Tampilkan menu produk
    - {% if can_create.inventory %} → Tampilkan tombol "Tambah"
    - {% if can_edit.pembelian.purchase_order %} → Tombol edit PO
    - {% if 'kategori' in accessible_subs.produk %} → Submenu kategori
    """
    if request.user.is_authenticated:
        # User sudah login → buat permission checkers
        user_role = get_user_role(request.user)

        # Permission checkers untuk setiap jenis aksi
        can_view = PermissionChecker(request.user, 'read')       # Cek akses baca
        can_create = PermissionChecker(request.user, 'create')   # Cek akses tambah
        can_edit = PermissionChecker(request.user, 'update')     # Cek akses edit
        can_delete = PermissionChecker(request.user, 'delete')   # Cek akses hapus

        # Checker untuk filtering submenu sidebar
        accessible_subs = AccessibleSubsChecker(request.user)

        # Status superuser (untuk kasus khusus di template)
        is_superuser = user_role == 'SUPERUSER'
        can_show_refresh_cache_button = has_exact_submodule_permission(
            request.user, 'read', 'dashboard', 'refresh_cache'
        )
        can_show_ai_assistant_widget = has_exact_submodule_permission(
            request.user, 'read', 'ai_assistant', 'chat_widget'
        )

        return {
            'user_role': user_role,

            # Dynamic permission checkers (driven by database)
            'can_view': can_view,
            'can_create': can_create,
            'can_edit': can_edit,
            'can_delete': can_delete,

            # SubCRUD filtering untuk sidebar
            'accessible_subs': accessible_subs,

            # Flag superuser
            'is_superuser': is_superuser,
            'can_show_refresh_cache_button': can_show_refresh_cache_button,
            'can_show_ai_assistant_widget': can_show_ai_assistant_widget,
        }

    # ==================== USER BELUM LOGIN ====================
    # Untuk user yang belum login, kembalikan False untuk semua cek
    class FalseChecker:
        """Dummy checker yang selalu return False untuk user yang belum login."""
        def __getattr__(self, name):
            """Override akses atribut — return default jika atribut tidak ditemukan."""
            return False
        def __bool__(self):
            """Override konversi boolean — return True/False."""
            return False

    false_checker = FalseChecker()
    return {
        'user_role': None,
        'can_view': false_checker,
        'can_create': false_checker,
        'can_edit': false_checker,
        'can_delete': false_checker,
        'is_superuser': False,
        'is_admin': False,
        'is_kasir': False,
        'can_manage_users': False,
        'can_manage_roles': False,
        'can_view_logs': False,
        'can_manage_settings': False,
        'can_show_refresh_cache_button': False,
        'can_show_ai_assistant_widget': False,
    }
