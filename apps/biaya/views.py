"""
==========================================================================
 BIAYA VIEWS - View CRUD untuk Kategori Biaya & Transaksi Biaya
==========================================================================
 File ini berisi views untuk modul Biaya (Expense):

 KATEGORI BIAYA CRUD:
   KategoriBiayaListView   → Daftar kategori biaya
   KategoriBiayaCreateView → Tambah kategori baru
   KategoriBiayaUpdateView → Edit kategori
   KategoriBiayaDeleteView → Hapus kategori (JSON)

 TRANSAKSI BIAYA CRUD:
   TransaksiBiayaListView   → Daftar transaksi + total nominal
   TransaksiBiayaCreateView → Catat pengeluaran baru + notifikasi Telegram
   TransaksiBiayaDetailView → Detail transaksi + riwayat activity log
   TransaksiBiayaUpdateView → Edit transaksi
   TransaksiBiayaDeleteView → Hapus transaksi + log sebelum hapus
   TransaksiBiayaPrintView  → Cetak bukti pengeluaran

 Fitur:
 - Detail transaksi menampilkan riwayat activity log (audit trail)
 - Notifikasi Telegram dikirim saat transaksi baru dibuat
 - Activity log dicatat untuk setiap perubahan (create/update/delete)
==========================================================================
"""

# Import dari framework Django
from django.shortcuts import render, redirect
from django.db.models import ProtectedError
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.urls import reverse_lazy
# Import dari framework Django
from django.contrib import messages
# Import dari modul internal proyek
from apps.biaya.models import KategoriBiaya, TransaksiBiaya
# Import dari modul internal proyek
from apps.biaya.forms import KategoriBiayaForm, TransaksiBiayaForm
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from django.db import transaction


# ╔══════════════════════════════════════════════════════════════╗
# ║               KATEGORI BIAYA CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class KategoriBiayaListView(ReadPermissionMixin, ListView):
    """Daftar kategori biaya. URL: /biaya/kategori/"""
    paginate_by = 50
    model = KategoriBiaya
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/kategori_list.html'
    context_object_name = 'kategori_list'
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_kategori — untuk ditampilkan di template
        context['total_kategori'] = self.get_queryset().count()
        return context


class KategoriBiayaCreateView(CreatePermissionMixin, CreateView):
    """Tambah kategori biaya. URL: /biaya/kategori/add/"""
    model = KategoriBiaya
    form_class = KategoriBiayaForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/kategori_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:kategori')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Tambah Kategori Biaya'
        return context

    def form_valid(self, form):
        """Simpan kategori biaya baru."""
        messages.success(self.request, 'Kategori biaya berhasil ditambahkan')
        return super().form_valid(form)


class KategoriBiayaUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit kategori biaya. URL: /biaya/kategori/<pk>/edit/"""
    model = KategoriBiaya
    form_class = KategoriBiayaForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/kategori_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:kategori')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Edit Kategori Biaya'
        return context

    def form_valid(self, form):
        """Update kategori biaya."""
        messages.success(self.request, 'Kategori biaya berhasil diperbarui')
        return super().form_valid(form)


class KategoriBiayaDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus kategori biaya — return JSON untuk AJAX."""
    model = KategoriBiaya
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:kategori')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error — coba jalankan kode di bawah
        try:
            kategori_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Kategori biaya {kategori_name} berhasil dihapus'
            })
        # Tangkap error Exception — lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus kategori biaya: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
# ║              TRANSAKSI BIAYA CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class TransaksiBiayaListView(ReadPermissionMixin, ListView):
    """
    Daftar transaksi biaya + summary nominal.
    URL: /biaya/transaksi/
    """
    paginate_by = 50
    model = TransaksiBiaya
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/transaksi_list.html'
    context_object_name = 'transaksi_list'
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari framework Django
        from django.db.models import Sum
        queryset = self.get_queryset()
        # Data konteks: total_transaksi_biaya — untuk ditampilkan di template
        context['total_transaksi_biaya'] = queryset.count()
        # Data konteks: total_amount_biaya — untuk ditampilkan di template
        context['total_amount_biaya'] = queryset.aggregate(Sum('jumlah'))['jumlah__sum'] or 0
        return context


