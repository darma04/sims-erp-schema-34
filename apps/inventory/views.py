"""
==========================================================================
INVENTORY VIEWS - View CRUD untuk Gudang, Stok, Transfer, Adjustment
==========================================================================
File ini berisi semua view untuk modul Inventory:

VIEWS CLASS-BASED (CBV):
┌─────────────────────────────────────────────────────────────────────┐
│ GUDANG (Sub-module gudang)                                         │
│   GudangListView     → Daftar semua gudang                        │
│   GudangCreateView   → Form tambah gudang baru                    │
│   GudangUpdateView   → Form edit gudang                           │
│   GudangDeleteView   → Hapus gudang (return JSON)                 │
├─────────────────────────────────────────────────────────────────────┤
│ STOK (Sub-module stok)                                             │
│   StokListView       → Daftar stok per produk per gudang          │
├─────────────────────────────────────────────────────────────────────┤
│ TRANSFER STOK (Sub-module transfer_stok)                           │
│   TransferStokView       → Daftar semua transfer                  │
│   TransferStokCreateView → Form buat transfer + items (formset)   │
│   TransferStokDetailView → Detail transfer + items                │
│   TransferStokUpdateView → Edit transfer (hanya status draft)     │
│   TransferStokDeleteView → Hapus transfer (hanya status draft)    │
├─────────────────────────────────────────────────────────────────────┤
│ ADJUSTMENT STOK                                                    │
│   AdjustmentStokView       → Daftar semua adjustment              │
│   AdjustmentStokCreateView → Form buat adjustment                 │
└─────────────────────────────────────────────────────────────────────┘

VIEWS FUNCTION-BASED (FBV):
- transfer_stok_approve() → Approve dan proses transfer stok
- get_stok_tersedia()     → API: cek stok per produk per gudang
- get_stok_produk_gudang()→ API: stok saat ini (untuk adjustment)
- search_produk()         → API: search produk via Select2 AJAX

Pola penting:
1. Semua CBV menggunakan Permission Mixins dari apps.core.mixins
2. DeleteView mengembalikan JSON (untuk AJAX delete di frontend)
3. TransferStok menggunakan Django Formset untuk items
4. TemplateLayout.init() digunakan di setiap get_context_data()
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


# Import dari framework Django
from django.shortcuts import render
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
# Import dari framework Django
from django.urls import reverse_lazy
# Import dari framework Django
from django.contrib import messages
# Import dari framework Django
from django.http import JsonResponse
# Import dari modul internal proyek
from apps.produk.models import Gudang, Stok, Produk
# Import dari modul internal proyek
from apps.inventory.models import TransferStok, AdjustmentStok
# Import dari modul internal proyek
from apps.inventory.forms import TransferStokForm, AdjustmentStokForm, TransferStokItemFormSet
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from apps.core.permissions import has_permission, permission_required
from django.db import transaction





# ╔══════════════════════════════════════════════════════════════╗
# ║                    GUDANG CRUD                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class GudangListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua gudang.
    URL: /inventory/gudang/
    Mixin: ReadPermissionMixin → cek permission 'inventory.gudang.read'
    """
    model = Gudang
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/gudang_list.html'
    context_object_name = 'gudang_list'
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'gudang'  # SubCRUD permission

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Tambah metrik summary untuk export dan baris ringkasan
        context['total_gudang'] = self.get_queryset().count()
        return context


