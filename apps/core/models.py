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
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


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
        ('kas_bank', 'Kas & Bank / Treasury'),     # Akun kas/bank, mutasi, transfer, rekonsiliasi
        ('biaya', 'Biaya'),                        # Pengeluaran / biaya operasional
        ('laporan', 'Laporan'),                    # Laporan: produk, stok, keuangan
        ('hr', 'HR / Human Resource'),             # Karyawan, absensi, penggajian
        ('user_management', 'User Management'),    # Kelola user
        ('activity_log', 'Log Aktivitas'),         # Riwayat aktivitas user
        ('pengaturan', 'Pengaturan'),              # Pengaturan perusahaan & sistem
        ('automation', 'Automasi Telegram'),        # Notifikasi Telegram
        ('access_control', 'Access Control'),       # Kelola role & permission
        ('ai_assistant', 'AI Manajemen'),            # AI Dashboard & AI Assistant
        ('fraud_detection', 'Fraud Detection'),      # Deteksi kecurangan
        ('service_center', 'Service Center'),             # Manajemen service elektronik
        # ========== MODUL AKUNTANSI ==========
        ('akuntansi', 'Akuntansi'),                # CoA, Jurnal, Buku Besar, Periode
        ('laporan_keuangan', 'Laporan Keuangan'),  # Trial Balance, Laba Rugi, Neraca, Arus Kas
        ('piutang', 'Piutang (AR)'),               # Accounts Receivable
        ('hutang', 'Hutang (AP)'),                 # Accounts Payable
        ('aset', 'Aset Tetap'),                    # Fixed Assets & Penyusutan
        ('pajak', 'Pajak (PPN)'),                  # Faktur Pajak & Rekap PPN
        ('rekonsiliasi_keuangan', 'Rekonsiliasi Keuangan'),  # Perbandingan Operasional vs Akuntansi
    ]

    # ==================== DAFTAR SUB-MODUL ====================
    # Sub-modul per modul — setiap sub-modul = 1 submenu di sidebar
    # Dictionary: key = kode modul, value = list of (kode_sub, nama_sub)
    SUB_MODULE_CHOICES = {
        'dashboard': [
            ('refresh_cache', 'Tombol Refresh Cache'),       # Floating button refresh cache tenant
        ],
        'produk': [
            ('kategori', 'Kategori'),              # CRUD Kategori Produk
            ('satuan', 'Satuan'),                   # CRUD Satuan (pcs, kg, liter)
            ('daftar_produk', 'Daftar Produk'),     # List semua produk
            ('tambah_produk', 'Tambah Produk'),     # Form tambah produk baru
            ('produk_import', 'Import Produk'),      # Import produk dari CSV/Excel
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
            ('purchase_order_import', 'Import Purchase Order'), # Import PO dari CSV/Excel
        ],
        'penjualan': [
            ('customer', 'Customer'),               # CRUD Customer
            ('sales_order', 'Sales Order'),          # CRUD Sales Order
            ('transaksi_pos', 'Transaksi POS'),     # Daftar transaksi POS
        ],
        'kas_bank': [
            ('dashboard', 'Dashboard Treasury'),       # Ringkasan saldo dan arus kas/bank
            ('akun', 'Akun Kas & Bank'),             # Rekening kas/bank/ewallet/clearing
            ('mutasi', 'Mutasi Kas & Bank'),         # Kas masuk/keluar dari transaksi operasional
            ('transfer', 'Transfer Kas & Bank'),     # Transfer internal antar akun kas/bank
            ('rekonsiliasi', 'Rekonsiliasi Kas & Bank'), # Cocokkan saldo sistem dengan statement
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
            ('penggajian_import', 'Import Penggajian'),       # Import slip gaji dari CSV/Excel
            ('pengaturan_absensi', 'Pengaturan Absensi'),    # Setting absensi
        ],
        'laporan': [
            ('laporan_produk', 'Laporan Produk'),           # Laporan produk
            ('laporan_stok', 'Laporan Stok'),               # Laporan stok
            ('laporan_penjualan', 'Laporan Penjualan'),     # Laporan penjualan
            ('laporan_pembelian', 'Laporan Pembelian'),     # Laporan pembelian
            ('laporan_keuangan', 'Laporan Keuangan Operasional'), # Laporan keuangan operasional
            ('laporan_service', 'Laporan Service'),         # Laporan service center
            ('laporan_sparepart', 'Laporan Sparepart'),     # Laporan penggunaan sparepart
            ('laporan_cabang', 'Laporan Cabang'),           # Laporan cabang
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
            ('chat_widget', 'Tombol AI Assistant'),           # Floating AI Chat Assistant
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
        # ========== AKUNTANSI ==========
        'akuntansi': [
            ('coa', 'Chart of Accounts'),              # Bagan akun
            ('jurnal', 'Jurnal Umum'),                  # Jurnal entry
            ('buku_besar', 'Buku Besar'),               # General Ledger
            ('periode', 'Periode Akuntansi'),           # Tutup buku / periode
            ('panduan', 'Panduan Akuntansi'),           # Panduan & referensi
        ],
        'laporan_keuangan': [
            ('trial_balance', 'Neraca Saldo'),          # Trial Balance
            ('laba_rugi', 'Laporan Laba Rugi'),         # Income Statement
            ('neraca', 'Neraca Keuangan'),              # Balance Sheet
            ('arus_kas', 'Laporan Arus Kas'),           # Cash Flow Statement
        ],
        'piutang': [
            ('daftar_piutang', 'Daftar Piutang'),      # List piutang AR
            ('aging_piutang', 'Aging Report Piutang'), # Aging analysis
        ],
        'hutang': [
            ('daftar_hutang', 'Daftar Hutang'),        # List hutang AP
            ('aging_hutang', 'Aging Report Hutang'),   # Aging analysis
        ],
        'aset': [
            ('daftar_aset', 'Daftar Aset Tetap'),      # Fixed asset list
            ('penyusutan', 'Dashboard Penyusutan'),    # Depreciation dashboard
        ],
        'pajak': [
            ('faktur_pajak', 'Daftar Faktur Pajak'),   # Tax invoice list
            ('rekap_ppn', 'Rekap PPN'),                # VAT summary report
            ('setting_pajak', 'Setting PPN'),          # Konfigurasi tarif PPN dan PKP
        ],
        # Catatan: 'rekonsiliasi_keuangan' TIDAK memiliki sub-modul.
        # Pola sama dengan 'dashboard', 'pos', 'activity_log' — modul tanpa submenu.
        # Permission dicek hanya di level modul (can_view, can_create, can_edit, can_delete).
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
        # === Dashboard ===
        'refresh_cache': 'refresh-cache',
        # === Produk ===
        'kategori': 'kategori',
        'satuan': 'satuan',
        'daftar_produk': 'list',       # sidebar: produk-list
        'tambah_produk': 'tambah',     # sidebar: produk-tambah
        'produk_import': 'import',     # sidebar/url: produk-import
        # === Sparepart ===
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
        'purchase_order_import': 'po-import',
        # === Penjualan ===
        'customer': 'customer',
        'sales_order': 'so',           # sidebar: penjualan-so
        'transaksi_pos': 'transaksi',
        # === Kas & Bank / Treasury ===
        'dashboard': 'dashboard',
        'akun': 'akun',
        'mutasi': 'mutasi',
        'transfer': 'transfer',
        'rekonsiliasi': 'rekonsiliasi',
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
        'penggajian_import': 'penggajian-import',
        'pengaturan_absensi': 'pengaturan-absensi',
        # === Laporan ===
        'laporan_produk': 'produk',
        'laporan_stok': 'stok',
        'laporan_penjualan': 'penjualan',
        'laporan_pembelian': 'pembelian',
        'laporan_keuangan': 'keuangan',
        'laporan_service': 'service',              # sidebar: laporan-service
        'laporan_sparepart': 'sparepart',          # sidebar: laporan-sparepart
        'laporan_cabang': 'cabang',
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
        'chat_widget': 'chat-widget',
        'dashboard_ai': 'dashboard',             # sidebar: ai-dashboard → extract → 'dashboard'
        'pengaturan_ai': 'assistant-settings',   # sidebar: ai-assistant-settings → extract → 'assistant-settings'
        # === Fraud Detection ===
        'dashboard_fraud': 'dashboard',           # sidebar: fraud-dashboard
        'daftar_anomali': 'anomali',              # sidebar: fraud-anomali
        'rekonsiliasi_kas': 'kas',                # sidebar: fraud-kas
        'pengaturan_fraud': 'pengaturan',         # sidebar: fraud-pengaturan
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
        # === Akuntansi ===
        'coa': 'coa',
        'jurnal': 'jurnal',
        'buku_besar': 'buku-besar',
        'periode': 'periode',
        'trial_balance': 'trial-balance',
        'laba_rugi': 'laba-rugi',
        'neraca': 'neraca',
        'arus_kas': 'arus-kas',
        'panduan': 'panduan',
        # === Piutang ===
        'daftar_piutang': 'list',
        'aging_piutang': 'aging',
        # === Hutang ===
        'daftar_hutang': 'list',
        'aging_hutang': 'aging',
        # === Aset ===
        'daftar_aset': 'list',
        'penyusutan': 'penyusutan',
        # === Pajak ===
        'faktur_pajak': 'list',
        'rekap_ppn': 'rekap',
        'setting_pajak': 'setting',
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
        indexes = [
            models.Index(fields=['role', 'module', 'sub_module'], name='core_rp_role_mod_sub_idx'),
            models.Index(fields=['module', 'sub_module'], name='core_rp_mod_sub_idx'),
        ]

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


@receiver(post_save, sender=RolePermission)
@receiver(post_delete, sender=RolePermission)
def invalidate_role_permission_cache_on_change(sender, instance, **kwargs):
    """Pastikan perubahan RolePermission langsung berlaku untuk menu dan action gating."""
    from apps.core.cache_utils import invalidate_role_permissions_cache

    invalidate_role_permissions_cache(instance.role)