class TransaksiBiayaCreateView(CreatePermissionMixin, CreateView):
    """
    Catat pengeluaran biaya baru.
    URL: /biaya/transaksi/add/

    Setelah save:
    - Kirim notifikasi Telegram
    - Log activity
    """
    model = TransaksiBiaya
    form_class = TransaksiBiayaForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/transaksi_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:transaksi')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Catat Pengeluaran Biaya'
        return context

    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        form.instance.dibuat_oleh = self.request.user
        response = super().form_valid(form)

        # Kirim notifikasi Telegram
        try:
            # Import dari modul internal proyek
            from apps.automation.signals import kirim_notifikasi_biaya
            kirim_notifikasi_biaya(self.object)
        # Tangkap error Exception — lanjutkan tanpa crash
        except ProtectedError:
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            pass

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            self.request,
            action='create',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Mencatat transaksi biaya: {self.object.nomor_transaksi} - Rp {self.object.jumlah:,.0f}'
        )

        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Transaksi biaya berhasil dicatat')
        return response


class TransaksiBiayaDetailView(ReadPermissionMixin, TemplateView):
    """
    Detail transaksi biaya + RIWAYAT ACTIVITY LOG.
    URL: /biaya/transaksi/<pk>/

    Menampilkan audit trail: siapa melakukan apa dan kapan
    untuk transaksi biaya ini.
    """
    template_name = 'biaya/transaksi_detail.html'
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari framework Django
        from django.shortcuts import get_object_or_404
        # Import dari modul internal proyek
        from apps.activity_log.models import UserActivity

        transaksi_id = kwargs.get('pk')
        transaksi = get_object_or_404(TransaksiBiaya, pk=transaksi_id)
        # Data konteks: transaksi — untuk ditampilkan di template
        context['transaksi'] = transaksi

        # Riwayat activity log (audit trail)
        context['activity_logs'] = UserActivity.objects.filter(
            model_name__icontains='transaksi',
            object_id=str(transaksi.pk)
        ).select_related('user').order_by('-timestamp')[:50]

        return context


class TransaksiBiayaUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Edit transaksi biaya + log activity. URL: /biaya/transaksi/<pk>/edit/

    ⚠ PROTEKSI: Transaksi yang sudah 'approved' atau 'rejected' TIDAK bisa diedit.
    Untuk koreksi, buat transaksi baru atau ubah status terlebih dahulu.
    """
    model = TransaksiBiaya
    form_class = TransaksiBiayaForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'biaya/transaksi_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:transaksi')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def dispatch(self, request, *args, **kwargs):
        """Cek apakah transaksi masih boleh diedit sebelum memproses request."""
        self.object = self.get_object()
        if self.object.status in ['approved', 'rejected']:
            messages.error(request, f'Transaksi biaya {self.object.nomor_transaksi} sudah berstatus "{self.object.get_status_display()}" dan tidak dapat diedit.')
            return redirect('biaya:transaksi_detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Edit Transaksi Biaya'
        return context

    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        response = super().form_valid(form)

        # Import dari modul internal proyek
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            self.request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Mengubah transaksi biaya: {self.object.nomor_transaksi}'
        )

        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Transaksi biaya berhasil diperbarui')
        return response


class TransaksiBiayaDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus transaksi biaya — log activity SEBELUM hapus, lalu return JSON.
    URL: /biaya/transaksi/<pk>/delete/
    """
    model = TransaksiBiaya
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('biaya:transaksi')
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Log activity SEBELUM hapus (agar referensi masih ada)
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='delete',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Menghapus transaksi biaya: {self.object.nomor_transaksi}'
        )

        # Blok penanganan error — coba jalankan kode di bawah
        try:
            nomor_transaksi = self.object.nomor_transaksi
            self.object.delete()
            return JsonResponse({
                'success': True,
                'message': f'Transaksi biaya {nomor_transaksi} berhasil dihapus'
            })
        # Tangkap error Exception — lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus transaksi biaya: {str(e)}'
            }, status=400)


