"""
==========================================================================
 AKUNTANSI VIEWS - Views untuk Chart of Accounts, Jurnal & Buku Besar
==========================================================================
 CHART OF ACCOUNTS:
   AkunListView        → Daftar CoA (tree view)
   AkunCreateView      → Tambah akun
   AkunUpdateView      → Edit akun
   AkunDeleteView      → Hapus akun
   SeedCoAView         → Seed data CoA default

 JURNAL:
   JurnalEntryListView   → Daftar jurnal + filter
   JurnalEntryCreateView → Input jurnal manual (inline formset)
   JurnalEntryDetailView → Detail jurnal + audit trail
   JurnalEntryDeleteView → Hapus jurnal (draft only)
   JurnalPostView        → Posting jurnal
   JurnalReverseView     → Buat jurnal pembalik

 BUKU BESAR:
   BukuBesarView → Ledger per akun

 PERIODE:
   PeriodeListView, PeriodeCreateView, PeriodeUpdateView, PeriodeTutupView
==========================================================================
"""

from django.shortcuts import redirect, get_object_or_404
from django.db.models import ProtectedError, Sum, Count, Q
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from decimal import Decimal

from apps.akuntansi.models import Akun, PeriodeAkuntansi, JurnalEntry, JurnalLine
from apps.akuntansi.forms import AkunForm, PeriodeAkuntansiForm, JurnalEntryForm, JurnalLineFormSet
from apps.akuntansi.services import get_saldo_akun, get_buku_besar, seed_default_coa, create_jurnal_pembalik
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin


# ╔══════════════════════════════════════════════════════════════╗
# ║               CHART OF ACCOUNTS (CoA)                         ║
# ╚══════════════════════════════════════════════════════════════╝

class AkunListView(ReadPermissionMixin, ListView):
    """Daftar Chart of Accounts (CoA). URL: /akuntansi/coa/"""
    paginate_by = 100
    model = Akun
    template_name = 'akuntansi/coa_list.html'
    context_object_name = 'akun_list'
    permission_module = 'akuntansi'
    permission_sub_module = 'coa'

    def get_queryset(self):
        qs = super().get_queryset()
        tipe = self.request.GET.get('tipe', '')
        if tipe:
            qs = qs.filter(tipe=tipe)
        search = self.request.GET.get('q', '')
        if search:
            qs = qs.filter(Q(kode__icontains=search) | Q(nama__icontains=search))
        return qs.order_by('kode')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        all_akun = Akun.objects.all()
        context['total_akun'] = all_akun.count()
        context['total_aset'] = all_akun.filter(tipe='aset').count()
        context['total_kewajiban'] = all_akun.filter(tipe='kewajiban').count()
        context['total_modal'] = all_akun.filter(tipe='modal').count()
        context['total_pendapatan'] = all_akun.filter(tipe='pendapatan').count()
        context['total_hpp'] = all_akun.filter(tipe='hpp').count()
        context['total_beban'] = all_akun.filter(tipe='beban').count()
        context['tipe_choices'] = Akun.TIPE_CHOICES
        context['selected_tipe'] = self.request.GET.get('tipe', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context


class AkunCreateView(CreatePermissionMixin, CreateView):
    """Tambah akun CoA. URL: /akuntansi/coa/add/"""
    model = Akun
    form_class = AkunForm
    template_name = 'akuntansi/coa_form.html'
    success_url = reverse_lazy('akuntansi:coa')
    permission_module = 'akuntansi'
    permission_sub_module = 'coa'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Akun Baru'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Akun {form.instance.kode} - {form.instance.nama} berhasil ditambahkan')
        return super().form_valid(form)


class AkunUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit akun CoA. URL: /akuntansi/coa/<pk>/edit/"""
    model = Akun
    form_class = AkunForm
    template_name = 'akuntansi/coa_form.html'
    success_url = reverse_lazy('akuntansi:coa')
    permission_module = 'akuntansi'
    permission_sub_module = 'coa'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit Akun: {self.object.kode}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Akun {form.instance.kode} berhasil diperbarui')
        return super().form_valid(form)


class AkunDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus akun CoA — return JSON untuk AJAX."""
    model = Akun
    success_url = reverse_lazy('akuntansi:coa')
    permission_module = 'akuntansi'
    permission_sub_module = 'coa'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            if self.object.is_system:
                return JsonResponse({'success': False, 'message': 'Akun sistem tidak dapat dihapus.'}, status=400)
            akun_name = f"{self.object.kode} - {self.object.nama}"
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Akun {akun_name} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Akun tidak dapat dihapus karena masih digunakan di jurnal.'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


class SeedCoAView(CreatePermissionMixin, TemplateView):
    """Seed data CoA default. URL: /akuntansi/coa/seed/ (POST)"""
    template_name = 'akuntansi/coa_list.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'coa'

    def get(self, request, *args, **kwargs):
        return redirect('akuntansi:coa')

    def post(self, request, *args, **kwargs):
        created, skipped = seed_default_coa()
        if created > 0:
            messages.success(request, f'Berhasil menambahkan {created} akun default. {skipped} akun sudah ada (dilewati).')
        else:
            messages.info(request, f'Semua {skipped} akun default sudah ada.')
        return redirect('akuntansi:coa')


# ╔══════════════════════════════════════════════════════════════╗
# ║               JURNAL ENTRY                                     ║
# ╚══════════════════════════════════════════════════════════════╝

class JurnalEntryListView(ReadPermissionMixin, ListView):
    """Daftar jurnal entry. URL: /akuntansi/jurnal/"""
    paginate_by = 50
    model = JurnalEntry
    template_name = 'akuntansi/jurnal_list.html'
    context_object_name = 'jurnal_list'
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cabang', 'created_by').annotate(
            sum_debit=Sum('lines__debit'),
            sum_kredit=Sum('lines__kredit'),
        )
        # Filter tanggal
        start = self.request.GET.get('start', '')
        end = self.request.GET.get('end', '')
        if start:
            qs = qs.filter(tanggal__gte=start)
        if end:
            qs = qs.filter(tanggal__lte=end)
        # Filter sumber
        sumber = self.request.GET.get('sumber', '')
        if sumber:
            qs = qs.filter(sumber=sumber)
        # Filter status
        status = self.request.GET.get('status', '')
        if status == 'posted':
            qs = qs.filter(is_posted=True)
        elif status == 'draft':
            qs = qs.filter(is_posted=False)
        # Filter cabang
        cabang = self.request.GET.get('cabang', '')
        if cabang:
            qs = qs.filter(cabang_id=cabang)
        # Search
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(nomor__icontains=q) | Q(deskripsi__icontains=q))
        return qs.order_by('-tanggal', '-dibuat_pada')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_jurnal'] = qs.count()
        context['total_posted'] = qs.filter(is_posted=True).count()
        context['total_draft'] = qs.filter(is_posted=False).count()

        # Hitung total debit/kredit dari lines
        from apps.akuntansi.models import JurnalLine
        line_totals = JurnalLine.objects.filter(
            jurnal__in=qs, jurnal__is_posted=True
        ).aggregate(total_d=Sum('debit'), total_k=Sum('kredit'))
        context['total_debit'] = line_totals['total_d'] or 0
        context['total_kredit'] = line_totals['total_k'] or 0

        context['sumber_choices'] = JurnalEntry.SUMBER_CHOICES
        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        return context


class JurnalEntryCreateView(CreatePermissionMixin, CreateView):
    """Input jurnal manual. URL: /akuntansi/jurnal/add/"""
    model = JurnalEntry
    form_class = JurnalEntryForm
    template_name = 'akuntansi/jurnal_form.html'
    success_url = reverse_lazy('akuntansi:jurnal')
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Input Jurnal Manual'
        if self.request.POST:
            context['formset'] = JurnalLineFormSet(self.request.POST)
        else:
            context['formset'] = JurnalLineFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if formset.is_valid():
            with transaction.atomic():
                from apps.akuntansi.services import validate_periode_open
                form.instance.created_by = self.request.user
                form.instance.sumber = 'manual'
                form.instance.periode = validate_periode_open(form.instance.tanggal, periode=form.instance.periode)
                self.object = form.save()

                formset.instance = self.object
                formset.save()

                # Validasi balance
                total_d = sum(l.debit for l in self.object.lines.all())
                total_k = sum(l.kredit for l in self.object.lines.all())
                if total_d != total_k:
                    messages.error(self.request, f'Jurnal tidak balance! Debit: Rp {total_d:,.0f} ≠ Kredit: Rp {total_k:,.0f}')
                    transaction.set_rollback(True)
                    return self.form_invalid(form)

                # Log activity
                try:
                    from apps.activity_log.middleware import ActivityLogMiddleware
                    ActivityLogMiddleware.log_activity(
                        self.request, action='create', model_name='Jurnal Entry',
                        object_id=self.object.pk, object_repr=str(self.object),
                        description=f'Input jurnal manual: {self.object.nomor}'
                    )
                except Exception:
                    pass

                messages.success(self.request, f'Jurnal {self.object.nomor} berhasil dibuat')
                return redirect(self.success_url)
        else:
            return self.form_invalid(form)


