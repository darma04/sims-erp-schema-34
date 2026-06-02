"""
==========================================================================
 ROLE MANAGEMENT VIEWS - CRUD Role & Permission Matrix
==========================================================================
 File ini menangani manajemen ROLE (terpisah dari permission per-record):

 Page View:
 - RoleListView          → Halaman kartu role + daftar user per role

 AJAX Views (return JSON):
 - RoleDataAjaxView      → Ambil data permission suatu role (GET)
 - RoleCreateAjaxView    → Buat role baru + set permission (POST)
 - RoleUpdateAjaxView    → Update permission role + rename role (POST)
 - RoleDeleteView        → Hapus role + reset user ke tanpa role (POST)

 Fitur penting:
 - Role baru otomatis tersedia di seluruh sistem (dynamic roles)
 - Rename role → semua user & permission ikut terupdate
 - Hapus role → bisa force (reset user ke tanpa role)
 - SUPERUSER tidak bisa dihapus
 - Cache permission di-invalidasi otomatis setelah perubahan

 Terhubung dengan:
 - apps/core/models.py → RolePermission (dynamic roles)
 - apps/core/cache_utils.py → invalidate_role_permissions_cache()
 - auth/models.py → Profile (field role)
 - templates/permission_management/role_list.html
==========================================================================
"""

# Import dari framework Django
from django.shortcuts import render
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import ListView, View
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.http import JsonResponse
# Import dari framework Django
from django.contrib.auth.models import User
# Import dari framework Django
from django.db.models import Count, Q

from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.core.models import RolePermission
# Import dari modul internal proyek
from apps.core.mixins import SuperuserRequiredMixin
from apps.core.cache_utils import invalidate_role_permissions_cache, invalidate_user_permissions_cache
from auth.models import Profile


@method_decorator(login_required, name='dispatch')
class RoleListView(SuperuserRequiredMixin, ListView):
    """
    Display Role cards with user counts and users datatables
    """
    model = User
    # Template HTML yang digunakan untuk render halaman
    template_name = 'permission_management/role_list.html'
    context_object_name = 'users'
    
    # Override queryset — filter atau optimasi query data
    def get_queryset(self):
        # Ambil semua user beserta profile mereka
        """Override queryset — filter atau optimasi query data."""
        return User.objects.select_related('profile').all()
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Roles Management'
        
        # Ambil semua pilihan role (termasuk role dinamis)
        role_choices = RolePermission.get_all_roles()
        
        # PERFORMANCE: Pre-fetch all permissions for all roles in one query
        from django.db.models import Prefetch
        # Query database — ambil semua data all_permissions
        all_permissions = RolePermission.objects.select_related().all()
        
        # PERFORMANCE: Pre-fetch all users with profiles in one query
        all_users_with_role = User.objects.select_related('profile').all()
        
        # Hitung jumlah user per role
        role_data = []
        for role_code, role_name in role_choices:
            # Filter data yang sudah di-prefetch, bukan membuat query baru
            users_with_role = [u for u in all_users_with_role if hasattr(u, 'profile') and u.profile.role == role_code]
            user_count = len(users_with_role)
            
            # Ambil permissions untuk role ini (dari data yang sudah di-prefetch)
            permissions = [p for p in all_permissions if p.role == role_code]
            
            # Hitung ringkasan permission - hitung hanya module dengan permission VIEW
            total_permissions = sum(1 for p in permissions if p.can_view)
            
            role_data.append({
                'code': role_code,
                'name': role_name,
                'user_count': user_count,
                'users': users_with_role[:4],  # First 4 for avatar group
                'total_permissions': total_permissions,
                'permissions': permissions
            })
        
        # Data konteks: roles — untuk ditampilkan di template
        context['roles'] = role_data
        # Data konteks: role_choices — untuk ditampilkan di template
        context['role_choices'] = role_choices
        # Data konteks: modules — untuk ditampilkan di template
        context['modules'] = RolePermission.MODULE_CHOICES
        # Data konteks: user_role — untuk ditampilkan di template
        context['user_role'] = getattr(self.request.user.profile, 'role', None) if hasattr(self.request.user, 'profile') else None
        
        # Bangun struktur module dengan sub-module untuk JavaScript modal
        import json
        module_structure = {}
        for module_code, module_name in RolePermission.MODULE_CHOICES:
            module_structure[module_code] = {
                'name': module_name,
                'sub_modules': [
                    {'code': sub_code, 'name': sub_name}
                    for sub_code, sub_name in RolePermission.SUB_MODULE_CHOICES.get(module_code, [])
                ]
            }
        # Data konteks: module_structure — untuk ditampilkan di template
        context['module_structure'] = json.dumps(module_structure)
        
        return context


