"""
==========================================================================
 PERMISSION MANAGEMENT URLS - Routing Manajemen Permission & Roles
==========================================================================
 Peta URL modul permission management:

 ROLE CRUD (via views_roles.py):
 - /access/roles/                    → Daftar roles
 - /access/roles/ajax/create/        → AJAX: Buat role baru
 - /access/roles/ajax/<role>/data/   → AJAX: Data role (JSON)
 - /access/roles/ajax/<role>/update/ → AJAX: Update role
 - /access/roles/delete/<role>/      → Hapus role

 PERMISSION CRUD (via views.py):
 - /access/permissions/                    → Daftar permission
 - /access/permissions/ajax/create/        → AJAX: Buat permission
 - /access/permissions/ajax/<id>/edit/     → AJAX: Edit permission
 - /access/permissions/ajax/<id>/data/     → AJAX: Data permission
 - /access/permissions/ajax/<id>/delete/   → AJAX: Hapus permission

 Didaftarkan di config/urls.py: path('access/', include('apps.permission_management.urls'))
==========================================================================
"""
from django.urls import path
from django.views.generic import RedirectView
from . import views, views_roles

app_name = 'permission_management'  # Namespace URL

urlpatterns = [
    # Default redirect to roles
    path('', RedirectView.as_view(url='/access/roles/'), name='index'),

    
    # Backward compatibility
    path('permission-management/', RedirectView.as_view(url='/access/roles/'), name='old_index'),
    
    # ===== ROLE CRUD =====
    path('roles/', views_roles.RoleListView.as_view(), name='role_list'),
    # URL: /permission_management/roles/ajax/create/ — role_create
    path('roles/ajax/create/', views_roles.RoleCreateAjaxView.as_view(), name='role_create'),
    # URL: /permission_management/roles/ajax/<str:role>/data/ — role_data
    path('roles/ajax/<str:role>/data/', views_roles.RoleDataAjaxView.as_view(), name='role_data'),
    # URL: /permission_management/roles/ajax/<str:role>/update/ — role_update
    path('roles/ajax/<str:role>/update/', views_roles.RoleUpdateAjaxView.as_view(), name='role_update'),
    # URL: /permission_management/roles/delete/<str:role_code>/ — role_delete
    path('roles/delete/<str:role_code>/', views_roles.RoleDeleteView.as_view(), name='role_delete'),
    
    # ===== PERMISSION CRUD =====
    path('permissions/', views.PermissionListView.as_view(), name='permission_list'),
    path('permissions/seed/', views.SeedPermissionView.as_view(), name='seed_permissions'),
    
    # Permission AJAX endpoints
    path('permissions/ajax/create/', views.PermissionCreateAjaxView.as_view(), name='ajax_create'),
    # URL: /permission_management/permissions/ajax/<int:pk>/edit/ — ajax_edit
    path('permissions/ajax/<int:pk>/edit/', views.PermissionUpdateAjaxView.as_view(), name='ajax_edit'),
    # URL: /permission_management/permissions/ajax/<int:pk>/data/ — ajax_data
    path('permissions/ajax/<int:pk>/data/', views.PermissionDataAjaxView.as_view(), name='ajax_data'),
    # URL: /permission_management/permissions/ajax/<int:pk>/delete/ — ajax_delete
    path('permissions/ajax/<int:pk>/delete/', views.RolePermissionDeleteView.as_view(), name='ajax_delete'),
    
    # Legacy full-page forms (fallback)
    path('tambah/', views.RolePermissionCreateView.as_view(), name='create'),
    # URL: /permission_management/<int:pk>/edit/ — edit
    path('<int:pk>/edit/', views.RolePermissionUpdateView.as_view(), name='edit'),
    # URL: /permission_management/<int:pk>/delete/ — delete
    path('<int:pk>/delete/', views.RolePermissionDeleteView.as_view(), name='delete'),
]