class JurnalEntryDetailView(ReadPermissionMixin, TemplateView):
    """Detail jurnal entry. URL: /akuntansi/jurnal/<pk>/"""
    template_name = 'akuntansi/jurnal_detail.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        jurnal = get_object_or_404(JurnalEntry.objects.select_related('cabang', 'created_by', 'periode', 'jurnal_asal'), pk=kwargs.get('pk'))
        context['jurnal'] = jurnal
        context['lines'] = jurnal.lines.select_related('akun').all()
        context['total_debit'] = sum(l.debit for l in context['lines'])
        context['total_kredit'] = sum(l.kredit for l in context['lines'])

        # Jurnal pembalik (jika ada)
        context['jurnal_pembalik_list'] = jurnal.jurnal_pembalik.all()

        # Audit trail
        try:
            from apps.activity_log.models import UserActivity
            context['activity_logs'] = UserActivity.objects.filter(
                model_name__icontains='jurnal', object_id=str(jurnal.pk)
            ).select_related('user').order_by('-timestamp')[:20]
        except Exception:
            context['activity_logs'] = []

        return context


class JurnalEntryDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus jurnal entry (hanya draft). URL: /akuntansi/jurnal/<pk>/delete/"""
    model = JurnalEntry
    success_url = reverse_lazy('akuntansi:jurnal')
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            if self.object.is_posted:
                return JsonResponse({
                    'success': False,
                    'message': 'Jurnal yang sudah diposting tidak dapat dihapus. Gunakan Jurnal Pembalik.'
                }, status=400)

            nomor = self.object.nomor
            self.object.delete()

            try:
                from apps.activity_log.middleware import ActivityLogMiddleware
                ActivityLogMiddleware.log_activity(
                    request, action='delete', model_name='Jurnal Entry',
                    object_id=0, object_repr=nomor,
                    description=f'Menghapus jurnal draft: {nomor}'
                )
            except Exception:
                pass

            return JsonResponse({'success': True, 'message': f'Jurnal {nomor} berhasil dihapus'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


class JurnalPostView(UpdatePermissionMixin, TemplateView):
    """Posting jurnal (draft → posted). URL: /akuntansi/jurnal/<pk>/post/ (POST)"""
    template_name = 'akuntansi/jurnal_detail.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def post(self, request, *args, **kwargs):
        jurnal = get_object_or_404(JurnalEntry, pk=kwargs['pk'])

        if jurnal.is_posted:
            return JsonResponse({'success': False, 'message': 'Jurnal sudah diposting.'}, status=400)

        # Validasi balance
        total_d = sum(l.debit for l in jurnal.lines.all())
        total_k = sum(l.kredit for l in jurnal.lines.all())
        if total_d != total_k:
            return JsonResponse({
                'success': False,
                'message': f'Jurnal tidak balance! Debit: {total_d:,.0f} ≠ Kredit: {total_k:,.0f}'
            }, status=400)

        try:
            from apps.akuntansi.services import validate_periode_open
            jurnal.periode = validate_periode_open(jurnal.tanggal, periode=jurnal.periode)
        except ValueError as exc:
            return JsonResponse({'success': False, 'message': str(exc)}, status=400)

        jurnal.is_posted = True
        jurnal.save(update_fields=['is_posted', 'periode'])

        try:
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                request, action='update', model_name='Jurnal Entry',
                object_id=jurnal.pk, object_repr=str(jurnal),
                description=f'Memposting jurnal: {jurnal.nomor}'
            )
        except Exception:
            pass

        return JsonResponse({'success': True, 'message': f'Jurnal {jurnal.nomor} berhasil diposting.'})


class JurnalReverseView(UpdatePermissionMixin, TemplateView):
    """Buat jurnal pembalik. URL: /akuntansi/jurnal/<pk>/reverse/ (POST)"""
    template_name = 'akuntansi/jurnal_detail.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'jurnal'

    def post(self, request, *args, **kwargs):
        jurnal = get_object_or_404(JurnalEntry, pk=kwargs['pk'])

        if not jurnal.is_posted:
            return JsonResponse({'success': False, 'message': 'Hanya jurnal yang sudah diposting yang bisa dibalik.'}, status=400)

        try:
            pembalik = create_jurnal_pembalik(jurnal, user=request.user)

            try:
                from apps.activity_log.middleware import ActivityLogMiddleware
                ActivityLogMiddleware.log_activity(
                    request, action='create', model_name='Jurnal Entry',
                    object_id=pembalik.pk, object_repr=str(pembalik),
                    description=f'Membuat jurnal pembalik {pembalik.nomor} dari {jurnal.nomor}'
                )
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'message': f'Jurnal pembalik {pembalik.nomor} berhasil dibuat dari {jurnal.nomor}.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Gagal membuat pembalik: {str(e)}'}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
# ║               BUKU BESAR (General Ledger)                      ║
# ╚══════════════════════════════════════════════════════════════╝

class BukuBesarView(ReadPermissionMixin, TemplateView):
    """Buku Besar (General Ledger). URL: /akuntansi/buku-besar/"""
    template_name = 'akuntansi/buku_besar.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'buku_besar'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        akun_id = self.request.GET.get('akun', '')
        start = self.request.GET.get('start', '')
        end = self.request.GET.get('end', '')
        cabang_id = self.request.GET.get('cabang', '')

        context['akun_list'] = Akun.objects.filter(is_active=True).order_by('kode')
        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)
        context['selected_akun'] = akun_id
        context['selected_start'] = start
        context['selected_end'] = end
        context['selected_cabang'] = cabang_id

        if akun_id:
            try:
                akun = Akun.objects.get(pk=akun_id)
                cabang = None
                if cabang_id:
                    cabang = Gudang.objects.get(pk=cabang_id)

                data = get_buku_besar(
                    akun,
                    tanggal_mulai=start if start else None,
                    tanggal_akhir=end if end else None,
                    cabang=cabang,
                )
                context['buku_besar'] = data
                context['has_data'] = len(data['mutasi']) > 0
            except (Akun.DoesNotExist, Exception):
                context['buku_besar'] = None
                context['has_data'] = False
        else:
            context['buku_besar'] = None
            context['has_data'] = False

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║               PERIODE AKUNTANSI                                ║
# ╚══════════════════════════════════════════════════════════════╝

class PeriodeListView(ReadPermissionMixin, ListView):
    """Daftar periode akuntansi. URL: /akuntansi/periode/"""
    paginate_by = 50
    model = PeriodeAkuntansi
    template_name = 'akuntansi/periode_list.html'
    context_object_name = 'periode_list'
    permission_module = 'akuntansi'
    permission_sub_module = 'periode'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_periode'] = PeriodeAkuntansi.objects.count()
        context['total_aktif'] = PeriodeAkuntansi.objects.filter(is_aktif=True).count()
        context['total_tutup'] = PeriodeAkuntansi.objects.filter(is_tutup=True).count()
        return context


class PeriodeCreateView(CreatePermissionMixin, CreateView):
    """Tambah periode. URL: /akuntansi/periode/add/"""
    model = PeriodeAkuntansi
    form_class = PeriodeAkuntansiForm
    template_name = 'akuntansi/periode_form.html'
    success_url = reverse_lazy('akuntansi:periode')
    permission_module = 'akuntansi'
    permission_sub_module = 'periode'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Periode Akuntansi'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Periode {form.instance.nama} berhasil ditambahkan')
        return super().form_valid(form)


class PeriodeUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit periode. URL: /akuntansi/periode/<pk>/edit/"""
    model = PeriodeAkuntansi
    form_class = PeriodeAkuntansiForm
    template_name = 'akuntansi/periode_form.html'
    success_url = reverse_lazy('akuntansi:periode')
    permission_module = 'akuntansi'
    permission_sub_module = 'periode'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit Periode: {self.object.nama}'
        return context

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_tutup:
            messages.error(request, 'Periode yang sudah ditutup tidak dapat diedit.')
            return redirect('akuntansi:periode')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, f'Periode {form.instance.nama} berhasil diperbarui')
        return super().form_valid(form)


