"""
==========================================================================
 CORE MODELS - Sistem RBAC (Role-Based Access Control)
==========================================================================
 File ini berisi model RolePermission — jantung sistem keamanan proyek.

 Apa itu RBAC?
 - Role-Based Access Control = Kontrol akses berdasarkan peran
 - Setiap user punya 1 role (dari Profile.role)
 - Setiap role punya daftar permission per modul/sub-modul
 - Permission: can_view, can_create, can_edit, can_delete

 Contoh penggunaan:
 - Role 'KASIR' → hanya bisa akses modul 'pos' dan 'penjualan'
 - Role 'ADMIN' → bisa akses semua modul kecuali pengaturan sistem
 - Role 'SUPERUSER' → bypass semua pengecekan (akses penuh)

 Koneksi penting:
 - auth/models.py → Profile.role menyimpan role user
 - apps/core/permissions.py → Fungsi has_permission() membaca model ini
 - apps/core/mixins.py → Mixin menggunakan has_permission() di views
 - apps/core/context_processors.py → Menyuntikkan permission ke template
 - apps/permission_management/ → UI untuk mengelola permissions
 - templates/layout/partials/menu/ → Sidebar difilter berdasarkan permission
==========================================================================
"""

from django.db import models  # Django ORM untuk definisi model database


