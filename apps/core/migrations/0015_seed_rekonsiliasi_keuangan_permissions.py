from django.db import migrations


def seed_rekonsiliasi_keuangan_permissions(apps, schema_editor):
    RolePermission = apps.get_model("core", "RolePermission")

    roles = (
        RolePermission.objects.order_by()
        .values_list("role", flat=True)
        .distinct()
    )

    for role in roles:
        if not role or role == "SUPERUSER":
            continue

        exists = RolePermission.objects.filter(
            role=role,
            module="rekonsiliasi_keuangan",
            sub_module__isnull=True,
        ).exists()
        if exists:
            continue

        RolePermission.objects.create(
            role=role,
            module="rekonsiliasi_keuangan",
            sub_module=None,
            can_view=True,
            can_create=False,
            can_edit=False,
            can_delete=False,
            description=f"Auto-seeded permission for Rekonsiliasi Keuangan ({role})",
        )


def unseed_rekonsiliasi_keuangan_permissions(apps, schema_editor):
    RolePermission = apps.get_model("core", "RolePermission")
    RolePermission.objects.filter(
        module="rekonsiliasi_keuangan",
        description__startswith="Auto-seeded permission for Rekonsiliasi Keuangan",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_delete_licenseconfig"),
    ]

    operations = [
        migrations.RunPython(
            seed_rekonsiliasi_keuangan_permissions,
            unseed_rekonsiliasi_keuangan_permissions,
        ),
    ]