class PeriodeTutupView(UpdatePermissionMixin, TemplateView):
    """Tutup periode akuntansi. URL: /akuntansi/periode/<pk>/tutup/ (POST)"""
    template_name = 'akuntansi/periode_list.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'periode'

    def post(self, request, *args, **kwargs):
        periode = get_object_or_404(PeriodeAkuntansi, pk=kwargs['pk'])

        if periode.is_tutup:
            return JsonResponse({'success': False, 'message': 'Periode sudah ditutup.'}, status=400)

        periode.is_tutup = True
        periode.is_aktif = False
        periode.save()

        # ── Closing Entry Otomatis (Sesuai Standar Akuntansi) ──
        # Proses tutup buku dengan 3 jurnal closing entry:
        # 1. Tutup akun Pendapatan → Ikhtisar Laba/Rugi
        # 2. Tutup akun HPP & Beban → Ikhtisar Laba/Rugi
        # 3. Transfer Ikhtisar Laba/Rugi → Laba Ditahan
        try:
            from apps.akuntansi.services import get_laba_rugi, create_jurnal, get_akun_by_kode
            from apps.akuntansi.models import Akun
            
            # Hitung laba/rugi periode
            data = get_laba_rugi(periode.tanggal_mulai, periode.tanggal_akhir)
            total_pendapatan = data.get('total_pendapatan', Decimal('0'))
            total_hpp = data.get('total_hpp', Decimal('0'))
            total_beban = data.get('total_beban', Decimal('0'))
            laba_bersih = data.get('laba_bersih', Decimal('0'))

            # Cek apakah akun Ikhtisar Laba/Rugi dan Laba Ditahan ada
            akun_ikhtisar = get_akun_by_kode('3-9000')  # Ikhtisar Laba/Rugi (temporary)
            akun_laba_ditahan = get_akun_by_kode('3-2000')  # Laba Ditahan
            
            if not akun_ikhtisar:
                # Buat akun Ikhtisar Laba/Rugi jika belum ada
                akun_ikhtisar = Akun.objects.create(
                    kode='3-9000',
                    nama='Ikhtisar Laba/Rugi',
                    tipe='modal',
                    sub_tipe='ikhtisar',
                    saldo_normal='kredit',
                    is_system=True,
                    is_active=True,
                    deskripsi='Akun temporary untuk closing entry'
                )

            if akun_ikhtisar and akun_laba_ditahan:
                # ═══ Jurnal 1: Tutup Akun Pendapatan ═══
                pendapatan_items = [
                    item for item in data.get('pendapatan', [])
                    if item.get('raw_saldo', item.get('saldo', Decimal('0'))) != 0
                ]
                if pendapatan_items:
                    lines_pendapatan = []
                    for item in pendapatan_items:
                        raw_saldo = abs(item.get('raw_saldo', item.get('saldo', Decimal('0'))))
                        if raw_saldo <= 0:
                            continue
                        if item['akun'].saldo_normal == 'kredit':
                            lines_pendapatan.append({
                                'akun': item['akun'],
                                'debit': raw_saldo,
                                'kredit': Decimal('0'),
                                'keterangan': f'Closing entry {periode.nama}'
                            })
                        else:
                            lines_pendapatan.append({
                                'akun': item['akun'],
                                'debit': Decimal('0'),
                                'kredit': raw_saldo,
                                'keterangan': f'Closing entry {periode.nama}'
                            })
                    
                    if total_pendapatan > 0:
                        lines_pendapatan.append({
                            'akun': akun_ikhtisar,
                            'debit': Decimal('0'),
                            'kredit': total_pendapatan,
                            'keterangan': f'Transfer pendapatan bersih ke Ikhtisar'
                        })
                    elif total_pendapatan < 0:
                        lines_pendapatan.append({
                            'akun': akun_ikhtisar,
                            'debit': abs(total_pendapatan),
                            'kredit': Decimal('0'),
                            'keterangan': f'Transfer kontra pendapatan ke Ikhtisar'
                        })
                    
                    create_jurnal(
                        tanggal=periode.tanggal_akhir,
                        deskripsi=f'Closing Entry (1/3) — Tutup Akun Pendapatan — {periode.nama}',
                        lines_data=lines_pendapatan,
                        sumber='closing',
                        sumber_ref=f'CLOSE-1-{periode.nama}',
                        user=request.user,
                        auto_post=True,
                        periode=periode,
                        allow_closed_period=True,
                    )

                # ═══ Jurnal 2: Tutup Akun HPP & Beban ═══
                total_hpp_beban = total_hpp + total_beban
                if total_hpp_beban > 0:
                    lines_hpp_beban = []
                    
                    # Debit Ikhtisar Laba/Rugi
                    lines_hpp_beban.append({
                        'akun': akun_ikhtisar,
                        'debit': total_hpp_beban,
                        'kredit': Decimal('0'),
                        'keterangan': f'Transfer HPP & Beban ke Ikhtisar'
                    })
                    
                    # Kredit untuk tutup akun HPP
                    for item in data.get('hpp', []):
                        if item['saldo'] > 0:
                            lines_hpp_beban.append({
                                'akun': item['akun'],
                                'debit': Decimal('0'),
                                'kredit': item['saldo'],  # Kredit untuk tutup akun HPP (saldo normal debit)
                                'keterangan': f'Closing entry {periode.nama}'
                            })
                    
                    # Kredit untuk tutup akun Beban
                    for item in data.get('beban', []):
                        if item['saldo'] > 0:
                            lines_hpp_beban.append({
                                'akun': item['akun'],
                                'debit': Decimal('0'),
                                'kredit': item['saldo'],  # Kredit untuk tutup akun Beban (saldo normal debit)
                                'keterangan': f'Closing entry {periode.nama}'
                            })
                    
                    create_jurnal(
                        tanggal=periode.tanggal_akhir,
                        deskripsi=f'Closing Entry (2/3) — Tutup Akun HPP & Beban — {periode.nama}',
                        lines_data=lines_hpp_beban,
                        sumber='closing',
                        sumber_ref=f'CLOSE-2-{periode.nama}',
                        user=request.user,
                        auto_post=True,
                        periode=periode,
                        allow_closed_period=True,
                    )

                # ═══ Jurnal 3: Transfer Ikhtisar ke Laba Ditahan ═══
                if laba_bersih != 0:
                    if laba_bersih > 0:
                        # Laba → Debit Ikhtisar, Kredit Laba Ditahan
                        lines_transfer = [
                            {
                                'akun': akun_ikhtisar,
                                'debit': abs(laba_bersih),
                                'kredit': Decimal('0'),
                                'keterangan': f'Transfer laba bersih ke Laba Ditahan'
                            },
                            {
                                'akun': akun_laba_ditahan,
                                'debit': Decimal('0'),
                                'kredit': abs(laba_bersih),
                                'keterangan': f'Laba bersih periode {periode.nama}'
                            }
                        ]
                    else:
                        # Rugi → Debit Laba Ditahan, Kredit Ikhtisar
                        lines_transfer = [
                            {
                                'akun': akun_laba_ditahan,
                                'debit': abs(laba_bersih),
                                'kredit': Decimal('0'),
                                'keterangan': f'Rugi bersih periode {periode.nama}'
                            },
                            {
                                'akun': akun_ikhtisar,
                                'debit': Decimal('0'),
                                'kredit': abs(laba_bersih),
                                'keterangan': f'Transfer rugi bersih dari Ikhtisar'
                            }
                        ]
                    
                    create_jurnal(
                        tanggal=periode.tanggal_akhir,
                        deskripsi=f'Closing Entry (3/3) — Transfer Ikhtisar ke Laba Ditahan — {periode.nama}',
                        lines_data=lines_transfer,
                        sumber='closing',
                        sumber_ref=f'CLOSE-3-{periode.nama}',
                        user=request.user,
                        auto_post=True,
                        periode=periode,
                        allow_closed_period=True,
                    )

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Gagal membuat closing entry untuk {periode.nama}: {e}')
            periode.is_tutup = False
            periode.is_aktif = True
            periode.save(update_fields=['is_tutup', 'is_aktif'])
            return JsonResponse({
                'success': False,
                'message': f'Periode gagal ditutup karena closing entry gagal dibuat: {e}'
            }, status=400)

        return JsonResponse({
            'success': True,
            'message': f'Periode {periode.nama} berhasil ditutup. Jurnal pada periode ini tidak dapat diubah.'
        })


