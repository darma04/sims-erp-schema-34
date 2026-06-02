"""
==========================================================================
 PERMISSION TAGS - Template Tags Permission dengan Support Sub-Modul
==========================================================================
 Template tags lanjutan untuk pengecekan permission di template HTML.
 Mendukung pengecekan level modul DAN sub-modul (SubCRUD).

 Tags & Filters yang tersedia:
 ┌──────────────────┬───────────────────────────────────────────────────┐
 │ Tag/Filter       │ Contoh Penggunaan                                 │
 ├──────────────────┼───────────────────────────────────────────────────┤
 │ has_perm (tag)   │ {% has_perm user 'read' 'produk' 'kategori' %}   │
 │ has_module_perm  │ {{ user|has_module_perm:"produk:read" }}          │
 │ has_sub_perm     │ {{ user|has_sub_perm:"produk:kategori:read" }}    │
 │ has_permission   │ {{ user|has_permission:"produk:view" }}           │
 │ attr             │ {{ can_view|attr:'produk' }}                      │
 │ split            │ {{ slug|split:'-' }}                              │
 │ extract_submodule│ {{ "produk-kategori"|extract_submodule }}→'kategori'│
 └──────────────────┴───────────────────────────────────────────────────┘

 Cara pakai: {% load permission_tags %} di awal template

 Terhubung dengan:
 - core/permissions.py → has_permission() (logika pengecekan inti)
 - core/context_processors.py → PermissionChecker yang diakses via attr filter
==========================================================================
"""
from django import template                     # Framework template Django
from apps.core.permissions import has_permission # Fungsi inti pengecekan hak akses

# Registry untuk mendaftarkan tags & filters ke Django template engine
# Setiap fungsi yang didekorasi @register.filter atau @register.simple_tag
# akan tersedia di template setelah {% load permission_tags %}
register = template.Library()


@register.simple_tag
def has_perm(user, action, module, sub_module=None):
    """
    Template tag untuk mengecek permission user.

    Tag ini digunakan untuk menyimpan hasil pengecekan ke variabel template
    menggunakan keyword 'as'. Mendukung pengecekan level modul DAN sub-modul.

    Cara pakai di template:
        {% load permission_tags %}

        {# Cek permission level modul → simpan ke variabel #}
        {% has_perm user 'read' 'produk' as bisa_lihat_produk %}
        {% if bisa_lihat_produk %}
            <a href="/produk/list/">Daftar Produk</a>
        {% endif %}

        {# Cek permission level sub-modul (SubCRUD) #}
        {% has_perm user 'edit' 'produk' 'kategori' as bisa_edit_kategori %}
        {% if bisa_edit_kategori %}
            <button>Edit Kategori</button>
        {% endif %}

    Parameter:
    - user       : Object User Django (dari request.user)
    - action     : Jenis aksi ('read', 'create', 'update', 'delete')
    - module     : Nama modul ('produk', 'inventory', 'pembelian', dll)
    - sub_module : Nama sub-modul opsional ('kategori', 'satuan', dll)

    Return:
    - True jika user punya hak akses, False jika tidak
    """
    return has_permission(user, action, module, sub_module)


@register.filter
def has_module_perm(user, module_action_str):
    """
    Template filter untuk mengecek permission level modul.
    Mendukung pengecekan single ("modul:aksi") atau multiple dengan koma ("modul1:aksi,modul2:aksi").
    Jika multiple, mengembalikan True jika SALAH SATU permission terpenuhi (OR logic).
    """
    try:
        permissions = str(module_action_str).split(',')
        for perm in permissions:
            parts = perm.strip().split(':')
            if len(parts) == 2:
                module, action = parts
                if has_permission(user, action.strip(), module.strip()):
                    return True
        return False
    except AttributeError:
        return False