class GudangCreateView(CreatePermissionMixin, CreateView):
    """
    Form tambah gudang baru.
    URL: /inventory/gudang/add/
    Fields: kode, nama, alamat, aktif
    """
    model = Gudang
    fields = ['kode', 'nama', 'alamat', 'pajak_persen', 'metode_pembayaran_default', 'aktif']
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/gudang_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:gudang')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'gudang'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Gudang'
        # Import dari modul internal proyek
        from apps.pos.models import MetodePembayaran
        # Query database - ambil data context['metode_pembayaran_list'] yang sesuai filter
        # Data konteks: metode_pembayaran_list - untuk ditampilkan di template
        context['metode_pembayaran_list'] = MetodePembayaran.objects.filter(aktif=True)
        return context

    def get_form(self, form_class=None):
        """Kustomisasi form - set queryset metode pembayaran aktif."""
        form = super().get_form(form_class)
        # Import dari modul internal proyek
        from apps.pos.models import MetodePembayaran
        # Query database - ambil data form.fields['metode_pembayaran_default'].queryset yang sesuai filter
        form.fields['metode_pembayaran_default'].queryset = MetodePembayaran.objects.filter(aktif=True)
        form.fields['metode_pembayaran_default'].empty_label = 'Pilih Metode Pembayaran (Opsional)'
        form.fields['metode_pembayaran_default'].widget.attrs['class'] = 'form-select'
        # Kustomisasi field pajak_persen
        form.fields['pajak_persen'].widget.attrs.update({
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'step': '0.01',
            'placeholder': '0.00'
        })
        form.fields['pajak_persen'].help_text = 'Tarif PPN khusus cabang ini. Kosongkan atau 0 = menggunakan default perusahaan.'
        return form


    def form_valid(self, form):


        """Dipanggil saat form valid - proses penyimpanan data."""
        messages.success(self.request, 'Gudang berhasil ditambahkan')
        return super().form_valid(form)


class GudangUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form edit gudang.
    URL: /inventory/gudang/<pk>/edit/
    """
    model = Gudang
    fields = ['kode', 'nama', 'alamat', 'pajak_persen', 'metode_pembayaran_default', 'aktif']
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/gudang_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:gudang')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'gudang'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Gudang'
        # Import dari modul internal proyek
        from apps.pos.models import MetodePembayaran
        # Query database - ambil data context['metode_pembayaran_list'] yang sesuai filter
        # Data konteks: metode_pembayaran_list - untuk ditampilkan di template
        context['metode_pembayaran_list'] = MetodePembayaran.objects.filter(aktif=True)
        return context

    def get_form(self, form_class=None):
        """Kustomisasi form - set queryset metode pembayaran aktif."""
        form = super().get_form(form_class)
        # Import dari modul internal proyek
        from apps.pos.models import MetodePembayaran
        # Query database - ambil data form.fields['metode_pembayaran_default'].queryset yang sesuai filter
        form.fields['metode_pembayaran_default'].queryset = MetodePembayaran.objects.filter(aktif=True)
        form.fields['metode_pembayaran_default'].empty_label = 'Pilih Metode Pembayaran (Opsional)'
        form.fields['metode_pembayaran_default'].widget.attrs['class'] = 'form-select'
        # Kustomisasi field pajak_persen
        form.fields['pajak_persen'].widget.attrs.update({
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'step': '0.01',
            'placeholder': '0.00'
        })
        form.fields['pajak_persen'].help_text = 'Tarif PPN khusus cabang ini. Kosongkan atau 0 = menggunakan default perusahaan.'
        return form


    def form_valid(self, form):

        """Dipanggil saat form valid - proses penyimpanan data."""
        messages.success(self.request, 'Gudang berhasil diupdate')
        return super().form_valid(form)


class GudangDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus gudang - return JSON response untuk AJAX.
    URL: /inventory/gudang/<pk>/delete/

    ⚠ Jika gudang masih punya stok atau transfer, akan gagal
    karena ForeignKey PROTECT pada model Stok dan TransferStok.
    """
    model = Gudang
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:gudang')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'gudang'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            gudang_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Gudang {gudang_name} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Gagal menghapus gudang: {str(e)}'
            }, status=400)


    # ╔══════════════════════════════════════════════════════════════╗
    # ║                    STOK LIST                                   ║
    # ╚══════════════════════════════════════════════════════════════╝

class StokListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar stok per produk per gudang.
    URL: /inventory/stok/

    Menggunakan select_related untuk optimasi query (1 query bukannya N+1).
    Menampilkan semua stok termasuk yang 0 agar user bisa melihat produk yang habis.
    """
    model = Stok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/stok_list.html'
    context_object_name = 'stok_list'
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'stok'

    # Override queryset - filter atau optimasi query data
    def get_queryset(self):
        # select_related: ambil data produk dan gudang dalam 1 query (JOIN)
        """Override queryset - filter atau optimasi query data."""
        return Stok.objects.select_related('produk', 'gudang').order_by('produk__nama', 'gudang__nama')

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari framework Django
        from django.db.models import Sum
        stok_queryset = self.get_queryset()
        # Data konteks: total_stok_records - untuk ditampilkan di template
        context['total_stok_records'] = stok_queryset.count()
        # Data konteks: total_stok_jumlah - untuk ditampilkan di template
        context['total_stok_jumlah'] = stok_queryset.aggregate(Sum('jumlah'))['jumlah__sum'] or 0
        return context


    # ╔══════════════════════════════════════════════════════════════╗
    # ║                 TRANSFER STOK CRUD                             ║
    # ╚══════════════════════════════════════════════════════════════╝

class TransferStokView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar semua transfer stok. URL: /inventory/transfer/"""
    model = TransferStok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/transfer_stok.html'
    context_object_name = 'transfer_list'
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_transfer - untuk ditampilkan di template
        context['total_transfer'] = self.get_queryset().count()
        return context


class AdjustmentStokView(ReadPermissionMixin, ListView):
    """Daftar semua adjustment stok. URL: /inventory/adjustment/"""
    model = AdjustmentStok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/adjustment_stok.html'
    context_object_name = 'adjustment_list'
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'adjustment_stok'

    def get_queryset(self):
        """Override queryset — support filter by date, jenis, gudang."""
        qs = AdjustmentStok.objects.select_related(
            'produk', 'produk__satuan', 'gudang', 'dibuat_oleh'
        ).order_by('-tanggal')

        # Filter tanggal
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if start:
            qs = qs.filter(tanggal__date__gte=start)
        if end:
            qs = qs.filter(tanggal__date__lte=end)

        # Filter jenis (in/out)
        jenis = self.request.GET.get('jenis')
        if jenis in ('in', 'out'):
            qs = qs.filter(tipe=jenis)

        # Filter gudang
        gudang_id = self.request.GET.get('gudang')
        if gudang_id:
            qs = qs.filter(gudang_id=gudang_id)

        return qs

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_adjustment - untuk ditampilkan di template
        context['total_adjustment'] = self.get_queryset().count()
        # Gudang list untuk filter dropdown
        context['gudang_list'] = Gudang.objects.filter(aktif=True).order_by('nama')

        # Export template context
        try:
            from apps.pengaturan.models import TemplateCetak
            context['export_excel_template'] = TemplateCetak.objects.filter(tipe='excel').first()
            context['export_pdf_template'] = TemplateCetak.objects.filter(tipe='pdf').first()
        except Exception as e:
            logger.warning("Gagal render template: %s", e)

        return context


class TransferStokCreateView(CreatePermissionMixin, CreateView):
    """
    Form buat TRANSFER STOK BARU + items (menggunakan Django Formset).
    URL: /inventory/transfer/add/

    CARA KERJA FORMSET:
    1. get_context_data() menyiapkan form utama (TransferStokForm) + formset (items)
    2. form_valid() akan:
        a. Simpan TransferStok (form utama) → dapatkan ID
        b. Simpan semua TransferStokItem (formset) → link ke transfer via ID
    3. Jika formset tidak valid → render ulang form dengan error
    """
    model = TransferStok
    form_class = TransferStokForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/transfer_stok_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:transfer')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'transfer_stok'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Buat Transfer Stok Baru'

        # Sediakan formset berdasarkan request method
        if self.request.POST:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = TransferStokItemFormSet(self.request.POST)
        else:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = TransferStokItemFormSet()

        return context


    def form_valid(self, form):

        context = self.get_context_data()
        # Data konteks: formset - untuk ditampilkan di template
        formset = context['formset']

        if formset.is_valid():
            with transaction.atomic():
                # Set user pembuat
                form.instance.dibuat_oleh = self.request.user
                self.object = form.save()

                # Link formset items ke transfer yang baru dibuat
                formset.instance = self.object
                formset.save()

            # Tampilkan pesan sukses ke user
            messages.success(self.request, f'Transfer Stok {self.object.nomor_transfer} berhasil dibuat')
            return redirect(self.get_success_url())
        else:
            # Formset tidak valid → render ulang form dengan error
            return self.render_to_response(self.get_context_data(form=form))


