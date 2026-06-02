"""
==========================================================================
 ASET — Management Command: auto_susutkan
==========================================================================
 Memproses penyusutan bulanan untuk SEMUA aset yang berstatus 'aktif'
 dan masih memiliki sisa umur ekonomis. Idempotent: jika record penyusutan
 untuk (aset, bulan, tahun) sudah ada, aset tersebut akan dilewati.

 Untuk tiap aset yang memenuhi syarat:
   - Buat record Penyusutan
   - Buat jurnal otomatis: D 6-4000 K 1-4100 (sumber='aset')
   - Link jurnal ke record Penyusutan

 Contoh pemakaian:
   python manage.py auto_susutkan                  # bulan & tahun saat ini
   python manage.py auto_susutkan --bulan 5 --tahun 2026
   python manage.py auto_susutkan --aset 12        # hanya aset dengan PK=12
   python manage.py auto_susutkan --dry-run        # simulasi tanpa commit
==========================================================================
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.aset.models import AsetTetap, Penyusutan


class Command(BaseCommand):
    help = "Proses penyusutan bulanan otomatis untuk semua aset aktif"

    def add_arguments(self, parser):
        parser.add_argument("--bulan", type=int, default=None, help="Bulan (1-12), default = bulan berjalan")
        parser.add_argument("--tahun", type=int, default=None, help="Tahun, default = tahun berjalan")
        parser.add_argument("--aset", type=int, default=None, help="PK aset spesifik (opsional)")
        parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan ke database")

    def handle(self, *args, **options):
        today = timezone.now().date()
        bulan = options["bulan"] or today.month
        tahun = options["tahun"] or today.year
        dry_run = options["dry_run"]
        aset_pk = options["aset"]

        if not (1 <= bulan <= 12):
            self.stderr.write(self.style.ERROR(f"Bulan tidak valid: {bulan}"))
            return

        qs = AsetTetap.objects.filter(status="aktif").select_related("cabang", "akun_aset")
        if aset_pk:
            qs = qs.filter(pk=aset_pk)

        total_aset = qs.count()
        if total_aset == 0:
            self.stdout.write(self.style.WARNING("Tidak ada aset aktif untuk diproses."))
            return

        processed = 0
        skipped = 0
        failed = 0
        total_nominal = Decimal("0")

        self.stdout.write(self.style.NOTICE(
            f"Memproses penyusutan {bulan:02d}/{tahun} untuk {total_aset} aset aktif "
            f"{'(DRY RUN)' if dry_run else ''}"
        ))

        for aset in qs:
            # Skip jika sudah ada record penyusutan untuk periode tersebut
            if Penyusutan.objects.filter(aset=aset, bulan=bulan, tahun=tahun).exists():
                skipped += 1
                self.stdout.write(f"  · {aset.kode} - {aset.nama}: sudah ada penyusutan {bulan:02d}/{tahun}")
                continue

            # Skip jika sisa umur sudah habis
            if aset.sisa_umur_bulan <= 0:
                skipped += 1
                self.stdout.write(f"  · {aset.kode} - {aset.nama}: umur ekonomis habis")
                continue

            jumlah = aset.penyusutan_per_bulan
            if jumlah <= 0:
                skipped += 1
                continue

            akumulasi_baru = aset.akumulasi_penyusutan + jumlah

            try:
                if dry_run:
                    self.stdout.write(
                        f"  + {aset.kode} - {aset.nama}: akan susut Rp {jumlah:,.0f} "
                        f"(akumulasi {akumulasi_baru:,.0f})"
                    )
                else:
                    with transaction.atomic():
                        peny = Penyusutan.objects.create(
                            aset=aset,
                            bulan=bulan,
                            tahun=tahun,
                            jumlah=jumlah,
                            akumulasi=akumulasi_baru,
                        )
                        from apps.aset.services import ensure_penyusutan_accounting
                        ensure_penyusutan_accounting(peny, tanggal=today)
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ {aset.kode} - {aset.nama}: susut Rp {jumlah:,.0f}"
                    ))
                processed += 1
                total_nominal += jumlah
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f"  ✗ {aset.kode} - {aset.nama}: gagal — {exc}"
                ))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Selesai: {processed} diproses, {skipped} dilewati, {failed} gagal. "
            f"Total nominal: Rp {total_nominal:,.0f}"
            f"{' (DRY RUN — tidak disimpan)' if dry_run else ''}"
        ))
