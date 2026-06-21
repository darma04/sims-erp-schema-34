from django.core.management.base import BaseCommand

from apps.akuntansi.models import JurnalEntry
from apps.kas_bank.services import metode_is_credit


class Command(BaseCommand):
    help = "Audit transaksi operasional yang seharusnya punya jurnal/hutang/piutang."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Coba perbaiki data yang hilang secara idempotent.",
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        issues = []

        issues.extend(self.audit_po(fix))
        issues.extend(self.audit_so(fix))
        issues.extend(self.audit_pos(fix))
        issues.extend(self.audit_biaya(fix))
        issues.extend(self.audit_payroll(fix))
        issues.extend(self.audit_aset(fix))

        if issues:
            self.stdout.write(self.style.WARNING(f"Ditemukan {len(issues)} issue akuntansi:"))
            for issue in issues:
                self.stdout.write(f"- {issue}")
        else:
            self.stdout.write(self.style.SUCCESS("Audit akuntansi bersih."))

    def audit_po(self, fix):
        from apps.pembelian.models import PurchaseOrder
        from apps.hutang.models import Hutang

        issues = []
        for po in PurchaseOrder.objects.filter(status="received").select_related("metode_pembayaran"):
            missing_journal = not JurnalEntry.objects.filter(sumber="po", sumber_id=po.pk).exists()
            is_credit = po.metode_pembayaran is None or metode_is_credit(po.metode_pembayaran)
            missing_hutang = is_credit and not Hutang.objects.filter(sumber="po", purchase_order=po).exists()
            if missing_journal or missing_hutang:
                issues.append(f"PO {po.nomor_po}: jurnal={not missing_journal}, hutang={not missing_hutang}")
                if fix:
                    from apps.pembelian.signals import create_po_journal_and_hutang
                    create_po_journal_and_hutang(PurchaseOrder, po, created=False)
        return issues

    def audit_so(self, fix):
        from apps.penjualan.models import SalesOrder
        from apps.piutang.models import Piutang

        issues = []
        qs = SalesOrder.objects.filter(status__in=["confirmed", "delivered", "completed"]).select_related("metode_pembayaran")
        for so in qs:
            missing_journal = not JurnalEntry.objects.filter(sumber="so", sumber_id=so.pk).exists()
            is_credit = so.metode_pembayaran is None or metode_is_credit(so.metode_pembayaran)
            missing_piutang = is_credit and not Piutang.objects.filter(sumber="so", sales_order=so).exists()
            if missing_journal or missing_piutang:
                issues.append(f"SO {so.nomor_so}: jurnal={not missing_journal}, piutang={not missing_piutang}")
                if fix:
                    from apps.penjualan.signals import create_so_journal_and_piutang
                    create_so_journal_and_piutang(SalesOrder, so, created=False)
        return issues

    def audit_pos(self, fix):
        from apps.pos.models import POSTransaction
        from apps.piutang.models import Piutang

        issues = []
        for trx in POSTransaction.objects.filter(status__in=["paid", "unpaid"]):
            missing_journal = not JurnalEntry.objects.filter(sumber="pos", sumber_id=trx.pk).exists()
            missing_piutang = (
                trx.status == "unpaid" and
                not Piutang.objects.filter(sumber="pos", pos_transaction=trx).exists()
            )
            if missing_journal or missing_piutang:
                issues.append(
                    f"POS {trx.nomor_transaksi}: jurnal={not missing_journal}, piutang={not missing_piutang}"
                )
                if fix:
                    if trx.status == "unpaid":
                        from apps.pos.services import ensure_pos_kasbon_accounting
                        ensure_pos_kasbon_accounting(trx, user=trx.kasir)
                    else:
                        trx.save()
        return issues

    def audit_biaya(self, fix):
        from apps.biaya.models import TransaksiBiaya

        issues = []
        for biaya in TransaksiBiaya.objects.filter(status="approved"):
            missing_journal = not JurnalEntry.objects.filter(sumber="biaya", sumber_id=biaya.pk).exists()
            if missing_journal:
                issues.append(f"Biaya {biaya.nomor_transaksi}: jurnal=False")
                if fix:
                    from apps.biaya.services import ensure_biaya_accounting
                    ensure_biaya_accounting(biaya, user=biaya.disetujui_oleh)
        return issues

    def audit_payroll(self, fix):
        from apps.hr.models import Penggajian

        issues = []
        for penggajian in Penggajian.objects.filter(status="dibayar").select_related("karyawan"):
            missing_journal = not JurnalEntry.objects.filter(
                sumber__in=["payroll", "hr"], sumber_id=penggajian.pk
            ).exists()
            if missing_journal:
                nama = penggajian.karyawan.nama if penggajian.karyawan_id else f"Penggajian #{penggajian.pk}"
                issues.append(
                    f"Penggajian {nama} {penggajian.periode_bulan}/{penggajian.periode_tahun}: jurnal=False"
                )
                if fix:
                    penggajian.save()
        return issues

    def audit_aset(self, fix):
        from apps.aset.models import DisposalAset, Penyusutan

        issues = []
        for peny in Penyusutan.objects.filter(jurnal__isnull=True).select_related("aset"):
            issues.append(f"Penyusutan {peny.aset.kode} {peny.bulan:02d}/{peny.tahun}: jurnal=False")
            if fix:
                from apps.aset.services import ensure_penyusutan_accounting
                ensure_penyusutan_accounting(peny, user=peny.created_by)

        for disposal in DisposalAset.objects.filter(jurnal__isnull=True).select_related("aset"):
            issues.append(f"Disposal {disposal.aset.kode} #{disposal.pk}: jurnal=False")
            if fix:
                from apps.aset.services import ensure_disposal_accounting
                ensure_disposal_accounting(disposal, user=disposal.created_by)
        return issues