class RolePermission(models.Model):
    """
    Model untuk menyimpan konfigurasi permission setiap role.

    Setiap record = 1 aturan permission:
    - Role X di Module Y (Sub-module Z) bisa View/Create/Edit/Delete

    Contoh data:
    | role   | module  | sub_module   | can_view | can_create | can_edit | can_delete |
    |--------|---------|--------------|----------|------------|----------|------------|
    | KASIR  | pos     | None         | True     | True       | False    | False      |
    | ADMIN  | produk  | kategori     | True     | True       | True     | True       |
    | USER   | produk  | daftar_produk| True     | False      | False    | False      |

    SUPERUSER tidak perlu record di tabel ini — selalu dapat akses penuh.
    """

    # ==================== DAFTAR ROLE STATIS ====================
    # Role bawaan sistem — untuk referensi dan backward compatibility
    # Role kustom bisa ditambahkan langsung di database
    ROLE_CHOICES = [
        ('SUPERUSER', 'Superuser - Full Access'),    # Akses penuh, bypass semua cek
        ('ADMIN', 'Admin - Limited Access'),          # Admin dengan akses terbatas
        ('USER', 'User - Read & Create Only'),        # User biasa
        ('KASIR', 'Kasir - POS Access Only'),         # Kasir: hanya POS
    ]

    # ==================== DAFTAR MODUL ====================
    # Semua modul yang tersedia di sistem
    # Setiap modul sesuai dengan 1 menu utama di sidebar
    MODULE_CHOICES = [
        ('dashboard', 'Dashboard'),                # Halaman utama analytics
        ('produk', 'Produk'),                      # Manajemen produk, kategori, satuan
        ('sparepart', 'Sparepart'),                # Manajemen sparepart (terpisah dari produk)
        ('inventory', 'Inventory'),                # Gudang, stok, transfer, adjustment
        ('pembelian', 'Pembelian'),                # Supplier, purchase order
        ('penjualan', 'Penjualan'),                # Customer, sales order
        ('pos', 'POS / Kasir'),                    # Point of Sale / kasir
        ('biaya', 'Biaya'),                        # Pengeluaran / biaya operasional
        ('laporan', 'Laporan'),                    # Laporan: produk, stok, keuangan
        ('hr', 'HR / Human Resource'),             # Karyawan, absensi, penggajian
        ('user_management', 'User Management'),    # Kelola user
        ('activity_log', 'Log Aktivitas'),         # Riwayat aktivitas user
        ('pengaturan', 'Pengaturan'),              # Pengaturan perusahaan & sistem
        ('automation', 'Automasi Telegram'),        # Notifikasi Telegram
        ('access_control', 'Access Control'),       # Kelola role & permission
        ('ai_assistant', 'AI Manajemen'),            # AI Dashboard & AI Assistant
        ('fraud_detection', 'Fraud Detection'),         # Deteksi kecurangan
        ('service_center', 'Service Center'),             # Manajemen service elektronik
    ]

    # ==================== DAFTAR SUB-MODUL ====================
    # Sub-modul per modul — setiap sub-modul = 1 submenu di sidebar
    # Dictionary: key = kode modul, value = list of (kode_sub, nama_sub)
    SUB_MODULE_CHOICES = {
        'produk': [
            ('kategori', 'Kategori'),              # CRUD Kategori Produk
            ('satuan', 'Satuan'),                   # CRUD Satuan (pcs, kg, liter)
            ('daftar_produk', 'Daftar Produk'),     # List semua produk
            ('tambah_produk', 'Tambah Produk'),     # Form tambah produk baru
        ],
        'sparepart': [
            ('daftar_sparepart', 'Daftar Sparepart'),  # List semua sparepart
            ('tambah_sparepart', 'Tambah Sparepart'),  # Form tambah sparepart baru
            ('kategori_sparepart', 'Kategori'),        # CRUD Kategori (shared)
            ('satuan_sparepart', 'Satuan'),             # CRUD Satuan (shared)
        ],
        'inventory': [
            ('gudang', 'Gudang'),                   # CRUD Gudang
            ('stok', 'Stok'),                       # Lihat stok per gudang
            ('transfer_stok', 'Transfer Stok'),     # Transfer antar gudang
            ('adjustment_stok', 'Adjustment Stok'), # Penyesuaian stok manual
        ],
        'pembelian': [
            ('supplier', 'Supplier'),               # CRUD Supplier
            ('purchase_order', 'Purchase Order'),    # CRUD Purchase Order
        ],
        'penjualan': [
            ('customer', 'Customer'),               # CRUD Customer
            ('sales_order', 'Sales Order'),          # CRUD Sales Order
            ('transaksi_pos', 'Transaksi POS'),     # Daftar transaksi POS
        ],
        'biaya': [
            ('kategori_biaya', 'Kategori Biaya'),   # CRUD Kategori Biaya
            ('tambah_biaya', 'Tambah Biaya'),       # Form tambah biaya
        ],
        'hr': [
            ('dashboard_hr', 'Dashboard HR'),               # Dashboard HR
            ('departemen', 'Departemen'),                    # CRUD Departemen
            ('jabatan', 'Jabatan'),                          # CRUD Jabatan
            ('karyawan', 'Karyawan'),                        # CRUD Karyawan
            ('absensi', 'Absensi'),                          # Daftar Absensi
            ('penggajian', 'Penggajian'),                    # CRUD Penggajian
            ('pengaturan_absensi', 'Pengaturan Absensi'),    # Setting absensi
        ],
        'laporan': [
            ('laporan_produk', 'Laporan Produk'),           # Laporan produk
            ('laporan_stok', 'Laporan Stok'),               # Laporan stok
            ('laporan_penjualan', 'Laporan Penjualan'),     # Laporan penjualan
            ('laporan_pembelian', 'Laporan Pembelian'),     # Laporan pembelian
            ('laporan_keuangan', 'Laporan Keuangan'),       # Laporan keuangan
            ('laporan_service', 'Laporan Service'),         # Laporan service center
            ('laporan_sparepart', 'Laporan Sparepart'),     # Laporan penggunaan sparepart
            ('laporan_cabang', 'Laporan Cabang'),             # Laporan performa per cabang/gudang
        ],
        'access_control': [
            ('roles', 'Roles'),                     # Daftar role
            ('permissions', 'Permissions'),          # Daftar permission
        ],
        'automation': [
            ('pengaturan_telegram', 'Pengaturan Telegram'),  # Setting bot Telegram
            ('template_pesan', 'Template Pesan'),             # Template pesan notifikasi
            ('log_notifikasi', 'Log Notifikasi'),             # Riwayat notifikasi
        ],
        'pengaturan': [
            ('profil', 'Pengaturan Profil'),                 # Edit profil user
            ('perusahaan', 'Pengaturan Perusahaan'),         # Setting perusahaan
            ('metode_pembayaran', 'Metode Pembayaran'),      # CRUD metode pembayaran
            ('template_cetak', 'Template Cetak'),             # Template cetak dokumen
            ('manajemen_data', 'Manajemen Data'),            # Manajemen hapus data dll
        ],
        'ai_assistant': [
            ('dashboard_ai', 'AI Dashboard'),                # Dashboard analitik AI
            ('pengaturan_ai', 'AI Assistant'),                # Pengaturan AI Assistant
        ],
        'fraud_detection': [
            ('dashboard_fraud', 'Dashboard Fraud'),          # Dashboard fraud detection
            ('daftar_anomali', 'Daftar Anomali'),            # Daftar anomali mencurigakan
            ('rekonsiliasi_kas', 'Rekonsiliasi Kas'),         # Blind cash closing
            ('pengaturan_fraud', 'Pengaturan Fraud'),         # Pengaturan pencegahan
        ],
        'service_center': [
            ('dashboard_service', 'Dashboard Service'),       # Dashboard service center
            ('pelanggan_service', 'Pelanggan'),               # CRUD pelanggan service
            ('perangkat', 'Jenis Perangkat'),                 # CRUD jenis perangkat
            ('kategori_service', 'Kategori Service'),         # CRUD kategori service
            ('jenis_service', 'Jenis Service'),               # CRUD jenis/layanan service
            ('order_service', 'Order Service'),               # CRUD order service
            ('sparepart_service', 'Sparepart Service'),       # DIPERBAIKI QA-R1: CRUD sparepart pada order
            ('terima_unit', 'Terima Unit Baru'),              # Form terima unit
            ('laporan_service', 'Laporan Service'),           # Laporan service center
        ],
    }

    # ==================== MAPPING SUB-MODULE KE SLUG MENU ====================
    # Konversi: kode database → slug sidebar (bagian setelah dash di menu)
    # Contoh:
    #   'daftar_produk' → 'list' (slug sidebar: 'produk-list')
    #   'purchase_order' → 'po' (slug sidebar: 'pembelian-po')
    #
    # Kenapa perlu mapping?
    # - Di database, sub-module disimpan sebagai 'daftar_produk', 'purchase_order'
    # - Di sidebar (vertical_menu.json), slug-nya 'produk-list', 'pembelian-po'
    # - Mapping ini menjembatani keduanya
    SUB_MODULE_TO_SLUG = {
        # === Produk ===
        'kategori': 'kategori',
        'satuan': 'satuan',
        'daftar_produk': 'list',       # sidebar: produk-list
        'tambah_produk': 'tambah',     # sidebar: produk-tambah
        'daftar_sparepart': 'daftar_sparepart',   # sidebar: sparepart-daftar_sparepart
        'tambah_sparepart': 'tambah_sparepart',   # sidebar: sparepart-tambah_sparepart
        'kategori_sparepart': 'kategori',          # sidebar: sparepart-kategori
        'satuan_sparepart': 'satuan',              # sidebar: sparepart-satuan
        # === Inventory ===
        'gudang': 'gudang',
        'stok': 'stok',
        'transfer_stok': 'transfer',   # sidebar: inventory-transfer
        'adjustment_stok': 'adjustment',
        # === Pembelian ===
        'supplier': 'supplier',
        'purchase_order': 'po',        # sidebar: pembelian-po
        # === Penjualan ===
        'customer': 'customer',
        'sales_order': 'so',           # sidebar: penjualan-so
        'transaksi_pos': 'transaksi',
        # === Biaya ===
        'kategori_biaya': 'kategori',
        'tambah_biaya': 'transaksi',
        # === HR ===
        'dashboard_hr': 'dashboard',
        'departemen': 'departemen',
        'jabatan': 'jabatan',
        'karyawan': 'karyawan',
        'absensi': 'absensi',
        'penggajian': 'penggajian',
        'pengaturan_absensi': 'pengaturan-absensi',
        # === Laporan ===
        'laporan_produk': 'produk',
        'laporan_stok': 'stok',
        'laporan_penjualan': 'penjualan',
        'laporan_pembelian': 'pembelian',
        'laporan_keuangan': 'keuangan',
        'laporan_service': 'service',              # sidebar: laporan-service
        'laporan_sparepart': 'sparepart',          # sidebar: laporan-sparepart
        'laporan_cabang': 'cabang',                  # sidebar: laporan-cabang
        # === Access Control ===
        'roles': 'roles',
        'permissions': 'permissions',
        # === Automation ===
        'pengaturan_telegram': 'pengaturan',
        'template_pesan': 'template',
        'log_notifikasi': 'log',
        # === Pengaturan ===
        'profil': 'profil',
        'perusahaan': 'perusahaan',
        'metode_pembayaran': 'metode-pembayaran',
        'template_cetak': 'template-cetak',
        'manajemen_data': 'manajemen-data',
        # === AI Manajemen ===
        'dashboard_ai': 'dashboard',             # sidebar: ai-dashboard → extract → 'dashboard'
        'pengaturan_ai': 'assistant-settings',   # sidebar: ai-assistant-settings → extract → 'assistant-settings'
        # === Fraud Detection ===
        'dashboard_fraud': 'dashboard',           # sidebar: fraud-dashboard
        'daftar_anomali': 'anomali',              # sidebar: fraud-anomali
        'rekonsiliasi_kas': 'kas',                # sidebar: fraud-kas
        'pengaturan_fraud': 'pengaturan',          # sidebar: fraud-pengaturan
        # === Service Center ===
        'dashboard_service': 'dashboard',          # sidebar: service-center-dashboard
        'pelanggan_service': 'pelanggan',          # sidebar: service-center-pelanggan
        'perangkat': 'perangkat',                  # sidebar: service-center-perangkat
        'kategori_service': 'kategori',            # sidebar: service-center-kategori
        'jenis_service': 'jenis',                  # sidebar: service-center-jenis
        'order_service': 'order',                  # sidebar: service-center-order
        'sparepart_service': 'sparepart',          # DIPERBAIKI QA-R1: sidebar: service-center-sparepart
        'terima_unit': 'terima',                   # sidebar: service-center-terima
        'laporan_service': 'laporan',              # sidebar: service-center-laporan
    }

    # ==================== REVERSE MAPPING: SLUG → DB CODE ====================
    # Kebalikan dari SUB_MODULE_TO_SLUG
    # Digunakan untuk konversi dari slug sidebar ke kode database
    # Dibuild otomatis dari mapping di atas menggunakan loop
    SLUG_TO_SUB_MODULE = {}
    for _module_code, _subs in SUB_MODULE_CHOICES.items():
        SLUG_TO_SUB_MODULE[_module_code] = {}
        for _sub_code, _sub_name in _subs:
            _slug = SUB_MODULE_TO_SLUG.get(_sub_code, _sub_code)
            SLUG_TO_SUB_MODULE[_module_code][_slug] = _sub_code

    # ==================== FIELD DATABASE ====================

    # Role user (contoh: 'ADMIN', 'KASIR', 'STAFF_GUDANG')
    # choices dihapus agar bisa menerima role kustom dari database
    role = models.CharField(
        max_length=50,
        verbose_name="Role"
    )

    # Modul yang diakses (contoh: 'produk', 'inventory', 'pos')
    module = models.CharField(
        max_length=50,
        choices=MODULE_CHOICES,
        verbose_name="Module"
    )

    # Sub-modul (opsional) — untuk permission lebih detail
    # Contoh: modul 'produk' → sub-modul 'kategori', 'satuan', 'daftar_produk'
    # Jika None → permission berlaku untuk SEMUA sub-modul di modul tersebut
    sub_module = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Sub Module",
        help_text="Specific page/feature within module (e.g., 'kategori', 'satuan', 'daftar_produk')"
    )

    # ==================== FIELD PERMISSION ====================
    # 4 jenis permission (CRUD):

    can_view = models.BooleanField(
        default=True,
        verbose_name="Can View",
        help_text="Dapat melihat/membaca data"
    )
    can_create = models.BooleanField(
        default=False,
        verbose_name="Can Create",
        help_text="Dapat menambah data baru"
    )
    can_edit = models.BooleanField(
        default=False,
        verbose_name="Can Edit",
        help_text="Dapat mengubah data"
    )
    can_delete = models.BooleanField(
        default=False,
        verbose_name="Can Delete",
        help_text="Dapat menghapus data"
    )

    # Catatan/deskripsi tambahan tentang permission ini
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Deskripsi",
        help_text="Catatan tambahan tentang permission ini"
    )

    # ==================== FIELD TRACKING ====================
    created_at = models.DateTimeField(auto_now_add=True)  # Tanggal dibuat (otomatis)
    updated_at = models.DateTimeField(auto_now=True)       # Tanggal terakhir diubah (otomatis)

    # ==================== META CLASS ====================
    class Meta:
        # unique_together: Kombinasi role + module + sub_module harus unik
        # Artinya: 1 role hanya bisa punya 1 record per module per sub_module
        """Konfigurasi metadata model untuk Django."""
        unique_together = ('role', 'module', 'sub_module')
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        ordering = ['role', 'module', 'sub_module']  # Urutan default saat query

    # ==================== METHOD ====================

    def get_role_display(self):
        """
        Mendapatkan nama role yang mudah dibaca manusia.

        Kenapa manual? Karena field 'role' tidak pakai choices=
        (agar bisa menerima role kustom), maka Django tidak otomatis
        menyediakan get_role_display().

        Contoh:
        - 'ADMIN' → 'Admin - Limited Access'
        - 'STAFF_GUDANG' → 'Staff Gudang' (format otomatis)
        """
        role_dict = dict(self.ROLE_CHOICES)
        return role_dict.get(self.role, self.role.replace('_', ' ').title())

    def __str__(self):
        """
        Representasi string RolePermission.
        Format: "Admin - Produk > Kategori" atau "Kasir - POS / Kasir"
        """
        base = f"{self.get_role_display()} - {self.get_module_display()}"
        if self.sub_module:
            return f"{base} > {self.sub_module.replace('_', ' ').title()}"
        return base

    def get_permissions_summary(self):
        """
        Menghasilkan ringkasan permission yang mudah dibaca.

        Return: String seperti "View, Create, Edit" atau "No Access"
        Digunakan di admin panel dan halaman permission management.
        """
        perms = []
        if self.can_view:
            perms.append('View')
        if self.can_create:
            perms.append('Create')
        if self.can_edit:
            perms.append('Edit')
        if self.can_delete:
            perms.append('Delete')
        return ', '.join(perms) if perms else 'No Access'

    @classmethod
    def get_all_roles(cls):
        """
        Mendapatkan semua role yang AKTIF di sistem.

        Cara kerja:
        1. Query database: ambil semua role unik yang punya RolePermission records
        2. Untuk role statis (ADMIN, USER, KASIR): hanya tampilkan jika punya records di DB
        3. SUPERUSER selalu ditampilkan (bypass semua permission checks)
        4. Role kustom di-format otomatis: 'STAFF_GUDANG' → 'Staff Gudang'

        PENTING: Jika sebuah role (termasuk statis) sudah dihapus semua
        RolePermission-nya, role tersebut TIDAK akan muncul lagi di daftar.
        Ini memungkinkan admin untuk benar-benar menghapus role statis.

        Return: List of tuples [(kode, nama), ...]
        """
        # Mapping nama untuk role statis (referensi nama saja)
        static_role_names = dict(cls.ROLE_CHOICES)

        # Ambil role unik yang BENAR-BENAR ada di database
        from django.db.models import Count
        db_roles = cls.objects.values('role').annotate(count=Count('role')).order_by('role')

        # Kumpulkan role yang ada di DB
        active_roles = {}
        for item in db_roles:
            role_code = item['role']
            if role_code in static_role_names:
                # Role statis yang punya records di DB → tampilkan dengan nama statis
                active_roles[role_code] = static_role_names[role_code]
            else:
                # Role kustom: format otomatis nama dari kode
                active_roles[role_code] = role_code.replace('_', ' ').title()

        # SUPERUSER selalu ditampilkan (tidak perlu RolePermission records)
        if 'SUPERUSER' not in active_roles:
            active_roles['SUPERUSER'] = static_role_names.get('SUPERUSER', 'Superuser - Full Access')

        # Konversi ke list of tuples dan sort
        result = [(code, name) for code, name in active_roles.items()]
        return sorted(result, key=lambda x: x[1])
