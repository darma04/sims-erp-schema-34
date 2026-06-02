"""
==========================================================================
 AKUNTANSI URLS - Routing URL untuk modul Akuntansi
==========================================================================
 app_name = 'akuntansi' → Namespace URL

 /akuntansi/coa/                    → Daftar Chart of Accounts
 /akuntansi/coa/add/                → Tambah akun
 /akuntansi/coa/<pk>/edit/          → Edit akun
 /akuntansi/coa/<pk>/delete/        → Hapus akun
 /akuntansi/coa/seed/               → Seed CoA default

 /akuntansi/jurnal/                 → Daftar jurnal
 /akuntansi/jurnal/add/             → Input jurnal manual
 /akuntansi/jurnal/<pk>/            → Detail jurnal
 /akuntansi/jurnal/<pk>/post/       → Posting jurnal
 /akuntansi/jurnal/<pk>/reverse/    → Buat jurnal pembalik
 /akuntansi/jurnal/<pk>/delete/     → Hapus jurnal (draft only)

 /akuntansi/buku-besar/             → Buku Besar (General Ledger)

 /akuntansi/periode/                → Daftar periode
 /akuntansi/periode/add/            → Tambah periode
 /akuntansi/periode/<pk>/edit/      → Edit periode
 /akuntansi/periode/<pk>/tutup/     → Tutup periode
==========================================================================
"""

from django.urls import path
from . import views

app_name = 'akuntansi'

urlpatterns = [
    # ===== CHART OF ACCOUNTS (CoA) =====
    path('coa/', views.AkunListView.as_view(), name='coa'),
    path('coa/add/', views.AkunCreateView.as_view(), name='coa_add'),
    path('coa/<int:pk>/edit/', views.AkunUpdateView.as_view(), name='coa_edit'),
    path('coa/<int:pk>/delete/', views.AkunDeleteView.as_view(), name='coa_delete'),
    path('coa/seed/', views.SeedCoAView.as_view(), name='coa_seed'),

    # ===== JURNAL ENTRY =====
    path('jurnal/', views.JurnalEntryListView.as_view(), name='jurnal'),
    path('jurnal/add/', views.JurnalEntryCreateView.as_view(), name='jurnal_add'),
    path('jurnal/<int:pk>/', views.JurnalEntryDetailView.as_view(), name='jurnal_detail'),
    path('jurnal/<int:pk>/post/', views.JurnalPostView.as_view(), name='jurnal_post'),
    path('jurnal/<int:pk>/reverse/', views.JurnalReverseView.as_view(), name='jurnal_reverse'),
    path('jurnal/<int:pk>/delete/', views.JurnalEntryDeleteView.as_view(), name='jurnal_delete'),

    # ===== BUKU BESAR =====
    path('buku-besar/', views.BukuBesarView.as_view(), name='buku_besar'),

    # ===== PERIODE AKUNTANSI =====
    path('periode/', views.PeriodeListView.as_view(), name='periode'),
    path('periode/add/', views.PeriodeCreateView.as_view(), name='periode_add'),
    path('periode/<int:pk>/edit/', views.PeriodeUpdateView.as_view(), name='periode_edit'),
    path('periode/<int:pk>/tutup/', views.PeriodeTutupView.as_view(), name='periode_tutup'),

    # ===== LAPORAN KEUANGAN =====
    path('neraca/', views.NeracaView.as_view(), name='neraca'),
    path('laba-rugi/', views.LabaRugiView.as_view(), name='laba_rugi'),
    path('arus-kas/', views.ArusKasView.as_view(), name='arus_kas'),
    path('trial-balance/', views.TrialBalanceView.as_view(), name='trial_balance'),

    # ===== REKONSILIASI KEUANGAN =====
    path('rekonsiliasi-keuangan/', views.RekonsiliasiKeuanganView.as_view(), name='rekonsiliasi_keuangan'),

    # ===== PANDUAN AKUNTANSI =====
    path('panduan/', views.PanduanAkuntansiView.as_view(), name='panduan'),
]