class TransaksiBiayaPrintView(ReadPermissionMixin, TemplateView):
    """
    Cetak bukti pengeluaran biaya.
    URL: /biaya/transaksi/<pk>/print/
    Menggunakan data perusahaan + template cetak 'expense'.
    """
    template_name = 'biaya/transaksi_biaya_print.html'
    # Modul permission yang dicek: 'biaya'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        # Import dari modul internal proyek
        from apps.pengaturan.models import PengaturanPerusahaan, TemplateCetak
        # Import dari framework Django
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=self.kwargs['pk'])
        # Data konteks: transaksi — untuk ditampilkan di template
        context['transaksi'] = transaksi
        # Data konteks: perusahaan — untuk ditampilkan di template
        context['perusahaan'] = PengaturanPerusahaan.load()
        # Data konteks: template — untuk ditampilkan di template
        context['template'] = TemplateCetak.get_template('expense')
        return context


class TransaksiBiayaApproveView(UpdatePermissionMixin, TemplateView):
    """
    Approve (Setujui) transaksi biaya — ubah status ke 'approved'.
    URL: /biaya/transaksi/<pk>/approve/
    Method: POST (via AJAX)
    
    Alur:
    1. Cek status saat ini (hanya draft/submitted boleh di-approve)
    2. Ubah status → 'approved'
    3. Catat siapa yang menyetujui (disetujui_oleh)
    4. Log activity
    """
    template_name = 'biaya/transaksi_detail.html'
    permission_module = 'biaya'

    def post(self, request, *args, **kwargs):
        """Proses approve transaksi biaya via AJAX POST."""
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=kwargs['pk'])

        # Validasi: hanya status draft/submitted yang bisa di-approve
        if transaksi.status not in ['draft', 'submitted']:
            return JsonResponse({
                'success': False,
                'message': f'Transaksi dengan status "{transaksi.get_status_display()}" tidak dapat disetujui.'
            }, status=400)

        # Simpan status lama untuk log
        old_status = transaksi.get_status_display()

        # Update status ke approved
        transaksi.status = 'approved'
        transaksi.save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=transaksi.pk,
            object_repr=str(transaksi),
            description=f'Menyetujui transaksi biaya: {transaksi.nomor_transaksi} (status: {old_status} → Disetujui)'
        )

        return JsonResponse({
            'success': True,
            'message': f'Transaksi biaya {transaksi.nomor_transaksi} berhasil disetujui.'
        })


class TransaksiBiayaRejectView(UpdatePermissionMixin, TemplateView):
    """
    Reject (Tolak) transaksi biaya — ubah status ke 'rejected'.
    URL: /biaya/transaksi/<pk>/reject/
    Method: POST (via AJAX)
    
    Alur:
    1. Cek status saat ini (hanya draft/submitted boleh di-reject)
    2. Ubah status → 'rejected'
    3. Log activity
    """
    template_name = 'biaya/transaksi_detail.html'
    permission_module = 'biaya'

    def post(self, request, *args, **kwargs):
        """Proses reject transaksi biaya via AJAX POST."""
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=kwargs['pk'])

        # Validasi: hanya status draft/submitted yang bisa di-reject
        if transaksi.status not in ['draft', 'submitted']:
            return JsonResponse({
                'success': False,
                'message': f'Transaksi dengan status "{transaksi.get_status_display()}" tidak dapat ditolak.'
            }, status=400)

        # Simpan status lama untuk log
        old_status = transaksi.get_status_display()

        # Update status ke rejected
        transaksi.status = 'rejected'
        transaksi.save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=transaksi.pk,
            object_repr=str(transaksi),
            description=f'Menolak transaksi biaya: {transaksi.nomor_transaksi} (status: {old_status} → Ditolak)'
        )

        return JsonResponse({
            'success': True,
            'message': f'Transaksi biaya {transaksi.nomor_transaksi} berhasil ditolak.'
        })