@register.filter
def has_sub_perm(user, full_path):
    """
    Template filter untuk mengecek permission level sub-modul (SubCRUD).

    Mendukung pengecekan permission yang lebih spesifik dibanding has_module_perm.
    Format input: "modul:sub_modul:aksi" (3 bagian dipisahkan titik dua)

    Cara pakai di template:
        {% load permission_tags %}

        {# Cek apakah user bisa melihat kategori di modul produk #}
        {% if user|has_sub_perm:"produk:kategori:read" %}
            <li>Kategori</li>
        {% endif %}

        {# Cek apakah user bisa edit satuan #}
        {% if user|has_sub_perm:"produk:satuan:edit" %}
            <button>Edit Satuan</button>
        {% endif %}

    Parameter:
    - user      : Object User Django
    - full_path : String format "modul:sub_modul:aksi"
                  (contoh: "produk:kategori:read")

    Return:
    - True/False berdasarkan hasil pengecekan permission

    Penanganan error:
    - Jika format salah (bukan 3 bagian) → return False
    """
    try:
        # Pisahkan "produk:kategori:read" menjadi 3 bagian
        parts = full_path.split(':')
        if len(parts) == 3:
            module, sub_module, action = parts
            return has_permission(user, action, module, sub_module)
        # Jika bukan 3 bagian → format salah
        return False
    except (ValueError, AttributeError):
        return False


@register.filter(name='attr')
def attr(obj, attr_name):
    """
    Template filter untuk mengakses atribut objek secara DINAMIS.

    Django template engine TIDAK mengizinkan akses atribut dinamis secara langsung.
    Contoh: {{ can_view.access-control }} → ERROR karena ada tanda '-'
    Solusi: {{ can_view|attr:'access-control' }} → BERHASIL

    Filter ini terutama digunakan bersama PermissionChecker dan
    AccessibleSubsChecker dari context_processors.py.

    Cara pakai di template:
        {% load permission_tags %}

        {# Akses atribut dengan karakter khusus (dash) #}
        {% if can_view|attr:'access-control' %}
            <li>Akses Kontrol</li>
        {% endif %}

        {# Akses sub-modul yang accessible #}
        {% with subs=accessible_subs|attr:'produk' %}
            {% if 'kategori' in subs %}...{% endif %}
        {% endwith %}

    Parameter:
    - obj       : Objek yang atributnya ingin diakses (biasanya PermissionChecker)
    - attr_name : Nama atribut yang ingin diakses (string)

    Return:
    - Nilai atribut jika ada
    - List kosong [] jika atribut tidak ditemukan (agar kompatibel dengan operator 'in')

    Alur kerja:
    1. Cek apakah objek punya method __getattr__ (magic method)
       → Jika ya, panggil getattr() yang akan trigger __getattr__
    2. Jika tidak, cek apakah objek punya atribut tersebut secara direct
    3. Jika semuanya gagal → kembalikan list kosong
    """
    if hasattr(obj, '__getattr__'):
        # Objek punya __getattr__ (contoh: PermissionChecker)
        # → getattr() akan memanggil __getattr__(attr_name)
        try:
            result = getattr(obj, attr_name)
            # Jika result None, kembalikan list kosong agar kompatibel dengan operator 'in'
            return result if result is not None else []
        except AttributeError:
            return []
    elif hasattr(obj, attr_name):
        # Objek punya atribut langsung (bukan via __getattr__)
        result = getattr(obj, attr_name, None)
        return result if result is not None else []
    # Atribut tidak ditemukan sama sekali
    return []


@register.filter(name='split')
def split(value, delimiter='-'):
    """
    Template filter untuk memecah string berdasarkan delimiter.

    Django template engine tidak punya built-in split, jadi filter ini
    menyediakan fungsionalitas tersebut.

    Cara pakai di template:
        {% load permission_tags %}

        {# Pecah slug "produk-kategori" menjadi ['produk', 'kategori'] #}
        {% with bagian=sub_slug|split:'-' %}
            {{ bagian.0 }} → "produk"
            {{ bagian.1 }} → "kategori"
        {% endwith %}

    Parameter:
    - value     : String yang akan dipecah
    - delimiter : Karakter pemisah (default: '-' dash)

    Return:
    - List string hasil pemecahan
    - List kosong [] jika terjadi error
    """
    try:
        return str(value).split(delimiter)
    except (ValueError, AttributeError):
        return []