class AdjustmentStokCreateView(CreatePermissionMixin, CreateView):
    """
    Form buat ADJUSTMENT STOK baru.
    URL: /inventory/adjustment/add/

    ⚠ Berbeda dengan transfer, adjustment LANGSUNG update stok
    saat save (lihat AdjustmentStok.save() di models.py).
    """
    model = AdjustmentStok
    form_class = AdjustmentStokForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/adjustment_stok_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:adjustment')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'adjustment_stok'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Buat Adjustment Stok'
        return context


    def form_valid(self, form):

        form.instance.dibuat_oleh = self.request.user
        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Adjustment Stok berhasil dibuat')
        return super().form_valid(form)


class AdjustmentStokDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus adjustment stok dengan rollback stok otomatis.
    URL: /inventory/adjustment/<pk>/delete/
    Return: JSON response untuk AJAX

    Saat dihapus:
    - Tipe 'in' (penambahan): stok dikurangi kembali
    - Tipe 'out' (pengurangan): stok dikembalikan
    - Produk.cabang: diupdate ke gudang stok terbanyak
    """
    model = AdjustmentStok
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:adjustment')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'adjustment_stok'

    def delete(self, request, *args, **kwargs):
        """Hapus adjustment - rollback stok, return JSON response."""
        self.object = self.get_object()

        try:
            adjustment = self.object
            nomor = adjustment.nomor_adjustment

            with transaction.atomic():
                # Rollback stok: kebalikan dari operasi adjustment awal
                stok, _ = Stok.objects.select_for_update().get_or_create(
                    produk=adjustment.produk, gudang=adjustment.gudang,
                    defaults={'jumlah': 0}
                )

                if adjustment.tipe == 'in':
                    # Adjustment tambah → rollback = kurangi stok
                    stok.jumlah -= adjustment.jumlah
                    if stok.jumlah < 0:
                        stok.jumlah = 0
                else:
                    # Adjustment kurang → rollback = tambah stok
                    stok.jumlah += adjustment.jumlah

                stok.save()

                # Update cabang produk ke gudang dengan stok terbanyak
                produk = adjustment.produk
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak:
                    if produk.cabang != stok_terbanyak.gudang:
                        produk.cabang = stok_terbanyak.gudang
                        produk.save(update_fields=['cabang'])
                else:
                    # Tidak ada stok di gudang manapun → cabang NULL
                    if produk.cabang is not None:
                        produk.cabang = None
                        produk.save(update_fields=['cabang'])

            adjustment.delete()
            return JsonResponse({
                'success': True,
                'message': f'Adjustment Stok {nomor} berhasil dihapus dan stok telah di-rollback'
            })
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus adjustment stok: {str(e)}'
            }, status=400)


class TransferStokDetailView(ReadPermissionMixin, DetailView):
    """
    Detail transfer stok + items.
    URL: /inventory/transfer/<pk>/
    """
    model = TransferStok
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/transfer_stok_detail.html'
    context_object_name = 'transfer'
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Ambil semua items dengan optimasi query (select_related)
        context['items'] = self.object.items.select_related('produk', 'produk__satuan').all()
        return context


class TransferStokUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Edit transfer stok - bisa diedit pada semua status.
    URL: /inventory/transfer/<pk>/edit/
    Permission: UpdatePermissionMixin → cek can_edit untuk modul inventory via RBAC
    """
    model = TransferStok
    form_class = TransferStokForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'inventory/transfer_stok_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:transfer')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'transfer_stok'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Transfer Stok'

        # Formset diisi dengan data items yang sudah ada (instance=self.object)
        if self.request.POST:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = TransferStokItemFormSet(self.request.POST, instance=self.object)
        else:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = TransferStokItemFormSet(instance=self.object)

        return context


    def form_valid(self, form):
        from django.db import transaction as db_transaction

        context = self.get_context_data()
        # Data konteks: formset - untuk ditampilkan di template
        formset = context['formset']

        if formset.is_valid():
            transfer = self.get_object()
            is_completed = transfer.status == 'completed'

            # Jika transfer sudah completed, ROLLBACK stok lama sebelum save
            old_items_data = []
            old_gudang_asal = transfer.gudang_asal
            old_gudang_tujuan = transfer.gudang_tujuan
            if is_completed:
                for item in transfer.items.select_related('produk'):
                    old_items_data.append({
                        'produk': item.produk,
                        'jumlah': item.jumlah,
                    })

            with db_transaction.atomic():
                # STEP 1: Rollback stok lama (jika transfer sudah completed)
                if is_completed and old_items_data:
                    for old_item in old_items_data:
                        # Kembalikan stok ke gudang asal (yang tadinya dikurangi)
                        stok_asal, _ = Stok.objects.select_for_update().get_or_create(
                            produk=old_item['produk'], gudang=old_gudang_asal,
                            defaults={'jumlah': 0}
                        )
                        stok_asal.jumlah += old_item['jumlah']
                        stok_asal.save()

                        # Kurangi stok dari gudang tujuan (yang tadinya ditambah)
                        stok_tujuan, _ = Stok.objects.select_for_update().get_or_create(
                            produk=old_item['produk'], gudang=old_gudang_tujuan,
                            defaults={'jumlah': 0}
                        )
                        stok_tujuan.jumlah -= old_item['jumlah']
                        if stok_tujuan.jumlah < 0:
                            stok_tujuan.jumlah = 0
                        stok_tujuan.save()

                # STEP 2: Save form dan formset (data baru)
                self.object = form.save()
                formset.instance = self.object
                formset.save()

                # STEP 3: Terapkan stok baru (jika transfer sudah completed)
                if is_completed:
                    new_gudang_asal = self.object.gudang_asal
                    new_gudang_tujuan = self.object.gudang_tujuan
                    for item in self.object.items.select_related('produk'):
                        # Kurangi stok di gudang asal baru
                        stok_asal, _ = Stok.objects.select_for_update().get_or_create(
                            produk=item.produk, gudang=new_gudang_asal,
                            defaults={'jumlah': 0}
                        )
                        stok_asal.jumlah -= item.jumlah
                        if stok_asal.jumlah < 0:
                            stok_asal.jumlah = 0
                        stok_asal.save()

                        # Tambah stok di gudang tujuan baru
                        stok_tujuan, _ = Stok.objects.select_for_update().get_or_create(
                            produk=item.produk, gudang=new_gudang_tujuan,
                            defaults={'jumlah': 0}
                        )
                        stok_tujuan.jumlah += item.jumlah
                        stok_tujuan.save()

                        # Update cabang produk ke gudang dengan stok terbanyak
                        produk = item.produk
                        stok_terbanyak = Stok.objects.filter(
                            produk=produk, jumlah__gt=0
                        ).order_by('-jumlah').first()

                        if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                            produk.cabang = stok_terbanyak.gudang
                            produk.save(update_fields=['cabang'])

            # Tampilkan pesan sukses ke user
            messages.success(self.request, f'Transfer Stok {self.object.nomor_transfer} berhasil diupdate')
            # Redirect ke halaman tujuan
            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))


