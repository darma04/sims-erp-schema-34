"""
==========================================================================
 ASET VIEWS - Daftar, Detail, Penyusutan, Disposal
==========================================================================
"""
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, Q
from django.db import transaction
from django.http import JsonResponse
from decimal import Decimal
from django.utils import timezone

from apps.aset.models import AsetTetap, Penyusutan, DisposalAset
from apps.aset.forms import AsetTetapForm, DisposalAsetForm
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin


class AsetListView(ReadPermissionMixin, ListView):
    """Daftar aset tetap. URL: /aset/"""
    paginate_by = 50
    model = AsetTetap
    template_name = 'aset/aset_list.html'
    context_object_name = 'aset_list'
    permission_module = 'aset'
    permission_sub_module = 'daftar_aset'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cabang', 'supplier', 'akun_aset')
        kategori = self.request.GET.get('kategori', '')
        if kategori:
            qs = qs.filter(kategori=kategori)
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        cabang = self.request.GET.get('cabang', '')
        if cabang:
            qs = qs.filter(cabang_id=cabang)
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(kode__icontains=q) | Q(nama__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_aset = AsetTetap.objects.all()

        context['count_total'] = all_aset.count()
        context['count_aktif'] = all_aset.filter(status='aktif').count()
        context['total_perolehan'] = all_aset.filter(status='aktif').aggregate(t=Sum('harga_perolehan'))['t'] or 0

        # Hitung total akumulasi penyusutan
        aktif_aset = all_aset.filter(status='aktif')
        total_akumulasi = Penyusutan.objects.filter(aset__status='aktif').aggregate(t=Sum('jumlah'))['t'] or Decimal('0')
        context['total_akumulasi'] = total_akumulasi
        context['total_nilai_buku'] = (context['total_perolehan'] or 0) - total_akumulasi

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['kategori_choices'] = AsetTetap.KATEGORI_CHOICES
        context['status_choices'] = AsetTetap.STATUS_CHOICES
        return context


class AsetCreateView(CreatePermissionMixin, CreateView):
    """Tambah aset baru. URL: /aset/add/"""
    model = AsetTetap
    form_class = AsetTetapForm
    template_name = 'aset/aset_form.html'
    success_url = reverse_lazy('aset:list')
    permission_module = 'aset'
    permission_sub_module = 'daftar_aset'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Registrasi Aset Tetap Baru'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        try:
            with transaction.atomic():
                response = super().form_valid(form)

                # Auto-create jurnal pembelian aset: D:Aset K:Kas
                from apps.akuntansi.services import create_jurnal
                from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping
                akun_kode = self.object.akun_aset.kode if self.object.akun_aset else '1-4000'
                kas_bank_account, _, kas_akun_kode = resolve_kas_bank_mapping(None)
                jurnal = create_jurnal(
                    tanggal=self.object.tanggal_perolehan,
                    deskripsi=f'Pembelian aset tetap: {self.object.nama}',
                    lines_data=[
                        {'akun_kode': akun_kode, 'debit': self.object.harga_perolehan, 'kredit': 0,
                         'keterangan': f'Perolehan aset {self.object.kode}'},
                        {'akun_kode': kas_akun_kode, 'debit': 0, 'kredit': self.object.harga_perolehan,
                         'keterangan': f'Pembayaran aset {self.object.kode}'},
                    ],
                    sumber='aset',
                    sumber_id=self.object.pk,
                    sumber_ref=self.object.kode,
                    cabang=self.object.cabang,
                    user=self.request.user,
                    auto_post=True,
                )
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe='keluar',
                    tanggal=self.object.tanggal_perolehan,
                    jumlah=self.object.harga_perolehan,
                    deskripsi=f'Pembelian aset tetap {self.object.kode}',
                    akun_lawan=self.object.akun_aset,
                    cabang=self.object.cabang,
                    sumber_app='aset',
                    sumber_model='AsetTetap',
                    sumber_id=self.object.pk,
                    sumber_ref=self.object.kode,
                    jurnal_entry=jurnal,
                    user=self.request.user,
                )
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        messages.success(self.request, f'Aset {self.object.nama} berhasil didaftarkan dan jurnal otomatis sudah dicatat')
        return response


class AsetUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit aset. URL: /aset/<pk>/edit/"""
    model = AsetTetap
    form_class = AsetTetapForm
    template_name = 'aset/aset_form.html'
    success_url = reverse_lazy('aset:list')
    permission_module = 'aset'
    permission_sub_module = 'daftar_aset'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit Aset: {self.object.nama}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Aset {form.instance.nama} berhasil diupdate')
        return super().form_valid(form)


class AsetDetailView(ReadPermissionMixin, TemplateView):
    """Detail aset + riwayat penyusutan. URL: /aset/<pk>/"""
    template_name = 'aset/aset_detail.html'
    permission_module = 'aset'
    permission_sub_module = 'daftar_aset'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        aset = get_object_or_404(
            AsetTetap.objects.select_related('cabang', 'supplier', 'akun_aset'),
            pk=kwargs['pk']
        )
        context['aset'] = aset
        context['penyusutan_list'] = aset.penyusutan_set.select_related('jurnal').all()
        context['disposal_list'] = aset.disposal_set.select_related('jurnal').all()
        context['disposal_form'] = DisposalAsetForm()

        # Chart data for depreciation
        py_data = aset.penyusutan_set.order_by('tahun', 'bulan')
        context['chart_labels'] = [f"{p.bulan:02d}/{p.tahun}" for p in py_data]
        context['chart_akumulasi'] = [float(p.akumulasi) for p in py_data]
        context['chart_nilai_buku'] = [float(aset.harga_perolehan - p.akumulasi) for p in py_data]

        return context


class ProsessPenyusutanView(UpdatePermissionMixin, TemplateView):
    """Proses penyusutan 1 bulan. URL: /aset/<pk>/susutkan/ (POST)"""
    template_name = 'aset/aset_detail.html'
    permission_module = 'aset'
    permission_sub_module = 'penyusutan'

    def get(self, request, *args, **kwargs):
        return redirect('aset:detail', pk=kwargs['pk'])

    def post(self, request, *args, **kwargs):
        aset = get_object_or_404(AsetTetap, pk=kwargs['pk'])

        if aset.status != 'aktif':
            return JsonResponse({'success': False, 'message': 'Aset tidak aktif.'}, status=400)

        if aset.sisa_umur_bulan <= 0:
            return JsonResponse({'success': False, 'message': 'Umur ekonomis sudah habis.'}, status=400)

        # Determine period
        today = timezone.now().date()
        bulan = int(request.POST.get('bulan', today.month))
        tahun = int(request.POST.get('tahun', today.year))

        # Check duplicate
        if Penyusutan.objects.filter(aset=aset, bulan=bulan, tahun=tahun).exists():
            return JsonResponse({'success': False, 'message': f'Penyusutan {bulan:02d}/{tahun} sudah tercatat.'}, status=400)

        jumlah = aset.penyusutan_per_bulan
        akumulasi_sebelum = aset.akumulasi_penyusutan
        akumulasi_baru = akumulasi_sebelum + jumlah

        with transaction.atomic():
            peny = Penyusutan.objects.create(
                aset=aset, bulan=bulan, tahun=tahun,
                jumlah=jumlah, akumulasi=akumulasi_baru,
                created_by=request.user
            )

            # Auto-create jurnal: D:Beban Penyusutan K:Akumulasi Penyusutan
            try:
                from apps.aset.services import ensure_penyusutan_accounting
                ensure_penyusutan_accounting(peny, user=request.user, tanggal=today)
            except Exception as exc:
                transaction.set_rollback(True)
                return JsonResponse(
                    {'success': False, 'message': f'Auto-jurnal penyusutan aset gagal: {exc}'},
                    status=400,
                )

        return JsonResponse({
            'success': True,
            'message': f'Penyusutan {bulan:02d}/{tahun} sebesar Rp {jumlah:,.0f} berhasil dicatat. Akumulasi: Rp {akumulasi_baru:,.0f}'
        })


class DisposalCreateView(CreatePermissionMixin, CreateView):
    """Disposal/jual/hapus aset. URL: /aset/<pk>/disposal/ (POST)"""
    model = DisposalAset
    form_class = DisposalAsetForm
    template_name = 'aset/aset_detail.html'
    permission_module = 'aset'
    permission_sub_module = 'daftar_aset'

    def get(self, request, *args, **kwargs):
        return redirect('aset:detail', pk=kwargs['pk'])

    def form_valid(self, form):
        aset = get_object_or_404(AsetTetap, pk=self.kwargs['pk'])

        if aset.status != 'aktif':
            messages.error(self.request, 'Aset tidak aktif.')
            return redirect('aset:detail', pk=aset.pk)

        with transaction.atomic():
            form.instance.aset = aset
            form.instance.nilai_buku_saat_disposal = aset.nilai_buku
            form.instance.created_by = self.request.user
            self.object = form.save()

            # Update status aset
            aset.status = 'dijual' if form.instance.tipe == 'jual' else 'dihapuskan'
            aset.save()

            # Auto-create jurnal disposal
            try:
                from apps.aset.services import ensure_disposal_accounting
                ensure_disposal_accounting(self.object, user=self.request.user)
            except Exception as exc:
                transaction.set_rollback(True)
                messages.error(self.request, f'Auto-jurnal disposal aset gagal: {exc}')
                return redirect('aset:detail', pk=aset.pk)

        messages.success(self.request, f'Aset {aset.nama} telah di-disposal. Laba/Rugi: Rp {self.object.laba_rugi:,.0f}')
        return redirect('aset:detail', pk=aset.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Gagal memproses disposal.')
        return redirect('aset:detail', pk=self.kwargs['pk'])


class PenyusutanDashboardView(ReadPermissionMixin, TemplateView):
    """Dashboard penyusutan semua aset. URL: /aset/penyusutan/"""
    template_name = 'aset/penyusutan_dashboard.html'
    permission_module = 'aset'
    permission_sub_module = 'penyusutan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        aktif_aset = AsetTetap.objects.filter(status='aktif').select_related('cabang')

        tahun = int(self.request.GET.get('tahun', timezone.now().year))
        context['selected_tahun'] = tahun
        context['tahun_list'] = range(timezone.now().year - 5, timezone.now().year + 2)
        # Per-aset summary
        aset_summary = []
        for a in aktif_aset:
            peny_tahun = Penyusutan.objects.filter(aset=a, tahun=tahun).aggregate(t=Sum('jumlah'))['t'] or 0
            aset_summary.append({
                'aset': a,
                'penyusutan_tahun': peny_tahun,
                'akumulasi': a.akumulasi_penyusutan,
                'nilai_buku': a.nilai_buku,
                'sisa_umur': a.sisa_umur_bulan,
            })
        context['aset_summary'] = aset_summary

        # Totals
        context['total_perolehan'] = sum(a['aset'].harga_perolehan for a in aset_summary)
        context['total_penyusutan_tahun'] = sum(a['penyusutan_tahun'] for a in aset_summary)
        context['total_akumulasi'] = sum(a['akumulasi'] for a in aset_summary)
        context['total_nilai_buku'] = sum(a['nilai_buku'] for a in aset_summary)

        # Chart data — monthly depreciation for the year
        monthly = []
        for m in range(1, 13):
            total = Penyusutan.objects.filter(tahun=tahun, bulan=m, aset__status='aktif').aggregate(t=Sum('jumlah'))['t'] or 0
            monthly.append(float(total))
        context['chart_months'] = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
        context['chart_monthly'] = monthly

        return context


class ProsessPenyusutanMassalView(UpdatePermissionMixin, TemplateView):
    """
    Proses penyusutan MASSAL untuk semua aset aktif yang belum disusutkan
    pada bulan/tahun tertentu. URL: /aset/penyusutan/massal/ (POST)

    Body POST: bulan (1-12), tahun (YYYY) — default = bulan & tahun berjalan.

    Untuk tiap aset aktif yang sisa umurnya > 0 dan belum punya record penyusutan
    pada periode tersebut: buat Penyusutan + jurnal otomatis (D 6-4000 K 1-4100).
    Idempotent: aset yang sudah disusutkan akan dilewati.
    """
    permission_module = 'aset'
    permission_sub_module = 'penyusutan'

    def get(self, request, *args, **kwargs):
        return redirect('aset:penyusutan')

    def post(self, request, *args, **kwargs):
        today = timezone.now().date()
        try:
            bulan = int(request.POST.get('bulan') or today.month)
            tahun = int(request.POST.get('tahun') or today.year)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Bulan/tahun tidak valid.'}, status=400)

        if not (1 <= bulan <= 12):
            return JsonResponse({'success': False, 'message': 'Bulan harus antara 1 sampai 12.'}, status=400)

        aset_qs = AsetTetap.objects.filter(status='aktif').select_related('cabang', 'akun_aset')

        processed = 0
        skipped = 0
        failed = []
        total_nominal = Decimal('0')

        for aset in aset_qs:
            if Penyusutan.objects.filter(aset=aset, bulan=bulan, tahun=tahun).exists():
                skipped += 1
                continue
            if aset.sisa_umur_bulan <= 0:
                skipped += 1
                continue
            jumlah = aset.penyusutan_per_bulan
            if jumlah <= 0:
                skipped += 1
                continue
            akumulasi_baru = aset.akumulasi_penyusutan + jumlah
            try:
                with transaction.atomic():
                    peny = Penyusutan.objects.create(
                        aset=aset, bulan=bulan, tahun=tahun,
                        jumlah=jumlah, akumulasi=akumulasi_baru,
                        created_by=request.user,
                    )
                    from apps.aset.services import ensure_penyusutan_accounting
                    ensure_penyusutan_accounting(peny, user=request.user, tanggal=today)
                processed += 1
                total_nominal += jumlah
            except Exception as exc:
                failed.append(f'{aset.kode}: {exc}')

        msg = (
            f'Penyusutan {bulan:02d}/{tahun}: {processed} aset disusutkan '
            f'(Rp {total_nominal:,.0f}), {skipped} dilewati'
        )
        if failed:
            msg += f', {len(failed)} gagal'
        return JsonResponse({
            'success': True,
            'message': msg,
            'processed': processed,
            'skipped': skipped,
            'failed': failed,
            'total_nominal': float(total_nominal),
        })
