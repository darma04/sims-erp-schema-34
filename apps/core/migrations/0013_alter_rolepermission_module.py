# Generated manually — add rekonsiliasi_keuangan to MODULE_CHOICES

from django.db import migrations, models


def seed_rekonsiliasi_keuangan_permission(apps, schema_editor):
    """
    Seed permission rekonsiliasi_keuangan untuk semua role yang sudah ada.
    Ini memastikan modul baru bisa dikelola di Edit Role / Add Role.
    """
    RolePermission = apps.get_model('core', 'RolePermission')

    # Ambil semua role unik yang sudah ada di database
    existing_roles = RolePermission.objects.values_list('role', flat=True).distinct()

    for role in existing_roles:
        # Buat permission module-level untuk rekonsiliasi_keuangan
        RolePermission.objects.get_or_create(
            role=role,
            module='rekonsiliasi_keuangan',
            sub_module=None,
            defaults={
                'can_view': True,   # Default: semua role bisa lihat
                'can_create': False,
                'can_edit': False,
                'can_delete': False,
                'description': f'Auto-seeded permission for Rekonsiliasi Keuangan ({role})',
            },
        )


def remove_rekonsiliasi_keuangan_permission(apps, schema_editor):
    """Reverse: hapus semua permission rekonsiliasi_keuangan."""
    RolePermission = apps.get_model('core', 'RolePermission')
    RolePermission.objects.filter(module='rekonsiliasi_keuangan').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_alter_rolepermission_module'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rolepermission',
            name='module',
            field=models.CharField(
                choices=[
                    ('dashboard', 'Dashboard'),
                    ('produk', 'Produk'),
                    ('inventory', 'Inventory'),
                    ('pembelian', 'Pembelian'),
                    ('penjualan', 'Penjualan'),
                    ('pos', 'POS / Kasir'),
                    ('kas_bank', 'Kas & Bank / Treasury'),
                    ('biaya', 'Biaya'),
                    ('laporan', 'Laporan'),
                    ('hr', 'HR / Human Resource'),
                    ('user_management', 'User Management'),
                    ('activity_log', 'Log Aktivitas'),
                    ('pengaturan', 'Pengaturan'),
                    ('automation', 'Automasi Telegram'),
                    ('access_control', 'Access Control'),
                    ('ai_assistant', 'AI Manajemen'),
                    ('fraud_detection', 'Fraud Detection'),
                    ('akuntansi', 'Akuntansi'),
                    ('laporan_keuangan', 'Laporan Keuangan'),
                    ('piutang', 'Piutang (AR)'),
                    ('hutang', 'Hutang (AP)'),
                    ('aset', 'Aset Tetap'),
                    ('pajak', 'Pajak (PPN)'),
                    ('rekonsiliasi_keuangan', 'Rekonsiliasi Keuangan'),
                ],
                max_length=50,
                verbose_name='Module',
            ),
        ),
        migrations.RunPython(
            seed_rekonsiliasi_keuangan_permission,
            remove_rekonsiliasi_keuangan_permission,
        ),
    ]
