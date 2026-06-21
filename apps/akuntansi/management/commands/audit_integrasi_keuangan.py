"""
Management command: audit_integrasi_keuangan
Deteksi inkonsistensi data antara modul operasional dan akuntansi.
"""
import sys

from django.core.management.base import BaseCommand
from django.db import models
from django.db.models import Count

from apps.akuntansi.models import JurnalEntry


class Command(BaseCommand):
    help = "Audit integritas data antara modul operasional dan akuntansi V35"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== AUDIT INTEGRASI KEUANGAN V35 ===\n"))

        total_issues = 0

        # 1. SO confirmed/delivered/completed tanpa JurnalEntry
        from apps.penjualan.models import SalesOrder
        so_orphans = SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed']
        ).exclude(
            pk__in=JurnalEntry.objects.filter(sumber='so').values_list('sumber_id', flat=True)
        )
        count = so_orphans.count()
        total_issues += count
        self.stdout.write(f"  SO tanpa jurnal: {count}")
        if count > 0:
            for so in so_orphans[:5]:
                self.stdout.write(f"    - {so.nomor_so} (status: {so.status})")

        # 2. PO received tanpa JurnalEntry
        from apps.pembelian.models import PurchaseOrder
        po_orphans = PurchaseOrder.objects.filter(
            status='received'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(sumber='po').values_list('sumber_id', flat=True)
        )
        count = po_orphans.count()
        total_issues += count
        self.stdout.write(f"  PO tanpa jurnal: {count}")
        if count > 0:
            for po in po_orphans[:5]:
                self.stdout.write(f"    - {po.nomor_po}")

        # 3. POS paid/unpaid tanpa JurnalEntry
        from apps.pos.models import POSTransaction
        pos_orphans = POSTransaction.objects.filter(
            status__in=['paid', 'unpaid']
        ).exclude(
            pk__in=JurnalEntry.objects.filter(sumber='pos').values_list('sumber_id', flat=True)
        )
        count = pos_orphans.count()
        total_issues += count
        self.stdout.write(f"  POS tanpa jurnal: {count}")
        if count > 0:
            for pos in pos_orphans[:5]:
                self.stdout.write(f"    - {pos.nomor_transaksi} (status: {pos.status})")

        # 4. TransaksiBiaya approved tanpa JurnalEntry
        from apps.biaya.models import TransaksiBiaya
        biaya_orphans = TransaksiBiaya.objects.filter(
            status='approved'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(sumber='biaya').values_list('sumber_id', flat=True)
        )
        count = biaya_orphans.count()
        total_issues += count
        self.stdout.write(f"  Biaya tanpa jurnal: {count}")
        if count > 0:
            for b in biaya_orphans[:5]:
                self.stdout.write(f"    - {b.nomor_transaksi}")

        # 5. Penggajian dibayar tanpa JurnalEntry
        from apps.hr.models import Penggajian
        hr_orphans = Penggajian.objects.filter(
            status='dibayar'
        ).exclude(
            pk__in=JurnalEntry.objects.filter(sumber__in=['payroll', 'hr']).values_list('sumber_id', flat=True)
        )
        count = hr_orphans.count()
        total_issues += count
        self.stdout.write(f"  Penggajian tanpa jurnal: {count}")
        if count > 0:
            for p in hr_orphans[:5]:
                self.stdout.write(f"    - {p.karyawan.nama} ({p.periode_bulan}/{p.periode_tahun})")

        # 6. JurnalEntry duplikat (same sumber + sumber_id)
        duplicates = JurnalEntry.objects.values('sumber', 'sumber_id').annotate(
            cnt=Count('id')
        ).filter(cnt__gt=1, sumber_id__isnull=False).exclude(
            sumber__in=['pembalik', 'kas_bank']
        )
        # Exclude reversal entries (sumber_ref ends with _reversal or _hpp)
        dup_count = 0
        for dup in duplicates:
            actual_dups = JurnalEntry.objects.filter(
                sumber=dup['sumber'], sumber_id=dup['sumber_id']
            ).exclude(sumber_ref__endswith='_reversal').exclude(sumber_ref__endswith='_hpp')
            if actual_dups.count() > 1:
                dup_count += 1
        total_issues += dup_count
        self.stdout.write(f"  Jurnal duplikat: {dup_count}")

        # 7. MetodePembayaran aktif tanpa mapping lengkap
        from apps.pos.models import MetodePembayaran
        from apps.kas_bank.services import metode_is_credit
        incomplete = MetodePembayaran.objects.filter(aktif=True).filter(
            models.Q(kas_bank_account__isnull=True) | models.Q(akun_kas_bank__isnull=True)
        )
        incomplete = [m for m in incomplete if not metode_is_credit(m)]
        count = len(incomplete)
        total_issues += count
        self.stdout.write(f"  MetodePembayaran tanpa mapping: {count}")
        if count > 0:
            for m in incomplete[:5]:
                self.stdout.write(f"    - {m.nama} (kode: {m.kode})")

        # Summary
        self.stdout.write("")
        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS(
                "[OK] Tidak ada masalah ditemukan. Data konsisten."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[WARNING] Total {total_issues} masalah ditemukan."
            ))
            self.stdout.write(
                "  Jalankan 'python manage.py backfill_jurnal' untuk memperbaiki jurnal yang hilang."
            )
            sys.exit(1)