# ╔══════════════════════════════════════════════════════════════╗
# ║          LAPORAN KEUANGAN (Financial Statements)               ║
# ╚══════════════════════════════════════════════════════════════╝

from apps.akuntansi.services import get_neraca, get_laba_rugi, get_all_saldo_akun
from datetime import date, timedelta
from decimal import Decimal
import json


class NeracaView(ReadPermissionMixin, TemplateView):
    """Laporan Neraca (Balance Sheet). URL: /akuntansi/neraca/"""
    template_name = 'akuntansi/laporan/neraca.html'
    permission_module = 'laporan_keuangan'
    permission_sub_module = 'neraca'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        
        today = date.today()
        start_str = self.request.GET.get('start', '')
        end_str = self.request.GET.get('end', '')
        cabang_id = self.request.GET.get('cabang', '')

        tanggal_mulai = date(today.year, today.month, 1)
        tanggal_akhir = today
        if start_str:
            try:
                tanggal_mulai = date.fromisoformat(start_str)
            except ValueError:
                pass
        if end_str:
            try:
                tanggal_akhir = date.fromisoformat(end_str)
            except ValueError:
                pass

        cabang = None
        if cabang_id:
            from apps.produk.models import Gudang
            try:
                cabang = Gudang.objects.get(pk=cabang_id)
            except Exception:
                pass

        neraca = get_neraca(tanggal_akhir, cabang=cabang)
        context.update(neraca)
        context['tanggal'] = tanggal_akhir
        context['selected_start'] = tanggal_mulai.isoformat()
        context['selected_end'] = tanggal_akhir.isoformat()
        context['selected_cabang'] = cabang_id

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)

        # Chart data
        context['chart_labels'] = json.dumps(['Aset Lancar', 'Aset Tetap', 'Kewajiban', 'Modal', 'Laba Bersih'])
        context['chart_data'] = json.dumps([
            float(neraca['total_aset_lancar']),
            float(neraca['total_aset_tetap']),
            float(neraca['total_kewajiban']),
            float(neraca['total_modal']),
            float(neraca['laba_bersih']),
        ])

        return context


class LabaRugiView(ReadPermissionMixin, TemplateView):
    """Laporan Laba Rugi (Income Statement). URL: /akuntansi/laba-rugi/"""
    template_name = 'akuntansi/laporan/laba_rugi.html'
    permission_module = 'laporan_keuangan'
    permission_sub_module = 'laba_rugi'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = date.today()
        start_str = self.request.GET.get('start', '')
        end_str = self.request.GET.get('end', '')
        cabang_id = self.request.GET.get('cabang', '')

        tanggal_mulai = date(today.year, today.month, 1)
        tanggal_akhir = today
        if start_str:
            try:
                tanggal_mulai = date.fromisoformat(start_str)
            except ValueError:
                pass
        if end_str:
            try:
                tanggal_akhir = date.fromisoformat(end_str)
            except ValueError:
                pass

        cabang = None
        if cabang_id:
            from apps.produk.models import Gudang
            try:
                cabang = Gudang.objects.get(pk=cabang_id)
            except Exception:
                pass

        data = get_laba_rugi(tanggal_mulai, tanggal_akhir, cabang=cabang)
        context.update(data)
        context['tanggal_mulai'] = tanggal_mulai
        context['tanggal_akhir'] = tanggal_akhir
        context['selected_start'] = tanggal_mulai.isoformat()
        context['selected_end'] = tanggal_akhir.isoformat()
        context['selected_cabang'] = cabang_id

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)

        # Margin
        if data['total_pendapatan'] > 0:
            context['margin_kotor'] = round(float(data['laba_kotor'] / data['total_pendapatan'] * 100), 1)
            context['margin_bersih'] = round(float(data['laba_bersih'] / data['total_pendapatan'] * 100), 1)
        else:
            context['margin_kotor'] = 0
            context['margin_bersih'] = 0

        # Monthly trend (6 bulan terakhir)
        trend_labels = []
        trend_pendapatan = []
        trend_laba = []
        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            first_day = date(y, m, 1)
            if m == 12:
                last_day = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(y, m + 1, 1) - timedelta(days=1)
            month_data = get_laba_rugi(first_day, last_day, cabang=cabang)
            nama_bulan = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
            trend_labels.append(f"{nama_bulan[m-1]} {y}")
            trend_pendapatan.append(float(month_data['total_pendapatan']))
            trend_laba.append(float(month_data['laba_bersih']))

        context['trend_labels'] = json.dumps(trend_labels)
        context['trend_pendapatan'] = json.dumps(trend_pendapatan)
        context['trend_laba'] = json.dumps(trend_laba)

        return context


class ArusKasView(ReadPermissionMixin, TemplateView):
    """Laporan Arus Kas (Cash Flow Statement). URL: /akuntansi/arus-kas/"""
    template_name = 'akuntansi/laporan/arus_kas.html'
    permission_module = 'laporan_keuangan'
    permission_sub_module = 'arus_kas'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = date.today()
        start_str = self.request.GET.get('start', '')
        end_str = self.request.GET.get('end', '')
        cabang_id = self.request.GET.get('cabang', '')

        tanggal_mulai = date(today.year, today.month, 1)
        tanggal_akhir = today
        if start_str:
            try:
                tanggal_mulai = date.fromisoformat(start_str)
            except ValueError:
                pass
        if end_str:
            try:
                tanggal_akhir = date.fromisoformat(end_str)
            except ValueError:
                pass

        cabang = None
        if cabang_id:
            from apps.produk.models import Gudang
            try:
                cabang = Gudang.objects.get(pk=cabang_id)
            except Exception:
                pass

        # Build cash flow from journal lines
        filters = Q(jurnal__is_posted=True,
                     jurnal__tanggal__gte=tanggal_mulai,
                     jurnal__tanggal__lte=tanggal_akhir)
        if cabang:
            filters &= Q(jurnal__cabang=cabang)

        # Ambil semua akun Kas/Bank secara dinamis (bukan hardcoded)
        # Mencakup akun aset lancar dengan kode berawalan 1-1 (Kas, Bank BCA, Bank Mandiri, dll)
        kas_akun_kodes = list(
            Akun.objects.filter(
                is_active=True,
                tipe='aset',
                sub_tipe='aset_lancar',
                kode__startswith='1-1',
            ).values_list('kode', flat=True)
        )

        # Kas masuk & keluar dari jurnal lines pada akun kas
        kas_lines = JurnalLine.objects.filter(
            filters, akun__kode__in=kas_akun_kodes
        ).select_related('jurnal', 'akun')

        total_kas_masuk = kas_lines.aggregate(t=Sum('debit'))['t'] or Decimal('0')
        total_kas_keluar = kas_lines.aggregate(t=Sum('kredit'))['t'] or Decimal('0')
        arus_kas_bersih = total_kas_masuk - total_kas_keluar

        # Categorize by sumber
        operasional_masuk = Decimal('0')
        operasional_keluar = Decimal('0')
        investasi_masuk = Decimal('0')
        investasi_keluar = Decimal('0')
        pendanaan_masuk = Decimal('0')
        pendanaan_keluar = Decimal('0')

        sumber_investasi = ['aset']
        sumber_pendanaan = ['modal', 'prive']

        for line in kas_lines:
            sumber = line.jurnal.sumber or 'manual'
            if sumber in sumber_investasi:
                investasi_masuk += line.debit
                investasi_keluar += line.kredit
            elif sumber in sumber_pendanaan:
                pendanaan_masuk += line.debit
                pendanaan_keluar += line.kredit
            else:
                operasional_masuk += line.debit
                operasional_keluar += line.kredit

        context['total_kas_masuk'] = total_kas_masuk
        context['total_kas_keluar'] = total_kas_keluar
        context['arus_kas_bersih'] = arus_kas_bersih

        context['operasional_masuk'] = operasional_masuk
        context['operasional_keluar'] = operasional_keluar
        context['operasional_net'] = operasional_masuk - operasional_keluar
        context['investasi_masuk'] = investasi_masuk
        context['investasi_keluar'] = investasi_keluar
        context['investasi_net'] = investasi_masuk - investasi_keluar
        context['pendanaan_masuk'] = pendanaan_masuk
        context['pendanaan_keluar'] = pendanaan_keluar
        context['pendanaan_net'] = pendanaan_masuk - pendanaan_keluar

        # Saldo kas per akun
        saldo_kas = []
        for kode in kas_akun_kodes:
            akun = Akun.objects.filter(kode=kode, is_active=True).first()
            if akun:
                saldo = get_saldo_akun(akun, tanggal_akhir=tanggal_akhir, cabang=cabang)
                saldo_kas.append({'akun': akun, 'saldo': saldo})
        context['saldo_kas'] = saldo_kas
        context['total_saldo_kas'] = sum(s['saldo'] for s in saldo_kas)

        context['tanggal_mulai'] = tanggal_mulai
        context['tanggal_akhir'] = tanggal_akhir
        context['selected_start'] = tanggal_mulai.isoformat()
        context['selected_end'] = tanggal_akhir.isoformat()
        context['selected_cabang'] = cabang_id

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)

        # Chart
        context['chart_labels'] = json.dumps(['Operasional', 'Investasi', 'Pendanaan'])
        context['chart_masuk'] = json.dumps([float(operasional_masuk), float(investasi_masuk), float(pendanaan_masuk)])
        context['chart_keluar'] = json.dumps([float(operasional_keluar), float(investasi_keluar), float(pendanaan_keluar)])

        return context


