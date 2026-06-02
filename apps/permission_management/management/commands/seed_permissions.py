"""
==========================================================================
 SEED PERMISSIONS - Management Command Generate Permission Default
==========================================================================
 Perintah CLI untuk membuat data permission default ke database.
 Berguna saat setup awal atau reset permission ke default.

 Usage:
   python manage.py seed_permissions

 Role default yang dibuat:
 - SUPERUSER → Full access (ditangani kode, bukan database)
 - ADMIN     → Akses hampir semua modul (CRUD, kecuali delete)
 - USER      → Akses dasar (view + create terbatas)
 - KASIR     → Hanya akses dashboard, produk, penjualan, POS

 Format module dengan sub-module: 'module__sub_module'
 Contoh: 'automation__pengaturan_telegram'

 Terhubung dengan:
 - apps/core/models.py → Model RolePermission
==========================================================================
"""

from django.core.management.base import BaseCommand
from apps.core.models import RolePermission


class Command(BaseCommand):
    """Management command Django — dijalankan via python manage.py."""
    help = 'Seed default role permissions'

    def handle(self, *args, **options):
        """Logika utama management command — dipanggil saat command dijalankan."""
        self.stdout.write(self.style.WARNING('Seeding default role permissions...'))
        
        # Default permissions configuration
        # Format: module: {view, create, edit, delete}
        # Sub-modules format: module__sub_module: {view, create, edit, delete}
        permissions_config = {
            'SUPERUSER': {
                # SUPERUSER has full access to everything (handled in code)
            },
            'ADMIN': {
                'dashboard': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'dashboard__refresh_cache': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'produk': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'produk__produk_import': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'inventory': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'pembelian': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'pembelian__purchase_order_import': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'penjualan': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'pos': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'kas_bank': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'kas_bank__dashboard': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__akun': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'kas_bank__mutasi': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'kas_bank__transfer': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'kas_bank__rekonsiliasi': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'biaya': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'laporan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'user_management': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'activity_log': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pengaturan': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'automation': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'automation__pengaturan_telegram': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'automation__template_pesan': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'automation__log_notifikasi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'ai_assistant': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'ai_assistant__chat_widget': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'ai_assistant__dashboard_ai': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'ai_assistant__pengaturan_ai': {'view': True, 'create': False, 'edit': True, 'delete': False},
                # Service Center module + sub-modules
                'service_center': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__dashboard_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__pelanggan_service': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__perangkat': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__kategori_service': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__jenis_service': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__order_service': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'service_center__terima_unit': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__laporan_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Akuntansi
                'akuntansi': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'akuntansi__coa': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'akuntansi__jurnal': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'akuntansi__buku_besar': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__periode': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'akuntansi__panduan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__trial_balance': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__laba_rugi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__neraca': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__arus_kas': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Piutang
                'piutang': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'piutang__daftar_piutang': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'piutang__aging_piutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Hutang
                'hutang': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'hutang__daftar_hutang': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'hutang__aging_hutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Aset Tetap
                'aset': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'aset__daftar_aset': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'aset__penyusutan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Pajak
                'pajak': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'pajak__faktur_pajak': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'pajak__rekap_ppn': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pajak__setting_pajak': {'view': True, 'create': False, 'edit': True, 'delete': False},
            },
            'USER': {
                'dashboard': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'produk': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'produk__produk_import': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'inventory': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pembelian': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'pembelian__purchase_order_import': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'penjualan': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'pos': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'kas_bank': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__dashboard': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__akun': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__mutasi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__transfer': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'kas_bank__rekonsiliasi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'biaya': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'laporan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'activity_log': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'automation': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'automation__pengaturan_telegram': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'automation__template_pesan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'automation__log_notifikasi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Service Center module + sub-modules
                'service_center': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__dashboard_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__pelanggan_service': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__perangkat': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__kategori_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__jenis_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__order_service': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__terima_unit': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__laporan_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                # Akuntansi (view only)
                'akuntansi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__coa': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__jurnal': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__buku_besar': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__periode': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'akuntansi__panduan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__trial_balance': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__laba_rugi': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__neraca': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'laporan_keuangan__arus_kas': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'piutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'piutang__daftar_piutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'piutang__aging_piutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'hutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'hutang__daftar_hutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'hutang__aging_hutang': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'aset': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'aset__daftar_aset': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'aset__penyusutan': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pajak': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pajak__faktur_pajak': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pajak__rekap_ppn': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'pajak__setting_pajak': {'view': True, 'create': False, 'edit': False, 'delete': False},
            },
            'KASIR': {
                'dashboard': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'produk': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'penjualan': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'pos': {'view': True, 'create': True, 'edit': False, 'delete': False},
                # Service Center — kasir bisa lihat order dan terima unit
                'service_center': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__dashboard_service': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'service_center__order_service': {'view': True, 'create': True, 'edit': False, 'delete': False},
                'service_center__terima_unit': {'view': True, 'create': True, 'edit': False, 'delete': False},
            },
        }
        
        created_count = 0
        updated_count = 0
        
        for role, modules in permissions_config.items():
            for module_key, perms in modules.items():
                # Parse module__sub_module format
                if '__' in module_key:
                    module, sub_module = module_key.split('__', 1)
                else:
                    module = module_key
                    sub_module = None
                
                obj, created = RolePermission.objects.update_or_create(
                    role=role,
                    module=module,
                    sub_module=sub_module,
                    defaults={
                        'can_view': perms.get('view', False),
                        'can_create': perms.get('create', False),
                        'can_edit': perms.get('edit', False),
                        'can_delete': perms.get('delete', False),
                        'description': f'Default permission untuk {role} pada module {module}' + (f' > {sub_module}' if sub_module else '')
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  + Created: {obj}'))
                else:
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(f'  ~ Updated: {obj}'))
        
        self.stdout.write(self.style.SUCCESS(f'\nSeeding complete!'))
        self.stdout.write(self.style.SUCCESS(f'   Created: {created_count} permissions'))
        self.stdout.write(self.style.SUCCESS(f'   Updated: {updated_count} permissions'))