@method_decorator(login_required, name='dispatch')
class RoleDataAjaxView(SuperuserRequiredMixin, View):
    """
    AJAX endpoint to get role data for editing
    """
    
    def get(self, request, role):
        """Handle HTTP GET request."""
        try:
            role_name = dict(RolePermission.get_all_roles()).get(role, role.replace('_', ' ').title())

            # SUPERUSER selalu punya semua permission — generate full list untuk UI
            if role == 'SUPERUSER':
                permissions_list = []
                for module_code, module_name in RolePermission.MODULE_CHOICES:
                    # Module-level permission
                    permissions_list.append({
                        'module': module_code,
                        'sub_module': None,
                        'can_view': True,
                        'can_create': True,
                        'can_edit': True,
                        'can_delete': True,
                    })
                    # Sub-module permissions
                    for sub_code, sub_name in RolePermission.SUB_MODULE_CHOICES.get(module_code, []):
                        permissions_list.append({
                            'module': module_code,
                            'sub_module': sub_code,
                            'can_view': True,
                            'can_create': True,
                            'can_edit': True,
                            'can_delete': True,
                        })
                return JsonResponse({
                    'success': True,
                    'role_code': role,
                    'role_display': role_name,
                    'permissions': permissions_list,
                    'is_superuser': True,
                })

            # Role biasa — ambil dari database
            permissions = RolePermission.objects.filter(role=role).values(
                'module', 'sub_module', 'can_view', 'can_create', 'can_edit', 'can_delete'
            )
            permissions_list = list(permissions)

            return JsonResponse({
                'success': True,
                'role_code': role,
                'role_display': role_name,
                'permissions': permissions_list,
                'is_superuser': False,
            })

        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)


@method_decorator(login_required, name='dispatch')
class RoleCreateAjaxView(SuperuserRequiredMixin, View):
    """
    AJAX endpoint to create new role with permissions
    """
    
    def post(self, request):
        """Handle HTTP POST request."""
        from django.db import transaction
        
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            # Ambil nama role dari POST data dan normalisasi
            role_name = request.POST.get('role_name', '').strip()
            role_name = role_name.replace(' ', '_').upper()
            
            if not role_name:
                return JsonResponse({
                    'success': False,
                    'message': 'Nama role wajib diisi!'
                }, status=400)
            
            # Cek apakah role sudah ada
            existing_roles = [code for code, name in RolePermission.get_all_roles()]
            if role_name in existing_roles:
                return JsonResponse({
                    'success': False,
                    'message': f'Role {role_name} sudah ada!'
                }, status=400)
            
            with transaction.atomic():
                # Parse permission data dari POST
                perm_keys = [k for k in request.POST.keys() if k.startswith('perms[')]
                
                # Group permissions by module dan sub_module
                permissions_to_create = {}
                
                for key in perm_keys:
                    parts = key.replace('perms[', '').replace(']', '').split('[')
                    
                    if len(parts) == 2:
                        # Module-level permission: perms[produk][view]
                        module, action = parts
                        perm_key = (module, '__MODULE__')
                        
                        if perm_key not in permissions_to_create:
                            permissions_to_create[perm_key] = {
                                'module': module,
                                'sub_module': None,
                                'can_view': False,
                                'can_create': False,
                                'can_edit': False,
                                'can_delete': False,
                            }
                        
                        if action == 'view':
                            permissions_to_create[perm_key]['can_view'] = True
                        elif action == 'create':
                            permissions_to_create[perm_key]['can_create'] = True
                        elif action == 'edit':
                            permissions_to_create[perm_key]['can_edit'] = True
                        elif action == 'delete':
                            permissions_to_create[perm_key]['can_delete'] = True
                            
                    elif len(parts) == 4 and parts[1] == 'subs':
                        # Sub-module permission: perms[produk][subs][kategori][view]
                        module, _, sub_module, action = parts
                        perm_key = (module, sub_module)
                        
                        if perm_key not in permissions_to_create:
                            permissions_to_create[perm_key] = {
                                'module': module,
                                'sub_module': sub_module,
                                'can_view': False,
                                'can_create': False,
                                'can_edit': False,
                                'can_delete': False,
                            }
                        
                        if action == 'view':
                            permissions_to_create[perm_key]['can_view'] = True
                        elif action == 'create':
                            permissions_to_create[perm_key]['can_create'] = True
                        elif action == 'edit':
                            permissions_to_create[perm_key]['can_edit'] = True
                        elif action == 'delete':
                            permissions_to_create[perm_key]['can_delete'] = True
                
                # Buat permission records (bulk_create untuk efisiensi)
                new_permissions = []
                for perm_data in permissions_to_create.values():
                    new_permissions.append(RolePermission(
                        role=role_name,
                        module=perm_data['module'],
                        sub_module=perm_data['sub_module'],
                        can_view=perm_data['can_view'],
                        can_create=perm_data['can_create'],
                        can_edit=perm_data['can_edit'],
                        can_delete=perm_data['can_delete'],
                    ))
                
                if new_permissions:
                    RolePermission.objects.bulk_create(new_permissions)
                
                created_count = len(new_permissions)
            
            # Hapus cache permission agar role baru langsung dikenali (real-time, 0 detik delay)
            invalidate_role_permissions_cache(role_name)
            
            return JsonResponse({
                'success': True,
                'message': f'Role {role_name} berhasil ditambahkan dengan {created_count} permissions!'
            })
            
        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)