class TrialBalanceView(ReadPermissionMixin, TemplateView):
    """Neraca Saldo (Trial Balance). URL: /akuntansi/trial-balance/"""
    template_name = 'akuntansi/laporan/trial_balance.html'
    permission_module = 'laporan_keuangan'
    permission_sub_module = 'trial_balance'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        tanggal_str = self.request.GET.get('tanggal', '')
        cabang_id = self.request.GET.get('cabang', '')

        tanggal = date.today()
        if tanggal_str:
            try:
                tanggal = date.fromisoformat(tanggal_str)
            except ValueError:
                pass

        cabang = None
        if cabang_id:
            from apps.produk.models import Gudang
            try:
                cabang = Gudang.objects.get(pk=cabang_id)
            except Exception:
                pass

        # Get all account balances
        all_saldo = get_all_saldo_akun(tanggal_akhir=tanggal, cabang=cabang)

        # Build trial balance rows
        rows = []
        total_debit = Decimal('0')
        total_kredit = Decimal('0')
        for item in all_saldo:
            akun = item['akun']
            saldo = item['saldo']
            saldo_d = saldo if akun.saldo_normal == 'debit' else (abs(saldo) if saldo < 0 else Decimal('0'))
            saldo_k = saldo if akun.saldo_normal == 'kredit' else (abs(saldo) if saldo < 0 else Decimal('0'))
            if akun.saldo_normal == 'debit':
                saldo_d = saldo if saldo >= 0 else Decimal('0')
                saldo_k = abs(saldo) if saldo < 0 else Decimal('0')
            else:
                saldo_k = saldo if saldo >= 0 else Decimal('0')
                saldo_d = abs(saldo) if saldo < 0 else Decimal('0')
            total_debit += saldo_d
            total_kredit += saldo_k
            rows.append({
                'akun': akun,
                'saldo': saldo,
                'saldo_debit': saldo_d,
                'saldo_kredit': saldo_k,
            })

        context['rows'] = rows
        context['total_debit'] = total_debit
        context['total_kredit'] = total_kredit
        context['is_balanced'] = total_debit == total_kredit
        context['selisih'] = abs(total_debit - total_kredit)

        context['tanggal'] = tanggal
        context['selected_tanggal'] = tanggal.isoformat()
        context['selected_cabang'] = cabang_id

        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)

        # Group totals for chart
        tipe_totals = {}
        for row in rows:
            tipe = row['akun'].get_tipe_display()
            if tipe not in tipe_totals:
                tipe_totals[tipe] = Decimal('0')
            tipe_totals[tipe] += abs(row['saldo'])

        context['chart_labels'] = json.dumps(list(tipe_totals.keys()))
        context['chart_data'] = json.dumps([float(v) for v in tipe_totals.values()])

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║        PANDUAN AKUNTANSI (Accounting Guide & Reference)        ║
# ╚══════════════════════════════════════════════════════════════╝

