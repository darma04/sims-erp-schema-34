"""
Data migration: Backfill KategoriBiaya.akun_beban defaults.

Mapping kategori biaya ke akun beban CoA berdasarkan nama kategori:
- 'listrik' atau 'air' → 6-2000 (Beban Listrik & Air)
- 'sewa' → 6-3000 (Beban Sewa)
- 'gaji' → 6-1000 (Beban Gaji & Tunjangan)
- 'transport' atau 'pengiriman' → 6-7000 (Beban Transport & Pengiriman)
- 'penyusutan' → 6-4000 (Beban Penyusutan)

Hanya set akun_beban jika target Akun exists di CoA; leave NULL otherwise.
"""

from django.db import migrations


# Mapping keyword (case-insensitive) → kode akun CoA
KATEGORI_AKUN_MAP = [
    (['listrik', 'air'], '6-2000'),
    (['sewa'], '6-3000'),
    (['gaji'], '6-1000'),
    (['transport', 'pengiriman'], '6-7000'),
    (['penyusutan'], '6-4000'),
]


def backfill_akun_beban(apps, schema_editor):
    """
    Set akun_beban pada KategoriBiaya berdasarkan case-insensitive matching nama.
    Hanya set jika akun target ada di CoA (Akun model).
    """
    KategoriBiaya = apps.get_model('biaya', 'KategoriBiaya')
    Akun = apps.get_model('akuntansi', 'Akun')

    for keywords, akun_kode in KATEGORI_AKUN_MAP:
        # Cek apakah akun target ada di CoA
        try:
            akun = Akun.objects.get(kode=akun_kode, is_active=True)
        except Akun.DoesNotExist:
            # Akun tidak ada di CoA → skip mapping ini
            continue

        # Cari kategori yang namanya mengandung salah satu keyword (case-insensitive)
        for keyword in keywords:
            kategoris = KategoriBiaya.objects.filter(
                nama__icontains=keyword,
                akun_beban__isnull=True,  # Hanya yang belum punya mapping
            )
            kategoris.update(akun_beban=akun)


def reverse_backfill(apps, schema_editor):
    """Reverse: set semua akun_beban kembali ke NULL."""
    KategoriBiaya = apps.get_model('biaya', 'KategoriBiaya')
    KategoriBiaya.objects.all().update(akun_beban=None)


class Migration(migrations.Migration):

    dependencies = [
        ('biaya', '0005_add_akun_beban_cancelled_fields'),
        ('akuntansi', '0005_add_is_reversed_to_jurnalentry'),
    ]

    operations = [
        migrations.RunPython(
            backfill_akun_beban,
            reverse_code=reverse_backfill,
        ),
    ]
