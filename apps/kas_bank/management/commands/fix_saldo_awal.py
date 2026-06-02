"""
==========================================================================
 MANAGEMENT COMMAND: fix_saldo_awal
==========================================================================
 Mendeteksi akun Kas/Bank dengan saldo negatif dan merekomendasikan
 koreksi saldo_awal yang diperlukan.

 Penggunaan:
   python manage.py fix_saldo_awal          → Hanya tampilkan laporan
   python manage.py fix_saldo_awal --apply  → Update saldo_awal ke database

 CATATAN PENTING:
 - Command ini TIDAK mengubah jurnal atau data transaksi
 - Hanya mengubah field saldo_awal pada KasBankAccount
 - Saldo awal yang baru = selisih agar saldo terhitung menjadi >= 0
 - Gunakan --apply hanya jika Anda yakin saldo negatif disebabkan oleh
   saldo_awal yang belum di-set dengan benar (bukan karena data korup)
==========================================================================
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.kas_bank.models import KasBankAccount


class Command(BaseCommand):
    help = "Deteksi dan perbaiki akun Kas/Bank dengan saldo negatif"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Terapkan koreksi saldo_awal ke database (tanpa flag ini hanya menampilkan laporan)",
        )
        parser.add_argument(
            "--target-saldo",
            type=int,
            default=0,
            help="Target saldo minimum setelah koreksi (default: 0)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        target_saldo = Decimal(str(options["target_saldo"]))

        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 60))
        self.stdout.write(self.style.MIGRATE_HEADING(" ANALISIS SALDO KAS/BANK"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))

        accounts = KasBankAccount.objects.filter(aktif=True).order_by("kode")
        negatif_count = 0
        koreksi_list = []

        for acc in accounts:
            saldo = acc.saldo_terhitung

            if saldo < target_saldo:
                negatif_count += 1
                # Hitung saldo_awal baru agar saldo_terhitung = target_saldo
                # saldo_terhitung = saldo_awal + total_masuk - total_keluar
                # target_saldo = saldo_awal_baru + total_masuk - total_keluar
                # saldo_awal_baru = target_saldo - total_masuk + total_keluar
                saldo_awal_baru = target_saldo - acc.total_masuk + acc.total_keluar
                selisih = saldo_awal_baru - acc.saldo_awal

                self.stdout.write(self.style.ERROR(f"\n  ❌ {acc.kode} - {acc.nama}"))
                self.stdout.write(f"     Tipe: {acc.get_tipe_display()}")
                self.stdout.write(f"     Saldo Awal Saat Ini: Rp {acc.saldo_awal:,.0f}")
                self.stdout.write(f"     Total Masuk: Rp {acc.total_masuk:,.0f}")
                self.stdout.write(f"     Total Keluar: Rp {acc.total_keluar:,.0f}")
                self.stdout.write(self.style.WARNING(f"     Saldo Terhitung: Rp {saldo:,.0f}"))
                self.stdout.write(self.style.SUCCESS(f"     → Rekomendasi saldo_awal: Rp {saldo_awal_baru:,.0f} (+Rp {selisih:,.0f})"))

                koreksi_list.append({
                    "account": acc,
                    "saldo_awal_lama": acc.saldo_awal,
                    "saldo_awal_baru": saldo_awal_baru,
                    "selisih": selisih,
                })
            else:
                self.stdout.write(self.style.SUCCESS(f"\n  ✅ {acc.kode} - {acc.nama}: Rp {saldo:,.0f}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "-" * 60))

        if negatif_count == 0:
            self.stdout.write(self.style.SUCCESS("\n  Semua akun Kas/Bank memiliki saldo positif. Tidak ada koreksi diperlukan.\n"))
            return

        self.stdout.write(self.style.WARNING(f"\n  Ditemukan {negatif_count} akun dengan saldo negatif."))

        if not apply:
            self.stdout.write(self.style.NOTICE(
                "\n  Untuk menerapkan koreksi, jalankan:\n"
                "    python manage.py fix_saldo_awal --apply\n"
            ))
            self.stdout.write(
                "  CATATAN: Pastikan saldo negatif memang disebabkan oleh saldo_awal\n"
                "  yang belum di-set (bukan karena data transaksi yang salah).\n"
                "  Alternatif: Set saldo awal manual via Pengaturan > Kas & Bank.\n"
            )
            return

        # Apply corrections
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Menerapkan koreksi..."))
        for item in koreksi_list:
            acc = item["account"]
            acc.saldo_awal = item["saldo_awal_baru"]
            acc.save(update_fields=["saldo_awal"])
            self.stdout.write(self.style.SUCCESS(
                f"    ✅ {acc.kode}: saldo_awal diubah dari "
                f"Rp {item['saldo_awal_lama']:,.0f} → Rp {item['saldo_awal_baru']:,.0f}"
            ))

        self.stdout.write(self.style.SUCCESS(f"\n  Selesai. {len(koreksi_list)} akun dikoreksi.\n"))