@method_decorator(login_required, name='dispatch')
class RoleUpdateAjaxView(SuperuserRequiredMixin, View):
    """
    AJAX endpoint to update role permissions
    """
    
    def post(self, request, role):
        """Handle HTTP POST request."""
        from django.db import transaction
        
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            # Cek apakah nama role diubah
            new_role_name = request.POST.get('role_name', '').strip()
            if new_role_name:
                new_role_name = new_role_name.replace(' ', '_').upper()
            
            old_role_name = role
            role_renamed = new_role_name and new_role_name != old_role_name
            
            with transaction.atomic():
                # Jika role di-rename
                if role_renamed:
                    # Cek apakah nama baru sudah ada
                    existing_roles = [code for code, name in RolePermission.get_all_roles()]
                    if new_role_name in existing_roles:
                        return JsonResponse({
                            'success': False,
                            'message': f'Role {new_role_name} sudah ada! Gunakan nama lain.'
                        }, status=400)
                    
                    # Update semua user dengan role lama ke role baru
                    from auth.models import Profile
                    # Query database — ambil data updated_users yang sesuai filter
                    updated_users = Profile.objects.filter(role=old_role_name).update(role=new_role_name)
                    
                    # Update semua permissions dari role lama ke role baru
                    RolePermission.objects.filter(role=old_role_name).update(role=new_role_name)
                    
                    target_role = new_role_name
                    message = f'Role berhasil direname dari {old_role_name} ke {new_role_name}. {updated_users} user diupdate. '
                else:
                    target_role = old_role_name
                    message = ''
                
                # Parse permission data dari POST
                perm_keys = [k for k in request.POST.keys() if k.startswith('perms[')]
                
                # Group permissions by module dan sub_module
                permissions_to_create = {}
                
                for key in perm_keys:
                    parts = key.replace('perms[', '').replace(']', '').split('[')
                    
                    if len(parts) == 2:
                        # Module-level permission: perms[produk][view]
                        module, action = parts
                        perm_key = (module, '__MODULE__')  # Gunakan marker unik untuk module-level
                        
                        if perm_key not in permissions_to_create:
                            permissions_to_create[perm_key] = {
                                'module': module,
                                'sub_module': None,
                                'can_view': False,
                                'can_create': False,
                                'can_edit': False,
                                'can_delete': False,
                            }
                        
                        if action == 'view':
                            permissions_to_create[perm_key]['can_view'] = True
                        elif action == 'create':
                            permissions_to_create[perm_key]['can_create'] = True
                        elif action == 'edit':
                            permissions_to_create[perm_key]['can_edit'] = True
                        elif action == 'delete':
                            permissions_to_create[perm_key]['can_delete'] = True
                            
                    elif len(parts) == 4 and parts[1] == 'subs':
                        # Sub-module permission: perms[produk][subs][kategori][view]
                        module, _, sub_module, action = parts
                        perm_key = (module, sub_module)
                        
                        if perm_key not in permissions_to_create:
                            permissions_to_create[perm_key] = {
                                'module': module,
                                'sub_module': sub_module,
                                'can_view': False,
                                'can_create': False,
                                'can_edit': False,
                                'can_delete': False,
                            }
                        
                        if action == 'view':
                            permissions_to_create[perm_key]['can_view'] = True
                        elif action == 'create':
                            permissions_to_create[perm_key]['can_create'] = True
                        elif action == 'edit':
                            permissions_to_create[perm_key]['can_edit'] = True
                        elif action == 'delete':
                            permissions_to_create[perm_key]['can_delete'] = True
                
                # HAPUS semua permission yang ada untuk role ini
                RolePermission.objects.filter(role=target_role).delete()
                
                # Buat permission records baru (bulk_create untuk efisiensi)
                new_permissions = []
                for perm_data in permissions_to_create.values():
                    new_permissions.append(RolePermission(
                        role=target_role,
                        module=perm_data['module'],
                        sub_module=perm_data['sub_module'],
                        can_view=perm_data['can_view'],
                        can_create=perm_data['can_create'],
                        can_edit=perm_data['can_edit'],
                        can_delete=perm_data['can_delete'],
                    ))
                
                if new_permissions:
                    RolePermission.objects.bulk_create(new_permissions)
                
                created_count = len(new_permissions)
            
            if role_renamed:
                invalidate_role_permissions_cache(old_role_name)
            invalidate_role_permissions_cache(target_role)
            
            role_display = dict(RolePermission.get_all_roles()).get(target_role, target_role)
            message += f'Permissions untuk {role_display} berhasil diupdate! ({created_count} permissions)'
            
            return JsonResponse({
                'success': True,
                'message': message
            })
            
        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)


