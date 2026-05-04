"""
==========================================================================
 TENANT API URLS — Routing Internal API untuk CLS
==========================================================================
 Base URL: /api/internal/tenants/
 Endpoints:
 - GET/POST /api/internal/tenants/              → List + Create
 - GET/DELETE /api/internal/tenants/<schema>/    → Detail + Delete
==========================================================================
"""
from django.urls import path
from .api_views import tenant_list_create, tenant_detail_delete

urlpatterns = [
    path('tenants/', tenant_list_create, name='tenant_list_create'),
    path('tenants/<str:schema_name>/', tenant_detail_delete, name='tenant_detail_delete'),
]
