"""
==========================================================================
 HUTANG VIEWS - Daftar, Detail, Pembayaran, Aging Report
==========================================================================
"""

import logging
logger = logging.getLogger(__name__)

# ==========================================================================
# PANDUAN DJANGO UNTUK DEVELOPER PEMULA (baca ini sebelum mempelajari views)
# ==========================================================================
#
# APA ITU CLASS-BASED VIEW (CBV)?
# - CBV = class Python yang menangani HTTP request dan return response
# - Django menyediakan CBV bawaan: ListView, CreateView, UpdateView, DeleteView
# - Setiap CBV punya "lifecycle" (siklus hidup) yang bisa di-customize
#
# SIKLUS HIDUP CBV (urutan method yang dipanggil):
# 1. as_view()     → Entry point, dipanggil oleh URL router
# 2. dispatch()    → Tentukan method (GET/POST) → panggil get() atau post()
# 3. get()/post()  → Handle request, kumpulkan data
# 4. get_queryset()→ Ambil data dari database (bisa di-filter/optimasi)
# 5. get_context_data() → Siapkan data untuk template (variabel {{ }})
# 6. render()      → Gabungkan template + context → HTML response
#
# METHOD PENTING YANG SERING DI-OVERRIDE:
# - get_queryset()     → Optimasi query (prefetch_related, select_related)
# - get_context_data() → Tambah variabel ke template (self.context)
# - form_valid()       → Proses setelah form divalidasi (sebelum save)
# - get_success_url()  → URL redirect setelah operasi berhasil
#
# DECORATOR YANG SERING DIGUNAKAN:
# @login_required       → User HARUS login, jika tidak → redirect ke /login/
# @permission_required  → User harus punya permission tertentu (RBAC)
# @require_http_methods → Batasi method yang diterima (GET, POST, dll)
# @never_cache          → Response tidak boleh di-cache oleh browser
#
# POLA UMUM VIEW DI PROYEK INI:
# class MyListView(SubModulePermissionMixin, ListView):
#     module_name = 'nama_modul'          # Untuk pengecekan RBAC
#     sub_module_name = 'nama_sub_modul'  # Sub-modul yang diakses
#     model = MyModel                      # Model database yang dipakai
#     template_name = 'modul/page.html'    # File HTML template
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context = TemplateLayout.init(self, context)  # WAJIB: setup layout
#         context['data_tambahan'] = ...    # Tambah data custom
#         return context
# ==========================================================================

from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, Q
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone

from apps.hutang.models import Hutang, PembayaranHutang
from apps.hutang.forms import HutangForm, PembayaranHutangForm
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin





class HutangListView(ReadPermissionMixin, ListView):
    """Daftar hutang. URL: /hutang/"""
    paginate_by = 50
    model = Hutang
    template_name = 'hutang/hutang_list.html'
    context_object_name = 'hutang_list'
    permission_module = 'hutang'
    permission_sub_module = 'daftar_hutang'

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier', 'cabang', 'created_by')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        start = self.request.GET.get('start', '')
        end = self.request.GET.get('end', '')
        if start:
            qs = qs.filter(tanggal__gte=start)
        if end:
            qs = qs.filter(tanggal__lte=end)
        supplier = self.request.GET.get('supplier', '')
        if supplier:
            qs = qs.filter(supplier_id=supplier)
        cabang = self.request.GET.get('cabang', '')
        if cabang:
            qs = qs.filter(cabang_id=cabang)
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(nomor__icontains=q) | Q(supplier__nama__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_hutang = Hutang.objects.all()

        agg = all_hutang.aggregate(
            total_hutang=Sum('jumlah_total'),
            total_dibayar=Sum('jumlah_dibayar'),
        )
        context['total_hutang'] = agg['total_hutang'] or 0
        context['total_dibayar'] = agg['total_dibayar'] or 0
        context['total_sisa'] = (agg['total_hutang'] or 0) - (agg['total_dibayar'] or 0)
        context['count_total'] = all_hutang.count()
        context['count_lunas'] = all_hutang.filter(status='lunas').count()
        context['count_belum'] = all_hutang.filter(status='belum_bayar').count()
        context['count_sebagian'] = all_hutang.filter(status='sebagian').count()

        from apps.pembelian.models import Supplier
        from apps.produk.models import Gudang
        context['supplier_list'] = Supplier.objects.filter(aktif=True)
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['status_choices'] = Hutang.STATUS_CHOICES
        return context


class HutangCreateView(CreatePermissionMixin, CreateView):
    """Input hutang manual. URL: /hutang/add/"""
    model = Hutang
    form_class = HutangForm
    template_name = 'hutang/hutang_form.html'
    success_url = reverse_lazy('hutang:list')
    permission_module = 'hutang'
    permission_sub_module = 'daftar_hutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Input Hutang Baru'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.sumber = 'manual'
        messages.success(self.request, 'Hutang berhasil ditambahkan')
        return super().form_valid(form)


class HutangDetailView(ReadPermissionMixin, TemplateView):
    """Detail hutang + riwayat pembayaran. URL: /hutang/<pk>/"""
    template_name = 'hutang/hutang_detail.html'
    permission_module = 'hutang'
    permission_sub_module = 'daftar_hutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        hutang = get_object_or_404(
            Hutang.objects.select_related('supplier', 'cabang', 'purchase_order'),
            pk=kwargs['pk']
        )
        context['hutang'] = hutang
        context['pembayaran_list'] = hutang.pembayaran_set.select_related('metode_pembayaran', 'jurnal').all()
        context['bayar_form'] = PembayaranHutangForm(hutang=hutang)
        return context