class PanduanAkuntansiView(ReadPermissionMixin, TemplateView):
    """Halaman Panduan Akuntansi — penjelasan alur, rumus, dan referensi. URL: /akuntansi/panduan/"""
    template_name = 'akuntansi/panduan/panduan_akuntansi.html'
    permission_module = 'akuntansi'
    permission_sub_module = 'panduan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Statistik Sistem
        context['total_akun'] = Akun.objects.filter(is_active=True).count()
        context['total_jurnal'] = JurnalEntry.objects.count()
        context['total_jurnal_posted'] = JurnalEntry.objects.filter(is_posted=True).count()
        context['total_jurnal_draft'] = JurnalEntry.objects.filter(is_posted=False).count()
        context['total_lines'] = JurnalLine.objects.count()

        # Per tipe akun
        tipe_counts = Akun.objects.filter(is_active=True).values('tipe').annotate(
            jumlah=Count('id')
        ).order_by('tipe')
        context['tipe_counts'] = list(tipe_counts)

        # Chart: distribusi akun per tipe
        tipe_labels = []
        tipe_data = []
        for t in tipe_counts:
            tipe_labels.append(dict(Akun.TIPE_CHOICES).get(t['tipe'], t['tipe']))
            tipe_data.append(t['jumlah'])
        context['tipe_chart_labels'] = json.dumps(tipe_labels)
        context['tipe_chart_data'] = json.dumps(tipe_data)

        # Jurnal per sumber
        sumber_counts = JurnalEntry.objects.values('sumber').annotate(
            jumlah=Count('id')
        ).order_by('-jumlah')
        context['sumber_counts'] = list(sumber_counts)
        sumber_labels = [s['sumber'] or 'manual' for s in sumber_counts]
        sumber_data = [s['jumlah'] for s in sumber_counts]
        context['sumber_chart_labels'] = json.dumps(sumber_labels)
        context['sumber_chart_data'] = json.dumps(sumber_data)

        # Periode aktif
        context['periode_aktif'] = PeriodeAkuntansi.objects.filter(is_aktif=True).first()
        context['total_periode'] = PeriodeAkuntansi.objects.count()
        context['total_periode_tutup'] = PeriodeAkuntansi.objects.filter(is_tutup=True).count()

        # Piutang & Hutang stats
        try:
            from apps.piutang.models import Piutang
            from apps.hutang.models import Hutang
            context['total_piutang'] = Piutang.objects.exclude(status='lunas').count()
            context['total_hutang'] = Hutang.objects.exclude(status='lunas').count()
            context['total_piutang_rupiah'] = Piutang.objects.exclude(
                status='lunas').aggregate(t=Sum('jumlah_total'))['t'] or 0
            context['total_hutang_rupiah'] = Hutang.objects.exclude(
                status='lunas').aggregate(t=Sum('jumlah_total'))['t'] or 0
        except Exception:
            context['total_piutang'] = 0
            context['total_hutang'] = 0
            context['total_piutang_rupiah'] = 0
            context['total_hutang_rupiah'] = 0

        # Aset stats
        try:
            from apps.aset.models import AsetTetap
            context['total_aset_aktif'] = AsetTetap.objects.filter(status='aktif').count()
            context['total_nilai_aset'] = AsetTetap.objects.filter(
                status='aktif').aggregate(t=Sum('harga_perolehan'))['t'] or 0
        except Exception:
            context['total_aset_aktif'] = 0
            context['total_nilai_aset'] = 0

        # Kas & Bank stats
        try:
            from apps.kas_bank.models import KasBankAccount, KasBankTransaction
            kas_accounts = KasBankAccount.objects.filter(aktif=True)
            context['total_kas_bank_accounts'] = kas_accounts.count()
            context['total_mutasi_posted'] = KasBankTransaction.objects.filter(status='posted').count()
        except Exception:
            context['total_kas_bank_accounts'] = 0
            context['total_mutasi_posted'] = 0

        # CoA structure reference
        context['coa_structure'] = [
            {'kode': '1-xxxx', 'tipe': 'Aset (Harta)', 'saldo_normal': 'Debit',
             'contoh': 'Kas, Bank, Piutang, PPN Masukan, Persediaan, Aset Tetap, Akumulasi Penyusutan', 'warna': 'primary'},
            {'kode': '2-xxxx', 'tipe': 'Kewajiban (Utang)', 'saldo_normal': 'Kredit',
             'contoh': 'Hutang Usaha, PPN Keluaran, Hutang Gaji, Hutang PPh21, Hutang BPJS', 'warna': 'warning'},
            {'kode': '3-xxxx', 'tipe': 'Modal (Ekuitas)', 'saldo_normal': 'Kredit',
             'contoh': 'Modal Pemilik, Laba Ditahan, Ikhtisar Laba/Rugi, Prive', 'warna': 'success'},
            {'kode': '4-xxxx', 'tipe': 'Pendapatan', 'saldo_normal': 'Kredit',
             'contoh': 'Pendapatan Penjualan, Pendapatan Jasa, Pendapatan Lainnya', 'warna': 'info'},
            {'kode': '5-xxxx', 'tipe': 'HPP (Harga Pokok)', 'saldo_normal': 'Debit',
             'contoh': 'HPP Barang Dagang', 'warna': 'danger'},
            {'kode': '6-xxxx', 'tipe': 'Beban Operasional', 'saldo_normal': 'Debit',
             'contoh': 'Beban Gaji, Beban Sewa, Beban Listrik, Beban Penyusutan, Beban Operasional Lainnya', 'warna': 'secondary'},
        ]

        # Rumus keuangan (diperluas)
        context['formulas'] = [
            {'nama': 'Persamaan Dasar Akuntansi', 'rumus': 'Aset = Kewajiban + Modal',
             'keterangan': 'Fondasi seluruh sistem double-entry. Setiap transaksi harus menjaga keseimbangan ini.'},
            {'nama': 'Laba Kotor (Gross Profit)', 'rumus': 'Laba Kotor = Pendapatan Bersih - HPP',
             'keterangan': 'Keuntungan sebelum beban operasional. Pendapatan bersih sudah dikurangi diskon dan tidak termasuk PPN.'},
            {'nama': 'Laba Bersih (Net Income)', 'rumus': 'Laba Bersih = Laba Kotor - Total Beban',
             'keterangan': 'Keuntungan akhir setelah semua beban dikurangi.'},
            {'nama': 'Margin Kotor (%)', 'rumus': 'Margin Kotor = (Laba Kotor / Pendapatan Bersih) x 100%',
             'keterangan': 'Persentase keuntungan kotor dari pendapatan bersih tanpa PPN.'},
            {'nama': 'Margin Bersih (%)', 'rumus': 'Margin Bersih = (Laba Bersih / Pendapatan Bersih) x 100%',
             'keterangan': 'Persentase keuntungan bersih dari pendapatan bersih tanpa PPN.'},
            {'nama': 'Saldo Kas/Bank', 'rumus': 'Saldo = Saldo Awal + Total Masuk - Total Keluar',
             'keterangan': 'Saldo treasury riil dihitung dari mutasi posted pada akun Kas/Bank.'},
            {'nama': 'Penyusutan Garis Lurus', 'rumus': 'Penyusutan/bln = (Harga Perolehan - Nilai Residu) / Umur Ekonomis',
             'keterangan': 'Metode penyusutan yang membagi biaya secara merata sepanjang umur aset.'},
            {'nama': 'Penyusutan Saldo Menurun', 'rumus': 'Penyusutan = (2 / Umur Ekonomis) × Nilai Buku',
             'keterangan': 'Metode penyusutan dengan beban lebih besar di awal umur aset (double-declining).'},
            {'nama': 'Nilai Buku Aset', 'rumus': 'Nilai Buku = Harga Perolehan - Akumulasi Penyusutan',
             'keterangan': 'Nilai tercatat aset setelah dikurangi total penyusutan.'},
            {'nama': 'PPN (Pajak Pertambahan Nilai)', 'rumus': 'PPN = DPP x Tarif (11%) | Setor = PPN Keluaran - PPN Masukan',
             'keterangan': 'PPN dipisahkan dari pendapatan/beban. PPN Keluaran menjadi kewajiban pajak; PPN Masukan menjadi aset pajak.'},
            {'nama': 'Arus Kas Bersih', 'rumus': 'Arus Kas = Kas Masuk - Kas Keluar',
             'keterangan': 'Selisih total penerimaan dan pengeluaran kas pada suatu periode.'},
            {'nama': 'HPP Penjualan', 'rumus': 'HPP = sum(Harga Beli x Qty Terjual)',
             'keterangan': 'Otomatis dihitung saat POS paid / SO completed. Mengurangi akun Persediaan (1-3000).'},
        ]

        # Alur integrasi modul (sesuai mekanisme aktual sistem)
        context['integration_flows'] = [
            {'sumber': 'POS (Tunai/Bank)', 'sumber_icon': 'ri-store-2-line',
             'jurnal': 'D: Kas/Bank  D: Diskon Penjualan  K: Pendapatan  K: PPN Keluaran | D: HPP  K: Persediaan',
             'trigger': 'Saat status = paid (signal post_save)'},
            {'sumber': 'Sales Order (Kredit/Tempo)', 'sumber_icon': 'ri-shopping-cart-2-line',
             'jurnal': 'D: Piutang Usaha  D: Diskon Penjualan  K: Pendapatan  K: PPN Keluaran | D: HPP  K: Persediaan',
             'trigger': 'Saat status = completed (signal post_save)'},
            {'sumber': 'Sales Order (Tunai/Bank)', 'sumber_icon': 'ri-shopping-cart-2-line',
             'jurnal': 'D: Kas/Bank  D: Diskon Penjualan  K: Pendapatan  K: PPN Keluaran | D: HPP  K: Persediaan',
             'trigger': 'Saat status = completed (signal post_save)'},
            {'sumber': 'Pelunasan Piutang', 'sumber_icon': 'ri-money-dollar-circle-line',
             'jurnal': 'D: Kas/Bank  K: Piutang Usaha',
             'trigger': 'Saat pembayaran disimpan (PembayaranPiutang.save)'},
            {'sumber': 'Purchase Order (Kredit/Tempo)', 'sumber_icon': 'ri-truck-line',
             'jurnal': 'D: Persediaan/DPP  D: PPN Masukan  K: Hutang Usaha',
             'trigger': 'Saat status = approved/received (signal post_save)'},
            {'sumber': 'Purchase Order (Tunai/Bank)', 'sumber_icon': 'ri-truck-line',
             'jurnal': 'D: Persediaan/DPP  D: PPN Masukan  K: Kas/Bank',
             'trigger': 'Saat status = approved/received (signal post_save)'},
            {'sumber': 'Pelunasan Hutang', 'sumber_icon': 'ri-hand-coin-line',
             'jurnal': 'D: Hutang Usaha  K: Kas/Bank',
             'trigger': 'Saat pembayaran disimpan (PembayaranHutang.save)'},
            {'sumber': 'Biaya Operasional', 'sumber_icon': 'ri-bill-line',
             'jurnal': 'D: Beban Operasional  K: Kas/Bank',
             'trigger': 'Saat biaya di-approve (TransaksiBiayaApproveView)'},
            {'sumber': 'Penggajian (Payroll)', 'sumber_icon': 'ri-user-star-line',
             'jurnal': 'D: Beban Gaji  K: Kas/Bank + Hutang PPh21 + Hutang BPJS',
             'trigger': 'Saat status penggajian = dibayar'},
            {'sumber': 'Adjustment Stok (Masuk)', 'sumber_icon': 'ri-add-box-line',
             'jurnal': 'D: Persediaan  K: Pendapatan Lainnya',
             'trigger': 'Saat adjustment stok dibuat'},
            {'sumber': 'Adjustment Stok (Keluar)', 'sumber_icon': 'ri-subtract-line',
             'jurnal': 'D: Beban Kerusakan  K: Persediaan',
             'trigger': 'Saat adjustment stok dibuat'},
            {'sumber': 'Pembelian Aset Tetap', 'sumber_icon': 'ri-building-2-line',
             'jurnal': 'D: Aset Tetap  K: Kas/Bank',
             'trigger': 'Saat aset baru didaftarkan'},
            {'sumber': 'Penyusutan Aset', 'sumber_icon': 'ri-time-line',
             'jurnal': 'D: Beban Penyusutan  K: Akumulasi Penyusutan',
             'trigger': 'Saat Susutkan / Susutkan Massal'},
            {'sumber': 'Disposal Aset', 'sumber_icon': 'ri-delete-bin-line',
             'jurnal': 'D: Kas + Akumulasi ± Laba/Rugi  K: Aset Tetap',
             'trigger': 'Saat disposal diproses'},
            {'sumber': 'Transfer Kas/Bank', 'sumber_icon': 'ri-arrow-left-right-line',
             'jurnal': 'D: Kas/Bank Tujuan  K: Kas/Bank Asal (+ Biaya Admin)',
             'trigger': 'Saat transfer dibuat (status posted)'},
            {'sumber': 'Mutasi Manual Kas/Bank', 'sumber_icon': 'ri-exchange-dollar-line',
             'jurnal': 'D/K: Kas/Bank  K/D: Akun Lawan',
             'trigger': 'Saat mutasi manual posted (akun lawan wajib)'},
            {'sumber': 'Settlement PPN', 'sumber_icon': 'ri-bank-line',
             'jurnal': 'D: PPN Keluaran  K: PPN Masukan  K: Kas/Bank',
             'trigger': 'Saat Setor PPN diproses'},
            {'sumber': 'Tutup Buku (Closing)', 'sumber_icon': 'ri-lock-line',
             'jurnal': '3 jurnal: Pendapatan → Ikhtisar → Laba Ditahan',
             'trigger': 'Saat periode ditutup'},
        ]

        # Alur Kas & Bank (section baru)
        context['kas_bank_info'] = {
            'perbedaan': [
                {'komponen': 'Metode Pembayaran', 'arti': 'Cara bayar (Tunai, Transfer, QRIS, E-Wallet, Tempo)',
                 'contoh': 'QRIS, Transfer BCA, Cash'},
                {'komponen': 'Akun Kas/Bank', 'arti': 'Akun treasury riil tempat uang dicatat',
                 'contoh': 'Kas Utama, Bank BCA, QRIS Clearing'},
                {'komponen': 'Akun CoA', 'arti': 'Akun di Chart of Accounts untuk jurnal',
                 'contoh': '1-1000 Kas, 1-1100 Bank BCA'},
            ],
            'proteksi': [
                'Mutasi yang sudah punya jurnal tidak bisa diedit/dihapus',
                'Transfer yang sudah punya jurnal tidak bisa diedit/dihapus',
                'Mutasi otomatis dari modul lain bersifat idempoten (get_or_create)',
                'Saldo realtime: Saldo Awal + Total Masuk (posted) - Total Keluar (posted)',
            ],
        }

        # Info Periode & Tutup Buku (section baru)
        context['periode_info'] = {
            'alur': [
                'Buat Periode Akuntansi (tanggal mulai & akhir)',
                'Aktifkan periode → jurnal baru masuk ke periode ini',
                'Tutup periode → sistem buat 3 Closing Entry otomatis',
                'Jurnal 1: Tutup Pendapatan → Ikhtisar Laba/Rugi (3-9000)',
                'Jurnal 2: Tutup HPP & Beban → Ikhtisar Laba/Rugi',
                'Jurnal 3: Transfer Ikhtisar → Laba Ditahan (3-2000)',
            ],
            'validasi': [
                'Jurnal baru tidak bisa masuk ke periode yang sudah ditutup',
                'Periode yang sudah ditutup tidak bisa diedit',
                'Koreksi harus menggunakan Jurnal Pembalik di periode baru',
                'Jurnal posted tidak bisa dihapus — hanya bisa dibalik (reverse)',
            ],
        }

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║     REKONSILIASI KEUANGAN (Financial Reconciliation)          ║
# ╚══════════════════════════════════════════════════════════════╝

