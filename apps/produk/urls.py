"""
==========================================================================
 PRODUK URLS - Routing URL Modul Produk (SubCRUD)
==========================================================================
 Peta URL modul produk — menggunakan SubCRUD:

 Kategori (SubCRUD):
 - /produk/kategori/              → Daftar kategori produk
 - /produk/kategori/add/          → Tambah kategori
 - /produk/kategori/<id>/edit/    → Edit kategori
 - /produk/kategori/<id>/delete/  → Hapus kategori

 Satuan (SubCRUD):
 - /produk/satuan/                → Daftar satuan (unit of measure)
 - /produk/satuan/add/            → Tambah satuan
 - /produk/satuan/<id>/edit/      → Edit satuan
 - /produk/satuan/<id>/delete/    → Hapus satuan

 Produk (CRUD utama):
 - /produk/list/                  → Daftar produk
 - /produk/tambah/                → Tambah produk
 - /produk/import/                → Import produk dari file
 - /produk/<id>/edit/             → Edit produk
 - /produk/<id>/delete/           → Hapus produk

 Didaftarkan di config/urls.py: path('produk/', include('apps.produk.urls'))
==========================================================================
"""
from django.urls import path
from . import views

app_name = 'produk'  # Namespace URL — {% url 'produk:list' %}

urlpatterns = [
    # Kategori URLs
    path('kategori/', views.KategoriListView.as_view(), name='kategori'),
    # URL: /produk/kategori/add/ — kategori_add
    path('kategori/add/', views.KategoriCreateView.as_view(), name='kategori_add'),
    # URL: /produk/kategori/<int:pk>/edit/ — kategori_edit
    path('kategori/<int:pk>/edit/', views.KategoriUpdateView.as_view(), name='kategori_edit'),
    # URL: /produk/kategori/<int:pk>/delete/ — kategori_delete
    path('kategori/<int:pk>/delete/', views.KategoriDeleteView.as_view(), name='kategori_delete'),
    
    # Satuan URLs
    path('satuan/', views.SatuanListView.as_view(), name='satuan'),
    path('satuan/seed-default/', views.SatuanSeedDefaultView.as_view(), name='satuan_seed_default'),
    # URL: /produk/satuan/add/ — satuan_add
    path('satuan/add/', views.SatuanCreateView.as_view(), name='satuan_add'),
    # URL: /produk/satuan/<int:pk>/edit/ — satuan_edit
    path('satuan/<int:pk>/edit/', views.SatuanUpdateView.as_view(), name='satuan_edit'),
    # URL: /produk/satuan/<int:pk>/delete/ — satuan_delete
    path('satuan/<int:pk>/delete/', views.SatuanDeleteView.as_view(), name='satuan_delete'),
    
    # Produk URLs
    path('list/', views.ProdukListView.as_view(), name='list'),
    # URL: /produk/tambah/ — tambah
    path('tambah/', views.ProdukCreateView.as_view(), name='tambah'),
    # URL: /produk/import/ — import
    path('import/', views.ProdukImportView.as_view(), name='import'),
    # URL: /produk/<int:pk>/edit/ — edit
    path('<int:pk>/edit/', views.ProdukUpdateView.as_view(), name='edit'),
    # URL: /produk/<int:pk>/delete/ — delete
    path('<int:pk>/delete/', views.ProdukDeleteView.as_view(), name='delete'),

    # URL: /produk/<int:pk>/update-barcode/ — update_barcode (update barcode produk via AJAX)
    path('<int:pk>/update-barcode/', views.update_barcode, name='update_barcode'),

    # API Konversi Satuan
    path('api/konversi-satuan/<int:produk_id>/', views.api_konversi_satuan, name='api_konversi_satuan'),

    # Sparepart URLs
    path('sparepart/', views.SparepartListView.as_view(), name='sparepart_list'),
    path('sparepart/import/', views.SparepartImportView.as_view(), name='sparepart_import'),
    path('sparepart/tambah/', views.SparepartCreateView.as_view(), name='sparepart_tambah'),
    path('sparepart/<int:pk>/edit/', views.SparepartUpdateView.as_view(), name='sparepart_edit'),
    path('sparepart/<int:pk>/delete/', views.SparepartDeleteView.as_view(), name='sparepart_delete'),
]
