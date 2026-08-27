from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from web_project import TemplateLayout
from apps.core.mixins import ModulePermissionMixin


class ApprovalCenterView(ModulePermissionMixin, LoginRequiredMixin, TemplateView):
    template_name = 'approval_center/index.html'
    permission_module = 'approval_center'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.reimburse.models import ReimburseRequest
        from apps.biaya.models import TransaksiBiaya
        from apps.hr.models import Penggajian
        from apps.pembelian.models import PurchaseOrder

        # ═══ MENUNGGU PERSETUJUAN ═══
        context['pending_reimburse'] = ReimburseRequest.objects.filter(
            status='submitted'
        ).order_by('-tanggal')

        context['pending_biaya'] = TransaksiBiaya.objects.filter(
            status='submitted'
        ).order_by('-tanggal')

        context['pending_penggajian'] = Penggajian.objects.filter(
            status='diproses'
        ).order_by('-dibuat_pada')

        context['pending_po'] = PurchaseOrder.objects.filter(
            status='submitted'
        ).order_by('-tanggal')

        # ═══ MENUNGGU PEMBAYARAN ═══
        context['pending_payment_reimburse'] = ReimburseRequest.objects.filter(
            status='approved'
        ).order_by('-tanggal')

        context['pending_payment_penggajian'] = Penggajian.objects.filter(
            status='diproses'
        ).order_by('-dibuat_pada')

        # ═══ SELESAI (semua modul) ═══
        from itertools import chain
        from django.db.models import Q

        completed_reimburse = ReimburseRequest.objects.filter(
            status__in=['paid', 'completed']
        ).order_by('-dibuat_pada')[:5]

        completed_biaya = TransaksiBiaya.objects.filter(
            status='approved'
        ).order_by('-dibuat_pada')[:5]

        completed_penggajian = Penggajian.objects.filter(
            status='dibayar'
        ).order_by('-dibuat_pada')[:5]

        completed_po = PurchaseOrder.objects.filter(
            status__in=['approved', 'received']
        ).order_by('-dibuat_pada')[:5]

        # Gabung semua completed items, sort by date, ambil 10
        all_completed = sorted(
            list(completed_reimburse) + list(completed_biaya) +
            list(completed_penggajian) + list(completed_po),
            key=lambda x: x.dibuat_pada if hasattr(x, 'dibuat_pada') else x.dibuat_pada,
            reverse=True
        )[:10]
        context['recent_completed_list'] = all_completed

        # ═══ COUNTERS ═══
        context['total_pending'] = (
            context['pending_reimburse'].count()
            + context['pending_biaya'].count()
            + context['pending_penggajian'].count()
            + context['pending_po'].count()
        )
        context['total_payment'] = (
            context['pending_payment_reimburse'].count()
            + context['pending_payment_penggajian'].count()
        )
        context['has_approval'] = context['total_pending'] > 0
        context['has_payment'] = context['total_payment'] > 0

        context['count_reimburse'] = context['pending_reimburse'].count()
        context['count_biaya'] = context['pending_biaya'].count()
        context['count_penggajian'] = context['pending_penggajian'].count()
        context['count_po'] = context['pending_po'].count()
        context['count_pay_reimburse'] = context['pending_payment_reimburse'].count()
        context['count_pay_penggajian'] = context['pending_payment_penggajian'].count()

        # ═══ COMPLETED COUNT (semua modul) ═══
        context['total_completed'] = (
            completed_reimburse.count()
            + completed_biaya.count()
            + completed_penggajian.count()
            + completed_po.count()
        )

        return context
