"""
==========================================================================
 HR URLS - Routing URL untuk modul HR (SDM)
==========================================================================
 app_name = 'hr' → Namespace URL

 Grup URL:
 1. Dashboard HR → /hr/
 2. Departemen CRUD → /hr/departemen/...
 3. Jabatan CRUD → /hr/jabatan/...
 4. Karyawan CRUD → /hr/karyawan/...
 5. Absensi CRUD + Clock In/Out → /hr/absensi/...
 6. Penggajian CRUD + Generate → /hr/penggajian/...
 7. Face Recognition API → /hr/absensi/registrasi-wajah/...
 8. Pengaturan Absensi CRUD → /hr/pengaturan-absensi/...
==========================================================================
"""

from django.urls import path
from apps.hr import views

app_name = 'hr'  # Namespace URL

urlpatterns = [
    # Dashboard HR
    path('', views.DashboardHRView.as_view(), name='dashboard'),
    
    # Departemen CRUD
    path('departemen/', views.DepartemenListView.as_view(), name='departemen'),
    # URL: /hr/departemen/add/ — departemen-add
    path('departemen/add/', views.DepartemenCreateView.as_view(), name='departemen-add'),
    # URL: /hr/departemen/<int:pk>/edit/ — departemen-edit
    path('departemen/<int:pk>/edit/', views.DepartemenUpdateView.as_view(), name='departemen-edit'),
    # URL: /hr/departemen/<int:pk>/delete/ — departemen-delete
    path('departemen/<int:pk>/delete/', views.DepartemenDeleteView.as_view(), name='departemen-delete'),
    
    # Jabatan CRUD
    path('jabatan/', views.JabatanListView.as_view(), name='jabatan'),
    # URL: /hr/jabatan/add/ — jabatan-add
    path('jabatan/add/', views.JabatanCreateView.as_view(), name='jabatan-add'),
    # URL: /hr/jabatan/<int:pk>/edit/ — jabatan-edit
    path('jabatan/<int:pk>/edit/', views.JabatanUpdateView.as_view(), name='jabatan-edit'),
    # URL: /hr/jabatan/<int:pk>/delete/ — jabatan-delete
    path('jabatan/<int:pk>/delete/', views.JabatanDeleteView.as_view(), name='jabatan-delete'),
    
    # Karyawan CRUD
    path('karyawan/', views.KaryawanListView.as_view(), name='karyawan'),
    # URL: /hr/karyawan/add/ — karyawan-add
    path('karyawan/add/', views.KaryawanCreateView.as_view(), name='karyawan-add'),
    # URL: /hr/karyawan/<int:pk>/ — karyawan-detail
    path('karyawan/<int:pk>/', views.KaryawanDetailView.as_view(), name='karyawan-detail'),
    # URL: /hr/karyawan/<int:pk>/edit/ — karyawan-edit
    path('karyawan/<int:pk>/edit/', views.KaryawanUpdateView.as_view(), name='karyawan-edit'),
    # URL: /hr/karyawan/<int:pk>/delete/ — karyawan-delete
    path('karyawan/<int:pk>/delete/', views.KaryawanDeleteView.as_view(), name='karyawan-delete'),
    
    # Absensi CRUD
    path('absensi/', views.AbsensiListView.as_view(), name='absensi'),
    # URL: /hr/absensi/add/ — absensi-add
    path('absensi/add/', views.AbsensiCreateView.as_view(), name='absensi-add'),
    # URL: /hr/absensi/<int:pk>/edit/ — absensi-edit
    path('absensi/<int:pk>/edit/', views.AbsensiUpdateView.as_view(), name='absensi-edit'),
    # URL: /hr/absensi/<int:pk>/delete/ — absensi-delete
    path('absensi/<int:pk>/delete/', views.AbsensiDeleteView.as_view(), name='absensi-delete'),
    # URL: /hr/absensi/deteksi-wajah/ — absensi-deteksi-wajah
    path('absensi/deteksi-wajah/', views.AbsensiDeteksiWajahView.as_view(), name='absensi-deteksi-wajah'),
    # URL: /hr/absensi/clock-in/ — absensi-clock-in
    path('absensi/clock-in/', views.absensi_clock_in, name='absensi-clock-in'),
    # URL: /hr/absensi/clock-out/ — absensi-clock-out
    path('absensi/clock-out/', views.absensi_clock_out, name='absensi-clock-out'),
    # URL: /hr/absensi/<int:pk>/lokasi-map/ — absensi-lokasi-map (Peta Folium)
    path('absensi/<int:pk>/lokasi-map/', views.absensi_lokasi_map, name='absensi-lokasi-map'),
    # URL: /hr/absensi/<int:pk>/detail/ — absensi-detail (Detail Absensi + Peta)
    path('absensi/<int:pk>/detail/', views.AbsensiDetailView.as_view(), name='absensi-detail'),
    
    # Penggajian CRUD
    path('penggajian/', views.PenggajianListView.as_view(), name='penggajian'),
    # URL: /hr/penggajian/add/ — penggajian-add
    path('penggajian/add/', views.PenggajianCreateView.as_view(), name='penggajian-add'),
    # URL: /hr/penggajian/import/ — penggajian-import
    path('penggajian/import/', views.ImportPenggajianView.as_view(), name='penggajian-import'),
    # URL: /hr/penggajian/generate/ — penggajian-generate
    path('penggajian/generate/', views.GeneratePenggajianView.as_view(), name='penggajian-generate'),
    # URL: /hr/penggajian/<int:pk>/ — penggajian-detail
    path('penggajian/<int:pk>/', views.PenggajianDetailView.as_view(), name='penggajian-detail'),
    # URL: /hr/penggajian/<int:pk>/edit/ — penggajian-edit
    path('penggajian/<int:pk>/edit/', views.PenggajianUpdateView.as_view(), name='penggajian-edit'),
    # URL: /hr/penggajian/<int:pk>/delete/ — penggajian-delete
    path('penggajian/<int:pk>/delete/', views.PenggajianDeleteView.as_view(), name='penggajian-delete'),
    # URL: /hr/penggajian/<int:pk>/status/ — penggajian-status
    path('penggajian/<int:pk>/status/', views.PenggajianUpdateStatusView.as_view(), name='penggajian-status'),
    # URL: /hr/penggajian/<int:pk>/print/ — penggajian-print
    path('penggajian/<int:pk>/print/', views.PenggajianPrintView.as_view(), name='penggajian-print'),
    
    # Face Recognition
    path('absensi/registrasi-wajah/', views.RegistrasiWajahView.as_view(), name='registrasi-wajah'),
    # URL: /hr/absensi/registrasi-wajah/save/ — save-face-encoding
    path('absensi/registrasi-wajah/save/', views.save_face_encoding, name='save-face-encoding'),
    # URL: /hr/absensi/registrasi-wajah/<int:pk>/delete/ — delete-face
    path('absensi/registrasi-wajah/<int:pk>/delete/', views.delete_face, name='delete-face'),
    # URL: /hr/absensi/detect-face/ — detect-face
    path('absensi/detect-face/', views.detect_face_api, name='detect-face'),
    # URL: /hr/absensi/face-clock-in/ — absensi-face-clock-in
    path('absensi/face-clock-in/', views.absensi_face_clock_in, name='absensi-face-clock-in'),
    # URL: /hr/absensi/face-clock-out/ — absensi-face-clock-out
    path('absensi/face-clock-out/', views.absensi_face_clock_out, name='absensi-face-clock-out'),
    
    # Pengaturan Absensi
    path('pengaturan-absensi/', views.PengaturanAbsensiView.as_view(), name='pengaturan-absensi'),
    # URL: /hr/pengaturan-absensi/new/ — pengaturan-absensi-new
    path('pengaturan-absensi/new/', views.PengaturanAbsensiCreateView.as_view(), name='pengaturan-absensi-new'),
    # URL: /hr/pengaturan-absensi/<int:pk>/edit/ — pengaturan-absensi-edit
    path('pengaturan-absensi/<int:pk>/edit/', views.PengaturanAbsensiUpdateView.as_view(), name='pengaturan-absensi-edit'),
    # URL: /hr/pengaturan-absensi/<int:pk>/delete/ — pengaturan-absensi-delete
    path('pengaturan-absensi/<int:pk>/delete/', views.pengaturan_absensi_delete, name='pengaturan-absensi-delete'),
    # URL: /hr/pengaturan-absensi/<int:pk>/activate/ — pengaturan-absensi-activate
    path('pengaturan-absensi/<int:pk>/activate/', views.pengaturan_absensi_activate, name='pengaturan-absensi-activate'),
]
