"""
==========================================================================
 SERVICE CENTER VIEWS - View untuk Manajemen Service Elektronik
==========================================================================
 Views untuk modul Service Center:
 - Dashboard service center (statistik, chart)
 - CRUD Pelanggan, Perangkat, Kategori Service, Jenis Service
 - CRUD Order Service (penerimaan, detail, update status)
 - Laporan Service (chart, filter tanggal, export)
 - Cek Status Publik (tanpa login — untuk pelanggan)
 - Cetak nota service
==========================================================================
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from apps.core.permissions import has_permission, permission_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json

from web_project import TemplateLayout
from .models import (
    Pelanggan, Perangkat, KategoriService, JenisService,
    OrderService, ItemService, RiwayatStatus, PenggunaanSparepart
)
from .forms import (
    PelangganForm, PerangkatForm, KategoriServiceForm, JenisServiceForm,
    OrderServiceForm, ItemServiceFormSet, UpdateStatusForm, PembayaranForm
)


def sync_order_biaya_akhir(order):
    """Simpan biaya_akhir konsisten dengan total_biaya dinamis."""
    order.biaya_akhir = order.total_biaya
    order.save(update_fields=['biaya_akhir'])


SERVICE_STATUS_TRANSITIONS = {
    'diterima': {'diagnosa', 'dibatalkan'},
    'diagnosa': {'menunggu_konfirmasi', 'dikerjakan', 'dibatalkan'},
    'menunggu_konfirmasi': {'dikerjakan', 'dibatalkan'},
    'dikerjakan': {'selesai', 'dibatalkan'},
    'selesai': {'diambil'},
    'diambil': set(),
    'dibatalkan': {'diterima'},
}


# ==========================================================================
#  DASHBOARD SERVICE CENTER
# ==========================================================================

class ServiceDashboardView(ReadPermissionMixin, TemplateView):
    """Dashboard utama Service Center — statistik, chart, ringkasan."""
    template_name = 'service_center/dashboard.html'
    permission_module = 'service_center'
    permission_sub_module = 'dashboard_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = timezone.now().date()
        month_start = today.replace(day=1)

        # Statistik umum
        context['total_order'] = OrderService.objects.count()
        context['order_aktif'] = OrderService.objects.exclude(
            status__in=['diambil', 'dibatalkan']
        ).count()
        context['order_selesai_bulan_ini'] = OrderService.objects.filter(
            status='selesai',
            tanggal_selesai__date__gte=month_start
        ).count()
        context['order_baru_hari_ini'] = OrderService.objects.filter(
            tanggal_masuk__date=today
        ).count()

        # Pendapatan bulan ini — konsisten dengan Dashboard & Laporan Keuangan: gunakan status_bayar
        context['pendapatan_bulan_ini'] = OrderService.objects.filter(
            status_bayar='lunas',
            tanggal_masuk__date__gte=month_start
        ).aggregate(total=Sum('biaya_akhir'))['total'] or Decimal('0')

        # Total pelanggan
        context['total_pelanggan'] = Pelanggan.objects.filter(aktif=True).count()

        # Order menunggu konfirmasi
        context['order_menunggu'] = OrderService.objects.filter(
            status='menunggu_konfirmasi'
        ).count()

        # Distribusi status (untuk donut chart)
        status_counts = OrderService.objects.exclude(
            status__in=['diambil', 'dibatalkan']
        ).values('status').annotate(count=Count('id')).order_by('status')

        status_dict = dict(OrderService.STATUS_CHOICES)
        status_labels = [status_dict.get(s['status'], s['status']) for s in status_counts]
        status_data = [s['count'] for s in status_counts]
        context['status_labels_json'] = json.dumps(status_labels)
        context['status_data_json'] = json.dumps(status_data)

        # Tren order per hari (30 hari terakhir, untuk area chart)
        tren_labels = []
        tren_data = []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            tren_labels.append(d.strftime('%d/%m'))
            tren_data.append(OrderService.objects.filter(tanggal_masuk__date=d).count())
        context['tren_labels_json'] = json.dumps(tren_labels)
        context['tren_data_json'] = json.dumps(tren_data)

        # Order terbaru (10 terakhir)
        context['order_terbaru'] = OrderService.objects.select_related(
            'pelanggan', 'jenis_perangkat', 'teknisi'
        ).order_by('-dibuat_pada')[:10]

        # Perangkat paling sering
        context['top_perangkat'] = OrderService.objects.values(
            'jenis_perangkat__nama'
        ).annotate(total=Count('id')).order_by('-total')[:5]

        # Jenis service populer
        context['top_jenis_service'] = ItemService.objects.values(
            'nama_layanan'
        ).annotate(total=Count('id')).order_by('-total')[:5]

        return context


# ==========================================================================
#  PELANGGAN VIEWS
# ==========================================================================

class PelangganListView(ReadPermissionMixin, TemplateView):
    """Daftar pelanggan service center — DataTables."""
    template_name = 'service_center/pelanggan_list.html'
    permission_module = 'service_center'
    permission_sub_module = 'pelanggan_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        pelanggan = Pelanggan.objects.all()

        # Hitung total order per pelanggan
        pelanggan = pelanggan.annotate(
            jumlah_order=Count('order_services')
        )

        context['pelanggan_list'] = pelanggan
        context['total_pelanggan'] = Pelanggan.objects.count()
        context['pelanggan_aktif'] = Pelanggan.objects.filter(aktif=True).count()

        return context


class PelangganCreateView(CreatePermissionMixin, TemplateView):
    """Form tambah pelanggan baru."""
    template_name = 'service_center/pelanggan_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'pelanggan_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = PelangganForm()
        context['form_title'] = 'Tambah Pelanggan Baru'
        return context

    def post(self, request, *args, **kwargs):
        form = PelangganForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pelanggan berhasil ditambahkan!')
            return redirect('service_center:pelanggan_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


class PelangganUpdateView(UpdatePermissionMixin, TemplateView):
    """Form edit pelanggan."""
    template_name = 'service_center/pelanggan_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'pelanggan_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        pelanggan = get_object_or_404(Pelanggan, pk=self.kwargs['pk'])
        context['form'] = PelangganForm(instance=pelanggan)
        context['form_title'] = f'Edit Pelanggan: {pelanggan.nama}'
        context['pelanggan'] = pelanggan
        return context

    def post(self, request, *args, **kwargs):
        pelanggan = get_object_or_404(Pelanggan, pk=kwargs['pk'])
        form = PelangganForm(request.POST, instance=pelanggan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Data pelanggan berhasil diperbarui!')
            return redirect('service_center:pelanggan_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


@login_required
@permission_required('delete', 'service_center')
def pelanggan_delete(request, pk):
    """Hapus pelanggan (AJAX DELETE atau POST)."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'service_center', 'pelanggan_service'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus pelanggan.'}, status=403)
    pelanggan = get_object_or_404(Pelanggan, pk=pk)
    if request.method in ['POST', 'DELETE']:
        try:
            nama = pelanggan.nama
            pelanggan.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': True, 'message': f'Pelanggan {nama} berhasil dihapus!'})
            messages.success(request, f'Pelanggan {nama} berhasil dihapus!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Gagal menghapus pelanggan: {str(e)}')
    return redirect('service_center:pelanggan_list')


