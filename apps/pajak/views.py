"""
==========================================================================
 PAJAK VIEWS - Faktur Pajak, Setting PPN, Rekap PPN
==========================================================================
"""

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
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils import timezone

from apps.pajak.models import SettingPajak, FakturPajak
from apps.pajak.forms import SettingPajakForm, FakturPajakForm
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin


class FakturPajakListView(ReadPermissionMixin, ListView):
    """Daftar faktur pajak. URL: /pajak/"""
    paginate_by = 50
    model = FakturPajak
    template_name = 'pajak/faktur_list.html'
    context_object_name = 'faktur_list'
    permission_module = 'pajak'
    permission_sub_module = 'faktur_pajak'

    def get_queryset(self):
        qs = super().get_queryset().select_related('sales_order', 'purchase_order', 'pos_transaction', 'created_by')
        tipe = self.request.GET.get('tipe', '')
        if tipe:
            qs = qs.filter(tipe=tipe)
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        start = self.request.GET.get('start', '')
        end = self.request.GET.get('end', '')
        if start:
            qs = qs.filter(tanggal__gte=start)
        if end:
            qs = qs.filter(tanggal__lte=end)
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(nomor_seri__icontains=q) | Q(nama_lawan__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_faktur = FakturPajak.objects.all()

        agg_masukan = all_faktur.filter(tipe='masukan', status__in=['approved', 'reported']).aggregate(
            total_dpp=Sum('dpp'), total_ppn=Sum('ppn'))
        agg_keluaran = all_faktur.filter(tipe='keluaran', status__in=['approved', 'reported']).aggregate(
            total_dpp=Sum('dpp'), total_ppn=Sum('ppn'))

        context['ppn_masukan'] = agg_masukan['total_ppn'] or 0
        context['ppn_keluaran'] = agg_keluaran['total_ppn'] or 0
        context['count_total'] = all_faktur.count()
        context['count_masukan'] = all_faktur.filter(tipe='masukan').count()
        context['count_keluaran'] = all_faktur.filter(tipe='keluaran').count()

        ppn_setor = (agg_keluaran['total_ppn'] or 0) - (agg_masukan['total_ppn'] or 0)
        context['ppn_setor'] = ppn_setor

        context['tipe_choices'] = FakturPajak.TIPE_CHOICES
        context['status_choices'] = FakturPajak.STATUS_CHOICES
        return context


class FakturPajakCreateView(CreatePermissionMixin, CreateView):
    """Tambah faktur pajak. URL: /pajak/add/"""
    model = FakturPajak
    form_class = FakturPajakForm
    template_name = 'pajak/faktur_form.html'
    success_url = reverse_lazy('pajak:list')
    permission_module = 'pajak'
    permission_sub_module = 'faktur_pajak'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Input Faktur Pajak Baru'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Faktur {form.instance.nomor_seri} berhasil dicatat')
        return super().form_valid(form)


class FakturPajakUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit faktur pajak. URL: /pajak/<pk>/edit/"""
    model = FakturPajak
    form_class = FakturPajakForm
    template_name = 'pajak/faktur_form.html'
    success_url = reverse_lazy('pajak:list')
    permission_module = 'pajak'
    permission_sub_module = 'faktur_pajak'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit Faktur: {self.object.nomor_seri}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Faktur {form.instance.nomor_seri} berhasil diupdate')
        return super().form_valid(form)


class SettingPajakView(UpdatePermissionMixin, UpdateView):
    """Setting PPN. URL: /pajak/setting/"""
    model = SettingPajak
    form_class = SettingPajakForm
    template_name = 'pajak/setting_pajak.html'
    success_url = reverse_lazy('pajak:setting')
    permission_module = 'pajak'
    permission_sub_module = 'setting_pajak'

    def get_object(self, queryset=None):
        return SettingPajak.get_setting()

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Setting PPN & Pajak'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Setting pajak berhasil disimpan')
        return super().form_valid(form)


class RekapPPNView(ReadPermissionMixin, TemplateView):
    """Rekap PPN masukan vs keluaran. URL: /pajak/rekap/"""
    template_name = 'pajak/rekap_ppn.html'
    permission_module = 'pajak'
    permission_sub_module = 'rekap_ppn'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        tahun = int(self.request.GET.get('tahun', timezone.now().year))
        context['selected_tahun'] = tahun
        context['tahun_list'] = range(timezone.now().year - 5, timezone.now().year + 2)

        # Monthly breakdown
        months = []
        chart_masukan = []
        chart_keluaran = []
        chart_setor = []
        total_masukan_tahun = Decimal('0')
        total_keluaran_tahun = Decimal('0')

        for m in range(1, 13):
            masukan = FakturPajak.objects.filter(
                tipe='masukan', tanggal__year=tahun, tanggal__month=m,
                status__in=['approved', 'reported']
            ).aggregate(ppn=Sum('ppn'), dpp=Sum('dpp'))
            keluaran = FakturPajak.objects.filter(
                tipe='keluaran', tanggal__year=tahun, tanggal__month=m,
                status__in=['approved', 'reported']
            ).aggregate(ppn=Sum('ppn'), dpp=Sum('dpp'))

            ppn_m = masukan['ppn'] or 0
            ppn_k = keluaran['ppn'] or 0
            setor = ppn_k - ppn_m

            total_masukan_tahun += ppn_m
            total_keluaran_tahun += ppn_k

            months.append({
                'bulan': m,
                'dpp_masukan': masukan['dpp'] or 0,
                'ppn_masukan': ppn_m,
                'dpp_keluaran': keluaran['dpp'] or 0,
                'ppn_keluaran': ppn_k,
                'setor': setor,
            })

            chart_masukan.append(float(ppn_m))
            chart_keluaran.append(float(ppn_k))
            chart_setor.append(float(setor))

        context['months'] = months
        context['total_masukan'] = total_masukan_tahun
        context['total_keluaran'] = total_keluaran_tahun
        context['total_setor'] = total_keluaran_tahun - total_masukan_tahun

        context['chart_labels'] = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
        context['chart_masukan'] = chart_masukan
        context['chart_keluaran'] = chart_keluaran
        context['chart_setor'] = chart_setor

        return context



# ╔══════════════════════════════════════════════════════════════╗
# ║          PEMBAYARAN PPN (Settlement PPN ke Kas Negara)         ║
# ╚══════════════════════════════════════════════════════════════╝

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import DetailView

from apps.pajak.models import PembayaranPPN


class PembayaranPPNListView(ReadPermissionMixin, ListView):
    """Daftar pembayaran/setor PPN. URL: /pajak/setor/"""
    paginate_by = 50
    model = PembayaranPPN
    template_name = 'pajak/setor_list.html'
    context_object_name = 'setor_list'
    permission_module = 'pajak'
    permission_sub_module = 'rekap_ppn'

    def get_queryset(self):
        qs = super().get_queryset().select_related('jurnal', 'metode_pembayaran', 'created_by')
        tahun = self.request.GET.get('tahun', '')
        if tahun:
            qs = qs.filter(masa_tahun=tahun)
        tipe = self.request.GET.get('tipe', '')
        if tipe:
            qs = qs.filter(tipe=tipe)
        return qs.order_by('-masa_tahun', '-masa_bulan')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_setor = PembayaranPPN.objects.all()
        agg = all_setor.aggregate(
            total_setor=Sum('jumlah_setor'),
            total_keluaran=Sum('total_ppn_keluaran'),
            total_masukan=Sum('total_ppn_masukan'),
        )
        context['total_setor'] = agg['total_setor'] or Decimal('0')
        context['total_keluaran'] = agg['total_keluaran'] or Decimal('0')
        context['total_masukan'] = agg['total_masukan'] or Decimal('0')
        context['count_total'] = all_setor.count()
        context['count_setor'] = all_setor.filter(tipe='setor').count()
        context['count_restitusi'] = all_setor.filter(tipe='restitusi').count()
        context['tahun_list'] = range(timezone.now().year - 5, timezone.now().year + 2)
        context['tipe_choices'] = PembayaranPPN.TIPE_CHOICES
        return context


class PembayaranPPNCreateView(CreatePermissionMixin, TemplateView):
    """
    Buat record pembayaran PPN untuk masa pajak tertentu.
    URL: /pajak/setor/add/ (POST: masa_bulan, masa_tahun, tanggal_setor, metode_pembayaran, nomor_bukti, keterangan)

    Logika:
      1. Hitung total PPN keluaran/masukan untuk periode tersebut (status approved/reported).
      2. Tentukan tipe (setor/restitusi) dan jumlah selisih.
      3. Buat jurnal otomatis (D 2-2000 K 1-1500 + Kas/Bank), mutasi Kas/Bank.
      4. Update status FakturPajak periode tersebut menjadi 'reported'.
    """
    template_name = 'pajak/setor_form.html'
    permission_module = 'pajak'
    permission_sub_module = 'rekap_ppn'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.pos.models import MetodePembayaran
        context['title'] = 'Buat Setor / Restitusi PPN'
        context['tahun_list'] = range(timezone.now().year - 5, timezone.now().year + 2)
        context['bulan_list'] = list(range(1, 13))
        context['metode_list'] = MetodePembayaran.objects.filter(aktif=True)
        # Pre-fill default = bulan lalu
        now = timezone.now()
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1
        context['default_bulan'] = prev_month
        context['default_tahun'] = prev_year
        return context

    def post(self, request, *args, **kwargs):
        try:
            masa_bulan = int(request.POST.get('masa_bulan'))
            masa_tahun = int(request.POST.get('masa_tahun'))
        except (TypeError, ValueError):
            messages.error(request, 'Masa bulan/tahun tidak valid.')
            return redirect('pajak:setor_list')

        if not (1 <= masa_bulan <= 12):
            messages.error(request, 'Masa bulan harus 1-12.')
            return redirect('pajak:setor_list')

        # Cek apakah periode ini sudah pernah diproses
        if PembayaranPPN.objects.filter(masa_bulan=masa_bulan, masa_tahun=masa_tahun).exists():
            messages.error(request, f'Setor/Restitusi PPN untuk masa {masa_bulan:02d}/{masa_tahun} sudah pernah dibuat.')
            return redirect('pajak:setor_list')

        # Hitung agregat PPN periode tersebut (faktur approved/reported)
        agg_keluaran = FakturPajak.objects.filter(
            tipe='keluaran', tanggal__year=masa_tahun, tanggal__month=masa_bulan,
            status__in=['approved', 'reported']
        ).aggregate(total=Sum('ppn'))
        agg_masukan = FakturPajak.objects.filter(
            tipe='masukan', tanggal__year=masa_tahun, tanggal__month=masa_bulan,
            status__in=['approved', 'reported']
        ).aggregate(total=Sum('ppn'))
        total_keluaran = agg_keluaran['total'] or Decimal('0')
        total_masukan = agg_masukan['total'] or Decimal('0')
        selisih = total_keluaran - total_masukan

        if total_keluaran == 0 and total_masukan == 0:
            messages.error(request, f'Tidak ada faktur pajak approved untuk masa {masa_bulan:02d}/{masa_tahun}.')
            return redirect('pajak:setor_list')

        if selisih == 0:
            messages.error(request, 'PPN Keluaran = PPN Masukan, tidak ada selisih untuk disetor.')
            return redirect('pajak:setor_list')

        tipe = 'setor' if selisih > 0 else 'restitusi'
        jumlah_setor = abs(selisih)

        tanggal_setor_str = request.POST.get('tanggal_setor', '')
        try:
            from datetime import datetime as _dt
            tanggal_setor = _dt.strptime(tanggal_setor_str, '%Y-%m-%d').date() if tanggal_setor_str else timezone.now().date()
        except ValueError:
            tanggal_setor = timezone.now().date()

        metode_id = request.POST.get('metode_pembayaran') or None
        metode = None
        if metode_id:
            from apps.pos.models import MetodePembayaran
            try:
                metode = MetodePembayaran.objects.get(pk=metode_id)
            except MetodePembayaran.DoesNotExist:
                metode = None

        nomor_bukti = request.POST.get('nomor_bukti', '').strip()
        keterangan = request.POST.get('keterangan', '').strip()

        try:
            with transaction.atomic():
                from apps.akuntansi.services import create_jurnal
                from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping

                kas_bank_account, _, kas_akun_kode = resolve_kas_bank_mapping(metode)

                lines = []
                # PPN Keluaran (saldo normal kredit) → tutup dengan Debit
                if total_keluaran > 0:
                    lines.append({
                        'akun_kode': '2-2000', 'debit': total_keluaran, 'kredit': 0,
                        'keterangan': f'Tutup PPN Keluaran masa {masa_bulan:02d}/{masa_tahun}'
                    })
                # PPN Masukan (saldo normal debit) → tutup dengan Kredit
                if total_masukan > 0:
                    lines.append({
                        'akun_kode': '1-1500', 'debit': 0, 'kredit': total_masukan,
                        'keterangan': f'Tutup PPN Masukan masa {masa_bulan:02d}/{masa_tahun}'
                    })
                # Selisih → setor (Kredit Kas) atau restitusi (Debit Kas)
                if tipe == 'setor':
                    lines.append({
                        'akun_kode': kas_akun_kode, 'debit': 0, 'kredit': jumlah_setor,
                        'keterangan': f'Setor PPN ke kas negara masa {masa_bulan:02d}/{masa_tahun}'
                    })
                else:
                    lines.append({
                        'akun_kode': kas_akun_kode, 'debit': jumlah_setor, 'kredit': 0,
                        'keterangan': f'Penerimaan restitusi PPN masa {masa_bulan:02d}/{masa_tahun}'
                    })

                jurnal = create_jurnal(
                    tanggal=tanggal_setor,
                    deskripsi=f'Settlement PPN {masa_bulan:02d}/{masa_tahun} ({tipe})',
                    lines_data=lines,
                    sumber='pajak',
                    sumber_ref=f'PPN-{masa_tahun}-{masa_bulan:02d}',
                    user=request.user,
                    auto_post=True,
                )

                pembayaran = PembayaranPPN.objects.create(
                    tipe=tipe,
                    masa_bulan=masa_bulan,
                    masa_tahun=masa_tahun,
                    total_ppn_keluaran=total_keluaran,
                    total_ppn_masukan=total_masukan,
                    jumlah_setor=jumlah_setor,
                    tanggal_setor=tanggal_setor,
                    metode_pembayaran=metode,
                    nomor_bukti=nomor_bukti,
                    keterangan=keterangan,
                    jurnal=jurnal,
                    created_by=request.user,
                )

                # Mutasi Kas/Bank (sesuai tipe)
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe='keluar' if tipe == 'setor' else 'masuk',
                    tanggal=tanggal_setor,
                    jumlah=jumlah_setor,
                    deskripsi=f'{"Setor" if tipe == "setor" else "Restitusi"} PPN masa {masa_bulan:02d}/{masa_tahun}',
                    cabang=None,
                    metode_pembayaran=metode,
                    sumber_app='pajak',
                    sumber_model='PembayaranPPN',
                    sumber_id=pembayaran.pk,
                    sumber_ref=pembayaran.nomor,
                    jurnal_entry=jurnal,
                    user=request.user,
                )

                # Update status faktur menjadi 'reported'
                FakturPajak.objects.filter(
                    tanggal__year=masa_tahun, tanggal__month=masa_bulan,
                    status='approved'
                ).update(status='reported')

        except Exception as exc:
            messages.error(request, f'Gagal memproses settlement PPN: {exc}')
            return redirect('pajak:setor_list')

        messages.success(
            request,
            f'Settlement PPN masa {masa_bulan:02d}/{masa_tahun} berhasil. '
            f'{tipe.capitalize()} sebesar Rp {jumlah_setor:,.0f}. Jurnal: {jurnal.nomor}'
        )
        return redirect('pajak:setor_detail', pk=pembayaran.pk)


class PembayaranPPNDetailView(ReadPermissionMixin, DetailView):
    """Detail pembayaran PPN. URL: /pajak/setor/<pk>/"""
    model = PembayaranPPN
    template_name = 'pajak/setor_detail.html'
    context_object_name = 'pembayaran'
    permission_module = 'pajak'
    permission_sub_module = 'rekap_ppn'

    def get_queryset(self):
        return PembayaranPPN.objects.select_related('jurnal', 'metode_pembayaran', 'created_by')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Faktur pajak terkait di periode ini
        context['faktur_keluaran'] = FakturPajak.objects.filter(
            tipe='keluaran',
            tanggal__year=self.object.masa_tahun,
            tanggal__month=self.object.masa_bulan,
        ).order_by('tanggal')
        context['faktur_masukan'] = FakturPajak.objects.filter(
            tipe='masukan',
            tanggal__year=self.object.masa_tahun,
            tanggal__month=self.object.masa_bulan,
        ).order_by('tanggal')
        if self.object.jurnal:
            context['jurnal_lines'] = self.object.jurnal.lines.select_related('akun').all()
        else:
            context['jurnal_lines'] = []
        return context