class PembayaranHutangCreateView(CreatePermissionMixin, CreateView):
    """Form pembayaran hutang. URL: /hutang/<pk>/bayar/ (POST)"""
    model = PembayaranHutang
    form_class = PembayaranHutangForm
    template_name = 'hutang/hutang_detail.html'
    permission_module = 'hutang'
    permission_sub_module = 'daftar_hutang'

    def get_hutang(self):
        return get_object_or_404(Hutang, pk=self.kwargs['pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hutang'] = self.get_hutang()
        return kwargs

    def form_valid(self, form):
        hutang = self.get_hutang()

        if hutang.status == 'lunas':
            messages.error(self.request, 'Hutang sudah lunas!')
            return redirect('hutang:detail', pk=hutang.pk)

        try:
            with transaction.atomic():
                form.instance.hutang = hutang
                form.instance.created_by = self.request.user
                self.object = form.save()

                # Jurnal dan mutasi Kas/Bank dibuat oleh PembayaranHutang.save().
                # View tidak membuat ulang agar jurnal tidak dobel.

                try:
                    from apps.activity_log.middleware import ActivityLogMiddleware
                    ActivityLogMiddleware.log_activity(
                        self.request, action='create', model_name='Pembayaran Hutang',
                        object_id=self.object.pk, object_repr=str(self.object),
                        description=f'Pembayaran hutang {hutang.nomor}: Rp {form.instance.jumlah:,.0f}'
                    )
                except Exception as e:
                    logger.warning("Gagal mencatat activity log: %s", e)
        except (ValidationError, ValueError) as exc:
            messages.error(self.request, str(exc))
            return redirect('hutang:detail', pk=hutang.pk)

        messages.success(self.request, f'Pembayaran Rp {form.instance.jumlah:,.0f} berhasil dicatat')
        return redirect('hutang:detail', pk=hutang.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Gagal mencatat pembayaran.')
        return redirect('hutang:detail', pk=self.kwargs['pk'])


class AgingReportView(ReadPermissionMixin, TemplateView):
    """Aging Report Hutang. URL: /hutang/aging/"""
    template_name = 'hutang/aging_report.html'
    permission_module = 'hutang'
    permission_sub_module = 'aging_hutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        active_hutang = Hutang.objects.filter(
            status__in=['belum_bayar', 'sebagian', 'macet']
        ).select_related('supplier', 'cabang')

        cabang_id = self.request.GET.get('cabang', '')
        if cabang_id:
            active_hutang = active_hutang.filter(cabang_id=cabang_id)

        buckets = {
            'current': {'label': 'Belum Jatuh Tempo', 'items': [], 'total': Decimal('0')},
            '1-30': {'label': '1-30 Hari', 'items': [], 'total': Decimal('0')},
            '31-60': {'label': '31-60 Hari', 'items': [], 'total': Decimal('0')},
            '61-90': {'label': '61-90 Hari', 'items': [], 'total': Decimal('0')},
            '>90': {'label': '> 90 Hari', 'items': [], 'total': Decimal('0')},
        }

        for h in active_hutang:
            sisa = h.sisa
            bucket_key = h.aging_bucket
            if bucket_key in buckets:
                buckets[bucket_key]['items'].append(h)
                buckets[bucket_key]['total'] += sisa

        context['buckets'] = buckets
        context['grand_total'] = sum(b['total'] for b in buckets.values())
        context['chart_labels'] = [b['label'] for b in buckets.values()]
        context['chart_data'] = [float(b['total']) for b in buckets.values()]

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['selected_cabang'] = cabang_id
        return context
