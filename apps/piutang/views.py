"""
==========================================================================
 PIUTANG VIEWS - Daftar, Detail, Pembayaran, Aging Report
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
from django.db.models import Sum, Q, Count, F
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from apps.piutang.models import Piutang, PembayaranPiutang
from apps.piutang.forms import PiutangForm, PembayaranPiutangForm
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin





class PiutangListView(ReadPermissionMixin, ListView):
    """Daftar piutang. URL: /piutang/"""
    paginate_by = 50
    model = Piutang
    template_name = 'piutang/piutang_list.html'
    context_object_name = 'piutang_list'
    permission_module = 'piutang'
    permission_sub_module = 'daftar_piutang'

    def get_queryset(self):
        qs = super().get_queryset().select_related('customer', 'cabang', 'created_by')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        start = self.request.GET.get('start', '')
        end = self.request.GET.get('end', '')
        if start:
            qs = qs.filter(tanggal__gte=start)
        if end:
            qs = qs.filter(tanggal__lte=end)
        customer = self.request.GET.get('customer', '')
        if customer:
            qs = qs.filter(customer_id=customer)
        cabang = self.request.GET.get('cabang', '')
        if cabang:
            qs = qs.filter(cabang_id=cabang)
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(nomor__icontains=q) | Q(customer__nama__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_piutang = Piutang.objects.all()

        agg = all_piutang.aggregate(
            total_piutang=Sum('jumlah_total'),
            total_dibayar=Sum('jumlah_dibayar'),
        )
        context['total_piutang'] = agg['total_piutang'] or 0
        context['total_dibayar'] = agg['total_dibayar'] or 0
        context['total_sisa'] = (agg['total_piutang'] or 0) - (agg['total_dibayar'] or 0)
        context['count_total'] = all_piutang.count()
        context['count_lunas'] = all_piutang.filter(status='lunas').count()
        context['count_belum'] = all_piutang.filter(status='belum_bayar').count()
        context['count_sebagian'] = all_piutang.filter(status='sebagian').count()
        context['count_macet'] = all_piutang.filter(status='macet').count()

        from apps.penjualan.models import Customer
        from apps.produk.models import Gudang
        context['customer_list'] = Customer.objects.filter(aktif=True)
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['status_choices'] = Piutang.STATUS_CHOICES
        return context


class PiutangCreateView(CreatePermissionMixin, CreateView):
    """Input piutang manual. URL: /piutang/add/"""
    model = Piutang
    form_class = PiutangForm
    template_name = 'piutang/piutang_form.html'
    success_url = reverse_lazy('piutang:list')
    permission_module = 'piutang'
    permission_sub_module = 'daftar_piutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Input Piutang Baru'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.sumber = 'manual'
        messages.success(self.request, f'Piutang berhasil ditambahkan')
        return super().form_valid(form)


class PiutangDetailView(ReadPermissionMixin, TemplateView):
    """Detail piutang + riwayat pembayaran. URL: /piutang/<pk>/"""
    template_name = 'piutang/piutang_detail.html'
    permission_module = 'piutang'
    permission_sub_module = 'daftar_piutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        piutang = get_object_or_404(
            Piutang.objects.select_related('customer', 'cabang', 'sales_order', 'pos_transaction'),
            pk=kwargs['pk']
        )
        context['piutang'] = piutang
        context['pembayaran_list'] = piutang.pembayaran_set.select_related('metode_pembayaran', 'jurnal').all()
        context['bayar_form'] = PembayaranPiutangForm(piutang=piutang)
        return context


class PembayaranPiutangCreateView(CreatePermissionMixin, CreateView):
    """Form pembayaran piutang. URL: /piutang/<pk>/bayar/ (POST)"""
    model = PembayaranPiutang
    form_class = PembayaranPiutangForm
    template_name = 'piutang/piutang_detail.html'
    permission_module = 'piutang'
    permission_sub_module = 'daftar_piutang'

    def get(self, request, *args, **kwargs):
        return redirect('piutang:detail', pk=kwargs['pk'])

    def get_piutang(self):
        return get_object_or_404(Piutang, pk=self.kwargs['pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['piutang'] = self.get_piutang()
        return kwargs

    def form_valid(self, form):
        piutang = self.get_piutang()

        if piutang.status == 'lunas':
            messages.error(self.request, 'Piutang sudah lunas!')
            return redirect('piutang:detail', pk=piutang.pk)

        try:
            with transaction.atomic():
                form.instance.piutang = piutang
                form.instance.created_by = self.request.user
                self.object = form.save()

                # Jurnal dan mutasi Kas/Bank dibuat oleh PembayaranPiutang.save().
                # View tidak membuat ulang agar jurnal tidak dobel.

                # Log activity
                try:
                    from apps.activity_log.middleware import ActivityLogMiddleware
                    ActivityLogMiddleware.log_activity(
                        self.request, action='create', model_name='Pembayaran Piutang',
                        object_id=self.object.pk, object_repr=str(self.object),
                        description=f'Pembayaran piutang {piutang.nomor}: Rp {form.instance.jumlah:,.0f}'
                    )
                except Exception as e:
                    logger.warning("Gagal mencatat activity log: %s", e)
        except (ValidationError, ValueError) as exc:
            messages.error(self.request, str(exc))
            return redirect('piutang:detail', pk=piutang.pk)

        messages.success(self.request, f'Pembayaran Rp {form.instance.jumlah:,.0f} berhasil dicatat')
        return redirect('piutang:detail', pk=piutang.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Gagal mencatat pembayaran. Periksa data input.')
        return redirect('piutang:detail', pk=self.kwargs['pk'])


class PiutangHapuskanView(UpdatePermissionMixin, TemplateView):
    """Hapuskan piutang macet (write-off). URL: /piutang/<pk>/hapuskan/ (POST)"""
    template_name = 'piutang/piutang_detail.html'
    permission_module = 'piutang'
    permission_sub_module = 'daftar_piutang'

    def get(self, request, *args, **kwargs):
        return redirect('piutang:detail', pk=kwargs['pk'])

    def post(self, request, *args, **kwargs):
        piutang = get_object_or_404(Piutang, pk=kwargs['pk'])

        if piutang.status == 'lunas':
            return JsonResponse({'success': False, 'message': 'Piutang sudah lunas.'}, status=400)

        with transaction.atomic():
            sisa = piutang.sisa

            # Auto-create jurnal: D:Beban Piutang Tak Tertagih K:Piutang Usaha
            try:
                from apps.akuntansi.services import create_jurnal
                create_jurnal(
                    tanggal=timezone.now().date(),
                    deskripsi=f'Penghapusan piutang macet {piutang.nomor} - {piutang.customer.nama}',
                    lines_data=[
                        {'akun_kode': '6-6000', 'debit': sisa, 'kredit': 0,
                         'keterangan': f'Beban piutang tak tertagih - {piutang.customer.nama}'},
                        {'akun_kode': '1-2000', 'debit': 0, 'kredit': sisa,
                         'keterangan': f'Hapus piutang {piutang.nomor}'},
                    ],
                    sumber='piutang',
                    sumber_id=piutang.pk,
                    sumber_ref=piutang.nomor,
                    cabang=piutang.cabang,
                    user=request.user,
                    auto_post=True,
                )
            except Exception as e:
                logger.warning("Gagal memproses jurnal akuntansi: %s", e)

            piutang.status = 'dihapuskan'
            piutang.jumlah_dibayar = piutang.jumlah_total
            piutang.save()

        return JsonResponse({
            'success': True,
            'message': f'Piutang {piutang.nomor} sebesar Rp {sisa:,.0f} telah dihapuskan (write-off).'
        })


class AgingReportView(ReadPermissionMixin, TemplateView):
    """Aging Report Piutang. URL: /piutang/aging/"""
    template_name = 'piutang/aging_report.html'
    permission_module = 'piutang'
    permission_sub_module = 'aging_piutang'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = timezone.now().date()
        active_piutang = Piutang.objects.filter(
            status__in=['belum_bayar', 'sebagian', 'macet']
        ).select_related('customer', 'cabang')

        cabang_id = self.request.GET.get('cabang', '')
        if cabang_id:
            active_piutang = active_piutang.filter(cabang_id=cabang_id)

        buckets = {
            'current': {'label': 'Belum Jatuh Tempo', 'items': [], 'total': Decimal('0')},
            '1-30': {'label': '1-30 Hari', 'items': [], 'total': Decimal('0')},
            '31-60': {'label': '31-60 Hari', 'items': [], 'total': Decimal('0')},
            '61-90': {'label': '61-90 Hari', 'items': [], 'total': Decimal('0')},
            '>90': {'label': '> 90 Hari', 'items': [], 'total': Decimal('0')},
        }

        for p in active_piutang:
            sisa = p.sisa
            bucket_key = p.aging_bucket
            if bucket_key in buckets:
                buckets[bucket_key]['items'].append(p)
                buckets[bucket_key]['total'] += sisa

        context['buckets'] = buckets
        context['grand_total'] = sum(b['total'] for b in buckets.values())

        # Chart data
        context['chart_labels'] = [b['label'] for b in buckets.values()]
        context['chart_data'] = [float(b['total']) for b in buckets.values()]

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['selected_cabang'] = cabang_id
        return context