# ==========================================================================
#  PERANGKAT VIEWS
# ==========================================================================

class PerangkatListView(ReadPermissionMixin, TemplateView):
    """Daftar jenis perangkat — DataTables."""
    template_name = 'service_center/perangkat_list.html'
    permission_module = 'service_center'
    permission_sub_module = 'perangkat'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        perangkat = Perangkat.objects.annotate(
            jumlah_order=Count('order_services')
        )
        context['perangkat_list'] = perangkat
        context['total_perangkat'] = Perangkat.objects.count()

        try:
            from apps.pengaturan.models import ExportPDFTemplate
            context['export_pdf_template'] = ExportPDFTemplate.objects.first()
        except Exception:
            context['export_pdf_template'] = None
        return context


class PerangkatCreateView(CreatePermissionMixin, TemplateView):
    """Form tambah perangkat baru."""
    template_name = 'service_center/perangkat_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'perangkat'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = PerangkatForm()
        context['form_title'] = 'Tambah Jenis Perangkat'
        return context

    def post(self, request, *args, **kwargs):
        form = PerangkatForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Jenis perangkat berhasil ditambahkan!')
            return redirect('service_center:perangkat_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


class PerangkatUpdateView(UpdatePermissionMixin, TemplateView):
    """Form edit perangkat."""
    template_name = 'service_center/perangkat_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'perangkat'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        perangkat = get_object_or_404(Perangkat, pk=self.kwargs['pk'])
        context['form'] = PerangkatForm(instance=perangkat)
        context['form_title'] = f'Edit Perangkat: {perangkat.nama}'
        context['perangkat'] = perangkat
        return context

    def post(self, request, *args, **kwargs):
        perangkat = get_object_or_404(Perangkat, pk=kwargs['pk'])
        form = PerangkatForm(request.POST, instance=perangkat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Data perangkat berhasil diperbarui!')
            return redirect('service_center:perangkat_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


@login_required
@permission_required('delete', 'service_center')
def perangkat_delete(request, pk):
    """Hapus perangkat (AJAX DELETE atau POST)."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'service_center', 'perangkat'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus perangkat.'}, status=403)
    perangkat = get_object_or_404(Perangkat, pk=pk)
    if request.method in ['POST', 'DELETE']:
        try:
            nama = perangkat.nama
            perangkat.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': True, 'message': f'Perangkat {nama} berhasil dihapus!'})
            messages.success(request, f'Perangkat {nama} berhasil dihapus!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Gagal menghapus perangkat: {str(e)}')
    return redirect('service_center:perangkat_list')


# ==========================================================================
#  KATEGORI SERVICE VIEWS
# ==========================================================================

class KategoriServiceListView(ReadPermissionMixin, TemplateView):
    """Daftar kategori service — DataTables."""
    template_name = 'service_center/kategori_service_list.html'
    permission_module = 'service_center'
    permission_sub_module = 'kategori_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['kategori_list'] = KategoriService.objects.annotate(
            jumlah_jenis=Count('jenis_services')
        )
        context['total_kategori'] = KategoriService.objects.count()

        try:
            from apps.pengaturan.models import ExportPDFTemplate
            context['export_pdf_template'] = ExportPDFTemplate.objects.first()
        except Exception:
            context['export_pdf_template'] = None
        return context


class KategoriServiceCreateView(CreatePermissionMixin, TemplateView):
    """Form tambah kategori service."""
    template_name = 'service_center/kategori_service_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'kategori_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = KategoriServiceForm()
        context['form_title'] = 'Tambah Kategori Service'
        return context

    def post(self, request, *args, **kwargs):
        form = KategoriServiceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategori service berhasil ditambahkan!')
            return redirect('service_center:kategori_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


class KategoriServiceUpdateView(UpdatePermissionMixin, TemplateView):
    """Form edit kategori service."""
    template_name = 'service_center/kategori_service_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'kategori_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        kategori = get_object_or_404(KategoriService, pk=self.kwargs['pk'])
        context['form'] = KategoriServiceForm(instance=kategori)
        context['form_title'] = f'Edit Kategori: {kategori.nama}'
        return context

    def post(self, request, *args, **kwargs):
        kategori = get_object_or_404(KategoriService, pk=kwargs['pk'])
        form = KategoriServiceForm(request.POST, instance=kategori)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategori service berhasil diperbarui!')
            return redirect('service_center:kategori_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


@login_required
@permission_required('delete', 'service_center')
def kategori_delete(request, pk):
    """Hapus kategori service."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'service_center', 'kategori_service'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus kategori.'}, status=403)
    kategori = get_object_or_404(KategoriService, pk=pk)
    if request.method in ['POST', 'DELETE']:
        try:
            nama = kategori.nama
            kategori.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': True, 'message': f'Kategori {nama} berhasil dihapus!'})
            messages.success(request, f'Kategori {nama} berhasil dihapus!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Gagal menghapus kategori: {str(e)}')
    return redirect('service_center:kategori_list')


# ==========================================================================
#  JENIS SERVICE VIEWS
# ==========================================================================

class JenisServiceListView(ReadPermissionMixin, TemplateView):
    """Daftar jenis service — DataTables."""
    template_name = 'service_center/jenis_service_list.html'
    permission_module = 'service_center'
    permission_sub_module = 'jenis_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        jenis = JenisService.objects.select_related('kategori').annotate(
            jumlah_dipakai=Count('item_services')
        )
        context['jenis_list'] = jenis
        context['total_jenis'] = JenisService.objects.count()
        context['kategori_list'] = KategoriService.objects.filter(aktif=True)
        context['total_harga_standar'] = JenisService.objects.filter(aktif=True).aggregate(
            total=Sum('harga_standar')
        )['total'] or Decimal('0')

        try:
            from apps.pengaturan.models import ExportPDFTemplate
            context['export_pdf_template'] = ExportPDFTemplate.objects.first()
        except Exception:
            context['export_pdf_template'] = None
        return context


class JenisServiceCreateView(CreatePermissionMixin, TemplateView):
    """Form tambah jenis service."""
    template_name = 'service_center/jenis_service_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'jenis_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = JenisServiceForm()
        context['form_title'] = 'Tambah Jenis Service'
        return context

    def post(self, request, *args, **kwargs):
        form = JenisServiceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Jenis service berhasil ditambahkan!')
            return redirect('service_center:jenis_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


class JenisServiceUpdateView(UpdatePermissionMixin, TemplateView):
    """Form edit jenis service."""
    template_name = 'service_center/jenis_service_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'jenis_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        jenis = get_object_or_404(JenisService, pk=self.kwargs['pk'])
        context['form'] = JenisServiceForm(instance=jenis)
        context['form_title'] = f'Edit: {jenis.nama}'
        return context

    def post(self, request, *args, **kwargs):
        jenis = get_object_or_404(JenisService, pk=kwargs['pk'])
        form = JenisServiceForm(request.POST, request.FILES, instance=jenis)
        if form.is_valid():
            form.save()
            messages.success(request, 'Jenis service berhasil diperbarui!')
            return redirect('service_center:jenis_list')
        context = self.get_context_data(**kwargs)
        context['form'] = form
        return render(request, self.template_name, context)


@login_required
@permission_required('delete', 'service_center')
def jenis_delete(request, pk):
    """Hapus jenis service."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'service_center', 'jenis_service'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus jenis service.'}, status=403)
    jenis = get_object_or_404(JenisService, pk=pk)
    if request.method in ['POST', 'DELETE']:
        try:
            nama = jenis.nama
            jenis.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': True, 'message': f'Jenis service {nama} berhasil dihapus!'})
            messages.success(request, f'Jenis service {nama} berhasil dihapus!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.method == 'DELETE':
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Gagal menghapus jenis service: {str(e)}')
    return redirect('service_center:jenis_list')


# ==========================================================================
#  ORDER SERVICE VIEWS
# ==========================================================================

class OrderServiceListView(ReadPermissionMixin, TemplateView):
    """Daftar order service — DataTables + filter."""
    template_name = 'service_center/order_list.html'
    permission_module = 'service_center'
    permission_sub_module = 'order_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        orders = OrderService.objects.select_related(
            'pelanggan', 'jenis_perangkat', 'teknisi'
        ).all()

        context['order_list'] = orders
        context['status_choices'] = OrderService.STATUS_CHOICES
        context['total_order'] = OrderService.objects.count()
        context['order_aktif'] = OrderService.objects.exclude(
            status__in=['diambil', 'dibatalkan']
        ).count()
        context['total_pendapatan'] = OrderService.objects.filter(
            status__in=['selesai', 'diambil']
        ).aggregate(total=Sum('biaya_akhir'))['total'] or Decimal('0')

        try:
            from apps.pengaturan.models import ExportPDFTemplate
            context['export_pdf_template'] = ExportPDFTemplate.objects.first()
        except Exception:
            context['export_pdf_template'] = None
        return context


class OrderServiceCreateView(CreatePermissionMixin, TemplateView):
    """Form penerimaan unit service baru (intake)."""
    template_name = 'service_center/order_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'terima_unit'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = OrderServiceForm()
        context['item_formset'] = ItemServiceFormSet()
        context['form_title'] = 'Terima Unit Service Baru'
        return context

    def post(self, request, *args, **kwargs):
        form = OrderServiceForm(request.POST, request.FILES)
        item_formset = ItemServiceFormSet(request.POST)

        if form.is_valid():
            # DIPERBAIKI #13: Bungkus dalam atomic agar rollback jika formset error
            from django.db import transaction
            try:
                with transaction.atomic():
                    order = form.save(commit=False)
                    order.diterima_oleh = request.user
                    order.save()

                    item_formset = ItemServiceFormSet(request.POST, instance=order)
                    if item_formset.is_valid():
                        item_formset.save()
                    else:
                        # Formset invalid → raise agar atomic rollback order
                        raise ValueError('FORMSET_INVALID')

                    sync_order_biaya_akhir(order)

                    # Buat riwayat status awal
                    RiwayatStatus.objects.create(
                        order_service=order,
                        status_sebelum='-',
                        status_sesudah='diterima',
                        catatan='Unit diterima untuk service',
                        diubah_oleh=request.user
                    )
            except ValueError as e:
                if 'FORMSET_INVALID' in str(e):
                    # Formset gagal → re-render form dengan error
                    context = self.get_context_data(**kwargs)
                    context['form'] = form
                    context['item_formset'] = item_formset
                    return render(request, self.template_name, context)
                raise  # Re-raise jika ValueError lain

            # Notifikasi di luar atomic (opsional, tidak boleh rollback order)
            try:
                from apps.automation.signals import kirim_notifikasi_order_service
                kirim_notifikasi_order_service(order)
            except Exception:
                pass

            messages.success(request, f'Order service {order.nomor_service} berhasil dibuat! Kode tracking: {order.kode_unik}')
            return redirect('service_center:order_detail', pk=order.pk)

        context = self.get_context_data(**kwargs)
        context['form'] = form
        context['item_formset'] = item_formset
        return render(request, self.template_name, context)


class OrderServiceDetailView(ReadPermissionMixin, TemplateView):
    """Detail order service lengkap."""
    template_name = 'service_center/order_detail.html'
    permission_module = 'service_center'
    permission_sub_module = 'order_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        order = get_object_or_404(
            OrderService.objects.select_related(
                'pelanggan', 'jenis_perangkat', 'teknisi', 'diterima_oleh'
            ),
            pk=self.kwargs['pk']
        )

        context['order'] = order
        context['items'] = order.items.select_related('jenis_service').all()
        context['riwayat'] = order.riwayat_status.select_related('diubah_oleh').all()
        context['status_form'] = UpdateStatusForm(initial={'status': order.status})
        context['pembayaran_form'] = PembayaranForm(initial={
            'status_bayar': order.status_bayar,
            'dp_bayar': order.dp_bayar,
            'metode_pembayaran': order.metode_pembayaran_id,
        })
        context['item_formset'] = ItemServiceFormSet(instance=order)
        context['status_choices'] = OrderService.STATUS_CHOICES

        # Sparepart data
        context['spareparts_used'] = order.penggunaan_sparepart.select_related('produk', 'gudang').all()
        context['total_biaya_sparepart'] = order.penggunaan_sparepart.aggregate(
            total=Sum(models.F('jumlah') * models.F('harga_satuan'))
        )['total'] or Decimal('0')
        context['total_biaya_layanan'] = order.items.aggregate(
            total=Sum('biaya')
        )['total'] or Decimal('0')

        # Gudang list for dropdown
        try:
            from apps.produk.models import Gudang
            context['gudang_list'] = Gudang.objects.filter(aktif=True)
        except Exception:
            context['gudang_list'] = []

        return context


class OrderServiceUpdateView(UpdatePermissionMixin, TemplateView):
    """Form edit order service."""
    template_name = 'service_center/order_form.html'
    permission_module = 'service_center'
    permission_sub_module = 'order_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        order = get_object_or_404(OrderService, pk=self.kwargs['pk'])
        context['form'] = OrderServiceForm(instance=order)
        context['item_formset'] = ItemServiceFormSet(instance=order)
        context['form_title'] = f'Edit Order: {order.nomor_service}'
        context['order'] = order
        return context

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(OrderService, pk=kwargs['pk'])
        form = OrderServiceForm(request.POST, request.FILES, instance=order)
        item_formset = ItemServiceFormSet(request.POST, instance=order)

        if form.is_valid() and item_formset.is_valid():
            order = form.save()
            item_formset.save()

            sync_order_biaya_akhir(order)
            from apps.service_center.services import sync_service_payment_accounting
            sync_service_payment_accounting(order, user=request.user)

            messages.success(request, f'Order {order.nomor_service} berhasil diperbarui!')
            return redirect('service_center:order_detail', pk=order.pk)

        context = self.get_context_data(**kwargs)
        context['form'] = form
        context['item_formset'] = item_formset
        return render(request, self.template_name, context)


@login_required
@permission_required('update', 'service_center')
def update_status(request, pk):
    """Update status order service."""
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'service_center', 'order_service'):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah status order.')
        return redirect('service_center:order_detail', pk=pk)
    order = get_object_or_404(OrderService, pk=pk)

    if request.method == 'POST':
        form = UpdateStatusForm(request.POST)
        if form.is_valid():
            old_status = order.status
            new_status = form.cleaned_data['status']

            if old_status != new_status:
                allowed_next = SERVICE_STATUS_TRANSITIONS.get(old_status, set())
                if new_status not in allowed_next:
                    old_display = dict(OrderService.STATUS_CHOICES).get(old_status, old_status)
                    new_display = dict(OrderService.STATUS_CHOICES).get(new_status, new_status)
                    messages.error(request, f'Perubahan status dari "{old_display}" ke "{new_display}" tidak diizinkan.')
                    return redirect('service_center:order_detail', pk=order.pk)

                order.status = new_status

                catatan_teknisi = form.cleaned_data.get('catatan_teknisi', '')
                if catatan_teknisi:
                    order.catatan_teknisi = catatan_teknisi

                biaya_akhir = form.cleaned_data.get('biaya_akhir')
                if biaya_akhir is not None and biaya_akhir > 0:
                    order.biaya_akhir = biaya_akhir

                order.save()

                # --- INTEGRASI INVENTORY: Kembalikan stok sparepart jika dibatalkan ---
                if new_status == 'dibatalkan':
                    for sp in order.penggunaan_sparepart.all():
                        sp.kembalikan_stok()
                        try:
                            from apps.activity_log.stock_signals import log_service_stock_return
                            log_service_stock_return(sp, request.user, request)
                        except Exception:
                            pass
                    # DIPERBAIKI #8: Reset biaya_akhir dan pembayaran saat dibatalkan
                    order.biaya_akhir = Decimal('0')
                    order.dp_bayar = Decimal('0')
                    order.status_bayar = 'belum_bayar'
                    order.save(update_fields=['biaya_akhir', 'dp_bayar', 'status_bayar'])
                    from apps.service_center.services import sync_service_payment_accounting
                    sync_service_payment_accounting(order, user=request.user)

                # DIPERBAIKI #15: Re-activate dari dibatalkan → kurangi stok ulang
                elif old_status == 'dibatalkan' and new_status != 'dibatalkan':
                    for sp in order.penggunaan_sparepart.all():
                        sp.kurangi_stok()
                        try:
                            from apps.activity_log.stock_signals import log_service_stock_out
                            log_service_stock_out(sp, request.user, request)
                        except Exception:
                            pass
                # ----------------------------------------------------------------------

                RiwayatStatus.objects.create(
                    order_service=order,
                    status_sebelum=old_status,
                    status_sesudah=new_status,
                    catatan=form.cleaned_data.get('catatan', ''),
                    diubah_oleh=request.user
                )

                # --- INTEGRASI: Notifikasi Telegram ---
                from apps.automation.signals import kirim_notifikasi_order_service
                kirim_notifikasi_order_service(order)
                # ----------------------------------------

                status_display = dict(OrderService.STATUS_CHOICES).get(new_status, new_status)
                messages.success(request, f'Status order {order.nomor_service} berhasil diubah menjadi "{status_display}"')
            else:
                messages.info(request, 'Status tidak berubah.')

    return redirect('service_center:order_detail', pk=order.pk)


@login_required
@permission_required('update', 'service_center')
def update_pembayaran(request, pk):
    """Update status pembayaran order service."""
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'service_center', 'order_service'):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah pembayaran.')
        return redirect('service_center:order_detail', pk=pk)
    order = get_object_or_404(OrderService, pk=pk)

    if request.method == 'POST':
        form = PembayaranForm(request.POST)
        if form.is_valid():
            new_status_bayar = form.cleaned_data['status_bayar']

            # DIPERBAIKI #9: Validasi biaya_akhir > 0 sebelum izinkan lunas
            if new_status_bayar == 'lunas' and (not order.biaya_akhir or order.biaya_akhir <= 0):
                messages.error(request, f'Tidak dapat melunasi order {order.nomor_service} karena biaya akhir masih Rp 0. Tambahkan layanan atau sparepart terlebih dahulu.')
                return redirect('service_center:order_detail', pk=order.pk)

            dp = form.cleaned_data.get('dp_bayar')
            metode = form.cleaned_data.get('metode_pembayaran')
            total_tagihan = order.biaya_akhir or order.total_biaya

            if order.status == 'dibatalkan' and new_status_bayar != 'belum_bayar':
                messages.error(request, 'Order dibatalkan tidak dapat diberi status pembayaran DP atau lunas.')
                return redirect('service_center:order_detail', pk=order.pk)

            if new_status_bayar in ['dp', 'lunas'] and not metode:
                messages.error(request, 'Metode pembayaran wajib dipilih untuk pembayaran DP atau lunas.')
                return redirect('service_center:order_detail', pk=order.pk)

            if dp is not None and dp < 0:
                messages.error(request, 'Nominal DP tidak boleh negatif.')
                return redirect('service_center:order_detail', pk=order.pk)

            if dp is not None and total_tagihan and dp > total_tagihan:
                messages.error(request, 'Nominal DP tidak boleh melebihi total tagihan service.')
                return redirect('service_center:order_detail', pk=order.pk)

            if new_status_bayar == 'dp' and (dp is None or dp <= 0):
                messages.error(request, 'Nominal DP harus lebih dari 0 untuk status pembayaran DP.')
                return redirect('service_center:order_detail', pk=order.pk)

            try:
                with transaction.atomic():
                    order = OrderService.objects.select_for_update().get(pk=order.pk)
                    order.status_bayar = new_status_bayar
                    if dp is not None:
                        order.dp_bayar = dp
                    order.metode_pembayaran = metode
                    order.save()
                    from apps.service_center.services import sync_service_payment_accounting
                    sync_service_payment_accounting(order, user=request.user)
            except Exception as exc:
                messages.error(request, f'Gagal memperbarui pembayaran service: {exc}')
                return redirect('service_center:order_detail', pk=order.pk)
            messages.success(request, f'Pembayaran order {order.nomor_service} berhasil diperbarui!')

    return redirect('service_center:order_detail', pk=order.pk)


@login_required
@permission_required('update', 'service_center')
def update_items(request, pk):
    """Update item service untuk order tertentu."""
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'service_center', 'order_service'):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah detail layanan.')
        return redirect('service_center:order_detail', pk=pk)
    order = get_object_or_404(OrderService, pk=pk)

    if request.method == 'POST':
        formset = ItemServiceFormSet(request.POST, instance=order)
        if formset.is_valid():
            formset.save()

            sync_order_biaya_akhir(order)
            from apps.service_center.services import sync_service_payment_accounting
            sync_service_payment_accounting(order, user=request.user)

            messages.success(request, 'Detail layanan berhasil diperbarui!')
        else:
            messages.error(request, 'Terjadi kesalahan saat menyimpan detail layanan.')

    return redirect('service_center:order_detail', pk=order.pk)


@login_required
@permission_required('delete', 'service_center')
def order_delete(request, pk):
    """Hapus order service. Kembalikan stok sparepart sebelum menghapus."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'service_center', 'order_service'):
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus order service.')
        return redirect('service_center:order_list')
    order = get_object_or_404(OrderService, pk=pk)
    if request.method == 'POST':
        nomor = order.nomor_service

        try:
            with transaction.atomic():
                # --- INTEGRASI INVENTORY: Kembalikan semua stok sparepart sebelum hapus ---
                for sp in order.penggunaan_sparepart.select_related('produk', 'gudang'):
                    sp.kembalikan_stok()
                    try:
                        from apps.activity_log.stock_signals import log_service_stock_return
                        log_service_stock_return(sp, request.user, request)
                    except Exception:
                        pass
                # --------------------------------------------------------------------------

                from apps.service_center.services import cancel_service_payment_accounting
                cancel_service_payment_accounting(order, user=request.user, reason='Penghapusan order service')

                # Set current user untuk fraud signal superuser exemption
                try:
                    from apps.fraud_detection.signals import set_current_delete_user, clear_current_delete_user
                    set_current_delete_user(request.user)
                except Exception:
                    pass

                order.delete()
            messages.success(request, f'Order {nomor} berhasil dihapus! Stok sparepart telah dikembalikan.')
        except Exception as e:
            if "FRAUD_BLOCK" in str(e):
                messages.error(request, 'Penghapusan diblokir oleh sistem keamanan Fraud Rule. Hanya superuser yang dapat menghapus data lunas.')
                return redirect('service_center:order_detail', pk=pk)
            raise
        finally:
            try:
                clear_current_delete_user()
            except Exception:
                pass
        return redirect('service_center:order_list')
    return redirect('service_center:order_detail', pk=pk)


# ==========================================================================
#  LAPORAN SERVICE
# ==========================================================================

class LaporanServiceView(ReadPermissionMixin, TemplateView):
    """Laporan service — chart, filter tanggal, ringkasan."""
    template_name = 'service_center/laporan_service.html'
    permission_module = 'service_center'
    permission_sub_module = 'laporan_service'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = timezone.now().date()
        start_date = self.request.GET.get('start_date', '')
        end_date = self.request.GET.get('end_date', '')

        orders = OrderService.objects.all()

        if start_date:
            orders = orders.filter(tanggal_masuk__date__gte=start_date)
        if end_date:
            orders = orders.filter(tanggal_masuk__date__lte=end_date)

        context['start_date'] = start_date
        context['end_date'] = end_date

        # Statistik
        context['total_order'] = orders.count()
        context['total_selesai'] = orders.filter(status__in=['selesai', 'diambil']).count()
        context['total_batal'] = orders.filter(status='dibatalkan').count()
        # DIPERBAIKI #11: Gunakan status_bayar='lunas' untuk konsistensi dengan Dashboard
        context['total_pendapatan'] = orders.filter(
            status_bayar='lunas'
        ).aggregate(total=Sum('biaya_akhir'))['total'] or Decimal('0')
        # DIPERBAIKI #16: Exclude order dibatalkan dari total DP
        context['total_dp'] = orders.exclude(
            status='dibatalkan'
        ).aggregate(total=Sum('dp_bayar'))['total'] or Decimal('0')

        # Daftar order (untuk tabel dan export)
        context['order_list'] = orders.select_related('pelanggan', 'jenis_perangkat', 'teknisi')

        # Chart data — order per hari
        date_range = 30  # default 30 hari
        if start_date and end_date:
            from datetime import datetime
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d').date()
                ed = datetime.strptime(end_date, '%Y-%m-%d').date()
                date_range = (ed - sd).days + 1
            except ValueError:
                pass

        tren_labels = []
        tren_data = []
        tren_revenue = []
        base_date = today if not end_date else (
            timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
            if isinstance(end_date, str) and end_date else today
        )
        for i in range(min(date_range, 60) - 1, -1, -1):
            d = base_date - timedelta(days=i)
            tren_labels.append(d.strftime('%d/%m'))
            tren_data.append(orders.filter(tanggal_masuk__date=d).count())
            rev = orders.filter(
                tanggal_masuk__date=d, status_bayar='lunas'
            ).aggregate(total=Sum('biaya_akhir'))['total'] or 0
            tren_revenue.append(float(rev))

        context['tren_labels_json'] = json.dumps(tren_labels)
        context['tren_data_json'] = json.dumps(tren_data)
        context['tren_revenue_json'] = json.dumps(tren_revenue)

        # Status distribution
        status_counts = orders.values('status').annotate(count=Count('id'))
        status_dict = dict(OrderService.STATUS_CHOICES)
        context['status_labels_json'] = json.dumps([status_dict.get(s['status'], s['status']) for s in status_counts])
        context['status_data_json'] = json.dumps([s['count'] for s in status_counts])

        try:
            from apps.pengaturan.models import ExportPDFTemplate
            context['export_pdf_template'] = ExportPDFTemplate.objects.first()
        except Exception:
            context['export_pdf_template'] = None

        return context


# ==========================================================================
#  CEK STATUS PUBLIK (TANPA LOGIN)
# ==========================================================================

class CekStatusPublikView(TemplateView):
    """Halaman publik untuk pelanggan cek status service — tanpa login."""
    template_name = 'service_center/cek_status_publik.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


def cek_status_api(request):
    """API JSON untuk cek status service secara realtime."""
    query = request.GET.get('q', '').strip().upper()

    if not query:
        return JsonResponse({'found': False, 'message': 'Masukkan nomor service atau kode tracking.'})

    # Cari berdasarkan nomor service, kode unik, atau nomor telepon pelanggan
    order = OrderService.objects.select_related(
        'pelanggan', 'jenis_perangkat', 'teknisi'
    ).filter(
        Q(nomor_service__iexact=query) |
        Q(kode_unik__iexact=query) |
        Q(pelanggan__telepon__icontains=query)
    ).first()

    if not order:
        return JsonResponse({'found': False, 'message': 'Data tidak ditemukan. Periksa kembali nomor service / kode tracking.'})

    # Ambil riwayat status
    riwayat = []
    status_dict = dict(OrderService.STATUS_CHOICES)
    for r in order.riwayat_status.order_by('-timestamp')[:10]:
        riwayat.append({
            'dari': status_dict.get(r.status_sebelum, r.status_sebelum),
            'ke': status_dict.get(r.status_sesudah, r.status_sesudah),
            'catatan': r.catatan or '',
            'waktu': r.timestamp.strftime('%d/%m/%Y %H:%M'),
        })

    # Ambil detail items
    items = []
    for item in order.items.all():
        items.append({
            'nama': item.nama_layanan,
            'biaya': float(item.biaya),
        })

    # Ambil penggunaan sparepart
    spareparts = []
    for sp in order.penggunaan_sparepart.select_related('produk', 'gudang').all():
        spareparts.append({
            'nama': sp.produk.nama,
            'jumlah': float(sp.jumlah),
            'satuan': sp.produk.satuan.singkatan if sp.produk.satuan else 'pcs',
            'harga_satuan': float(sp.harga_satuan),
            'subtotal': float(sp.subtotal),
        })

    data = {
        'found': True,
        'nomor_service': order.nomor_service,
        'kode_tracking': order.kode_unik,
        'pelanggan': order.pelanggan.nama,
        'telepon': order.pelanggan.telepon,
        'perangkat': f'{order.merek} {order.model_tipe or ""}',
        'jenis': order.jenis_perangkat.nama,
        'keluhan': order.keluhan,
        'status': order.get_status_display(),
        'status_code': order.status,
        'status_class': order.status_badge_class,
        'prioritas': order.get_prioritas_display(),
        'tanggal_masuk': order.tanggal_masuk.strftime('%d/%m/%Y %H:%M'),
        'estimasi_selesai': order.estimasi_selesai.strftime('%d/%m/%Y') if order.estimasi_selesai else '-',
        'tanggal_selesai': order.tanggal_selesai.strftime('%d/%m/%Y %H:%M') if order.tanggal_selesai else None,
        'biaya': float(order.total_biaya),
        'dp': float(order.dp_bayar),
        'sisa': float(order.sisa_bayar),
        'status_bayar': order.get_status_bayar_display(),
        'teknisi': order.teknisi.get_full_name() if order.teknisi else '-',
        'riwayat': riwayat,
        'items': items,
        'spareparts': spareparts,
    }

    return JsonResponse(data)


# ==========================================================================
#  CETAK NOTA SERVICE
# ==========================================================================

class CetakNotaServiceView(ReadPermissionMixin, TemplateView):
    """Cetak nota/invoice service (print-friendly)."""
    template_name = 'service_center/cetak_nota.html'
    permission_module = 'service_center'
    permission_sub_module = 'order_service'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = get_object_or_404(
            OrderService.objects.select_related(
                'pelanggan', 'jenis_perangkat', 'teknisi', 'diterima_oleh'
            ),
            pk=self.kwargs['pk']
        )
        context['order'] = order
        context['items'] = order.items.all()
        context['spareparts_used'] = order.penggunaan_sparepart.select_related('produk', 'gudang').all()
        context['total_biaya_sparepart'] = order.penggunaan_sparepart.aggregate(
            total=Sum(F('jumlah') * F('harga_satuan'))
        )['total'] or Decimal('0')
        context['total_biaya_layanan'] = order.items.aggregate(
            total=Sum('biaya')
        )['total'] or Decimal('0')
        context['tanggal_cetak'] = timezone.now()

        try:
            from apps.pengaturan.models import PengaturanPerusahaan, TemplateCetak
            context['perusahaan'] = PengaturanPerusahaan.load()
            context['template'] = TemplateCetak.get_template('nota_service')
        except Exception:
            context['perusahaan'] = None
            context['template'] = None

        return context


# ==========================================================================
#  CETAK BUKTI PEMBAYARAN SERVICE (Pengganti Invoice)
# ==========================================================================

class CetakBuktiPembayaranView(ReadPermissionMixin, TemplateView):
    """Cetak bukti pembayaran/transaksi service (print-friendly) — pengganti modul Invoice."""
    template_name = 'service_center/cetak_bukti_bayar.html'
    permission_module = 'service_center'
    permission_sub_module = 'order_service'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = get_object_or_404(
            OrderService.objects.select_related(
                'pelanggan', 'jenis_perangkat', 'teknisi', 'diterima_oleh'
            ),
            pk=self.kwargs['pk']
        )
        context['order'] = order
        context['items'] = order.items.all()
        context['spareparts_used'] = order.penggunaan_sparepart.select_related('produk', 'gudang').all()
        context['total_biaya_sparepart'] = order.penggunaan_sparepart.aggregate(
            total=Sum(F('jumlah') * F('harga_satuan'))
        )['total'] or Decimal('0')
        context['total_biaya_layanan'] = order.items.aggregate(
            total=Sum('biaya')
        )['total'] or Decimal('0')
        context['tanggal_cetak'] = timezone.now()

        try:
            from apps.pengaturan.models import PengaturanPerusahaan, TemplateCetak
            context['perusahaan'] = PengaturanPerusahaan.load()
            context['template'] = TemplateCetak.get_template('bukti_bayar_service')
        except Exception:
            context['perusahaan'] = None
            context['template'] = None

        return context


# ==========================================================================
#  API SPAREPART UNTUK SERVICE ORDER
# ==========================================================================

@login_required
@permission_required('create', 'sparepart')
def tambah_sparepart(request, pk):
    """Tambah sparepart ke order service. Otomatis kurangi stok."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    # RBAC: Cek permission create untuk sub-modul sparepart_service (QA-R1: granular)
    if not has_permission(request.user, 'create', 'service_center', 'sparepart_service'):
        return JsonResponse({'success': False, 'error': 'Anda tidak memiliki izin untuk menambah sparepart.'}, status=403)

    order = get_object_or_404(OrderService, pk=pk)

    # DIPERBAIKI #18: Validasi status order — hanya boleh tambah sparepart jika order masih aktif
    if order.status in ['diambil', 'dibatalkan']:
        status_display = dict(OrderService.STATUS_CHOICES).get(order.status, order.status)
        return JsonResponse({
            'success': False,
            'error': f'Tidak dapat menambah sparepart. Order sudah berstatus "{status_display}".'
        }, status=400)

    try:
        from apps.produk.models import Produk, Gudang, Stok

        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        produk_id = data.get('produk_id')
        gudang_id = data.get('gudang_id')
        jumlah = Decimal(str(data.get('jumlah', 1)))
        harga_satuan = Decimal(str(data.get('harga_satuan', 0)))
        catatan = data.get('catatan', '')

        produk = get_object_or_404(Produk, pk=produk_id)
        gudang = get_object_or_404(Gudang, pk=gudang_id)

        with transaction.atomic():
            order = OrderService.objects.select_for_update().get(pk=order.pk)
            if order.status in ['diambil', 'dibatalkan']:
                status_display = dict(OrderService.STATUS_CHOICES).get(order.status, order.status)
                return JsonResponse({
                    'success': False,
                    'error': f'Tidak dapat menambah sparepart. Order sudah berstatus "{status_display}".'
                }, status=400)

            # Cek stok tersedia dengan lock supaya tidak terjadi race condition.
            stok = Stok.objects.select_for_update().filter(produk=produk, gudang=gudang).first()
            stok_tersedia = stok.jumlah if stok else 0

            if jumlah > stok_tersedia:
                return JsonResponse({
                    'success': False,
                    'error': f'Stok tidak cukup. Tersedia: {stok_tersedia} {produk.satuan.singkatan}'
                })

            # Buat penggunaan sparepart
            penggunaan = PenggunaanSparepart.objects.create(
                order_service=order,
                produk=produk,
                gudang=gudang,
                jumlah=jumlah,
                harga_satuan=harga_satuan if harga_satuan > 0 else produk.harga_jual,
                catatan=catatan,
            )
            # Kurangi stok
            penggunaan.kurangi_stok()

            # --- INTEGRASI: Stock Log (detail tracking stok) ---
            try:
                from apps.activity_log.stock_signals import log_service_stock_out
                log_service_stock_out(penggunaan, request.user, request)
            except Exception:
                pass
            # ---------------------------------------------------

            sync_order_biaya_akhir(order)
            from apps.service_center.services import sync_service_payment_accounting
            sync_service_payment_accounting(order, user=request.user)

        # --- INTEGRASI: Activity Log ---
        try:
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                request,
                action='create',
                model_name='PenggunaanSparepart',
                object_id=penggunaan.pk,
                object_repr=f"{produk.nama} ({jumlah} {produk.satuan.singkatan})",
                description=f"Menambahkan sparepart {produk.nama} x{jumlah} ke Order {order.nomor_service}"
            )
        except Exception:
            pass
        # -------------------------------

        return JsonResponse({
            'success': True,
            'data': {
                'id': penggunaan.id,
                'produk_nama': produk.nama,
                'sku': produk.sku,
                'gudang_nama': gudang.nama,
                'jumlah': str(penggunaan.jumlah),
                'satuan': produk.satuan.singkatan,
                'harga_satuan': str(penggunaan.harga_satuan),
                'subtotal': str(penggunaan.subtotal),
                'biaya_akhir': str(order.total_biaya),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@permission_required('delete', 'sparepart')
def hapus_sparepart(request, pk, sparepart_id):
    """Hapus sparepart dari order service. Kembalikan stok."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    # RBAC: Cek permission delete untuk sub-modul sparepart_service (QA-R1: granular)
    if not has_permission(request.user, 'delete', 'service_center', 'sparepart_service'):
        return JsonResponse({'success': False, 'error': 'Anda tidak memiliki izin untuk menghapus sparepart.'}, status=403)

    order = get_object_or_404(OrderService, pk=pk)
    penggunaan = get_object_or_404(PenggunaanSparepart, pk=sparepart_id, order_service=order)

    try:
        with transaction.atomic():
            order = OrderService.objects.select_for_update().get(pk=order.pk)
            penggunaan = PenggunaanSparepart.objects.select_for_update().get(
                pk=penggunaan.pk,
                order_service=order
            )

            # Kembalikan stok
            penggunaan.kembalikan_stok()

            # --- INTEGRASI: Stock Log (detail tracking stok) ---
            try:
                from apps.activity_log.stock_signals import log_service_stock_return
                log_service_stock_return(penggunaan, request.user, request)
            except Exception:
                pass
            # ---------------------------------------------------

            penggunaan.delete()

            sync_order_biaya_akhir(order)
            from apps.service_center.services import sync_service_payment_accounting
            sync_service_payment_accounting(order, user=request.user)

        # --- INTEGRASI: Activity Log ---
        try:
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                request,
                action='delete',
                model_name='PenggunaanSparepart',
                object_id=sparepart_id,
                object_repr=f"Sparepart ID {sparepart_id} (Dihapus)",
                description=f"Menghapus sparepart dari Order {order.nomor_service} dan mengembalikan stok"
            )
        except Exception:
            pass
        # -------------------------------

        return JsonResponse({
            'success': True,
            'biaya_akhir': str(order.total_biaya),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@permission_required('update', 'sparepart')
def edit_sparepart(request, pk, sparepart_id):
    """
    Edit penggunaan sparepart pada order service.
    Alur realtime:
    1. Kembalikan stok lama ke gudang lama
    2. Update data penggunaan (jumlah, harga, gudang)
    3. Kurangi stok baru dari gudang baru
    4. Recalculate biaya_akhir order
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    # RBAC: Cek permission update untuk sub-modul sparepart_service (QA-R1: granular)
    if not has_permission(request.user, 'update', 'service_center', 'sparepart_service'):
        return JsonResponse({'success': False, 'error': 'Anda tidak memiliki izin untuk mengubah sparepart.'}, status=403)

    order = get_object_or_404(OrderService, pk=pk)
    penggunaan = get_object_or_404(PenggunaanSparepart, pk=sparepart_id, order_service=order)

    try:
        from apps.produk.models import Produk, Gudang, Stok as StokModel

        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        new_jumlah = Decimal(str(data.get('jumlah', penggunaan.jumlah)))
        new_harga = Decimal(str(data.get('harga_satuan', penggunaan.harga_satuan)))
        new_gudang_id = data.get('gudang_id', penggunaan.gudang_id)
        new_catatan = data.get('catatan', penggunaan.catatan)

        new_gudang = get_object_or_404(Gudang, pk=new_gudang_id)

        with transaction.atomic():
            order = OrderService.objects.select_for_update().get(pk=order.pk)
            penggunaan = PenggunaanSparepart.objects.select_for_update().get(
                pk=penggunaan.pk,
                order_service=order
            )

            # Simpan data lama untuk perbandingan
            old_jumlah = penggunaan.jumlah
            old_gudang = penggunaan.gudang
            old_stok_dikurangi = penggunaan.stok_dikurangi

            # LANGKAH 1: Kembalikan stok lama
            penggunaan.kembalikan_stok()

            # --- INTEGRASI: Stock Log (stok dikembalikan dari edit) ---
            try:
                from apps.activity_log.stock_signals import log_service_stock_return, log_service_stock_out
                log_service_stock_return(penggunaan, request.user, request)
            except Exception:
                pass
            # -----------------------------------------------------------

            # LANGKAH 2: Cek stok baru tersedia
            stok_baru = StokModel.objects.select_for_update().filter(
                produk=penggunaan.produk,
                gudang=new_gudang
            ).first()
            stok_tersedia = stok_baru.jumlah if stok_baru else 0

            if new_jumlah > stok_tersedia:
                # Rollback: kurangi stok lama kembali karena sudah dikembalikan
                penggunaan.gudang = old_gudang
                penggunaan.jumlah = old_jumlah
                penggunaan.stok_dikurangi = False
                penggunaan.save(update_fields=['gudang', 'jumlah', 'stok_dikurangi'])
                penggunaan.kurangi_stok()
                satuan = penggunaan.produk.satuan.singkatan if penggunaan.produk.satuan else 'pcs'
                return JsonResponse({
                    'success': False,
                    'error': f'Stok tidak cukup di gudang {new_gudang.nama}. Tersedia: {stok_tersedia} {satuan}'
                })

            # LANGKAH 3: Update data penggunaan
            penggunaan.jumlah = new_jumlah
            penggunaan.harga_satuan = new_harga
            penggunaan.gudang = new_gudang
            penggunaan.catatan = new_catatan
            penggunaan.stok_dikurangi = False
            penggunaan.save()

            # LANGKAH 4: Kurangi stok baru
            penggunaan.kurangi_stok()

            # --- INTEGRASI: Stock Log (stok dikurangi setelah edit) ---
            try:
                log_service_stock_out(penggunaan, request.user, request)
            except Exception:
                pass
            # -----------------------------------------------------------

            sync_order_biaya_akhir(order)
            from apps.service_center.services import sync_service_payment_accounting
            sync_service_payment_accounting(order, user=request.user)

        # --- INTEGRASI: Activity Log ---
        try:
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                request,
                action='update',
                model_name='PenggunaanSparepart',
                object_id=penggunaan.pk,
                object_repr=f"{penggunaan.produk.nama} ({new_jumlah})",
                description=(
                f"Edit sparepart pada Order {order.nomor_service}: "
                f"jumlah {old_jumlah}→{new_jumlah}, "
                f"gudang {old_gudang.nama}→{new_gudang.nama}"
                )
            )
        except Exception:
            pass
        # -------------------------------

        return JsonResponse({
            'success': True,
            'data': {
                'id': penggunaan.id,
                'produk_nama': penggunaan.produk.nama,
                'gudang_nama': new_gudang.nama,
                'jumlah': str(penggunaan.jumlah),
                'satuan': penggunaan.produk.satuan.singkatan if penggunaan.produk.satuan else 'pcs',
                'harga_satuan': str(penggunaan.harga_satuan),
                'subtotal': str(penggunaan.subtotal),
                'biaya_akhir': str(order.total_biaya),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@permission_required('read', 'sparepart')
def api_search_sparepart(request):
    """API untuk search sparepart by name/SKU, termasuk info stok per gudang."""
    q = request.GET.get('q', '').strip()
    gudang_id = request.GET.get('gudang_id', '')

    if len(q) < 2:
        return JsonResponse({'results': []})

    try:
        from apps.produk.models import Produk, Stok

        produk_list = Produk.objects.filter(
            Q(nama__icontains=q) | Q(sku__icontains=q),
            aktif=True,
            tipe='sparepart'  # Hanya tampilkan sparepart untuk Service Center
        ).select_related('satuan', 'kategori')[:20]

        results = []
        for p in produk_list:
            stok_info = 0
            if gudang_id:
                stok_obj = Stok.objects.filter(produk=p, gudang_id=gudang_id).first()
                stok_info = float(stok_obj.jumlah) if stok_obj else 0
            else:
                stok_info = float(p.stok_total)

            results.append({
                'id': p.id,
                'nama': p.nama,
                'sku': p.sku,
                'harga_jual': str(p.harga_jual),
                'satuan': p.satuan.singkatan if p.satuan else 'pcs',
                'kategori': p.kategori.nama if p.kategori else '-',
                'stok': stok_info,
                'gambar': p.gambar.url if p.gambar else '',
            })

        return JsonResponse({'results': results})
    except Exception as e:
        return JsonResponse({'results': [], 'error': str(e)})
