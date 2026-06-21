"""
==========================================================================
 PAGES VIEWS - View untuk Halaman Statis (Error, Maintenance, dll)
==========================================================================
 View generik untuk halaman-halaman statis/misc:
 - Error page (404/500)
 - Under Maintenance page
 - Coming Soon page
 - Not Authorized page (403)
 - Server Error page

 Semua halaman menggunakan layout_blank.html (tanpa sidebar/navbar)
 karena ini adalah halaman yang ditampilkan saat terjadi error
 atau saat user tidak memiliki akses.

 Terhubung dengan:
 - pages/urls.py → Routing ke template berbeda via template_name parameter
 - web_project → TemplateLayout untuk inisialisasi global layout
 - web_project/template_helpers/theme.py → TemplateHelper untuk set layout
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

from django.shortcuts import redirect
from django.views.generic import TemplateView
from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class MiscPagesView(TemplateView):
    """
    View generik untuk halaman statis/error.
    Template ditentukan via parameter di urls.py, bukan di sini.
    Menggunakan layout_blank.html (halaman tanpa sidebar/navbar).
    """
    # Menambahkan data konteks tambahan ke template
    def get(self, request, *args, **kwargs):
        if self.template_name == 'pages_misc_under_maintenance.html':
            from apps.core.license_models import LicenseConfig
            try:
                from apps.pengaturan.models import PengaturanPerusahaan
                pengaturan = PengaturanPerusahaan.load()
                local_maintenance = getattr(pengaturan, 'maintenance_mode', False)
            except Exception:
                local_maintenance = False
                
            config = LicenseConfig.get_config()
            # Jika user terlanjur mendarat di halaman perbaikan, tapi sekarang Maintenance Mode (baik remote CLS maupun lokal) ternyata SUDAH DIMATIKAN
            if not config.is_maintenance and not local_maintenance:
                return redirect('/')
                
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Inisialisasi layout global (tema, warna, dll)
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Set layout ke blank (tanpa sidebar dan navbar)
        context.update(
            {
                "layout_path": TemplateHelper.set_layout("layout_blank.html", context),
            }
        )

        # Load config lisensi
        from apps.core.license_models import LicenseConfig
        try:
            lc = LicenseConfig.get_config()
            context['license_config'] = lc
        except Exception:
            context['license_config'] = None

        return context
