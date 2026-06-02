"""
==========================================================================
 USER MANAGEMENT VIEWS - CRUD Manajemen User ERP
==========================================================================
 File ini menangani semua operasi CRUD untuk manajemen user:

 Page Views (dengan template):
 - UserManagementIndexView → Daftar user + filter (role, status, search)
 - UserAddView             → Form tambah user baru (set password + role)
 - UserDetailView          → Detail user (role, permission)
 - UserEditView            → Edit user (username, role, status)
 - UserDeleteView          → Hapus user (AJAX JSON response)

 AJAX Views (return JSON):
 - UserDetailAjaxView      → Data user untuk modal popup detail

 Helper Functions:
 - get_role_display()       → Ambil nama role dari dynamic roles

 Proteksi akses via mixins:
 - ReadPermissionMixin   → Cek can_view pada module user_management
 - CreatePermissionMixin → Cek can_create
 - UpdatePermissionMixin → Cek can_edit
 - DeletePermissionMixin → Cek can_delete

 Terhubung dengan:
 - auth/models.py → Profile (role, avatar)
 - apps/core/models.py → RolePermission (dynamic roles)
 - apps/core/mixins.py → Permission mixins
 - templates/user_management/ → Template HTML
==========================================================================
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, TemplateView, DetailView, UpdateView, DeleteView, CreateView, View
from django.utils.decorators import method_decorator
from web_project import TemplateLayout
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from auth.models import Profile
from apps.core.models import RolePermission
from apps.core.mixins import AdminOrSuperuserMixin, UpdatePermissionMixin, DeletePermissionMixin, CreatePermissionMixin, ReadPermissionMixin
from django.db import transaction


def get_role_display(role_code):
    """Mendapatkan nama tampilan role dari daftar role dinamis"""
    all_roles = dict(RolePermission.get_all_roles())
    return all_roles.get(role_code, role_code.replace('_', ' ').title())


class UserManagementIndexView(ReadPermissionMixin, ListView):
    """
    View untuk menampilkan DAFTAR SEMUA USER di sistem ERP.

    Fitur:
    - Tabel user dengan pagination (25 per halaman)
    - Filter berdasarkan: role, status aktif/tidak, pencarian nama/email
    - Metrik ringkasan: total users
    - Proteksi: ReadPermissionMixin → cek can_view modul user_management

    Template: user_management/index.html
    URL: /users/ (namespace: user_management:index)
    """
    model = User
    template_name = 'user_management/index.html'
    context_object_name = 'user_list'
    paginate_by = 25
    ordering = ['username']
    permission_module = 'user_management'

    def get_queryset(self):
        """Override queryset — filter atau optimasi query data."""
        queryset = super().get_queryset()
        
        # Penyaringan / Filtering
        query = self.request.GET.get('q')
        role = self.request.GET.get('role')
        status = self.request.GET.get('status')
        
        if query:
            queryset = queryset.filter(username__icontains=query) | queryset.filter(email__icontains=query) | queryset.filter(first_name__icontains=query)
        
        if role:
            # Filter berdasarkan role dari Profile - mendukung semua kode role
            queryset = queryset.filter(profile__role=role)
                
        if status:
            if status == 'active':
                queryset = queryset.filter(is_active=True)
            elif status == 'inactive':
                queryset = queryset.filter(is_active=False)
            
        return queryset

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['role_choices'] = RolePermission.get_all_roles()
        # Tambah metrik ringkasan
        queryset = self.get_queryset()
        context['total_users'] = queryset.count()
        return context


@method_decorator(login_required, name='dispatch')
class UserAddView(CreatePermissionMixin, CreateView):
    """
    View untuk MENAMBAHKAN USER BARU ke sistem.

    Fitur:
    - Form input: username, email, nama, password, role
    - Auto-set password dari form (default: 'defaultPassword123')
    - Auto-create Profile dengan role yang dipilih
    - Proteksi: CreatePermissionMixin → cek can_create modul user_management

    Template: user_management/user_form.html
    URL: /users/add/ (namespace: user_management:add)
    """
    model = User
    template_name = 'user_management/user_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    success_url = reverse_lazy('user_management:index')
    permission_module = 'user_management'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah User Baru'
        # Filter SUPERUSER dari dropdown jika pembuka form bukan SUPERUSER
        all_roles = RolePermission.get_all_roles()
        is_my_role_super = hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'SUPERUSER'
        if not self.request.user.is_superuser and not is_my_role_super:
            all_roles = [(code, name) for code, name in all_roles if code != 'SUPERUSER']
        context['role_choices'] = all_roles
        return context
    
    
    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        user = form.save(commit=False)
        password = self.request.POST.get('password', 'defaultPassword123')
        user.set_password(password)
        user.save()
        
        # Set role dari form
        role = self.request.POST.get('role', 'USER')
        try:
            user.profile.role = role
            user.profile.save()
        except Exception:
            # Buat profile jika belum ada
            Profile.objects.create(user=user, email=user.email, role=role)
        
        messages.success(self.request, f'User {user.username} berhasil ditambahkan dengan role {role}!')
        return super().form_valid(form)


class UserDetailView(ReadPermissionMixin, DetailView):
    """
    View untuk menampilkan DETAIL USER (halaman penuh).

    Menampilkan informasi lengkap user: username, email, role,
    tanggal bergabung, dan permission yang dimiliki.

    Template: user_management/user_detail.html
    URL: /users/<pk>/detail/ (namespace: user_management:detail)
    """
    model = User
    template_name = 'user_management/user_detail.html'
    context_object_name = 'user_obj'
    pk_url_kwarg = 'pk'
    permission_module = 'user_management'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Detail User: {self.object.username}'
        try:
            context['user_role'] = self.object.profile.role
            context['role_display'] = get_role_display(self.object.profile.role)
        except Exception:
            context['user_role'] = 'USER'
            context['role_display'] = 'User'
        return context



class UserDetailAjaxView(ReadPermissionMixin, View):
    """
    AJAX endpoint untuk menampilkan detail user di MODAL POPUP.

    Dipanggil via JavaScript saat user klik tombol "Detail" di tabel.
    Return JSON berisi: username, nama, email, role, permissions, dll.
    Berbeda dari UserDetailView yang return halaman HTML penuh.

    URL: /users/<pk>/detail-ajax/ (namespace: user_management:detail_ajax)
    Return: JsonResponse
    """
    permission_module = 'user_management'

    def get(self, request, pk):
        """Handle HTTP GET request."""
        try:
            user = get_object_or_404(User, pk=pk)
        
            # Ambil data profile
            role = 'USER'
            role_display = 'User'
            phone = '-'
            try:
                if hasattr(user, 'profile'):
                    role = user.profile.role or 'USER'
                    role_display = get_role_display(role)
                    phone = user.profile.phone or '-'
            except Exception:
                pass
        
            # Ambil permissions untuk role user ini
            permissions = []
            try:
                role_perms = RolePermission.objects.filter(role=role)
                for perm in role_perms:
                    module_name = perm.get_module_display()
                    if perm.can_view:
                        permissions.append(f"{module_name}: View")
                    if perm.can_create:
                        permissions.append(f"{module_name}: Create")
                    if perm.can_edit:
                        permissions.append(f"{module_name}: Edit")
                    if perm.can_delete:
                        permissions.append(f"{module_name}: Delete")
            except Exception:
                pass
        
            return JsonResponse({
                'success': True,
                'user': {
                    'id': user.pk,
                    'username': user.username,
                    'full_name': user.get_full_name() or user.username,
                    'email': user.email or '-',
                    'phone': phone,
                    'role': role_display,
                    'is_active': user.is_active,
                    'date_joined': user.date_joined.strftime('%d %b %Y') if user.date_joined else '-',
                    'last_login': user.last_login.strftime('%d %b %Y %H:%M') if user.last_login else 'Never',
                    'avatar': user.profile.avatar.url if hasattr(user, 'profile') and user.profile.avatar else None,
                    'permissions': permissions[:10] if permissions else ['No specific permissions'],
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)


@method_decorator(login_required, name='dispatch')
class UserEditView(UpdatePermissionMixin, UpdateView):
    """
    View untuk MENGEDIT DATA USER yang sudah ada.

    Fitur:
    - Form edit: username, email, nama, role, status aktif
    - Update role di Profile model
    - Smart redirect: kembali ke halaman asal (roles/users)
    - Proteksi: UpdatePermissionMixin → cek can_edit modul user_management

    Template: user_management/user_form.html (shared dengan UserAddView)
    URL: /users/<pk>/edit/ (namespace: user_management:edit)
    """
    model = User
    template_name = 'user_management/user_form.html'
    fields = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('user_management:index')
    permission_module = 'user_management'

    def dispatch(self, request, *args, **kwargs):
        """Proteksi SUPERUSER: non-SUPERUSER tidak boleh edit akun SUPERUSER."""
        user_target = self.get_object()
        is_my_role_super = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'SUPERUSER')
        target_is_super = hasattr(user_target, 'profile') and user_target.profile.role == 'SUPERUSER'
        if target_is_super and not is_my_role_super:
            messages.error(request, 'Role SUPERUSER bersifat khusus dan tidak dapat diedit oleh role Anda.')
            return redirect('user_management:index')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit User: {self.object.username}'
        context['is_edit'] = True
        # Filter SUPERUSER dari dropdown jika pembuka form bukan SUPERUSER
        all_roles = RolePermission.get_all_roles()
        is_my_role_super = self.request.user.is_superuser or (hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'SUPERUSER')
        if not is_my_role_super:
            all_roles = [(code, name) for code, name in all_roles if code != 'SUPERUSER']
        context['role_choices'] = all_roles
        try:
            context['current_role'] = self.object.profile.role
        except Exception:
            context['current_role'] = 'USER'
        # Simpan referrer agar bisa redirect kembali ke halaman asal
        referer = self.request.GET.get('next') or self.request.META.get('HTTP_REFERER', '')
        if '/access/roles/' in referer:
            context['next_url'] = '/access/roles/'
        return context

    def get_success_url(self):
        """URL redirect setelah operasi berhasil."""
        next_url = self.request.POST.get('next_url', '')
        if next_url and '/access/roles/' in next_url:
            return '/access/roles/'
        return str(self.success_url)

    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        role = self.request.POST.get('role')
        if role:
            try:
                self.object.profile.role = role
                self.object.profile.save()
            except Exception:
                # Buat profile jika belum ada
                Profile.objects.create(user=self.object, email=self.object.email, role=role)
    
        messages.success(self.request, f'User {form.instance.username} berhasil diupdate')
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class UserDeleteView(DeletePermissionMixin, DeleteView):
    """
    View untuk MENGHAPUS USER dari sistem.

    Menggunakan AJAX delete — return JsonResponse (bukan redirect).
    Frontend menampilkan konfirmasi via SweetAlert sebelum menghapus.
    Proteksi: DeletePermissionMixin → cek can_delete modul user_management.

    URL: /users/<pk>/delete/ (namespace: user_management:delete)
    Return: JsonResponse (success/fail)
    """
    model = User
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('user_management:index')
    permission_module = 'user_management'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Hapus User: {self.object.username}'
        return context
    
    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        user = self.get_object()
        username = user.username

        # Proteksi: tidak boleh hapus diri sendiri
        if user == request.user:
            return JsonResponse({
                'success': False,
                'message': 'Anda tidak dapat menghapus akun sendiri!'
            }, status=400)

        # Proteksi SUPERUSER: non-SUPERUSER tidak boleh hapus akun SUPERUSER
        is_my_role_super = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'SUPERUSER')
        target_is_super = hasattr(user, 'profile') and user.profile.role == 'SUPERUSER'
        if target_is_super and not is_my_role_super:
            return JsonResponse({
                'success': False,
                'message': 'Role SUPERUSER bersifat khusus dan tidak dapat dihapus oleh role Anda!'
            }, status=400)

        try:
            user.delete()
            return JsonResponse({
                'success': True,
                'message': f'User {username} berhasil dihapus'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus user: {str(e)}'
            }, status=400)


@login_required
def user_toggle_status(request, pk):
    """Toggle status aktif/nonaktif user (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        user = get_object_or_404(User, pk=pk)

        # Proteksi: tidak boleh toggle diri sendiri
        if user == request.user:
            return JsonResponse({'success': False, 'message': 'Anda tidak dapat menonaktifkan akun sendiri!'}, status=400)

        # Proteksi SUPERUSER: non-SUPERUSER tidak boleh toggle akun SUPERUSER
        is_my_role_super = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'SUPERUSER')
        target_is_super = hasattr(user, 'profile') and user.profile.role == 'SUPERUSER'
        if target_is_super and not is_my_role_super:
            return JsonResponse({'success': False, 'message': 'Role SUPERUSER bersifat khusus dan statusnya tidak dapat diubah oleh role Anda!'}, status=400)

        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        
        status_text = 'diaktifkan' if user.is_active else 'dinonaktifkan'
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} berhasil {status_text}',
            'is_active': user.is_active,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Gagal mengubah status: {str(e)}'
        }, status=400)

