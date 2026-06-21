"""
==========================================================================
PRODUK VIEWS - Views untuk Modul Produk (Kategori, Satuan, Produk)
==========================================================================
File ini berisi semua view (controller) untuk modul Produk.
Menggunakan Django Class-Based Views (CBV) dengan permission mixins.

Pola view yang digunakan (setiap entitas punya 4 view CRUD):
- ListView → Menampilkan daftar data
- CreateView → Form tambah data baru
- UpdateView → Form edit data yang sudah ada
- DeleteView → Hapus data (via AJAX)

View yang tersedia:
[Kategori] KategoriListView, KategoriCreateView, KategoriUpdateView, KategoriDeleteView
[Satuan]   SatuanListView, SatuanCreateView, SatuanUpdateView, SatuanDeleteView
[Produk]   ProdukListView, ProdukCreateView, ProdukUpdateView, ProdukDeleteView, ProdukImportView

Konsep penting:
1. SubModulePermissionMixin → Setiap view dicek permission di level sub-modul
2. TemplateLayout.init() → Menginisialisasi layout template (sidebar, header)
3. reverse_lazy() → URL redirect yang dievaluasi saat runtime (bukan saat import)
4. JsonResponse → Untuk delete via AJAX (tanpa reload halaman)

Koneksi:
- apps/core/mixins.py → SubModulePermissionMixin untuk pengecekan permission
- apps/produk/models.py → Model Kategori, Satuan, Produk, Gudang, Stok
- apps/produk/forms.py → ProdukForm untuk form create/update produk
- apps/produk/urls.py → URL routing yang mengarah ke view ini
- web_project/__init__.py → TemplateLayout untuk layout management
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
from django.shortcuts import render, redirect
from django.db.models import ProtectedError
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django import forms
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.produk.models import Kategori, Satuan, Produk, Gudang, Stok  # Model database
# Import dari modul internal proyek
from apps.produk.forms import ProdukForm                               # Form produk
# Import dari modul internal proyek
from apps.core.mixins import (                                         # Permission mixins
    ReadPermissionMixin, CreatePermissionMixin,
    UpdatePermissionMixin, DeletePermissionMixin,
    SubModulePermissionMixin
)
from apps.core.permissions import permission_required
import logging  # Modul logging standar Python - pengganti print() untuk production
from django.db import transaction

# Inisialisasi logger untuk modul Produk


# ╔══════════════════════════════════════════════════════════════╗
# ║                    CRUD KATEGORI                              ║
# ╚══════════════════════════════════════════════════════════════╝

class KategoriListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua kategori produk.

    URL: /produk/kategori/
    Permission: produk.kategori.read
    Template: produk/kategori_list.html
    """
    model = Kategori                              # Model yang ditampilkan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/kategori_list.html'   # Template HTML
    context_object_name = 'kategori_list'         # Nama variabel di template

    # Permission configuration
    permission_module = 'produk'                  # Modul: produk
    permission_sub_module = 'kategori'            # Sub-modul: kategori
    permission_action = 'read'                    # Aksi: baca/lihat

    def get_context_data(self, **kwargs):
        """Menambahkan data tambahan ke template context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_kategori - untuk ditampilkan di template
        context['total_kategori'] = self.get_queryset().count()  # Untuk summary/export
        return context


class KategoriCreateView(SubModulePermissionMixin, CreateView):
    """
    Form untuk menambahkan kategori baru.

    URL: /produk/kategori/add/
    Permission: produk.kategori.create
    Template: produk/kategori_form.html
    """
    model = Kategori
    fields = ['nama', 'deskripsi']                    # Field yang ditampilkan di form
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/kategori_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:kategori')     # Redirect setelah berhasil
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'kategori'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Kategori'
        return context


    def form_valid(self, form):


        """
        Dipanggil saat form valid (validasi berhasil).
        Set field dibuat_oleh ke user yang sedang login.
        """
        form.instance.dibuat_oleh = self.request.user  # Set pembuat = user login
        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Kategori berhasil ditambahkan')
        return super().form_valid(form)


class KategoriUpdateView(SubModulePermissionMixin, UpdateView):
    """
    Form untuk mengedit kategori yang sudah ada.

    URL: /produk/kategori/<pk>/edit/
    Permission: produk.kategori.write
    """
    model = Kategori
    fields = ['nama', 'deskripsi']
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/kategori_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:kategori')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'kategori'
    permission_action = 'write'  # 'write' = alias untuk 'update' di permission system

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Kategori'
        return context


    def form_valid(self, form):

        """Dipanggil saat form valid - proses penyimpanan data."""
        messages.success(self.request, 'Kategori berhasil diupdate')
        return super().form_valid(form)


class KategoriDeleteView(SubModulePermissionMixin, DeleteView):
    """
    Menghapus kategori via AJAX.

    URL: /produk/kategori/<pk>/delete/
    Permission: produk.kategori.delete
    Response: JSON (bukan HTML) karena dipanggil via AJAX dari frontend
    """
    model = Kategori
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:kategori')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'kategori'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        """
        Override delete() untuk mengembalikan JSON response (bukan HTML).

        Kenapa JSON?
        - Frontend menggunakan AJAX (JavaScript) untuk menghapus data
        - Tidak perlu reload halaman → UX lebih baik
        - Frontend menangani response JSON untuk menampilkan notifikasi
        """
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            kategori_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Kategori {kategori_name} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus kategori: {str(e)}'
            }, status=400)


    # ╔══════════════════════════════════════════════════════════════╗
    # ║                      CRUD SATUAN                              ║
    # ╚══════════════════════════════════════════════════════════════╝

class SatuanListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """Menampilkan daftar semua satuan. URL: /produk/satuan/"""
    model = Satuan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/satuan_list.html'
    context_object_name = 'satuan_list'
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'satuan'
    permission_action = 'read'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_satuan - untuk ditampilkan di template
        context['total_satuan'] = self.get_queryset().count()
        return context


class SatuanCreateView(SubModulePermissionMixin, CreateView):
    """Form tambah satuan baru. URL: /produk/satuan/add/"""
    model = Satuan
    fields = ['nama', 'singkatan']
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/satuan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:satuan')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'satuan'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Satuan'
        return context


    def form_valid(self, form):

        """Dipanggil saat form valid - proses penyimpanan data."""
        messages.success(self.request, 'Satuan berhasil ditambahkan')
        return super().form_valid(form)


class SatuanSeedDefaultView(SubModulePermissionMixin, TemplateView):
    """Seed satuan dan konversi default. URL: /produk/satuan/seed-default/"""
    template_name = 'produk/satuan_list.html'
    permission_module = 'produk'
    permission_sub_module = 'satuan'
    permission_action = 'create'

    def get(self, request, *args, **kwargs):
        return redirect('produk:satuan')

    def post(self, request, *args, **kwargs):
        try:
            from io import StringIO
            from django.core.management import call_command

            output = StringIO()
            call_command('seed_konversi_satuan', stdout=output)
            messages.success(
                request,
                'Seed satuan default berhasil dijalankan. Satuan dan konversi default sudah dilengkapi.'
            )
        except Exception as exc:
            logger.exception('Gagal menjalankan seed satuan default')
            messages.error(request, f'Gagal menjalankan seed satuan default: {exc}')
        return redirect('produk:satuan')


class SatuanUpdateView(SubModulePermissionMixin, UpdateView):
    """Form edit satuan. URL: /produk/satuan/<pk>/edit/"""
    model = Satuan
    fields = ['nama', 'singkatan']
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/satuan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:satuan')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'satuan'
    permission_action = 'write'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Satuan'
        return context


    def form_valid(self, form):

        """Dipanggil saat form valid - proses penyimpanan data."""
        messages.success(self.request, 'Satuan berhasil diupdate')
        return super().form_valid(form)


class SatuanDeleteView(SubModulePermissionMixin, DeleteView):
    """Hapus satuan via AJAX. URL: /produk/satuan/<pk>/delete/"""
    model = Satuan
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:satuan')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'satuan'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            satuan_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Satuan {satuan_name} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus satuan: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
        # ║                      CRUD PRODUK                              ║
# ╚══════════════════════════════════════════════════════════════╝

class ProdukListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua produk dengan informasi lengkap.

    URL: /produk/list/
    Permission: produk.daftar_produk.read

    Fitur:
    - Prefetch stok → mengurangi jumlah query (N+1 problem)
    - Menghitung total produk, stok, nilai beli, nilai jual
    """
    model = Produk
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/produk_list.html'
    context_object_name = 'produk_list'
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'daftar_produk'  # Sesuai SUB_MODULE_CHOICES di RolePermission
    permission_action = 'read'

    def get_queryset(self):
        """
        Override queryset untuk optimasi query database.

        prefetch_related() → mengambil data relasi many-to-many/reverse FK dalam 1 query
        select_related() → mengambil data relasi FK dalam 1 JOIN query

        Tanpa optimasi: 1 query produk + N query stok + N query gudang = N*2+1 query
        Dengan optimasi: 3 query saja (produk, stok+gudang, kategori+satuan)
        """
        return Produk.objects.filter(
            tipe='produk'
        ).prefetch_related(
            'stok_set',           # Prefetch semua stok (reverse FK)
            'stok_set__gudang'    # Prefetch gudang dari setiap stok
        ).select_related(
            'kategori',           # JOIN kategori
            'satuan',             # JOIN satuan
            'cabang'              # JOIN gudang cabang
        )

    def get_context_data(self, **kwargs):
        """Menghitung data summary untuk template (total produk, stok, nilai)."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: produk_list - untuk ditampilkan di template
        produk_list = context['produk_list']

        # Daftar gudang aktif (untuk filter dropdown)
        context['gudang_list'] = Gudang.objects.filter(aktif=True)

        # Hitung total untuk tabel summary dan export
        total_produk = 0
        total_stok = 0
        total_nilai_beli = 0
        total_nilai_jual = 0

        for produk in produk_list:
            total_produk += 1
            stok = produk.stok_total
            total_stok += stok
            total_nilai_beli += produk.harga_beli * stok
            total_nilai_jual += produk.harga_jual * stok

        # Data konteks: total_produk - untuk ditampilkan di template
        context['total_produk'] = total_produk
        # Data konteks: total_stok - untuk ditampilkan di template
        context['total_stok'] = total_stok
        # Data konteks: total_nilai_beli - untuk ditampilkan di template
        context['total_nilai_beli'] = total_nilai_beli
        # Data konteks: total_nilai_jual - untuk ditampilkan di template
        context['total_nilai_jual'] = total_nilai_jual

        return context


class ProdukCreateView(SubModulePermissionMixin, CreateView):
    """
    Form untuk menambahkan produk baru.

    URL: /produk/tambah/
    Permission: produk.tambah_produk.create

    Fitur khusus:
    - Auto-generate SKU jika kosong
    - Handle stok awal (buat record Stok di gudang default)
    """
    model = Produk
    form_class = ProdukForm    # Menggunakan custom form (bukan fields=[...])
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/produk_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:list')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'tambah_produk'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Produk'
        return context


    def form_valid(self, form):

        """
        Setelah form valid:
        1. Set pembuat = user login
        2. Simpan produk
        3. Handle stok awal (jika ada input stok_awal di form)
        """
        form.instance.dibuat_oleh = self.request.user
        response = super().form_valid(form)

        # ===== HANDLE STOK AWAL =====
        # stok_awal bukan field di model, tapi input tambahan di form HTML
        stok_awal = self.request.POST.get('stok_awal')
        if stok_awal and float(stok_awal) > 0:
            # Tentukan gudang: dari cabang yang dipilih, atau gudang default
            gudang = form.instance.cabang
            if not gudang:
                # Query database - ambil data gudang yang sesuai filter
                gudang = Gudang.objects.filter(aktif=True).first()
                if not gudang:
                    # Buat gudang default jika belum ada
                    gudang = Gudang.objects.create(
                        kode='GD-DEFAULT',
                        nama='Gudang Utama',
                        aktif=True
                    )

            # Buat atau update record Stok
            # update_or_create() → cari berdasarkan produk+gudang, update/create jumlah
            Stok.objects.update_or_create(
                produk=form.instance,
                gudang=gudang,
                defaults={'jumlah': float(stok_awal)}
            )

        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Produk berhasil ditambahkan')
        return response


class ProdukUpdateView(SubModulePermissionMixin, UpdateView):
    """
    Form untuk mengedit produk yang sudah ada.

    URL: /produk/<pk>/edit/
    Permission: produk.write (level modul, tanpa sub_module spesifik)

    Fitur:
    - Menampilkan stok per-cabang (gudang) di form edit
    - Bisa edit stok masing-masing cabang secara terpisah
    - Data stok terhubung dengan Transfer Stok & Adjustment Stok
    """
    model = Produk
    form_class = ProdukForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'produk/produk_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:list')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_action = 'write'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template, termasuk stok per-cabang."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Produk'

        # ===== STOK PER-CABANG =====
        # Ambil semua record Stok untuk produk ini (di semua gudang)
        stok_queryset = Stok.objects.filter(
            produk=self.object
        ).select_related('gudang').order_by('gudang__nama')

        stok_per_cabang = []
        total_stok = 0
        for stok_item in stok_queryset:
            stok_per_cabang.append({
                'gudang_id': stok_item.gudang.id,
                'gudang_kode': stok_item.gudang.kode,
                'gudang_nama': stok_item.gudang.nama,
                'jumlah': stok_item.jumlah,
            })
            total_stok += stok_item.jumlah

        # Data konteks: stok_per_cabang - untuk ditampilkan di template
        context['stok_per_cabang'] = stok_per_cabang
        # Data konteks: total_stok - untuk ditampilkan di template
        context['total_stok'] = total_stok

        # Backward compat: stok_saat_ini untuk fallback
        if stok_per_cabang:
            # Data konteks: stok_saat_ini - untuk ditampilkan di template
            context['stok_saat_ini'] = total_stok

        return context


    def form_valid(self, form):

        """Handle update stok per-cabang dari input form."""
        response = super().form_valid(form)

        # ===== SIMPAN STOK PER-CABANG =====
        # Cek apakah ada input stok per-cabang (stok_cabang_{gudang_id})
        has_per_cabang_input = False
        for key in self.request.POST:
            if key.startswith('stok_cabang_'):
                has_per_cabang_input = True
                gudang_id = key.replace('stok_cabang_', '')
                stok_value = self.request.POST.get(key, '').strip()
                if stok_value:
                    # Blok penanganan error - coba jalankan kode di bawah
                    try:
                        jumlah = float(stok_value)
                        Stok.objects.update_or_create(
                            produk=form.instance,
                            gudang_id=int(gudang_id),
                            defaults={'jumlah': jumlah}
                        )
                    # Tangkap error (ValueError, TypeError) - lanjutkan tanpa crash
                    except (ValueError, TypeError):
                        pass  # Abaikan input tidak valid

        # Fallback: jika tidak ada input per-cabang, gunakan stok_awal tunggal
        if not has_per_cabang_input:
            stok_input = self.request.POST.get('stok_awal')
            if stok_input:
                gudang = form.instance.cabang
                if not gudang:
                    # Query database - ambil data gudang yang sesuai filter
                    gudang = Gudang.objects.filter(aktif=True).first()
                    if not gudang:
                        # Buat record baru di database
                        gudang = Gudang.objects.create(
                            kode='GD-DEFAULT',
                            nama='Gudang Utama',
                            aktif=True
                        )

                Stok.objects.update_or_create(
                    produk=form.instance,
                    gudang=gudang,
                    defaults={'jumlah': float(stok_input)}
                )

        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Produk berhasil diupdate')
        return response


class ProdukDeleteView(SubModulePermissionMixin, DeleteView):
    """Hapus produk via AJAX. URL: /produk/<pk>/delete/"""
    model = Produk
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('produk:list')
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            produk_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Produk {produk_name} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus produk: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
                # ║                   IMPORT PRODUK (CSV/EXCEL)                   ║
# ╚══════════════════════════════════════════════════════════════╝

class ProdukImportView(SubModulePermissionMixin, TemplateView):
    """
    Halaman import produk dari file CSV atau Excel.

    URL: /produk/import/
    Permission: produk.produk_import.create

    Mendukung format:
    - CSV (.csv) → Dengan auto-detect delimiter (koma, titik koma, tab)
    - Excel (.xlsx, .xls) → Parse HTML table (format export dari sistem)

    Alur import:
    1. User upload file CSV/Excel
    2. Sistem parsing file → ambil data per baris
    3. Untuk setiap baris: buat/cari Kategori & Satuan → buat Produk
    4. Return summary: berapa berhasil, berapa gagal + alasan error
    """
    template_name = 'produk/produk_import.html'
    # Modul permission yang dicek: 'produk'
    permission_module = 'produk'
    permission_sub_module = 'produk_import'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database - ambil semua data context['kategori_list']
        # Data konteks: kategori_list - untuk ditampilkan di template
        context['kategori_list'] = Kategori.objects.all()  # Untuk referensi di template
        # Query database - ambil semua data context['satuan_list']
        # Data konteks: satuan_list - untuk ditampilkan di template
        context['satuan_list'] = Satuan.objects.all()
        return context


    def post(self, request, *args, **kwargs):

        """
        Proses upload dan import file (POST).

        Tahapan:
        1. Validasi: file ada? format didukung?
        2. Parse file (CSV atau HTML/Excel)
        3. Loop setiap baris → buat produk
        4. Return summary (jumlah berhasil/gagal)
        """
        # Cek apakah request dari AJAX (JavaScript)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Validasi: file harus ada
        if 'file' not in request.FILES:
            if is_ajax:
                # Kembalikan respons JSON gagal ke klien
                return JsonResponse({'success': False, 'message': 'Tidak ada file yang diupload!'})
            # Tampilkan pesan error ke user
            messages.error(request, 'Tidak ada file yang diupload!')
            return self.get(request, *args, **kwargs)

        file = request.FILES['file']
        file_name = file.name.lower()

        # Validasi: format file
        if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            if is_ajax:
                # Kembalikan respons JSON gagal ke klien
                return JsonResponse({'success': False, 'message': 'Format file tidak didukung! Gunakan CSV atau Excel.'})
            # Tampilkan pesan error ke user
            messages.error(request, 'Format file tidak didukung! Gunakan CSV atau Excel.')
            return self.get(request, *args, **kwargs)

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            import io
            import csv

            if file_name.endswith('.csv'):
                # ===== PARSE CSV =====
                # Decode file CSV (handle BOM untuk file dari Windows)
                decoded_file = file.read().decode('utf-8-sig')

                # Skip 'sep=,' directive jika ada (dari Excel)
                lines = decoded_file.splitlines()
                if lines and lines[0].strip().startswith('sep='):
                    decoded_file = '\n'.join(lines[1:])

                # Auto-detect delimiter (koma, titik koma, tab)
                # Beberapa negara pakai titik koma sebagai pemisah kolom
                io_string = io.StringIO(decoded_file)
                sample = io_string.read(1024)
                io_string.seek(0)

                # Blok penanganan error - coba jalankan kode di bawah
                try:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample, delimiters=',;\t')
                    delimiter = dialect.delimiter
                # Tangkap error Exception - lanjutkan tanpa crash
                except Exception:
                    delimiter = ','  # Default: koma

                reader = csv.DictReader(io_string, delimiter=delimiter)
                rows = list(reader)  # Konversi ke list of dict

            else:
                # ===== PARSE EXCEL (HTML format) =====
                # File Excel export dari sistem ini menggunakan format HTML table
                try:
                    file.seek(0)
                    content_bytes = file.read()

                    # Coba decode dengan berbagai encoding
                    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
                    html_content = None

                    for enc in encodings:
                        # Blok penanganan error - coba jalankan kode di bawah
                        try:
                            html_content = content_bytes.decode(enc)
                            break
                        # Tangkap error UnicodeDecodeError - lanjutkan tanpa crash
                        except UnicodeDecodeError:
                            continue

                    if not html_content:
                        raise ValueError("Could not decode file")

                    # Parse HTML menggunakan BeautifulSoup
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Cek apakah frameset (export Excel multi-file)
                    frameset = soup.find('frameset')
                    if frameset:
                        frames = soup.find_all('frame')
                        sheet_file = None
                        for frame in frames:
                            src = frame.get('src', '')
                            if 'sheet' in src.lower() and src.endswith('.htm'):
                                sheet_file = src
                                break

                        if not sheet_file:
                            raise ValueError("File export menggunakan frameset tapi tidak ditemukan sheet data. Gunakan template CSV atau konversi ke format sederhana.")
                        raise ValueError("File export ini memiliki format frameset Excel. Silakan gunakan 'Download Template CSV' atau export ulang ke format yang lebih sederhana.")

                    # Cari table di HTML
                    table = soup.find('table')

                    if not table:
                        # Fallback: cari dengan regex
                        import re
                        table_match = re.search(r'<table[^>]*>(.*?)</table>', html_content, re.DOTALL | re.IGNORECASE)
                        if table_match:
                            soup = BeautifulSoup(table_match.group(0), 'html.parser')
                            table = soup.find('table')

                    if not table:
                        raise ValueError("Tidak ditemukan tabel dalam file. Pastikan file adalah hasil export atau template yang valid.")

                    # Ekstrak header
                    headers = []
                    header_row = table.find('thead')
                    if header_row:
                        headers = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
                    else:
                        first_row = table.find('tr')
                        if first_row:
                            headers = [td.get_text(strip=True).lower() for td in first_row.find_all(['th', 'td'])]

                    if not headers or 'nama' not in headers:
                        raise ValueError(f"Header tidak valid atau kolom 'nama' tidak ditemukan. Headers ditemukan: {headers}")

                    # Ekstrak baris data
                    rows = []
                    rows_iter = table.find_all('tr')
                    if header_row:
                        rows_iter = table.find('tbody').find_all('tr') if table.find('tbody') else rows_iter[1:]
                    else:
                        rows_iter = rows_iter[1:]  # Skip header row

                    for tr in rows_iter:
                        cells = tr.find_all(['td', 'th'])
                        if not cells:
                            continue

                        # Skip baris kosong
                        row_text = ''.join([cell.get_text(strip=True) for cell in cells])
                        if not row_text or row_text.replace('\xa0', '').strip() == '':
                            continue

                        row_data = {}
                        for idx, cell in enumerate(cells):
                            if idx < len(headers):
                                cell_text = cell.get_text(strip=True).replace('\xa0', '').strip()
                                row_data[headers[idx]] = cell_text if cell_text else ''

                        # Hanya tambahkan baris yang punya nama produk
                        if row_data.get('nama', '').strip():
                            rows.append(row_data)

                # Tangkap error Exception - lanjutkan tanpa crash
                except ProtectedError:
                    return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
                except Exception as e:
                    # Catat error parsing HTML ke log - tidak menghentikan proses
                    logger.warning("HTML parsing error saat import produk: %s", e)
                    if is_ajax:
                        # Kembalikan respons JSON gagal ke klien
                        return JsonResponse({'success': False, 'message': f'Gagal membaca file: {str(e)}'})
                    # Tampilkan pesan error ke user
                    messages.error(request, f'Gagal membaca file: {str(e)}')
                    return self.get(request, *args, **kwargs)

            # ===== PROSES SETIAP BARIS DATA =====
            success_count = 0
            error_count = 0
            errors = []

            for idx, row in enumerate(rows, start=2):  # Mulai dari 2 (baris 1 = header)
                # Blok penanganan error - coba jalankan kode di bawah
                try:
                    # Ambil atau buat Kategori (get_or_create)
                    kategori = None
                    if 'kategori' in row and row['kategori']:
                        kategori, _ = Kategori.objects.get_or_create(
                            nama=str(row['kategori']).strip(),
                            defaults={'dibuat_oleh': request.user}
                        )

                    # Ambil atau buat Satuan (get_or_create)
                    satuan_nama = str(row.get('satuan', 'pcs')).strip()
                    satuan, _ = Satuan.objects.get_or_create(
                        nama=satuan_nama,
                        defaults={'singkatan': satuan_nama[:3].upper()}
                    )

                    # Cek duplikasi SKU
                    sku = str(row.get('sku', '')).strip() if row.get('sku') else None
                    # Query database - ambil data if sku and Produk.objects.filter(sku yang sesuai filter
                    if sku and Produk.objects.filter(sku=sku).exists():
                        errors.append(f"Baris {idx}: SKU '{sku}' sudah ada")
                        error_count += 1
                        continue

                    # Tentukan metode pembayaran dari file import atau default
                    metode_pembayaran = None
                    metode_nama = str(row.get('metode_pembayaran', '')).strip() if row.get('metode_pembayaran') else ''
                    if metode_nama:
                        from apps.pos.models import MetodePembayaran
                        metode_pembayaran = MetodePembayaran.objects.filter(
                            nama__iexact=metode_nama, aktif=True
                        ).first()
                    if not metode_pembayaran:
                        # Fallback: gunakan metode pembayaran default pertama yang aktif
                        from apps.pos.models import MetodePembayaran
                        metode_pembayaran = MetodePembayaran.objects.filter(aktif=True).first()

                    # Ambil gudang target dari file import (by nama/kode) atau default
                    gudang_nama = str(row.get('gudang', '')).strip() if row.get('gudang') else ''
                    gudang_target = None
                    if gudang_nama:
                        gudang_target = Gudang.objects.filter(nama__iexact=gudang_nama, aktif=True).first()
                        if not gudang_target:
                            gudang_target = Gudang.objects.filter(kode__iexact=gudang_nama, aktif=True).first()
                    if not gudang_target:
                        gudang_target = Gudang.objects.filter(aktif=True).first()
                    if not gudang_target:
                        gudang_target = Gudang.objects.create(
                            kode='GD-DEFAULT', nama='Gudang Utama', aktif=True
                        )

                    # Tentukan status kena_ppn dari file import
                    kena_ppn_raw = str(row.get('kena_ppn', '')).strip().lower()
                    kena_ppn = kena_ppn_raw not in ('0', 'false', 'tidak', 'no')

                    # Buat produk baru
                    produk = Produk.objects.create(
                        sku=sku or '',
                        nama=str(row['nama']).strip(),
                        deskripsi=str(row.get('deskripsi', '')).strip() if row.get('deskripsi') else '',
                        kategori=kategori,
                        satuan=satuan,
                        harga_beli=float(row.get('harga_beli', 0) or 0),
                        harga_jual=float(row.get('harga_jual', 0) or 0),
                        barcode=str(row.get('barcode', '')).strip() if row.get('barcode') else '',
                        aktif=True,
                        kena_ppn=kena_ppn,
                        cabang=gudang_target,
                        dibuat_oleh=request.user,
                        metode_pembayaran=metode_pembayaran
                    )

                    # Tangani stok — masuk ke gudang_target (stok per-cabang)
                    stok_value = row.get('stok', None)
                    if stok_value is not None and str(stok_value).strip():
                        try:
                            stok_jumlah = float(str(stok_value).strip())
                            if stok_jumlah > 0:
                                Stok.objects.update_or_create(
                                    produk=produk,
                                    gudang=gudang_target,
                                    defaults={'jumlah': stok_jumlah}
                                )
                        except (ValueError, TypeError):
                            pass  # Abaikan nilai stok yang tidak valid

                    success_count += 1

                # Tangkap error KeyError - lanjutkan tanpa crash
                except KeyError as e:
                    errors.append(f"Baris {idx}: Kolom {str(e)} tidak ditemukan")
                    error_count += 1
                # Tangkap error Exception - lanjutkan tanpa crash
                except ProtectedError:
                    return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
                except Exception as e:
                    errors.append(f"Baris {idx}: {str(e)}")
                    error_count += 1

            # ===== BUAT PESAN RESPONSE =====
            success_msg = ''
            error_msg = ''

            if success_count > 0:
                success_msg = f'<strong>Berhasil import {success_count} produk!</strong>'

            if error_count > 0:
                error_details = '<br>'.join(errors[:5]) if len(errors) <= 5 else '<br>'.join(errors[:5]) + f'<br>... dan {len(errors)-5} error lainnya'
                error_msg = f'<br><strong>{error_count} produk gagal diimport</strong><br><small>{error_details}</small>'

            final_message = success_msg + error_msg

            # Kembalikan response sesuai tipe request (AJAX atau biasa)
            if is_ajax:
                if success_count > 0:
                    # Kembalikan respons JSON sukses ke klien
                    return JsonResponse({'success': True, 'message': final_message})
                else:
                    # Kembalikan respons JSON gagal ke klien
                    return JsonResponse({'success': False, 'message': final_message})
            else:
                if success_count > 0:
                    # Tampilkan pesan sukses ke user
                    messages.success(request, f'Berhasil import {success_count} produk!')
                if error_count > 0:
                    error_msg_plain = f'{error_count} produk gagal diimport. '
                    if len(errors) <= 5:
                        error_msg_plain += 'Error: ' + '; '.join(errors)
                    else:
                        error_msg_plain += 'Error: ' + '; '.join(errors[:5]) + f'... dan {len(errors)-5} error lainnya'
                    # Tampilkan pesan peringatan ke user
                    messages.warning(request, error_msg_plain)

        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            if is_ajax:
                # Kembalikan respons JSON gagal ke klien
                return JsonResponse({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'})
            # Tampilkan pesan error ke user
            messages.error(request, f'Terjadi kesalahan: {str(e)}')

        return self.get(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
                    # ║               API KONVERSI SATUAN                             ║
# ╚══════════════════════════════════════════════════════════════╝

# Wajib login - redirect ke login page jika belum login
@login_required
@permission_required('read', 'produk')
def api_konversi_satuan(request, produk_id):
    """
    API: Ambil daftar satuan yang tersedia untuk produk tertentu.
    URL: /produk/api/konversi-satuan/<produk_id>/

    Return JSON:
    {
        "success": true,
        "satuan_dasar": {"id": 1, "nama": "Kilogram", "singkatan": "kg"},
        "konversi": [
            {"satuan_id": 2, "satuan_nama": "Gram", "singkatan": "gr", "faktor": 1000, "arah": "turun"},
            {"satuan_id": 3, "satuan_nama": "Ons", "singkatan": "ons", "faktor": 10, "arah": "turun"},
        ]
    }
    """
    from apps.produk.models import KonversiSatuan

    # Blok penanganan error - coba jalankan kode di bawah
    try:
        # Query database - ambil satu data produk
        produk = Produk.objects.select_related('satuan').get(pk=produk_id)
    # Tangkap error Produk.DoesNotExist - lanjutkan tanpa crash
    except Produk.DoesNotExist:
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Produk tidak ditemukan'}, status=404)

    konversi_list = KonversiSatuan.get_konversi_untuk_produk(produk)

    return JsonResponse({
        'success': True,
        'satuan_dasar': {
            'id': produk.satuan.id,
            'nama': produk.satuan.nama,
            'singkatan': produk.satuan.singkatan,
    },
'harga_jual': float(produk.harga_jual),
            'harga_beli': float(produk.harga_beli),
        'konversi': konversi_list,
    })


# ╔══════════════════════════════════════════════════════════════╗
# ║                   SPAREPART CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class SparepartListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    model = Produk
    template_name = 'produk/sparepart_list.html'
    context_object_name = 'produk_list'
    permission_module = 'sparepart'
    permission_sub_module = 'daftar_sparepart'
    permission_action = 'read'

    def get_queryset(self):
        return Produk.objects.filter(
            tipe='sparepart'
        ).prefetch_related(
            'stok_set',
            'stok_set__gudang'
        ).select_related(
            'kategori',
            'satuan',
            'cabang'
        )

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        produk_list = context['produk_list']
        context['gudang_list'] = Gudang.objects.filter(aktif=True)
        total_produk = 0
        total_stok = 0
        total_nilai_beli = 0
        total_nilai_jual = 0
        for produk in produk_list:
            total_produk += 1
            stok = produk.stok_total
            total_stok += stok
            total_nilai_beli += produk.harga_beli * stok
            total_nilai_jual += produk.harga_jual * stok
        context['total_produk'] = total_produk
        context['total_stok'] = total_stok
        context['total_nilai_beli'] = total_nilai_beli
        context['total_nilai_jual'] = total_nilai_jual
        return context


class SparepartCreateView(SubModulePermissionMixin, CreateView):
    model = Produk
    form_class = ProdukForm
    template_name = 'produk/produk_form.html'
    success_url = reverse_lazy('produk:sparepart_list')
    permission_module = 'sparepart'
    permission_sub_module = 'tambah_sparepart'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Sparepart'
        context['is_sparepart'] = True
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'tipe' in form.fields:
            form.fields['tipe'].initial = 'sparepart'
            form.fields['tipe'].widget = forms.HiddenInput()
        return form

    def form_valid(self, form):
        form.instance.dibuat_oleh = self.request.user
        form.instance.tipe = 'sparepart'
        response = super().form_valid(form)
        stok_awal = self.request.POST.get('stok_awal')
        if stok_awal and float(stok_awal) > 0:
            gudang = form.instance.cabang
            if not gudang:
                gudang = Gudang.objects.filter(aktif=True).first()
                if not gudang:
                    gudang = Gudang.objects.create(
                        kode='GD-DEFAULT',
                        nama='Gudang Utama',
                        aktif=True
                    )
            Stok.objects.update_or_create(
                produk=form.instance,
                gudang=gudang,
                defaults={'jumlah': float(stok_awal)}
            )
        messages.success(self.request, 'Sparepart berhasil ditambahkan')
        return response


class SparepartUpdateView(SubModulePermissionMixin, UpdateView):
    model = Produk
    form_class = ProdukForm
    template_name = 'produk/produk_form.html'
    success_url = reverse_lazy('produk:sparepart_list')
    permission_module = 'sparepart'
    permission_sub_module = 'daftar_sparepart'
    permission_action = 'write'

    def get_queryset(self):
        return Produk.objects.filter(tipe='sparepart')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Sparepart'
        context['is_sparepart'] = True
        stok_queryset = Stok.objects.filter(
            produk=self.object
        ).select_related('gudang').order_by('gudang__nama')
        stok_per_cabang = []
        total_stok = 0
        for stok_item in stok_queryset:
            stok_per_cabang.append({
                'gudang_id': stok_item.gudang.id,
                'gudang_kode': stok_item.gudang.kode,
                'gudang_nama': stok_item.gudang.nama,
                'jumlah': stok_item.jumlah,
            })
            total_stok += stok_item.jumlah
        context['stok_per_cabang'] = stok_per_cabang
        context['total_stok'] = total_stok
        if stok_per_cabang:
            context['stok_saat_ini'] = total_stok
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'tipe' in form.fields:
            form.fields['tipe'].widget = forms.HiddenInput()
        return form

    def form_valid(self, form):
        form.instance.tipe = 'sparepart'
        response = super().form_valid(form)
        has_per_cabang_input = False
        for key in self.request.POST:
            if key.startswith('stok_cabang_'):
                has_per_cabang_input = True
                gudang_id = key.replace('stok_cabang_', '')
                stok_value = self.request.POST.get(key, '').strip()
                if stok_value:
                    try:
                        jumlah = float(stok_value)
                        Stok.objects.update_or_create(
                            produk=form.instance,
                            gudang_id=int(gudang_id),
                            defaults={'jumlah': jumlah}
                        )
                    except (ValueError, TypeError):
                        pass
        if not has_per_cabang_input:
            stok_input = self.request.POST.get('stok_awal')
            if stok_input:
                gudang = form.instance.cabang
                if not gudang:
                    gudang = Gudang.objects.filter(aktif=True).first()
                    if not gudang:
                        gudang = Gudang.objects.create(
                            kode='GD-DEFAULT',
                            nama='Gudang Utama',
                            aktif=True
                        )
                Stok.objects.update_or_create(
                    produk=form.instance,
                    gudang=gudang,
                    defaults={'jumlah': float(stok_input)}
                )
        messages.success(self.request, 'Sparepart berhasil diupdate')
        return response


class SparepartDeleteView(SubModulePermissionMixin, DeleteView):
    model = Produk
    success_url = reverse_lazy('produk:sparepart_list')
    permission_module = 'sparepart'
    permission_sub_module = 'daftar_sparepart'
    permission_action = 'delete'

    def get_queryset(self):
        return Produk.objects.filter(tipe='sparepart')

    def delete(self, request, *args, **kwargs):
        from django.http import JsonResponse
        self.object = self.get_object()
        try:
            produk_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Sparepart {produk_name} berhasil dihapus'
            })
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus sparepart: {str(e)}'
            }, status=400)


class SparepartImportView(SubModulePermissionMixin, TemplateView):
    template_name = 'produk/sparepart_import.html'
    permission_module = 'sparepart'
    permission_sub_module = 'sparepart_import'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['kategori_list'] = Kategori.objects.all()
        context['satuan_list'] = Satuan.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if 'file' not in request.FILES:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Tidak ada file yang diupload!'})
            messages.error(request, 'Tidak ada file yang diupload!')
            return self.get(request, *args, **kwargs)
        file = request.FILES['file']
        file_name = file.name.lower()
        if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Format file tidak didukung! Gunakan CSV atau Excel.'})
            messages.error(request, 'Format file tidak didukung! Gunakan CSV atau Excel.')
            return self.get(request, *args, **kwargs)
        try:
            import io
            import csv
            if file_name.endswith('.csv'):
                decoded_file = file.read().decode('utf-8-sig')
                lines = decoded_file.splitlines()
                if lines and lines[0].strip().startswith('sep='):
                    decoded_file = '\n'.join(lines[1:])
                io_string = io.StringIO(decoded_file)
                sample = io_string.read(1024)
                io_string.seek(0)
                try:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample, delimiters=',;\t')
                    delimiter = dialect.delimiter
                except Exception:
                    delimiter = ','
                reader = csv.DictReader(io_string, delimiter=delimiter)
                rows = list(reader)
            else:
                try:
                    file.seek(0)
                    content_bytes = file.read()
                    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
                    html_content = None
                    for enc in encodings:
                        try:
                            html_content = content_bytes.decode(enc)
                            break
                        except (UnicodeDecodeError, UnicodeError):
                            continue
                    if not html_content:
                        raise ValueError('Tidak dapat membaca file dengan encoding yang didukung')
                except Exception as e:
                    if is_ajax:
                        return JsonResponse({'success': False, 'message': f'Gagal membaca file: {str(e)}'})
                    messages.error(request, f'Gagal membaca file: {str(e)}')
                    return self.get(request, *args, **kwargs)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                table = soup.find('table')
                if not table:
                    if is_ajax:
                        return JsonResponse({'success': False, 'message': 'Tidak menemukan tabel dalam file Excel/HTML.'})
                    messages.error(request, 'Tidak menemukan tabel dalam file Excel/HTML.')
                    return self.get(request, *args, **kwargs)
                rows_data = []
                headers = []
                for i, tr in enumerate(table.find_all('tr')):
                    cols = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    if i == 0:
                        headers = cols
                    else:
                        if cols:
                            rows_data.append(dict(zip(headers, cols)))
                rows = rows_data
            success_count = 0
            error_count = 0
            error_details = ''
            for row in rows:
                try:
                    nama = (row.get('Nama') or row.get('nama') or row.get('Nama Produk') or row.get('nama_produk') or '').strip()
                    if not nama:
                        error_count += 1
                        error_details += f'<br>- Baris {success_count + error_count}: Nama kosong'
                        continue
                    sku = (row.get('SKU') or row.get('sku') or row.get('Kode') or '').strip()
                    if not sku:
                        import uuid
                        sku = f'SPR-{uuid.uuid4().hex[:8].upper()}'
                    kategori_nama = (row.get('Kategori') or row.get('kategori') or '').strip()
                    kategori = None
                    if kategori_nama:
                        kategori, _ = Kategori.objects.get_or_create(nama=kategori_nama)
                    satuan_nama = (row.get('Satuan') or row.get('satuan') or 'Unit').strip()
                    satuan, _ = Satuan.objects.get_or_create(nama=satuan_nama, defaults={'singkatan': satuan_nama[:3].upper()})
                    harga_beli_str = (row.get('Harga Beli') or row.get('harga_beli') or '0').strip().replace(',', '').replace('.', '').replace('Rp', '').replace(' ', '')
                    harga_jual_str = (row.get('Harga Jual') or row.get('harga_jual') or '0').strip().replace(',', '').replace('.', '').replace('Rp', '').replace(' ', '')
                    try:
                        harga_beli = float(harga_beli_str) if harga_beli_str else 0
                    except ValueError:
                        harga_beli = 0
                    try:
                        harga_jual = float(harga_jual_str) if harga_jual_str else 0
                    except ValueError:
                        harga_jual = 0
                    Produk.objects.create(
                        sku=sku,
                        nama=nama,
                        tipe='sparepart',
                        kategori=kategori,
                        satuan=satuan,
                        harga_beli=harga_beli,
                        harga_jual=harga_jual,
                        dibuat_oleh=request.user if request.user.is_authenticated else None,
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    error_details += f'<br>- Baris {success_count + error_count}: {str(e)}'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f'Berhasil import {success_count} sparepart!',
                    'success_count': success_count,
                    'error_count': error_count,
                    'error_details': error_details
                })
            if success_count > 0:
                messages.success(request, f'Berhasil import {success_count} sparepart!')
            if error_count > 0:
                messages.warning(request, f'{error_count} sparepart gagal diimport. {error_details}')
            return redirect('produk:sparepart_list')
        except Exception as e:
            logger.error(f"Error import sparepart: {str(e)}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': f'Gagal import sparepart: {str(e)}'})
            messages.error(request, f'Gagal import sparepart: {str(e)}')
            return self.get(request, *args, **kwargs)


@login_required
@permission_required('update', 'produk')
def update_barcode(request, pk):
    """
    API: Update field barcode produk via AJAX POST.
    URL: /produk/<pk>/update-barcode/
    Digunakan oleh modal Generator Barcode di halaman Daftar Produk.
    Permission: produk.edit (can_edit)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    # Permission check: hanya user dengan hak edit produk yang bisa simpan barcode
    from apps.core.permissions import has_permission
    if not request.user.is_superuser and not has_permission(request.user, 'write', 'produk'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengubah barcode produk.'}, status=403)
    
    import json
    try:
        data = json.loads(request.body)
        barcode_value = data.get('barcode', '').strip()
    except json.JSONDecodeError:
        barcode_value = request.POST.get('barcode', '').strip()
    
    try:
        produk = Produk.objects.get(pk=pk)
    except Produk.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Produk tidak ditemukan'}, status=404)
    
    # Cek apakah barcode sudah dipakai produk lain
    if barcode_value:
        existing = Produk.objects.filter(barcode=barcode_value).exclude(pk=pk).first()
        if existing:
            return JsonResponse({
                'success': False,
                'message': f'Barcode "{barcode_value}" sudah digunakan oleh produk: {existing.nama}'
            })
    
    produk.barcode = barcode_value if barcode_value else None
    produk.save(update_fields=['barcode'])
    
    return JsonResponse({
        'success': True,
        'message': f'Barcode produk "{produk.nama}" berhasil diperbarui',
        'barcode': produk.barcode or ''
    })