# ╔══════════════════════════════════════════════════════════════╗
            # ║            FUNCTION-BASED VIEWS (FBV)                         ║
# ╚══════════════════════════════════════════════════════════════╝

# Wajib login - redirect ke login page jika belum login
@login_required
@permission_required('update', 'inventory')
def transfer_stok_approve(request, pk):
    """
    Approve transfer stok dan proses update stok.
    URL: /inventory/transfer/<pk>/approve/
    Permission: Mengecek can_edit pada modul inventory via RBAC

    Alur:
    1. Cek permission RBAC (harus punya can_edit inventory)
    2. Cek status (harus draft/submitted)
    3. Jika masih draft → set ke submitted dulu
    4. Panggil transfer.approve() → update stok gudang asal & tujuan
    5. Redirect ke halaman detail
    """
    # Cek permission RBAC - hanya user dengan can_edit inventory yang bisa approve
    if not request.user.is_superuser:
        if not has_permission(request.user, 'write', 'inventory', 'transfer_stok'):
            messages.error(request, 'Anda tidak memiliki izin untuk melakukan approve transfer stok.')
            return redirect('inventory:transfer')

    transfer = get_object_or_404(TransferStok, pk=pk)

    if transfer.status not in ['draft', 'submitted']:
        # Tampilkan pesan error ke user
        messages.error(request, f'Transfer stok dengan status {transfer.get_status_display()} tidak bisa diapprove')
        # Redirect ke halaman tujuan
        return redirect('inventory:transfer_detail', pk=pk)

    # Blok penanganan error - coba jalankan kode di bawah
    try:
        # Set submitted jika masih draft
        if transfer.status == 'draft':
            transfer.status = 'submitted'
            transfer.save()

        # Approve → update stok otomatis (lihat TransferStok.approve())
        transfer.approve(request.user)
        # Tampilkan pesan sukses ke user
        messages.success(request, f'Transfer Stok {transfer.nomor_transfer} berhasil diapprove dan stok telah diupdate')
    # Tangkap error ValueError - lanjutkan tanpa crash
    except ValueError as e:
        # Tampilkan pesan error ke user
        messages.error(request, f'Gagal approve transfer stok: {str(e)}')
    # Tangkap error Exception - lanjutkan tanpa crash
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
    except Exception as e:
        # Tampilkan pesan error ke user
        messages.error(request, f'Terjadi kesalahan: {str(e)}')

    # Redirect ke halaman tujuan
    return redirect('inventory:transfer_detail', pk=pk)


class TransferStokDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus transfer stok - bisa dihapus pada semua status.
    URL: /inventory/transfer/<pk>/delete/
    Return: JSON response untuk AJAX
    Permission: DeletePermissionMixin → cek can_delete untuk modul inventory

    Jika transfer sudah completed, stok akan di-rollback:
    - Gudang asal: stok dikembalikan (+)
    - Gudang tujuan: stok dikurangi (-)
    - Produk.cabang: diupdate ke gudang stok terbanyak
    """
    model = TransferStok
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('inventory:transfer')
    # Modul permission yang dicek: 'inventory'
    permission_module = 'inventory'
    permission_sub_module = 'transfer_stok'

    def delete(self, request, *args, **kwargs):
        """Hapus data - rollback stok jika completed, return JSON response."""
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            transfer = self.object
            nomor_transfer = transfer.nomor_transfer

            # Jika transfer sudah completed, rollback stok sebelum hapus
            if transfer.status == 'completed':
                with transaction.atomic():
                    for item in transfer.items.select_related('produk'):
                        # Kembalikan stok ke gudang asal
                        stok_asal, _ = Stok.objects.select_for_update().get_or_create(
                            produk=item.produk, gudang=transfer.gudang_asal,
                            defaults={'jumlah': 0}
                        )
                        stok_asal.jumlah += item.jumlah
                        stok_asal.save()

                        # Kurangi stok dari gudang tujuan
                        stok_tujuan, _ = Stok.objects.select_for_update().get_or_create(
                            produk=item.produk, gudang=transfer.gudang_tujuan,
                            defaults={'jumlah': 0}
                        )
                        stok_tujuan.jumlah -= item.jumlah
                        if stok_tujuan.jumlah < 0:
                            stok_tujuan.jumlah = 0
                        stok_tujuan.save()

                        # Update cabang produk ke gudang dengan stok terbanyak
                        produk = item.produk
                        stok_terbanyak = Stok.objects.filter(
                            produk=produk, jumlah__gt=0
                        ).order_by('-jumlah').first()

                        if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                            produk.cabang = stok_terbanyak.gudang
                            produk.save(update_fields=['cabang'])

            transfer.delete()
            return JsonResponse({
                'success': True,
                'message': f'Transfer Stok {nomor_transfer} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus transfer stok: {str(e)}'
            }, status=400)


class AdjustmentStokDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus adjustment stok dengan rollback stok otomatis.
    URL: /inventory/adjustment/<pk>/delete/
    Return: JSON response untuk AJAX

    Saat dihapus:
    - Tipe 'in' (penambahan): stok dikurangi kembali
    - Tipe 'out' (pengurangan): stok dikembalikan
    - Produk.cabang: diupdate ke gudang stok terbanyak
    """
    model = AdjustmentStok
    success_url = reverse_lazy('inventory:adjustment')
    permission_module = 'inventory'
    permission_sub_module = 'adjustment_stok'

    def delete(self, request, *args, **kwargs):
        """Hapus adjustment - rollback stok, return JSON response."""
        self.object = self.get_object()

        try:
            adjustment = self.object
            nomor = adjustment.nomor_adjustment

            with transaction.atomic():
                # Rollback stok: kebalikan dari operasi adjustment awal
                stok, _ = Stok.objects.select_for_update().get_or_create(
                    produk=adjustment.produk, gudang=adjustment.gudang,
                    defaults={'jumlah': 0}
                )

                if adjustment.tipe == 'in':
                    # Adjustment tambah → rollback = kurangi stok
                    stok.jumlah -= adjustment.jumlah
                    if stok.jumlah < 0:
                        stok.jumlah = 0
                else:
                    # Adjustment kurang → rollback = tambah stok
                    stok.jumlah += adjustment.jumlah

                stok.save()

                # Update cabang produk ke gudang dengan stok terbanyak
                produk = adjustment.produk
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak:
                    if produk.cabang != stok_terbanyak.gudang:
                        produk.cabang = stok_terbanyak.gudang
                        produk.save(update_fields=['cabang'])
                else:
                    # Tidak ada stok di gudang manapun → cabang NULL
                    if produk.cabang is not None:
                        produk.cabang = None
                        produk.save(update_fields=['cabang'])

            adjustment.delete()
            return JsonResponse({
                'success': True,
                'message': f'Adjustment Stok {nomor} berhasil dihapus dan stok telah di-rollback'
            })
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus adjustment stok: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
            # ║               API ENDPOINTS (JSON)                             ║