@register.filter(name='extract_submodule')
def extract_submodule(slug):
    """
    Template filter untuk mengekstrak nama sub-modul dari slug URL.

    Slug di sistem ini menggunakan format "modul-submodul".
    Filter ini mengambil bagian SETELAH dash pertama dan
    mengembalikannya dalam huruf kecil (lowercase) untuk
    konsistensi pencocokan dengan get_accessible_submodules().

    Contoh konversi:
    - "produk-kategori"    → "kategori"
    - "inventory-gudang"   → "gudang"
    - "produk-Kategori"    → "kategori" (dinormalisasi ke lowercase)
    - "pembelian-purchase-order" → "purchase-order" (semua setelah dash pertama)
    - "pos"                → "pos" (tanpa dash, dikembalikan apa adanya)

    Cara pakai di template:
        {% load permission_tags %}

        {# Ekstrak submodule dari slug submenu #}
        {% with nama_sub=sub_item.slug|extract_submodule %}
            {% if nama_sub in accessible_subs|attr:'produk' %}
                <li>{{ sub_item.name }}</li>
            {% endif %}
        {% endwith %}

    Parameter:
    - slug : String slug URL (contoh: "produk-kategori")

    Return:
    - String nama sub-modul dalam lowercase

    ⚠ PENTING: Selalu return lowercase untuk konsistensi pencocokan
    dengan data dari get_accessible_submodules() di permissions.py
    """
    try:
        slug_str = str(slug).strip()
        # PENTING: Hanya prefix yang benar-benar memetakan ke MODULE NAMA di sidebar.
        # 'ai-assistant-' DIHAPUS karena 'ai-assistant-settings' harus memetakan ke
        # sub-modul 'assistant-settings' (sesuai SUB_MODULE_TO_SLUG['pengaturan_ai']),
        # bukan 'settings'.
        known_prefixes = [
            'kas-bank-',
            'laporan-keuangan-',
            'access-control-',
            'activity-log-',
            'fraud-detection-',
        ]
        slug_lower = slug_str.lower()
        for prefix in known_prefixes:
            if slug_lower.startswith(prefix):
                return slug_lower[len(prefix):]

        parts = slug_str.split('-')
        if len(parts) > 1:
            # Ada dash → ambil semua bagian SETELAH dash pertama
            # Contoh: "produk-kategori" → ['produk', 'kategori'] → 'kategori'
            # Contoh: "pembelian-purchase-order" → ['pembelian', 'purchase', 'order'] → 'purchase-order'
            result = '-'.join(parts[1:]).lower()
            return result
        # Tidak ada dash → kembalikan slug apa adanya dalam lowercase
        return slug_str.lower()
    except (ValueError, AttributeError):
        # Jika terjadi error → kembalikan slug asli dalam lowercase
        return str(slug).lower() if slug else ''
"""
=== AKHIR FILE permission_tags.py ===

Ringkasan semua tag/filter yang terdaftar:
1. has_perm          → Simple tag: {% has_perm user 'read' 'produk' as var %}
2. has_module_perm   → Filter: {{ user|has_module_perm:"produk:read" }}
3. has_sub_perm      → Filter: {{ user|has_sub_perm:"produk:kategori:read" }}
4. attr              → Filter: {{ can_view|attr:'produk' }}
5. split             → Filter: {{ slug|split:'-' }}
6. extract_submodule → Filter: {{ slug|extract_submodule }}
7. has_permission    → Filter: {{ user|has_permission:"produk:view" }}
"""
