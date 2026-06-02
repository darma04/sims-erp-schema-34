"""
Management command: validate_metode_pembayaran
Report MetodePembayaran aktif dengan mapping tidak lengkap.
"""
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Report MetodePembayaran aktif dengan mapping Kas/Bank tidak lengkap"

    def handle(self, *args, **options):
        from apps.pos.models import MetodePembayaran
        from apps.kas_bank.services import metode_is_credit

        self.stdout.write(self.style.MIGRATE_HEADING("=== VALIDASI METODE PEMBAYARAN ===\n"))

        aktif_metode = MetodePembayaran.objects.filter(aktif=True)
        issues = []
        checked_count = 0

        for metode in aktif_metode:
            if metode_is_credit(metode):
                continue

            checked_count += 1
            problems = []

            if metode.kas_bank_account is None:
                problems.append("kas_bank_account = NULL")
            elif not metode.kas_bank_account.aktif:
                problems.append(f"kas_bank_account '{metode.kas_bank_account.nama}' tidak aktif")

            if metode.akun_kas_bank is None:
                problems.append("akun_kas_bank = NULL")
            elif not metode.akun_kas_bank.is_active:
                problems.append(f"akun_kas_bank '{metode.akun_kas_bank.kode}' tidak aktif")

            if problems:
                issues.append((metode, problems))

        if not issues:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Semua {checked_count} MetodePembayaran aktif non-kredit memiliki mapping lengkap."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[WARNING] {len(issues)} dari {checked_count} MetodePembayaran aktif non-kredit memiliki masalah:\n"
            ))
            for metode, problems in issues:
                self.stdout.write(f"  [{metode.kode}] {metode.nama}:")
                for p in problems:
                    self.stdout.write(f"    - {p}")
                self.stdout.write("")

            self.stdout.write(
                "  Perbaiki di: Admin > Pengaturan > Metode Pembayaran"
            )
            sys.exit(1)