# ╚══════════════════════════════════════════════════════════════╝

# Wajib login - redirect ke login page jika belum login
@login_required
@permission_required('read', 'inventory')
def get_stok_tersedia(request):
    """
    API endpoint: dapatkan stok tersedia per produk per gudang.
    URL: /inventory/api/stok-tersedia/?produk_id=1&gudang_id=2
    Digunakan oleh: form transfer stok (untuk validasi stok sebelum transfer)
    """
    produk_id = request.GET.get('produk_id')
    gudang_id = request.GET.get('gudang_id')

    if not produk_id or not gudang_id:
        return JsonResponse({
            'success': False,
            'message': 'Produk dan Gudang harus dipilih'
        })

    # Blok penanganan error - coba jalankan kode di bawah
    try:
        # Query database - ambil satu data produk
        produk = Produk.objects.select_related('satuan').get(id=produk_id)
        # Query database - ambil satu data gudang
        gudang = Gudang.objects.get(id=gudang_id)

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Query database - ambil satu data stok
            stok = Stok.objects.get(produk=produk, gudang=gudang)
            jumlah_tersedia = float(stok.jumlah)
        # Tangkap error Stok.DoesNotExist - lanjutkan tanpa crash
        except Stok.DoesNotExist:
            jumlah_tersedia = 0

        return JsonResponse({
            'success': True,
            'produk_nama': produk.nama,
            'gudang_nama': gudang.nama,
            'stok_tersedia': jumlah_tersedia,
            'satuan': produk.satuan.singkatan if produk.satuan else 'unit'
        })
    # Tangkap error (Produk.DoesNotExist, Gudang.DoesNotExist) - lanjutkan tanpa crash
    except (Produk.DoesNotExist, Gudang.DoesNotExist) as e:
        return JsonResponse({
            'success': False,
            'message': 'Produk atau Gudang tidak ditemukan'
        })


