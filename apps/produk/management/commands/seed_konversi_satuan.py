"""
Seed master Satuan dan KonversiSatuan default.

Jalankan:
    python manage.py seed_konversi_satuan
    python manage.py seed_konversi_satuan --dry-run

Command ini idempotent:
- Tidak membuat Satuan duplikat jika nama/singkatan/alias sudah ada.
- Menormalisasi singkatan umum seperti gram -> g, liter -> l, meter -> m.
- Membuat konversi global standar untuk satuan universal dan packaging default.

Catatan:
Konversi packaging seperti box -> pcs adalah default awal. Jika isi kemasan
berbeda per produk, tambahkan KonversiSatuan khusus produk agar override global.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.produk.models import KonversiSatuan, Satuan


DEFAULT_UNITS = [
    # Unit / count
    ("Pieces", "pcs", ["pc", "pcs", "piece", "pieces", "pce"]),
    ("Unit", "unit", ["unit", "unt"]),
    ("Buah", "buah", ["buah", "bh"]),
    ("Set", "set", ["set"]),
    ("Pair", "pair", ["pair", "pr"]),
    ("Pasang", "psng", ["psng", "pasang", "psg"]),
    ("Lusin", "lsn", ["lsn", "lusin", "dozen", "dz"]),
    ("Kodi", "kodi", ["kodi"]),
    ("Gross", "gross", ["gross", "grs"]),
    ("Pack", "pack", ["pack", "pak"]),
    ("Bundle", "bdl", ["bdl", "bundle", "bundel"]),
    ("Paket", "pkt", ["pkt", "paket"]),
    ("Box", "box", ["box", "bx"]),
    ("Dus", "dus", ["dus"]),
    ("Karton", "ctn", ["ctn", "karton", "carton", "krt"]),
    ("Pallet", "plt", ["plt", "pallet"]),
    ("Roll", "roll", ["roll", "rol"]),
    ("Lembar", "lbr", ["lbr", "lembar"]),
    ("Rim", "rim", ["rim", "ream"]),
    ("Sheet", "sheet", ["sheet", "sht"]),
    ("Strip", "strip", ["strip"]),
    ("Sachet", "sch", ["sch", "sachet", "sct"]),
    ("Tablet", "tab", ["tab", "tablet"]),
    ("Kapsul", "cap", ["cap", "capsule", "kapsul"]),
    ("Blister", "bls", ["bls", "blister"]),
    ("Tray", "tray", ["tray"]),
    ("Slop", "slop", ["slop"]),

    # Weight
    ("Milligram", "mg", ["mg", "milligram"]),
    ("Gram", "g", ["g", "gr", "gram"]),
    ("Kilogram", "kg", ["kg", "kilogram"]),
    ("Ons", "ons", ["ons"]),
    ("Pound", "lb", ["lb", "lbs", "pound"]),
    ("Ounce", "oz", ["oz", "ounce"]),
    ("Kuintal", "kw", ["kw", "kuintal", "kwintal"]),
    ("Ton", "ton", ["ton"]),
    ("Sak", "sak", ["sak"]),
    ("Karung", "krg", ["krg", "karung"]),

    # Liquid / container
    ("Milliliter", "ml", ["ml", "milliliter", "mililiter"]),
    ("Centiliter", "cl", ["cl", "centiliter"]),
    ("Liter", "l", ["l", "lt", "ltr", "liter"]),
    ("Galon", "gal", ["gal", "galon", "gallon"]),
    ("Drum", "drum", ["drum"]),
    ("Jerigen", "jrg", ["jrg", "jerigen", "jirigen"]),
    ("Botol", "btl", ["btl", "botol", "bottle", "bootle"]),
    ("Kaleng", "klg", ["klg", "kaleng", "can"]),
    ("Cup", "cup", ["cup"]),
    ("Pail", "pail", ["pail", "ember"]),
    ("Tube", "tube", ["tube"]),
    ("Tabung", "tbg", ["tbg", "tabung"]),

    # Length
    ("Millimeter", "mm", ["mm", "millimeter", "milimeter"]),
    ("Centimeter", "cm", ["cm", "centimeter", "sentimeter"]),
    ("Meter", "m", ["m", "meter"]),
    ("Kilometer", "km", ["km", "kilometer"]),
    ("Inch", "inch", ["inch", "in"]),
    ("Feet", "ft", ["ft", "feet", "foot"]),
    ("Yard", "yd", ["yd", "yard"]),

    # Area
    ("Centimeter Persegi", "cm2", ["cm2", "cm^2", "cm\u00b2", "cm\u00c2\u00b2"]),
    ("Meter Persegi", "m2", ["m2", "m^2", "m\u00b2", "m\u00c2\u00b2"]),
    ("Are", "are", ["are"]),
    ("Hektar", "ha", ["ha", "hektar", "hectare"]),

    # Cubic volume
    ("Centimeter Kubik", "cm3", ["cm3", "cm^3", "cm\u00b3", "cm\u00c2\u00b3"]),
    ("Meter Kubik", "m3", ["m3", "m^3", "m\u00b3", "m\u00c2\u00b3"]),
]


DEFAULT_CONVERSIONS = [
    # Count and retail packaging defaults
    ("lsn", "pcs", "12"),
    ("lsn", "buah", "12"),
    ("kodi", "pcs", "20"),
    ("gross", "pcs", "144"),
    ("psng", "pcs", "2"),
    ("rim", "lbr", "500"),
    ("rim", "sheet", "500"),
    ("pack", "pcs", "6"),
    ("box", "pcs", "12"),
    ("dus", "pcs", "24"),
    ("ctn", "pcs", "24"),
    ("ctn", "box", "2"),
    ("plt", "ctn", "40"),
    ("plt", "pcs", "960"),
    ("bdl", "pcs", "10"),
    ("tray", "pcs", "30"),
    ("tray", "buah", "30"),
    ("slop", "pack", "10"),
    ("strip", "tab", "10"),
    ("bls", "tab", "10"),

    # Weight
    ("ton", "kg", "1000"),
    ("kw", "kg", "100"),
    ("kg", "g", "1000"),
    ("kg", "mg", "1000000"),
    ("g", "mg", "1000"),
    ("ons", "g", "100"),
    ("lb", "g", "453.5924"),
    ("oz", "g", "28.3495"),
    ("sak", "kg", "50"),
    ("krg", "kg", "50"),

    # Liquid / volume
    ("l", "ml", "1000"),
    ("cl", "ml", "10"),
    ("gal", "l", "19"),
    ("gal", "ml", "19000"),
    ("drum", "l", "200"),
    ("drum", "ml", "200000"),
    ("jrg", "l", "20"),
    ("jrg", "ml", "20000"),
    ("m3", "l", "1000"),
    ("m3", "ml", "1000000"),
    ("m3", "cm3", "1000000"),
    ("cm3", "ml", "1"),

    # Length
    ("km", "m", "1000"),
    ("km", "cm", "100000"),
    ("m", "cm", "100"),
    ("m", "mm", "1000"),
    ("cm", "mm", "10"),
    ("inch", "cm", "2.54"),
    ("ft", "inch", "12"),
    ("yd", "ft", "3"),
    ("roll", "m", "50"),

    # Area
    ("m2", "cm2", "10000"),
    ("ha", "m2", "10000"),
    ("are", "m2", "100"),
    ("ha", "are", "100"),
]


class Command(BaseCommand):
    help = "Seed Satuan dan KonversiSatuan default secara idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview perubahan tanpa menulis ke database.",
        )
        parser.add_argument(
            "--no-update",
            action="store_true",
            help="Jangan normalisasi nama/singkatan/faktor yang sudah ada.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        update_existing = not options["no_update"]

        self.stdout.write(self.style.MIGRATE_HEADING("Seed satuan dan konversi default"))
        if dry_run:
            self.stdout.write("[DRY-RUN] Database tidak akan diubah.")

        with transaction.atomic():
            unit_map, unit_stats = self.seed_units(dry_run, update_existing)
            conversion_stats = self.seed_conversions(unit_map, dry_run, update_existing)

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            "Satuan: {created} dibuat, {updated} dinormalisasi, {skipped} sudah sesuai.".format(
                **unit_stats
            )
        )
        self.stdout.write(
            "Konversi: {created} dibuat, {updated} diperbarui, {skipped} sudah sesuai.".format(
                **conversion_stats
            )
        )
        self.stdout.write(f"Total master Satuan: {Satuan.objects.count()}")
        self.stdout.write(
            f"Total KonversiSatuan global: {KonversiSatuan.objects.filter(produk__isnull=True).count()}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run selesai. Jalankan tanpa --dry-run untuk eksekusi."))
        else:
            self.stdout.write(self.style.SUCCESS("Seed satuan dan konversi selesai."))

    def seed_units(self, dry_run, update_existing):
        stats = {"created": 0, "updated": 0, "skipped": 0}
        unit_map = {}

        for name, code, aliases in DEFAULT_UNITS:
            unit = self.find_unit(name, code, aliases)
            if unit:
                changes = {}
                if update_existing and unit.nama != name:
                    changes["nama"] = name
                if update_existing and unit.singkatan != code:
                    changes["singkatan"] = code

                if changes:
                    stats["updated"] += 1
                    if not dry_run:
                        for field, value in changes.items():
                            setattr(unit, field, value)
                        unit.save(update_fields=list(changes.keys()))
                else:
                    stats["skipped"] += 1

                unit_map[code] = unit
                continue

            stats["created"] += 1
            if dry_run:
                unit_map[code] = None
            else:
                unit_map[code] = Satuan.objects.create(nama=name, singkatan=code)

        return unit_map, stats

    def seed_conversions(self, unit_map, dry_run, update_existing):
        stats = {"created": 0, "updated": 0, "skipped": 0}

        for from_code, to_code, factor_text in DEFAULT_CONVERSIONS:
            factor = Decimal(factor_text)
            from_unit = unit_map.get(from_code)
            to_unit = unit_map.get(to_code)

            if dry_run and (from_unit is None or to_unit is None):
                stats["created"] += 1
                continue

            if not from_unit or not to_unit:
                self.stdout.write(self.style.WARNING(
                    f"Konversi dilewati, satuan belum tersedia: {from_code} -> {to_code}"
                ))
                continue

            conversion = KonversiSatuan.objects.filter(
                dari_satuan=from_unit,
                ke_satuan=to_unit,
                produk__isnull=True,
            ).first()

            if conversion:
                if update_existing and conversion.faktor_konversi != factor:
                    stats["updated"] += 1
                    if not dry_run:
                        conversion.faktor_konversi = factor
                        conversion.save(update_fields=["faktor_konversi"])
                else:
                    stats["skipped"] += 1
                continue

            stats["created"] += 1
            if not dry_run:
                KonversiSatuan.objects.create(
                    dari_satuan=from_unit,
                    ke_satuan=to_unit,
                    faktor_konversi=factor,
                    produk=None,
                )

        return stats

    @staticmethod
    def find_unit(name, code, aliases):
        lookup_values = [code, *aliases]
        for value in lookup_values:
            unit = Satuan.objects.filter(singkatan__iexact=value).first()
            if unit:
                return unit

        names = {name, name.lower(), name.title()}
        for value in names:
            unit = Satuan.objects.filter(nama__iexact=value).first()
            if unit:
                return unit

        return None