class RekonsiliasiKeuanganView(ReadPermissionMixin, TemplateView):
    """
    Halaman Rekonsiliasi Keuangan — membandingkan data operasional vs jurnal akuntansi.
    Menampilkan selisih dan penyebabnya secara detail.
    URL: /akuntansi/rekonsiliasi-keuangan/
    """
    template_name = 'akuntansi/laporan/rekonsiliasi_keuangan.html'
    permission_module = 'rekonsiliasi_keuangan'
    # Tidak ada sub-modul — pola identik dengan POS, Activity Log, Dashboard
    # Permission dicek hanya di level modul (can_view dst).

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        today = date.today()
        start_str = self.request.GET.get('start', '')
        end_str = self.request.GET.get('end', '')
        cabang_id = self.request.GET.get('cabang', '')

        tanggal_mulai = date(today.year, today.month, 1)
        tanggal_akhir = today
        if start_str:
            try:
                tanggal_mulai = date.fromisoformat(start_str)
            except ValueError:
                pass
        if end_str:
            try:
                tanggal_akhir = date.fromisoformat(end_str)
            except ValueError:
                pass

        cabang = None
        if cabang_id:
            from apps.produk.models import Gudang
            try:
                cabang = Gudang.objects.get(pk=cabang_id)
            except Exception:
                pass

        # ═══════════════════════════════════════════════════════
        # DATA OPERASIONAL (dari tabel transaksi langsung)
        # ═══════════════════════════════════════════════════════
        from apps.penjualan.models import SalesOrder
        from apps.pos.models import POSTransaction
        from apps.pembelian.models import PurchaseOrder
        from apps.biaya.models import TransaksiBiaya
        from apps.core.finance_metrics import aggregate_purchase_amounts, aggregate_sales_amounts

        # PENTING: Filter SO hanya 'completed' agar konsisten dengan trigger jurnal.
        # Jurnal SO hanya dibuat saat status = completed (lihat penjualan/signals.py).
        # Jika menggunakan confirmed/delivered, akan selalu ada selisih karena
        # transaksi tersebut belum ter-jurnal di akuntansi.
        so_filter = {'status': 'completed',
                     'tanggal__date__gte': tanggal_mulai, 'tanggal__date__lte': tanggal_akhir}
        pos_filter = {'status': 'paid',
                      'tanggal__date__gte': tanggal_mulai, 'tanggal__date__lte': tanggal_akhir}
        # PO: jurnal dibuat saat status = approved/received (lihat pembelian/signals.py)
        po_filter = {'status__in': ['approved', 'received'],
                     'tanggal__date__gte': tanggal_mulai, 'tanggal__date__lte': tanggal_akhir}
        biaya_filter = {'status': 'approved',
                        'tanggal__gte': tanggal_mulai, 'tanggal__lte': tanggal_akhir}

        if cabang:
            so_filter['gudang'] = cabang
            pos_filter['gudang'] = cabang
            po_filter['gudang'] = cabang
            biaya_filter['cabang'] = cabang

        ops_pemasukan_so = aggregate_sales_amounts(SalesOrder.objects.filter(**so_filter))['net']
        ops_pemasukan_pos = aggregate_sales_amounts(POSTransaction.objects.filter(**pos_filter))['net']

        ops_total_pemasukan = ops_pemasukan_so + ops_pemasukan_pos

        ops_pengeluaran_po = aggregate_purchase_amounts(PurchaseOrder.objects.filter(**po_filter))['subtotal']
        ops_pengeluaran_biaya = TransaksiBiaya.objects.filter(**biaya_filter).aggregate(
            total=Sum('jumlah'))['total'] or Decimal('0')
        ops_total_pengeluaran = ops_pengeluaran_po + ops_pengeluaran_biaya

        ops_laba = ops_total_pemasukan - ops_total_pengeluaran

        # ═══════════════════════════════════════════════════════
        # DATA AKUNTANSI (dari JurnalLine posted)
        # ═══════════════════════════════════════════════════════
        data_akuntansi = get_laba_rugi(tanggal_mulai, tanggal_akhir, cabang=cabang)
        akun_pendapatan = data_akuntansi['total_pendapatan']
        akun_hpp = data_akuntansi['total_hpp']
        akun_beban = data_akuntansi['total_beban']
        akun_laba_bersih = data_akuntansi['laba_bersih']

        # ═══════════════════════════════════════════════════════
        # SELISIH & ANALISIS PENYEBAB
        # ═══════════════════════════════════════════════════════
        selisih_pemasukan = akun_pendapatan - ops_total_pemasukan
        selisih_pengeluaran = (akun_hpp + akun_beban) - ops_total_pengeluaran
        selisih_laba = akun_laba_bersih - ops_laba

        # Detail penyebab selisih — jurnal yang BUKAN dari transaksi operasional utama
        sumber_operasional = ['pos', 'so', 'po', 'biaya']
        jurnal_non_ops = JurnalEntry.objects.filter(
            is_posted=True,
            tanggal__gte=tanggal_mulai,
            tanggal__lte=tanggal_akhir,
        ).exclude(sumber__in=sumber_operasional)

        if cabang:
            jurnal_non_ops = jurnal_non_ops.filter(cabang=cabang)

        penyebab_selisih = []
        sumber_groups = jurnal_non_ops.values('sumber').annotate(
            total_debit=Sum('lines__debit'),
            total_kredit=Sum('lines__kredit'),
            jumlah_jurnal=Count('id', distinct=True),
        ).order_by('-total_debit')

        sumber_labels = {
            'manual': 'Jurnal Manual / Adjusting Entry',
            'payroll': 'Penggajian (Payroll)',
            'aset': 'Pembelian / Penyusutan Aset',
            'kas_bank': 'Mutasi Kas/Bank Manual',
            'pembalik': 'Jurnal Pembalik',
            'closing': 'Closing Entry (Tutup Buku)',
            'piutang': 'Pelunasan Piutang',
            'hutang': 'Pelunasan Hutang',
            'inventory': 'Adjustment Stok',
            'pajak': 'Settlement PPN',
        }

        for group in sumber_groups:
            sumber = group['sumber'] or 'manual'
            total_d = group['total_debit'] or Decimal('0')
            total_k = group['total_kredit'] or Decimal('0')
            penyebab_selisih.append({
                'sumber': sumber,
                'label': sumber_labels.get(sumber, sumber.replace('_', ' ').title()),
                'total_debit': total_d,
                'total_kredit': total_k,
                'jumlah_jurnal': group['jumlah_jurnal'],
            })

        # Detail jurnal non-operasional
        detail_jurnal_non_ops = jurnal_non_ops.select_related('cabang', 'created_by').order_by('-tanggal')[:50]

        # Chart data
        chart_labels = json.dumps(['Pendapatan Bersih', 'Beban/DPP', 'Laba/Rugi'])
        chart_operasional = json.dumps([
            float(ops_total_pemasukan), float(ops_total_pengeluaran), float(ops_laba)
        ])
        chart_akuntansi = json.dumps([
            float(akun_pendapatan), float(akun_hpp + akun_beban), float(akun_laba_bersih)
        ])

        is_reconciled = (selisih_pemasukan == 0 and selisih_pengeluaran == 0)

        # ═══════════════════════════════════════════════════════
        # TREASURY vs ACCOUNTING (Saldo Kas/Bank)
        # Membandingkan saldo_terhitung (KasBankAccount) dengan
        # saldo Buku Besar akun CoA terkait.
        # ═══════════════════════════════════════════════════════
        from apps.kas_bank.models import KasBankAccount, KasBankTransaction

        treasury_vs_accounting = []
        total_selisih_treasury = Decimal('0')
        for kba in KasBankAccount.objects.filter(aktif=True).select_related('akun').order_by('kode'):
            saldo_treasury = kba.saldo_terhitung
            saldo_accounting = get_saldo_akun(kba.akun)
            selisih = saldo_treasury - saldo_accounting
            total_selisih_treasury += abs(selisih)
            treasury_vs_accounting.append({
                'kode': kba.kode,
                'nama': kba.nama,
                'tipe': kba.get_tipe_display(),
                'akun_coa': f"{kba.akun.kode} - {kba.akun.nama}",
                'saldo_treasury': saldo_treasury,
                'saldo_accounting': saldo_accounting,
                'selisih': selisih,
                'is_match': selisih == 0,
            })

        treasury_all_match = total_selisih_treasury == 0

        # ═══════════════════════════════════════════════════════
        # ORPHAN DETECTION (Mutasi tanpa Jurnal & Jurnal tanpa Mutasi)
        # ═══════════════════════════════════════════════════════
        # Mutasi posted yang tidak punya jurnal (signal gagal)
        orphan_mutasi = KasBankTransaction.objects.filter(
            status='posted',
            jurnal_entry__isnull=True,
        ).select_related('akun_kas_bank').order_by('-tanggal')[:20]
        orphan_mutasi_count = KasBankTransaction.objects.filter(
            status='posted',
            jurnal_entry__isnull=True,
        ).count()

        # Jurnal posted yang menyentuh akun kas/bank tapi tidak ada mutasi terkait
        akun_kas_ids = list(KasBankAccount.objects.filter(aktif=True).values_list('akun_id', flat=True))
        jurnal_with_kas = JurnalEntry.objects.filter(
            is_posted=True,
            lines__akun_id__in=akun_kas_ids,
        ).distinct()
        jurnal_with_mutasi = JurnalEntry.objects.filter(
            is_posted=True,
            kas_bank_mutasi__isnull=False,
        ).distinct()
        orphan_jurnal_qs = jurnal_with_kas.exclude(pk__in=jurnal_with_mutasi.values_list('pk', flat=True))
        orphan_jurnal_count = orphan_jurnal_qs.count()
        orphan_jurnal = orphan_jurnal_qs.select_related('cabang', 'created_by').order_by('-tanggal')[:20]

        # ═══════════════════════════════════════════════════════
        # TRIAL BALANCE CHECK
        # ═══════════════════════════════════════════════════════
        from django.db.models import Sum as DjSum
        tb_totals = JurnalLine.objects.filter(
            jurnal__is_posted=True,
        ).aggregate(
            total_debit=DjSum('debit'),
            total_kredit=DjSum('kredit'),
        )
        tb_total_debit = tb_totals['total_debit'] or Decimal('0')
        tb_total_kredit = tb_totals['total_kredit'] or Decimal('0')
        tb_is_balanced = tb_total_debit == tb_total_kredit
        tb_selisih = tb_total_debit - tb_total_kredit

        # ═══════════════════════════════════════════════════════
        # JURNAL FAILURE LOG (dari Activity Log)
        # Mendeteksi transaksi yang gagal generate jurnal
        # ═══════════════════════════════════════════════════════
        from apps.activity_log.models import UserActivity
        jurnal_failures = UserActivity.objects.filter(
            description__startswith='[JURNAL GAGAL]',
        ).order_by('-timestamp')[:20]
        jurnal_failures_count = UserActivity.objects.filter(
            description__startswith='[JURNAL GAGAL]',
        ).count()

        context.update({
            'tanggal_mulai': tanggal_mulai,
            'tanggal_akhir': tanggal_akhir,
            'selected_start': tanggal_mulai.isoformat(),
            'selected_end': tanggal_akhir.isoformat(),
            'selected_cabang': cabang_id,
            'ops_pemasukan_so': ops_pemasukan_so,
            'ops_pemasukan_pos': ops_pemasukan_pos,
            'ops_total_pemasukan': ops_total_pemasukan,
            'ops_pengeluaran_po': ops_pengeluaran_po,
            'ops_pengeluaran_biaya': ops_pengeluaran_biaya,
            'ops_total_pengeluaran': ops_total_pengeluaran,
            'ops_laba': ops_laba,
            'akun_pendapatan': akun_pendapatan,
            'akun_hpp': akun_hpp,
            'akun_beban': akun_beban,
            'akun_total_pengeluaran': akun_hpp + akun_beban,
            'akun_laba_bersih': akun_laba_bersih,
            'selisih_pemasukan': selisih_pemasukan,
            'selisih_pengeluaran': selisih_pengeluaran,
            'selisih_laba': selisih_laba,
            'is_reconciled': is_reconciled,
            'penyebab_selisih': penyebab_selisih,
            'detail_jurnal_non_ops': detail_jurnal_non_ops,
            'chart_labels': chart_labels,
            'chart_operasional': chart_operasional,
            'chart_akuntansi': chart_akuntansi,
            # Treasury vs Accounting
            'treasury_vs_accounting': treasury_vs_accounting,
            'treasury_all_match': treasury_all_match,
            'total_selisih_treasury': total_selisih_treasury,
            # Orphan Detection
            'orphan_mutasi': orphan_mutasi,
            'orphan_mutasi_count': orphan_mutasi_count,
            'orphan_jurnal': orphan_jurnal,
            'orphan_jurnal_count': orphan_jurnal_count,
            # Trial Balance Check
            'tb_total_debit': tb_total_debit,
            'tb_total_kredit': tb_total_kredit,
            'tb_is_balanced': tb_is_balanced,
            'tb_selisih': tb_selisih,
            # Jurnal Failure Log
            'jurnal_failures': jurnal_failures,
            'jurnal_failures_count': jurnal_failures_count,
        })
        from apps.produk.models import Gudang
        context['cabang_list'] = Gudang.objects.filter(aktif=True)

        return context