# Wajib login - redirect ke login page jika belum login
@login_required
@permission_required('read', 'inventory')
def get_stok_produk_gudang(request):
    """
    API endpoint: stok saat ini (untuk form adjustment).
    URL: /inventory/api/stok-produk-gudang/?produk_id=1&gudang_id=2
    Digunakan oleh: form adjustment stok (menampilkan stok sebelum adjustment)
    """
    produk_id = request.GET.get('produk_id')
    gudang_id = request.GET.get('gudang_id')

    if not produk_id or not gudang_id:
        return JsonResponse({
            'success': False,
            'message': 'Produk dan Gudang harus dipilih'
        })

    # Blok penanganan error - coba jalankan kode di bawah
    try:
        # Query database - ambil satu data produk
        produk = Produk.objects.select_related('satuan').get(id=produk_id)
        # Query database - ambil satu data gudang
        gudang = Gudang.objects.get(id=gudang_id)

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Query database - ambil satu data stok
            stok = Stok.objects.get(produk=produk, gudang=gudang)
            stok_saat_ini = float(stok.jumlah)
        # Tangkap error Stok.DoesNotExist - lanjutkan tanpa crash
        except Stok.DoesNotExist:
            stok_saat_ini = 0

        return JsonResponse({
            'success': True,
            'stok_saat_ini': stok_saat_ini,
            'satuan': produk.satuan.singkatan if produk.satuan else 'unit'
        })
    # Tangkap error (Produk.DoesNotExist, Gudang.DoesNotExist) - lanjutkan tanpa crash
    except (Produk.DoesNotExist, Gudang.DoesNotExist):
        return JsonResponse({
            'success': False,
            'message': 'Produk atau Gudang tidak ditemukan'
        })


# Wajib login - redirect ke login page jika belum login
@login_required
@permission_required('read', 'inventory')
def search_produk(request):
    """
    API endpoint: pencarian produk via Select2 AJAX.
    URL: /inventory/api/search-produk/?q=keyword&gudang_id=1&page=1

    Digunakan oleh: dropdown Select2 di form transfer stok.
    Fitur:
    - Search berdasarkan nama atau SKU
    - Pagination (20 hasil per halaman)
    - Menampilkan stok tersedia jika gudang_id diberikan
    - Format text: "Nama Produk (SKU) - Stok: 100 pcs"
    """
    from django.db.models import Q

    q = request.GET.get('q', '').strip()
    gudang_id = request.GET.get('gudang_id', None)
    page = int(request.GET.get('page', 1))
    per_page = 20

    # Base queryset - hanya produk aktif
    queryset = Produk.objects.filter(aktif=True).select_related('satuan', 'kategori')

    # Filter berdasarkan keyword (nama atau SKU)
    if q:
        queryset = queryset.filter(
            Q(nama__icontains=q) | Q(sku__icontains=q)
        )

    queryset = queryset.order_by('nama')

    # Pagination manual (slice queryset)
    start = (page - 1) * per_page
    end = start + per_page
    products = queryset[start:end + 1]  # +1 untuk cek ada halaman berikutnya

    # Build result - cek stok jika gudang_id diberikan
    results = []
    for produk in products[:per_page]:
        stok_tersedia = 0
        if gudang_id:
            # Blok penanganan error - coba jalankan kode di bawah
            try:
                # Query database - ambil satu data stok
                stok = Stok.objects.get(produk=produk, gudang_id=gudang_id)
                stok_tersedia = float(stok.jumlah)
            # Tangkap error Stok.DoesNotExist - lanjutkan tanpa crash
            except Stok.DoesNotExist:
                stok_tersedia = 0

        satuan_nama = produk.satuan.nama if produk.satuan else 'pcs'
        satuan_singkatan = produk.satuan.singkatan if produk.satuan else 'pcs'

        # Format text untuk tampilan Select2
        text = f"{produk.nama}"
        if produk.sku:
            text += f" ({produk.sku})"
        if gudang_id:
            text += f" - Stok: {stok_tersedia} {satuan_singkatan}"

        results.append({
            'id': produk.id,
            'text': text,
            'nama': produk.nama,
            'sku': produk.sku or '',
            'stok': stok_tersedia,
            'satuan': satuan_nama,
            'satuan_singkatan': satuan_singkatan,
        })

    # Apakah ada halaman berikutnya?
    has_more = len(products) > per_page

    return JsonResponse({
        'results': results,
        'pagination': {
        'more': has_more
}
    })
