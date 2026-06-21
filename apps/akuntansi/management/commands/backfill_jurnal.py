"""
Management command: backfill_jurnal
Buat jurnal untuk transaksi yang terdeteksi hilang (orphaned).
Idempotent: aman dijalankan berulang kali tanpa duplikasi.
"""
import sys

from django.core.management.base import BaseCommand
from apps.akuntansi.models import JurnalEntry


class Command(BaseCommand):
    help = "Backfill jurnal untuk transaksi yang terdeteksi hilang"

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            choices=['biaya', 'penjualan', 'pembelian', 'pos', 'hr', 'all'],
            default='all',
            help='Modul yang akan di-backfill (default: all)'
        )
        parser.add_argument(
            '--yes', action='store_true',
            help='Skip konfirmasi (langsung proses)'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview saja, tidak membuat jurnal'
        )

    def handle(self, *args, **options):
        module = options['module']
        dry_run = options['dry_run']
        auto_yes = options['yes']

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== BACKFILL JURNAL V35 ===\n"
        ))

        total_processed = 0
        total_created = 0

        if module in ('biaya', 'all'):
            created = self._backfill_biaya(dry_run)
            total_created += created

        if module in ('pos', 'all'):
            created = self._backfill_pos(dry_run)
            total_created += created

        if module in ('penjualan', 'all'):
            created = self._backfill_so(dry_run)
            total_created += created

        if module in ('pembelian', 'all'):
            created = self._backfill_po(dry_run)
            total_created += created

        if module in ('hr', 'all'):
            created = self._backfill_hr(dry_run)
            total_created += created

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY-RUN] {total_created} transaksi AKAN diproses. "
                f"Jalankan tanpa --dry-run untuk eksekusi."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Selesai. {total_created} transaksi berhasil diproses."
            ))

    def _backfill_biaya(self, dry_run):
        from apps.biaya.models import TransaksiBiaya
        from apps.biaya.services import ensure_biaya_accounting

        orphans = TransaksiBiaya.objects.filter(
            status='approved'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(
                sumber='biaya'
            ).values_list('sumber_id', flat=True)
        )
        count = orphans.count()
        self.stdout.write(f"  Biaya approved tanpa jurnal: {count}")

        if count == 0 or dry_run:
            return count

        created = 0
        for trx in orphans:
            try:
                ensure_biaya_accounting(trx, user=trx.disetujui_oleh)
                created += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"    GAGAL: {trx.nomor_transaksi} - {e}")
                )
        return created

    def _backfill_pos(self, dry_run):
        from apps.pos.models import POSTransaction

        orphans = POSTransaction.objects.filter(
            status__in=['paid', 'unpaid']
        ).exclude(
            pk__in=JurnalEntry.objects.filter(
                sumber='pos'
            ).values_list('sumber_id', flat=True)
        )
        count = orphans.count()
        self.stdout.write(f"  POS paid/unpaid tanpa jurnal: {count}")

        if count == 0 or dry_run:
            return count

        created = 0
        for pos in orphans:
            try:
                if pos.status == 'unpaid':
                    from apps.pos.services import ensure_pos_kasbon_accounting
                    ensure_pos_kasbon_accounting(pos, user=pos.kasir)
                # For 'paid', signal should have created it
                # Re-trigger by saving (signal will handle idempotently)
                elif pos.status == 'paid':
                    pos.save()
                created += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"    GAGAL: {pos.nomor_transaksi} - {e}"
                    )
                )
        return created

    def _backfill_so(self, dry_run):
        from apps.penjualan.models import SalesOrder

        orphans = SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed']
        ).exclude(
            pk__in=JurnalEntry.objects.filter(
                sumber='so'
            ).values_list('sumber_id', flat=True)
        )
        count = orphans.count()
        self.stdout.write(f"  SO confirmed+ tanpa jurnal: {count}")

        if count == 0 or dry_run:
            return count

        created = 0
        for so in orphans:
            try:
                so.save()  # Re-trigger signal (idempotent)
                created += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"    GAGAL: {so.nomor_so} - {e}")
                )
        return created

    def _backfill_po(self, dry_run):
        from apps.pembelian.models import PurchaseOrder

        orphans = PurchaseOrder.objects.filter(
            status='received'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(
                sumber='po'
            ).values_list('sumber_id', flat=True)
        )
        count = orphans.count()
        self.stdout.write(f"  PO received tanpa jurnal: {count}")

        if count == 0 or dry_run:
            return count

        created = 0
        for po in orphans:
            try:
                po.save()  # Re-trigger signal (idempotent)
                created += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"    GAGAL: {po.nomor_po} - {e}")
                )
        return created

    def _backfill_hr(self, dry_run):
        from apps.hr.models import Penggajian

        orphans = Penggajian.objects.filter(
            status='dibayar'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(
                sumber__in=['payroll', 'hr']
            ).values_list('sumber_id', flat=True)
        )
        count = orphans.count()
        self.stdout.write(f"  Penggajian dibayar tanpa jurnal: {count}")

        if count == 0 or dry_run:
            return count

        created = 0
        for p in orphans:
            try:
                p.save()  # Re-trigger signal (idempotent)
                created += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"    GAGAL: {p.karyawan.nama} {p.periode_bulan}/{p.periode_tahun} - {e}"
                    )
                )
        return created