@method_decorator(login_required, name='dispatch')
class RoleDeleteView(SuperuserRequiredMixin, View):
    """
    Handle penghapusan role beserta semua permission-nya.
    Role SUPERUSER tidak bisa dihapus.
    Jika role masih digunakan user, user akan di-reset ke role kosong (force).
    """

    def post(self, request, role_code):
        """Handle HTTP POST request."""
        import json
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            # Jangan izinkan hapus role SUPERUSER
            if role_code == 'SUPERUSER':
                return JsonResponse({
                    'success': False,
                    'message': 'Role SUPERUSER tidak dapat dihapus.'
                }, status=400)

            # Cek apakah masih ada user yang memakai role ini
            user_count = Profile.objects.filter(role=role_code).count()
            affected_user_ids = list(Profile.objects.filter(role=role_code).values_list('user_id', flat=True))

            # Cek apakah ada parameter force dari request
            force = False
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                body = json.loads(request.body) if request.body else {}
                force = body.get('force', False)
            # Tangkap error (json.JSONDecodeError, ValueError) — lanjutkan tanpa crash
            except (json.JSONDecodeError, ValueError):
                force = False

            if user_count > 0 and not force:
                return JsonResponse({
                    'success': False,
                    'has_users': True,
                    'user_count': user_count,
                    'message': f'Role masih digunakan oleh {user_count} user. Pilih "Hapus Paksa" untuk memindahkan semua user ke tanpa role dan menghapus role ini.'
                }, status=400)

            # Jika force dan ada user, reset role user ke kosong
            if user_count > 0 and force:
                # Query database — ambil data Profile.objects.filter(role yang sesuai filter
                Profile.objects.filter(role=role_code).update(role='')

            # Hapus semua RolePermission records untuk role ini
            deleted_count, _ = RolePermission.objects.filter(role=role_code).delete()

            # Hapus cache permission agar perubahan langsung terasa
            invalidate_role_permissions_cache(role_code)
            for user_id in affected_user_ids:
                invalidate_user_permissions_cache(user_id)

            role_display = role_code.replace('_', ' ').title()
            msg = f'Role {role_display} berhasil dihapus. ({deleted_count} permission records dihapus)'
            if user_count > 0 and force:
                msg += f' {user_count} user telah dipindahkan ke tanpa role.'

            return JsonResponse({
                'success': True,
                'message': msg
            })

        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)
