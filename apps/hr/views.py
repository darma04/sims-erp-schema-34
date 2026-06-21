"""
==========================================================================
HR VIEWS - View untuk Human Resources (SDM)
==========================================================================
File ini berisi views untuk modul HR (1292 baris - modul terbesar):

DASHBOARD HR:
    DashboardHRView → Statistik karyawan, absensi, penggajian

DEPARTEMEN CRUD (SubModulePermissionMixin):
    DepartemenListView/Create/Update/Delete

JABATAN CRUD:
    JabatanListView/Create/Update/Delete

KARYAWAN CRUD:
    KaryawanListView/Create/Update/Detail/Delete
    - Detail menampilkan riwayat absensi + penggajian

ABSENSI:
    AbsensiListView/Create/Update/Delete → CRUD manual
    AbsensiDeteksiWajahView → Halaman absensi deteksi wajah
    absensi_clock_in/clock_out → API clock in/out manual
    absensi_face_clock_in/out → API clock in/out via face recognition

PENGGAJIAN:
    PenggajianListView/Create/Update/Detail/Delete
    GeneratePenggajianView → Generate slip gaji massal untuk semua karyawan
    PenggajianUpdateStatusView → Update status bayar

FACE RECOGNITION:
    RegistrasiWajahView → Halaman registrasi wajah karyawan
    save_face_encoding() → API simpan encoding wajah
    delete_face() → API hapus foto wajah
    detect_face_api() → API deteksi & matching wajah

PENGATURAN ABSENSI:
    PengaturanAbsensiView → Kelola pengaturan (jam, lokasi, radius)
    PengaturanAbsensiCreateView/UpdateView
    pengaturan_absensi_delete/activate → Hapus/aktifkan pengaturan

⚠ FITUR KHUSUS:
- Face recognition opsional (FACE_RECOGNITION_ENABLED flag)
- Validasi lokasi GPS (radius kantor) untuk absensi
- Generate slip gaji massal dengan skip duplikasi
- Toleransi keterlambatan dari PengaturanAbsensi
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
from django.shortcuts import render
from django.db.models import ProtectedError
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
# Import dari framework Django
from django.urls import reverse_lazy
# Import dari framework Django
from django.contrib import messages
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.http import JsonResponse
# Import decorator untuk izin iframe embedding (peta lokasi)
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_http_methods
# Import dari framework Django
from django.db.models import Sum, Count, Avg, F
# Import dari framework Django
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import base64
from io import BytesIO

# Geolocation Maps — untuk rendering peta lokasi absensi
try:
    import folium
    FOLIUM_ENABLED = True
except ImportError:
    FOLIUM_ENABLED = False

# Geolocation Distance — untuk menghitung jarak GPS dari kantor
try:
    from geopy.distance import geodesic
    GEOLOCATION_ENABLED = True
except ImportError:
    GEOLOCATION_ENABLED = False

from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.hr.models import Departemen, Jabatan, Karyawan, FotoWajah, Absensi, Penggajian, PengaturanAbsensi
# Import dari modul internal proyek
from apps.hr.forms import (
    DepartemenForm, JabatanForm, KaryawanForm, 
    AbsensiForm, PenggajianForm, FotoWajahForm, GeneratePenggajianForm,
    PengaturanAbsensiForm
)
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin, SubModulePermissionMixin
from apps.core.permissions import has_permission





def get_default_payroll_payment_method():
    """Return metode pembayaran kas default untuk payroll jika slip belum memilih metode."""
    from apps.pos.models import MetodePembayaran

    return (
        MetodePembayaran.objects.filter(aktif=True, akun_kas_bank__kode='1-1000')
        .order_by('kode')
        .first()
        or MetodePembayaran.objects.filter(aktif=True).order_by('kode').first()
    )


def create_penggajian_payment_journal(slip, user=None):
    """Buat jurnal payroll dan mutasi Kas/Bank untuk slip yang sudah dibayar."""
    if slip.status != 'dibayar':
        return None

    update_fields = []
    if not slip.tanggal_bayar:
        slip.tanggal_bayar = timezone.now().date()
        update_fields.append('tanggal_bayar')
    if not slip.cabang_id and slip.karyawan_id:
        slip.cabang = slip.karyawan.cabang
        update_fields.append('cabang')
    if not slip.metode_pembayaran_id:
        slip.metode_pembayaran = get_default_payroll_payment_method()
        if slip.metode_pembayaran_id:
            update_fields.append('metode_pembayaran')
    if update_fields:
        update_fields.append('diupdate_pada')
        slip.save(update_fields=update_fields)

    from apps.akuntansi.models import JurnalEntry

    existing_jurnal = JurnalEntry.objects.filter(
        sumber__in=['payroll', 'hr'],
        sumber_id=slip.pk,
    ).first()
    if existing_jurnal:
        return existing_jurnal

    if slip.total_pendapatan <= 0:
        return None

    from apps.akuntansi.services import create_jurnal
    from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping

    kas_bank_account, _, kas_akun_kode = resolve_kas_bank_mapping(slip.metode_pembayaran)
    cabang = slip.cabang or (slip.karyawan.cabang if slip.karyawan_id else None)
    bpjs_total = slip.potongan_bpjs_kesehatan + slip.potongan_bpjs_ketenagakerjaan
    lines_data = [
        {
            'akun_kode': '6-1000',
            'debit': slip.total_pendapatan,
            'kredit': Decimal('0'),
            'keterangan': f'Beban gaji {slip.karyawan.nama} - {slip.periode}',
        }
    ]
    if slip.gaji_bersih > 0:
        lines_data.append({
            'akun_kode': kas_akun_kode,
            'debit': Decimal('0'),
            'kredit': slip.gaji_bersih,
            'keterangan': f'Pembayaran gaji bersih {slip.karyawan.nama}',
        })
    if slip.potongan_pph21 > 0:
        lines_data.append({
            'akun_kode': '2-3100',
            'debit': Decimal('0'),
            'kredit': slip.potongan_pph21,
            'keterangan': f'Hutang PPh 21 {slip.karyawan.nama}',
        })
    if bpjs_total > 0:
        lines_data.append({
            'akun_kode': '2-3200',
            'debit': Decimal('0'),
            'kredit': bpjs_total,
            'keterangan': f'Hutang BPJS {slip.karyawan.nama}',
        })
    if slip.potongan_lainnya > 0:
        lines_data.append({
            'akun_kode': '2-3000',
            'debit': Decimal('0'),
            'kredit': slip.potongan_lainnya,
            'keterangan': f'Potongan lain gaji {slip.karyawan.nama}',
        })

    jurnal = create_jurnal(
        tanggal=slip.tanggal_bayar,
        deskripsi=f'Pembayaran gaji {slip.karyawan.nama} - {slip.periode}',
        lines_data=lines_data,
        sumber='payroll',
        sumber_id=slip.pk,
        sumber_ref=f'PAY-{slip.pk}',
        cabang=cabang,
        user=user or slip.dibuat_oleh,
        auto_post=True,
    )

    create_operational_mutation(
        akun_kas_bank=kas_bank_account,
        tipe='keluar',
        tanggal=slip.tanggal_bayar,
        jumlah=slip.gaji_bersih,
        deskripsi=f'Pembayaran gaji {slip.karyawan.nama} - {slip.periode}',
        cabang=cabang,
        metode_pembayaran=slip.metode_pembayaran,
        sumber_app='hr',
        sumber_model='Penggajian',
        sumber_id=slip.pk,
        sumber_ref=f'PAY-{slip.pk}',
        jurnal_entry=jurnal,
        user=user or slip.dibuat_oleh,
    )
    return jurnal



# ╔══════════════════════════════════════════════════════════════╗
# ║  DASHBOARD HR - Statistik karyawan, absensi, penggajian       ║
# ╚══════════════════════════════════════════════════════════════╝
class DashboardHRView(ReadPermissionMixin, TemplateView):
    """
    Dashboard utama modul HR - menampilkan ringkasan statistik SDM.

    URL: /hr/
    Permission: hr.dashboard_hr.read (SubCRUD)
    Template: hr/dashboard.html

    Data yang ditampilkan:
    - Statistik karyawan (total, aktif, cuti)
    - Statistik departemen dan jabatan
    - Absensi hari ini (hadir, terlambat, izin, alpha)
    - Tingkat kehadiran (persentase)
    - Total penggajian bulan ini
    - Daftar karyawan terbaru (5 terakhir)
    - Riwayat absensi terbaru (10 terakhir)
    """
    template_name = 'hr/dashboard.html'          # Template halaman dashboard HR
    # Modul permission yang dicek: 'hr'                      # Modul permission: HR'
    permission_module = 'hr'                      # Modul permission: HR
    permission_sub_module = 'dashboard_hr'        # Sub-modul: dashboard_hr (SubCRUD permission)

    def get_context_data(self, **kwargs):
        """
        Mengumpulkan semua data statistik HR untuk ditampilkan di dashboard.
        Menghitung: total karyawan, absensi hari ini, penggajian bulan ini,
        dan daftar karyawan/absensi terbaru.
        """
        # Inisialisasi layout global (sidebar, header, tema)
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        today = timezone.now().date()  # Tanggal hari ini untuk filter absensi
        # Data konteks: today - untuk ditampilkan di template
        context['today'] = today

# ── Statistik Karyawan ─────────────────────────────────
        # Hitung total karyawan yang masih aktif (belum resign/nonaktif)
        total_karyawan = Karyawan.objects.filter(aktif=True).count()
        # Data konteks: total_karyawan - untuk ditampilkan di template
        context['total_karyawan'] = total_karyawan
        # Query database - ambil data context['total_departemen'] yang sesuai filter
        # Data konteks: total_departemen - untuk ditampilkan di template
        context['total_departemen'] = Departemen.objects.filter(aktif=True).count()  # Departemen aktif
        # Query database - ambil data context['total_jabatan'] yang sesuai filter
        # Data konteks: total_jabatan - untuk ditampilkan di template
        context['total_jabatan'] = Jabatan.objects.filter(aktif=True).count()        # Jabatan aktif

# ── Statistik Status Karyawan ──────────────────────────
        # Status 'aktif' = sedang bekerja, 'cuti' = sedang cuti
        context['karyawan_aktif'] = Karyawan.objects.filter(status='aktif').count()
        # Query database - ambil data context['karyawan_cuti'] yang sesuai filter
        # Data konteks: karyawan_cuti - untuk ditampilkan di template
        context['karyawan_cuti'] = Karyawan.objects.filter(status='cuti').count()

# ── Absensi Hari Ini (detail per status) ──────────────
        # Query absensi untuk tanggal hari ini saja
        absensi_hari_ini = Absensi.objects.filter(tanggal=today)
        # Data konteks: absensi_hadir - untuk ditampilkan di template
        context['absensi_hadir'] = absensi_hari_ini.filter(status='hadir').count()           # Hadir tepat waktu
        # Data konteks: absensi_terlambat - untuk ditampilkan di template
        context['absensi_terlambat'] = absensi_hari_ini.filter(status='terlambat').count()   # Hadir tapi terlambat
        # Data konteks: absensi_izin - untuk ditampilkan di template
        context['absensi_izin'] = absensi_hari_ini.filter(status__in=['izin', 'sakit', 'cuti']).count()  # Izin/sakit/cuti
        # Alpha = karyawan yang TIDAK absen sama sekali (total - yang sudah absen)
        context['absensi_alpha'] = max(0, total_karyawan - absensi_hari_ini.count()) if total_karyawan > 0 else 0

# ── Tingkat Kehadiran ──────────────────────────────────
        # Persentase kehadiran = (yang absen / total karyawan) × 100
        total_absen_hari_ini = absensi_hari_ini.count()
        # Data konteks: tingkat_kehadiran - untuk ditampilkan di template
        context['tingkat_kehadiran'] = round((total_absen_hari_ini / total_karyawan * 100), 1) if total_karyawan > 0 else 0

# ── Penggajian Bulan Ini ───────────────────────────────
        # Aggregate total gaji bersih dan jumlah slip untuk bulan & tahun ini
        bulan_ini = today.month
        tahun_ini = today.year
        # Query database - ambil data penggajian_bulan_ini yang sesuai filter
        penggajian_bulan_ini = Penggajian.objects.filter(
            periode_bulan=bulan_ini, 
            periode_tahun=tahun_ini
        ).aggregate(
            total=Sum('gaji_bersih'),   # Total semua gaji bersih
            count=Count('id')           # Jumlah slip gaji
        )
        # Data konteks: total_gaji_bulan_ini - untuk ditampilkan di template
        context['total_gaji_bulan_ini'] = penggajian_bulan_ini['total'] or 0

# ── Daftar Karyawan Terbaru (5 terakhir ditambahkan) ──
        # select_related() untuk menghindari N+1 query (join jabatan & departemen)
        context['karyawan_terbaru'] = Karyawan.objects.filter(aktif=True).select_related('jabatan', 'departemen').order_by('-dibuat_pada')[:5]

# ── Riwayat Absensi Terbaru (10 terakhir) ─────────────
        # Diurutkan berdasarkan tanggal terbaru, lalu jam masuk terbaru
        context['absensi_terbaru'] = Absensi.objects.select_related('karyawan').order_by('-tanggal', '-jam_masuk')[:10]

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPARTEMEN CRUD - Menggunakan SubModulePermissionMixin       ║
# ║  (berbeda dari modul lain yang pakai ReadPermissionMixin)     ║
# ╚══════════════════════════════════════════════════════════════╝
class DepartemenListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua departemen.

    URL: /hr/departemen/
    Permission: hr.departemen.read (SubCRUD - menggunakan SubModulePermissionMixin)
    Template: hr/departemen_list.html
    """
    model = Departemen                              # Model: Departemen
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/departemen_list.html'       # Template daftar departemen
    context_object_name = 'departemen_list'         # Nama variabel di template
    # Modul permission yang dicek: 'hr'                        # Modul permission: HR'
    permission_module = 'hr'                        # Modul permission: HR
    permission_sub_module = 'departemen'            # Sub-modul: departemen
    permission_action = 'read'                      # Aksi: read (lihat data)

    def get_context_data(self, **kwargs):
        """Menambahkan total departemen dan karyawan untuk ringkasan di template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_departemen - untuk ditampilkan di template
        context['total_departemen'] = self.get_queryset().count()           # Jumlah total departemen
        # Query database - ambil data context['total_karyawan'] yang sesuai filter
        # Data konteks: total_karyawan - untuk ditampilkan di template
        context['total_karyawan'] = Karyawan.objects.filter(aktif=True).count()  # Jumlah karyawan aktif
        return context



class DepartemenCreateView(SubModulePermissionMixin, CreateView):
    """
    Form untuk menambahkan departemen baru.

    URL: /hr/departemen/add/
    Permission: hr.departemen.create
    Template: hr/departemen_form.html
    Redirect: /hr/departemen/ setelah berhasil simpan
    """
    model = Departemen                              # Model: Departemen
    form_class = DepartemenForm                     # Form: DepartemenForm (kode, nama, kepala)
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/departemen_form.html'       # Template form create/edit
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:departemen')     # Redirect ke daftar setelah simpan
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'create'                    # Aksi: create (tambah data)

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Tambah Departemen' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Departemen'  # Judul di header form
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Departemen berhasil ditambahkan')
        return super().form_valid(form)  # Simpan ke database dan redirect



class DepartemenUpdateView(SubModulePermissionMixin, UpdateView):
    """
    Form untuk mengedit departemen yang sudah ada.

    URL: /hr/departemen/<pk>/edit/
    Permission: hr.departemen.write
    Template: hr/departemen_form.html (sama dengan create)
    Redirect: /hr/departemen/ setelah berhasil update
    """
    model = Departemen
    form_class = DepartemenForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/departemen_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:departemen')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'write'                     # Aksi: write (edit data)

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Edit Departemen' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Departemen'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Departemen berhasil diupdate')
        return super().form_valid(form)



class DepartemenDeleteView(SubModulePermissionMixin, DeleteView):
    """
    Hapus departemen - dipanggil via AJAX dari frontend.

    URL: /hr/departemen/<pk>/delete/
    Permission: hr.departemen.delete
    Response: JSON {success: bool, message: string}
    """
    model = Departemen
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:departemen')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'delete'                    # Aksi: delete (hapus data)

    def delete(self, request, *args, **kwargs):
        """
        Override method delete untuk mengembalikan JSON response (bukan redirect).
        Frontend memanggil endpoint ini via AJAX dan mengharapkan JSON.
        Jika gagal (misal: ada karyawan terkait), tangkap exception dan kembalikan error.
        """
        self.object = self.get_object()  # Ambil objek departemen berdasarkan pk dari URL
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            nama = self.object.nama       # Simpan nama sebelum dihapus (untuk pesan)
            self.object.delete()          # Hapus dari database
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': f'Departemen {nama} berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Gagal hapus - biasanya karena ada relasi yang masih terkait
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


    # ╔══════════════════════════════════════════════════════════════╗
    # ║  JABATAN CRUD - Posisi/jabatan + gaji pokok per jabatan       ║
    # ╚══════════════════════════════════════════════════════════════╝
class JabatanListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua jabatan beserta gaji pokok.

    URL: /hr/jabatan/
    Permission: hr.jabatan.read (SubCRUD)
    Template: hr/jabatan_list.html
    """
    model = Jabatan                                 # Model: Jabatan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/jabatan_list.html'          # Template daftar jabatan
    context_object_name = 'jabatan_list'            # Nama variabel di template
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'jabatan'               # Sub-modul: jabatan

    def get_queryset(self):
        """
        Query semua jabatan dengan select_related('departemen').
        select_related() melakukan JOIN SQL untuk menghindari N+1 query
        saat template mengakses jabatan.departemen.nama.
        """
        return Jabatan.objects.select_related('departemen').all()

    def get_context_data(self, **kwargs):
        """
        Menambahkan ringkasan jabatan ke context:
        - total_jabatan: jumlah semua jabatan
        - total_gaji: total keseluruhan gaji pokok (untuk summary card)
        - departemen_list: daftar departemen aktif (untuk filter dropdown)
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        queryset = self.get_queryset()
        # Data konteks: total_jabatan - untuk ditampilkan di template
        context['total_jabatan'] = queryset.count()                                         # Jumlah total jabatan
        # Data konteks: total_gaji - untuk ditampilkan di template
        context['total_gaji'] = queryset.aggregate(total=Sum('gaji_pokok'))['total'] or 0   # Total gaji pokok semua jabatan
        # Query database - ambil data context['departemen_list'] yang sesuai filter
        # Data konteks: departemen_list - untuk ditampilkan di template
        context['departemen_list'] = Departemen.objects.filter(aktif=True).order_by('nama') # Departemen untuk filter
        return context



class JabatanCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambahkan jabatan baru.

    URL: /hr/jabatan/add/
    Permission: hr.create (menggunakan CreatePermissionMixin)
    Template: hr/jabatan_form.html
    Redirect: /hr/jabatan/ setelah berhasil simpan
    """
    model = Jabatan
    form_class = JabatanForm                        # Form: kode, nama, gaji_pokok, tunjangan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/jabatan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:jabatan')        # Redirect ke daftar jabatan
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Tambah Jabatan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Jabatan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Jabatan berhasil ditambahkan')
        return super().form_valid(form)



class JabatanUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit jabatan yang sudah ada.

    URL: /hr/jabatan/<pk>/edit/
    Permission: hr.edit (menggunakan UpdatePermissionMixin)
    Template: hr/jabatan_form.html
    """
    model = Jabatan
    form_class = JabatanForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/jabatan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:jabatan')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Edit Jabatan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Jabatan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Jabatan berhasil diupdate')
        return super().form_valid(form)



class JabatanDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus jabatan - dipanggil via AJAX dari frontend.

    URL: /hr/jabatan/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}
    """
    model = Jabatan
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:jabatan')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """
        Override delete untuk return JSON (AJAX).
        Jika jabatan masih dipakai karyawan, exception akan ditangkap.
        """
        self.object = self.get_object()
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            nama = self.object.nama
            self.object.delete()
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': f'Jabatan {nama} berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
        # ║  KARYAWAN CRUD - Data karyawan + detail riwayat               ║
        # ║  Detail: absensi 30 hari terakhir + penggajian 12 bulan       ║
# ╚══════════════════════════════════════════════════════════════╝
class KaryawanListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua karyawan dengan data jabatan dan departemen.

    URL: /hr/karyawan/
    Permission: hr.karyawan.read (SubCRUD)
    Template: hr/karyawan_list.html

    Context tambahan:
    - total_karyawan: jumlah seluruh karyawan
    - karyawan_aktif: jumlah karyawan berstatus 'aktif'
    - departemen_struktur: data departemen + karyawan + jabatan (untuk org chart)
    """
    model = Karyawan                                # Model: Karyawan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/karyawan_list.html'         # Template daftar karyawan
    context_object_name = 'karyawan_list'           # Nama variabel di template
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'karyawan'              # Sub-modul: karyawan

    def get_queryset(self):
        """
        Query semua karyawan dengan JOIN ke jabatan dan departemen.
        select_related() menghindari N+1 query saat template akses relasi.
        """
        return Karyawan.objects.select_related('jabatan', 'departemen').all()

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik karyawan dan struktur organisasi ke context.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_karyawan - untuk ditampilkan di template
        context['total_karyawan'] = self.get_queryset().count()                    # Total karyawan
        # Data konteks: karyawan_aktif - untuk ditampilkan di template
        context['karyawan_aktif'] = self.get_queryset().filter(status='aktif').count()  # Yang berstatus aktif

        # Struktur organisasi - prefetch_related() untuk menghindari N+1
        # saat iterasi departemen → karyawan & jabatan di template
        context['departemen_struktur'] = Departemen.objects.filter(aktif=True).prefetch_related(
            'karyawan_set', 'jabatan_set'
        )
        return context



class KaryawanCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambahkan karyawan baru.

    URL: /hr/karyawan/add/
    Permission: hr.create
    Template: hr/karyawan_form.html
    Redirect: /hr/karyawan/ setelah sukses

    Catatan: field 'dibuat_oleh' diisi otomatis dengan user yang login
    melalui form_valid() - bukan dari form input.
    """
    model = Karyawan
    form_class = KaryawanForm                       # Form: nama, NIK, jabatan, departemen, dll
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/karyawan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:karyawan')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Karyawan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Karyawan'
        return context


    def form_valid(self, form):
        """
        Dipanggil saat form valid. Set field 'dibuat_oleh' dengan user
        yang sedang login sebelum menyimpan ke database.
        """
        form.instance.dibuat_oleh = self.request.user  # Set user pembuat otomatis
        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Karyawan berhasil ditambahkan')
        return super().form_valid(form)



class KaryawanUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit data karyawan.

    URL: /hr/karyawan/<pk>/edit/
    Permission: hr.edit
    Template: hr/karyawan_form.html (sama dengan create)
    """
    model = Karyawan
    form_class = KaryawanForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/karyawan_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:karyawan')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Karyawan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Karyawan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Data karyawan berhasil diupdate')
        return super().form_valid(form)



class KaryawanDetailView(ReadPermissionMixin, DetailView):
    """
    Halaman detail karyawan - menampilkan profil lengkap + riwayat.

    URL: /hr/karyawan/<pk>/
    Permission: hr.read
    Template: hr/karyawan_detail.html

    Context tambahan:
    - absensi_list: riwayat absensi 30 hari terakhir
    - penggajian_list: riwayat slip gaji 12 bulan terakhir
    """
    model = Karyawan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/karyawan_detail.html'
    context_object_name = 'karyawan'                # Nama variabel di template
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """
        Menambahkan riwayat absensi dan penggajian karyawan ke context.
        self.object = karyawan yang sedang dilihat (diambil berdasarkan pk URL).
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Riwayat absensi 30 hari terakhir (latest first)
        context['absensi_list'] = self.object.absensi_set.order_by('-tanggal')[:30]
        # Riwayat penggajian 12 bulan terakhir (latest first)
        context['penggajian_list'] = self.object.penggajian_set.order_by('-periode_tahun', '-periode_bulan')[:12]
        return context



class KaryawanDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus karyawan - dipanggil via AJAX dari frontend.

    URL: /hr/karyawan/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}

    ⚠ PERHATIAN: Menghapus karyawan akan menghapus semua data terkait
    (absensi, penggajian, foto wajah) jika menggunakan CASCADE.
    """
    model = Karyawan
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:karyawan')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON (bukan redirect HTML)."""
        self.object = self.get_object()  # Ambil karyawan berdasarkan pk
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            nama = self.object.nama       # Simpan nama sebelum dihapus
            self.object.delete()          # Hapus karyawan + data terkait
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': f'Karyawan {nama} berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
                # ║  ABSENSI - CRUD manual + clock in/out + face recognition      ║
                # ║  Filter by date range, status hadir/terlambat                 ║
# ╚══════════════════════════════════════════════════════════════╝
class AbsensiListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar absensi karyawan dengan filter tanggal.

    URL: /hr/absensi/
    Permission: hr.absensi.read (SubCRUD)
    Template: hr/absensi_list.html

    Fitur filter via GET params:
    - ?tanggal_dari=YYYY-MM-DD → filter absensi mulai dari tanggal ini
    - ?tanggal_sampai=YYYY-MM-DD → filter absensi sampai tanggal ini
    """
    model = Absensi                                 # Model: Absensi (kehadiran karyawan)
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/absensi_list.html'          # Template daftar absensi
    context_object_name = 'absensi_list'            # Nama variabel di template
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'absensi'               # Sub-modul: absensi

    def get_queryset(self):
        """
        Query absensi dengan filter tanggal dari GET params.
        Urutkan dari tanggal terbaru, lalu jam masuk terbaru.
        select_related('karyawan') untuk JOIN dan hindari N+1 query.
        """
        queryset = Absensi.objects.select_related('karyawan').order_by('-tanggal', '-jam_masuk')

        # Ambil parameter filter tanggal dari URL query string
        tanggal_dari = self.request.GET.get('tanggal_dari')      # Format: YYYY-MM-DD
        tanggal_sampai = self.request.GET.get('tanggal_sampai')  # Format: YYYY-MM-DD

        # Terapkan filter tanggal jika diberikan
        if tanggal_dari:
            queryset = queryset.filter(tanggal__gte=tanggal_dari)    # Tanggal >= dari
        if tanggal_sampai:
            queryset = queryset.filter(tanggal__lte=tanggal_sampai)  # Tanggal <= sampai

        return queryset

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik absensi ke context:
        - total_absensi: jumlah record absensi (setelah filter)
        - today: tanggal hari ini untuk default filter
        - karyawan_list: dropdown filter karyawan
        - total_hadir/total_terlambat: hitungan per status
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_absensi - untuk ditampilkan di template
        context['total_absensi'] = self.get_queryset().count()                         # Total record
        # Data konteks: today - untuk ditampilkan di template
        context['today'] = timezone.now().date()                                       # Tanggal hari ini
        # Query database - ambil data context['karyawan_list'] yang sesuai filter
        # Data konteks: karyawan_list - untuk ditampilkan di template
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True).order_by('nama') # Untuk filter dropdown
        # Data konteks: total_hadir - untuk ditampilkan di template
        context['total_hadir'] = self.get_queryset().filter(status='hadir').count()         # Jumlah hadir tepat waktu
        # Data konteks: total_terlambat - untuk ditampilkan di template
        context['total_terlambat'] = self.get_queryset().filter(status='terlambat').count() # Jumlah terlambat
        return context



class AbsensiCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambah absensi secara manual.

    URL: /hr/absensi/add/
    Permission: hr.create
    Template: hr/absensi_form.html

    Catatan: ini untuk input absensi manual oleh admin/HR.
    Untuk clock in/out otomatis, gunakan API absensi_clock_in/out.
    """
    model = Absensi
    form_class = AbsensiForm                        # Form: karyawan, tanggal, jam, status
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/absensi_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:absensi')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Absensi Manual' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Absensi Manual'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Absensi berhasil ditambahkan')
        return super().form_valid(form)



class AbsensiDeteksiWajahView(ReadPermissionMixin, TemplateView):
    """
    Halaman absensi dengan deteksi wajah (face recognition).

    URL: /hr/absensi/deteksi-wajah/
    Permission: hr.read
    Template: hr/absensi_deteksi.html

    Halaman ini menyediakan antarmuka kamera untuk:
    - Mendeteksi wajah karyawan secara real-time
    - Melakukan clock in/out otomatis berdasarkan matching wajah
    """
    template_name = 'hr/absensi_deteksi.html'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menyediakan data karyawan aktif dan waktu saat ini untuk form absensi."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database - ambil data context['karyawan_list'] yang sesuai filter
        # Data konteks: karyawan_list - untuk ditampilkan di template
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True, status='aktif')  # Hanya karyawan aktif
        # Data konteks: today - untuk ditampilkan di template
        context['today'] = timezone.now().date()  # Tanggal hari ini
        # Data konteks: now - untuk ditampilkan di template
        context['now'] = timezone.now()           # Waktu saat ini (untuk tampilan jam)
        # Data konteks: pengaturan - pengaturan absensi aktif (untuk lokasi kantor & radius)
        context['pengaturan'] = PengaturanAbsensi.get_active()
        return context


# Wajib login - redirect ke login page jika belum login
@login_required
def absensi_clock_in(request):
    """
    API endpoint untuk melakukan Clock In karyawan.

    URL: /hr/absensi/clock-in/  (POST only)
    Input: karyawan_id (POST), foto (FILES, opsional), latitude, longitude (POST, opsional)
    Response: JSON {success, message, jarak, lokasi_valid}

    Alur kerja:
    1. Cari karyawan berdasarkan ID
    2. Cek apakah sudah clock in hari ini (get_or_create)
    3. Jika belum → buat record absensi baru
        - Hitung jarak dari kantor via Geopy (jika GPS tersedia)
        - Validasi radius (jika wajib_lokasi aktif)
        - Jam masuk < 09:00 → status 'hadir'
        - Jam masuk >= 09:00 → status 'terlambat'
    4. Jika sudah → return error (tidak boleh clock in 2x)
    """
    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'create', 'hr', 'absensi'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk membuat data absensi.'}, status=403)

        karyawan_id = request.POST.get('karyawan_id')  # ID karyawan dari form
        foto = request.FILES.get('foto')                # Foto opsional (selfie saat clock in)
        latitude = request.POST.get('latitude')          # Latitude GPS dari device
        longitude = request.POST.get('longitude')        # Longitude GPS dari device

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Cari karyawan - harus aktif
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
            today = timezone.now().date()   # Tanggal hari ini
            now = timezone.now().time()     # Jam saat ini

            # === GPS LOCATION TRACKING ===
            lokasi_masuk_str = None
            jarak_masuk_val = None
            lokasi_valid = True  # Default: valid (jika GPS tidak dikirim)

            if latitude and longitude and GEOLOCATION_ENABLED:
                try:
                    lat = float(latitude)
                    lng = float(longitude)
                    lokasi_masuk_str = f"{lat},{lng}"

                    # Hitung jarak dari kantor menggunakan Geopy
                    pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)
                    if pengaturan and pengaturan.latitude and pengaturan.longitude:
                        kantor = (float(pengaturan.latitude), float(pengaturan.longitude))
                        karyawan_pos = (lat, lng)
                        jarak_masuk_val = round(geodesic(kantor, karyawan_pos).meters, 1)

                        # Validasi radius jika wajib_lokasi aktif
                        if pengaturan.wajib_lokasi and jarak_masuk_val > pengaturan.radius_lokasi:
                            lokasi_valid = False
                            return JsonResponse({
                                'success': False,
                                'message': f'Lokasi Anda di luar radius kantor ({jarak_masuk_val:.0f}m dari kantor, batas: {pengaturan.radius_lokasi}m). Silakan absen dari lokasi yang lebih dekat.',
                                'jarak': jarak_masuk_val,
                                'lokasi_valid': False
                            })
                except (ValueError, TypeError):
                    pass  # GPS data invalid, lanjutkan tanpa lokasi

            # Tentukan status berdasarkan pengaturan absensi
            pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)
            if pengaturan:
                batas_terlambat = pengaturan.jam_masuk
                # Tambah toleransi
                from datetime import datetime as dt_cls, timedelta as td_cls
                batas_waktu = (dt_cls.combine(today, batas_terlambat) + td_cls(minutes=pengaturan.toleransi_terlambat)).time()
                status_absen = 'hadir' if now <= batas_waktu else 'terlambat'
            else:
                status_absen = 'hadir' if now.hour < 9 else 'terlambat'

            # get_or_create() = cari record, jika tidak ada maka buat baru
            absensi, created = Absensi.objects.get_or_create(
                karyawan=karyawan,
                tanggal=today,
                defaults={
                    'jam_masuk': now,
                    'status': status_absen,
                    'foto_masuk': foto,
                    'lokasi_masuk': lokasi_masuk_str,
                    'jarak_masuk': jarak_masuk_val,
                    'cabang': karyawan.cabang,
                    'pengaturan_snapshot': pengaturan,
                }
            )

            # Jika record sudah ada (created=False), tolak clock in duplikat
            if not created:
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} sudah melakukan clock in hari ini'
                })

            # Berhasil clock in - return success dengan info lokasi
            response_data = {
                'success': True,
                'message': f'Clock In berhasil untuk {karyawan.nama} pada {now.strftime("%H:%M")}'
            }
            if jarak_masuk_val is not None:
                response_data['message'] += f' (Jarak: {jarak_masuk_val:.0f}m dari kantor)'
                response_data['jarak'] = jarak_masuk_val
                response_data['lokasi_valid'] = lokasi_valid

            return JsonResponse(response_data)

        # Tangkap error Karyawan.DoesNotExist - lanjutkan tanpa crash
        except Karyawan.DoesNotExist:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': 'Karyawan tidak ditemukan'}, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    # Hanya menerima method POST
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)


# Wajib login - redirect ke login page jika belum login
@login_required
def absensi_clock_out(request):
    """
    API endpoint untuk melakukan Clock Out karyawan.

    URL: /hr/absensi/clock-out/  (POST only)
    Input: karyawan_id (POST), foto (FILES, opsional), latitude, longitude (POST, opsional)
    Response: JSON {success, message, jarak}

    Alur kerja:
    1. Cari karyawan berdasarkan ID
    2. Cari record absensi hari ini (harus sudah clock in)
    3. Cek apakah sudah clock out (jam_keluar sudah terisi)
    4. Jika belum → isi jam_keluar, lokasi_keluar, jarak_keluar dan simpan
    5. Jika sudah → return error (tidak boleh clock out 2x)
    """
    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'hr', 'absensi'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengubah data absensi.'}, status=403)

        karyawan_id = request.POST.get('karyawan_id')  # ID karyawan dari form
        foto = request.FILES.get('foto')                # Foto opsional (selfie saat clock out)
        latitude = request.POST.get('latitude')          # Latitude GPS dari device
        longitude = request.POST.get('longitude')        # Longitude GPS dari device

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Query database - ambil satu data karyawan
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
            today = timezone.now().date()
            now = timezone.now().time()

            # === GPS LOCATION TRACKING ===
            lokasi_keluar_str = None
            jarak_keluar_val = None

            if latitude and longitude and GEOLOCATION_ENABLED:
                try:
                    lat = float(latitude)
                    lng = float(longitude)
                    lokasi_keluar_str = f"{lat},{lng}"

                    # Hitung jarak dari kantor menggunakan Geopy
                    pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)
                    if pengaturan and pengaturan.latitude and pengaturan.longitude:
                        kantor = (float(pengaturan.latitude), float(pengaturan.longitude))
                        karyawan_pos = (lat, lng)
                        jarak_keluar_val = round(geodesic(kantor, karyawan_pos).meters, 1)
                except (ValueError, TypeError):
                    pass  # GPS data invalid, lanjutkan tanpa lokasi

            # Cari record absensi hari ini - harus sudah clock in
            try:
                # Query database - ambil satu data absensi
                absensi = Absensi.objects.get(karyawan=karyawan, tanggal=today)

                # Cek apakah sudah clock out (jam_keluar sudah terisi)
                if absensi.jam_keluar:
                    return JsonResponse({
                        'success': False,
                        'message': f'{karyawan.nama} sudah melakukan clock out hari ini'
                    })

                # Isi jam keluar, foto, lokasi, dan jarak, lalu simpan
                absensi.jam_keluar = now                    # Set jam keluar = waktu sekarang
                absensi.foto_keluar = foto                  # Simpan foto clock out
                absensi.lokasi_keluar = lokasi_keluar_str   # Simpan lokasi GPS keluar
                absensi.jarak_keluar = jarak_keluar_val     # Simpan jarak dari kantor
                absensi.save()                              # Update ke database

                response_data = {
                    'success': True,
                    'message': f'Clock Out berhasil untuk {karyawan.nama} pada {now.strftime("%H:%M")}'
                }
                if jarak_keluar_val is not None:
                    response_data['message'] += f' (Jarak: {jarak_keluar_val:.0f}m dari kantor)'
                    response_data['jarak'] = jarak_keluar_val

                return JsonResponse(response_data)

            # Tangkap error Absensi.DoesNotExist - lanjutkan tanpa crash
            except Absensi.DoesNotExist:
                # Belum clock in hari ini - tidak bisa clock out
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} belum melakukan clock in hari ini'
                })

        # Tangkap error Karyawan.DoesNotExist - lanjutkan tanpa crash
        except Karyawan.DoesNotExist:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': 'Karyawan tidak ditemukan'}, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    # Hanya menerima method POST
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)


@login_required
@xframe_options_exempt
def absensi_lokasi_map(request, pk):
    """
    API endpoint untuk generate peta Folium dari lokasi absensi karyawan.

    URL: /hr/absensi/<pk>/lokasi-map/
    Response: Standalone HTML page — peta Folium atau empty state jika tidak ada GPS data
    """
    from django.http import HttpResponse

    try:
        absensi = Absensi.objects.select_related('karyawan').get(pk=pk)
    except Absensi.DoesNotExist:
        return HttpResponse(_map_empty_html('Data absensi tidak ditemukan'), content_type='text/html')

    # Jika tidak ada data lokasi GPS sama sekali → tampilkan empty state
    if not absensi.lokasi_masuk and not absensi.lokasi_keluar:
        return HttpResponse(_map_empty_html(
            'Data lokasi GPS belum tersedia',
            'Lokasi akan terekam otomatis saat karyawan melakukan absensi via Deteksi Wajah.'
        ), content_type='text/html')

    if not FOLIUM_ENABLED:
        return HttpResponse(_map_empty_html(
            'Library Folium tidak terinstall',
            'Silakan install folium: pip install folium'
        ), content_type='text/html')

    # Tentukan center peta — prioritas: lokasi masuk > lokasi kantor > default Jakarta
    pengaturan = PengaturanAbsensi.get_active(cabang=absensi.cabang)
    center_lat, center_lng = -6.2088, 106.8456  # Default: Jakarta

    if pengaturan and pengaturan.latitude and pengaturan.longitude:
        center_lat = float(pengaturan.latitude)
        center_lng = float(pengaturan.longitude)

    # Buat peta Folium
    m = folium.Map(location=[center_lat, center_lng], zoom_start=16, tiles='OpenStreetMap')

    # Marker lokasi kantor (jika ada pengaturan)
    if pengaturan and pengaturan.latitude and pengaturan.longitude:
        folium.Marker(
            [float(pengaturan.latitude), float(pengaturan.longitude)],
            popup=f'<b>Kantor</b><br>{pengaturan.nama_lokasi or "Lokasi Kantor"}',
            icon=folium.Icon(color='blue', icon='building', prefix='fa'),
            tooltip='Lokasi Kantor'
        ).add_to(m)

        # Lingkaran radius kantor
        folium.Circle(
            [float(pengaturan.latitude), float(pengaturan.longitude)],
            radius=pengaturan.radius_lokasi,
            color='blue',
            fill=True,
            fill_opacity=0.1,
            popup=f'Radius Absensi: {pengaturan.radius_lokasi}m'
        ).add_to(m)

    # Marker lokasi masuk (jika ada)
    if absensi.lokasi_masuk:
        try:
            lat, lng = [float(x) for x in absensi.lokasi_masuk.split(',')]
            jarak_text = f'<br>Jarak: {absensi.jarak_masuk:.0f}m' if absensi.jarak_masuk else ''
            folium.Marker(
                [lat, lng],
                popup=f'<b>Clock In</b><br>{absensi.karyawan.nama}<br>{absensi.jam_masuk.strftime("%H:%M") if absensi.jam_masuk else "-"}{jarak_text}',
                icon=folium.Icon(color='green', icon='sign-in', prefix='fa'),
                tooltip=f'Clock In - {absensi.karyawan.nama}'
            ).add_to(m)
            center_lat, center_lng = lat, lng
        except (ValueError, AttributeError):
            pass

    # Marker lokasi keluar (jika ada)
    if absensi.lokasi_keluar:
        try:
            lat, lng = [float(x) for x in absensi.lokasi_keluar.split(',')]
            jarak_text = f'<br>Jarak: {absensi.jarak_keluar:.0f}m' if absensi.jarak_keluar else ''
            folium.Marker(
                [lat, lng],
                popup=f'<b>Clock Out</b><br>{absensi.karyawan.nama}<br>{absensi.jam_keluar.strftime("%H:%M") if absensi.jam_keluar else "-"}{jarak_text}',
                icon=folium.Icon(color='red', icon='sign-out', prefix='fa'),
                tooltip=f'Clock Out - {absensi.karyawan.nama}'
            ).add_to(m)
        except (ValueError, AttributeError):
            pass

    # Refit center peta
    m.location = [center_lat, center_lng]

    return HttpResponse(m._repr_html_(), content_type='text/html')


def _map_empty_html(title, subtitle=''):
    """Helper: Generate styled empty state HTML untuk iframe peta."""
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ margin:0; display:flex; align-items:center; justify-content:center; height:100vh;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       background:#f5f5f9; color:#697a8d; text-align:center; }}
.empty {{ padding:2rem; }}
.empty svg {{ width:64px; height:64px; fill:#a1acb8; margin-bottom:1rem; }}
.empty h5 {{ color:#566a7f; margin:0 0 0.5rem; font-size:1.1rem; }}
.empty p {{ margin:0; font-size:0.875rem; color:#a1acb8; }}
</style></head><body>
<div class="empty">
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/></svg>
  <h5>{title}</h5>
  {"<p>" + subtitle + "</p>" if subtitle else ""}
</div>
</body></html>'''


class AbsensiDetailView(ReadPermissionMixin, DetailView):
    """
    Halaman detail absensi - menampilkan data lengkap + peta lokasi.

    URL: /hr/absensi/<pk>/detail/
    Permission: hr.read
    Template: hr/absensi_detail.html

    Context tambahan:
    - peta_html: Peta Folium (HTML string) dengan lokasi masuk/keluar
    - pengaturan: PengaturanAbsensi aktif (jam kerja, lokasi, radius, dll)
    """
    model = Absensi
    template_name = 'hr/absensi_detail.html'
    context_object_name = 'absensi'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan peta Folium dan pengaturan absensi ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        absensi = self.object
        pengaturan = PengaturanAbsensi.get_active(cabang=absensi.cabang)
        context['pengaturan'] = pengaturan

        # Generate peta Folium jika ada data lokasi dan Folium terinstall
        if FOLIUM_ENABLED and (absensi.lokasi_masuk or absensi.lokasi_keluar):
            center_lat, center_lng = -6.2088, 106.8456

            if pengaturan and pengaturan.latitude and pengaturan.longitude:
                center_lat = float(pengaturan.latitude)
                center_lng = float(pengaturan.longitude)

            m = folium.Map(location=[center_lat, center_lng], zoom_start=16, tiles='OpenStreetMap')

            # Marker lokasi kantor
            if pengaturan and pengaturan.latitude and pengaturan.longitude:
                folium.Marker(
                    [float(pengaturan.latitude), float(pengaturan.longitude)],
                    popup=f'<b>Kantor</b><br>{pengaturan.nama_lokasi or "Lokasi Kantor"}',
                    icon=folium.Icon(color='blue', icon='building', prefix='fa'),
                    tooltip='Lokasi Kantor'
                ).add_to(m)
                folium.Circle(
                    [float(pengaturan.latitude), float(pengaturan.longitude)],
                    radius=pengaturan.radius_lokasi,
                    color='blue', fill=True, fill_opacity=0.1,
                    popup=f'Radius: {pengaturan.radius_lokasi}m'
                ).add_to(m)

            # Marker lokasi masuk
            if absensi.lokasi_masuk:
                try:
                    lat, lng = [float(x) for x in absensi.lokasi_masuk.split(',')]
                    jarak_text = f'<br>Jarak: {absensi.jarak_masuk:.0f}m' if absensi.jarak_masuk else ''
                    folium.Marker(
                        [lat, lng],
                        popup=f'<b>Clock In</b><br>{absensi.karyawan.nama}<br>{absensi.jam_masuk.strftime("%H:%M") if absensi.jam_masuk else "-"}{jarak_text}',
                        icon=folium.Icon(color='green', icon='sign-in', prefix='fa'),
                        tooltip=f'Clock In - {absensi.karyawan.nama}'
                    ).add_to(m)
                    center_lat, center_lng = lat, lng
                except (ValueError, AttributeError):
                    pass

            # Marker lokasi keluar
            if absensi.lokasi_keluar:
                try:
                    lat, lng = [float(x) for x in absensi.lokasi_keluar.split(',')]
                    jarak_text = f'<br>Jarak: {absensi.jarak_keluar:.0f}m' if absensi.jarak_keluar else ''
                    folium.Marker(
                        [lat, lng],
                        popup=f'<b>Clock Out</b><br>{absensi.karyawan.nama}<br>{absensi.jam_keluar.strftime("%H:%M") if absensi.jam_keluar else "-"}{jarak_text}',
                        icon=folium.Icon(color='red', icon='sign-out', prefix='fa'),
                        tooltip=f'Clock Out - {absensi.karyawan.nama}'
                    ).add_to(m)
                except (ValueError, AttributeError):
                    pass

            m.location = [center_lat, center_lng]
            context['peta_html'] = m._repr_html_()
        else:
            context['peta_html'] = None

        return context



class AbsensiUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit record absensi yang sudah ada.

    URL: /hr/absensi/<pk>/edit/
    Permission: hr.edit
    Template: hr/absensi_form.html
    """
    model = Absensi
    form_class = AbsensiForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/absensi_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:absensi')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Absensi' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Absensi'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Absensi berhasil diupdate')
        return super().form_valid(form)



class AbsensiDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus record absensi - dipanggil via AJAX.

    URL: /hr/absensi/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}
    """
    model = Absensi
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:absensi')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON - sertakan nama karyawan dan tanggal."""
        self.object = self.get_object()
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            karyawan_nama = self.object.karyawan.nama  # Nama karyawan untuk pesan
            tanggal = self.object.tanggal               # Tanggal absensi untuk pesan
            self.object.delete()
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': f'Absensi {karyawan_nama} tanggal {tanggal} berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
                        # ║  PENGGAJIAN - Slip gaji + generate massal                     ║
                        # ║  GeneratePenggajianView: buat slip untuk SEMUA karyawan aktif ║
                        # ║  PenggajianUpdateStatusView: update status bayar              ║
# ╚══════════════════════════════════════════════════════════════╝
class PenggajianListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua slip gaji karyawan.

    URL: /hr/penggajian/
    Permission: hr.penggajian.read (SubCRUD)
    Template: hr/penggajian_list.html

    Context tambahan:
    - total_slip: jumlah total slip gaji
    - grand_total: total seluruh gaji bersih
    - total_dibayar/total_diproses: hitungan per status
    - karyawan_list: untuk filter dropdown
    """
    model = Penggajian                              # Model: Penggajian (slip gaji)
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/penggajian_list.html'       # Template daftar slip gaji
    context_object_name = 'penggajian_list'         # Nama variabel di template
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'penggajian'            # Sub-modul: penggajian

    def get_queryset(self):
        """
        Query slip gaji dengan JOIN ke karyawan.
        Urutkan dari periode terbaru (tahun desc, bulan desc).
        """
        return Penggajian.objects.select_related('karyawan').order_by('-periode_tahun', '-periode_bulan')

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik penggajian untuk summary card dan filter.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        queryset = self.get_queryset()
        # Data konteks: total_slip - untuk ditampilkan di template
        context['total_slip'] = queryset.count()                                          # Jumlah slip
        # Data konteks: grand_total - untuk ditampilkan di template
        context['grand_total'] = queryset.aggregate(total=Sum('gaji_bersih'))['total'] or 0  # Total gaji bersih
        # Data konteks: total_gaji_pokok - untuk export FOOTER_DATA
        context['total_gaji_pokok'] = queryset.aggregate(total=Sum('gaji_pokok'))['total'] or 0
        # Data konteks: total_tunjangan - untuk export FOOTER_DATA
        from django.db.models.functions import Coalesce
        from django.db.models import Value, DecimalField as DjDecimalField
        context['total_tunjangan'] = queryset.aggregate(
            total=Sum(
                Coalesce(F('tunjangan_jabatan'), Value(0), output_field=DjDecimalField()) +
                Coalesce(F('tunjangan_makan'), Value(0), output_field=DjDecimalField()) +
                Coalesce(F('tunjangan_transport'), Value(0), output_field=DjDecimalField()) +
                Coalesce(F('tunjangan_lainnya'), Value(0), output_field=DjDecimalField()) +
                Coalesce(F('lembur'), Value(0), output_field=DjDecimalField()) +
                Coalesce(F('bonus'), Value(0), output_field=DjDecimalField()),
                output_field=DjDecimalField()
            )
        )['total'] or 0
        # Data konteks: total_potongan - untuk export FOOTER_DATA
        context['total_potongan'] = queryset.aggregate(total=Sum('total_potongan'))['total'] or 0
        # Data konteks: total_dibayar - untuk ditampilkan di template
        context['total_dibayar'] = queryset.filter(status='dibayar').count()               # Sudah dibayar
        # Data konteks: total_diproses - untuk ditampilkan di template
        context['total_diproses'] = queryset.filter(status='diproses').count()             # Masih diproses
        # Query database - ambil data context['karyawan_list'] yang sesuai filter
        # Data konteks: karyawan_list - untuk ditampilkan di template
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True).order_by('nama')    # Dropdown filter
        return context



class PenggajianCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk membuat slip gaji individual untuk satu karyawan.

    URL: /hr/penggajian/add/
    Permission: hr.penggajian.create
    Template: hr/penggajian_form.html

    Catatan: Untuk generate slip gaji massal (semua karyawan sekaligus),
    gunakan GeneratePenggajianView.
    """
    model = Penggajian
    form_class = PenggajianForm                     # Form: karyawan, periode, gaji_pokok, tunjangan, potongan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/penggajian_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:penggajian')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Slip Gaji' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Slip Gaji'
        return context


    def form_valid(self, form):

        form.instance.dibuat_oleh = self.request.user  # User yang membuat slip
        response = super().form_valid(form)
        
        # Kirim notifikasi Telegram
        try:
            from apps.automation.signals import kirim_notifikasi_penggajian
            kirim_notifikasi_penggajian(self.object)
        except Exception as e:
            logger.warning("Gagal kirim notifikasi: %s", e)

        # Tampilkan pesan sukses ke user
        messages.success(self.request, 'Slip gaji berhasil dibuat')
        return response



class PenggajianUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit slip gaji yang sudah ada.

    URL: /hr/penggajian/<pk>/edit/
    Permission: hr.penggajian.edit
    Template: hr/penggajian_form.html
    """
    model = Penggajian
    form_class = PenggajianForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/penggajian_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:penggajian')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Slip Gaji' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Slip Gaji'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Slip gaji berhasil diupdate')
        return super().form_valid(form)



class PenggajianDetailView(ReadPermissionMixin, DetailView):
    """
    Halaman detail slip gaji - menampilkan rincian gaji lengkap.

    URL: /hr/penggajian/<pk>/
    Permission: hr.read
    Template: hr/penggajian_detail.html

    Menampilkan: gaji pokok, tunjangan, potongan, gaji bersih, status bayar.
    """
    model = Penggajian
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/penggajian_detail.html'
    context_object_name = 'slip'                    # Nama variabel di template = 'slip'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Inisialisasi layout. Data slip sudah tersedia via self.object."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        return context


class PenggajianPrintView(ReadPermissionMixin, DetailView):
    """
    Cetak slip gaji - template standalone A4 (tanpa layout dashboard).

    URL: /hr/penggajian/<pk>/print/
    Permission: hr.read
    Template: hr/penggajian_print.html (standalone, auto window.print())

    Menggunakan TemplateCetak.get_template('slip_gaji') untuk header,
    footer, dan signature - sama seperti PO/SO/Invoice print.
    """
    model = Penggajian
    # Template HTML yang digunakan untuk render halaman
    template_name = 'hr/penggajian_print.html'
    context_object_name = 'slip'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan template cetak ke context."""
        context = super().get_context_data(**kwargs)
        # Import dari modul internal proyek
        from apps.pengaturan.models import TemplateCetak, PengaturanPerusahaan
        # Data konteks: template - untuk ditampilkan di template
        context['template'] = TemplateCetak.get_template('slip_gaji')
        # Data konteks: perusahaan — untuk logo di header cetak
        context['perusahaan'] = PengaturanPerusahaan.load()
        return context


class PenggajianDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus slip gaji - dipanggil via AJAX.

    URL: /hr/penggajian/<pk>/delete/
    Permission: hr.penggajian.delete
    Response: JSON {success, message}
    """
    model = Penggajian
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:penggajian')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON - sertakan nama karyawan dan periode."""
        self.object = self.get_object()
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            karyawan_nama = self.object.karyawan.nama  # Nama karyawan untuk pesan
            periode = self.object.periode               # Periode slip untuk pesan
            self.object.delete()
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': f'Slip gaji {karyawan_nama} {periode} berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=400)



class GeneratePenggajianView(CreatePermissionMixin, TemplateView):
    """
    Generate slip gaji massal untuk SEMUA karyawan aktif dalam satu periode.

    URL: /hr/penggajian/generate/
    Permission: hr.create
    Template: hr/penggajian_generate.html

    Alur kerja (POST):
    1. Validasi form (bulan, tahun, tunjangan_makan, tunjangan_transport)
    2. Loop semua karyawan aktif
    3. Cek duplikasi - skip jika slip sudah ada untuk periode tersebut
    4. Buat slip gaji baru dengan gaji_pokok dari karyawan/jabatan
    5. Report: berapa yang dibuat vs dilewati
    """
    template_name = 'hr/penggajian_generate.html'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menyediakan form generate dan jumlah karyawan yang akan diproses."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = GeneratePenggajianForm()                                          # Form: bulan, tahun, tunjangan
        # Query database - ambil data context['karyawan_count'] yang sesuai filter
        # Data konteks: karyawan_count - untuk ditampilkan di template
        context['karyawan_count'] = Karyawan.objects.filter(aktif=True, status='aktif').count()  # Jumlah karyawan aktif
        return context


    def post(self, request, *args, **kwargs):
        """
        Proses generate slip gaji massal.
        Iterasi semua karyawan aktif, cek duplikasi, buat slip baru.
        """
        form = GeneratePenggajianForm(request.POST)

        if form.is_valid():
            # Ambil data dari form yang sudah divalidasi
            bulan = int(form.cleaned_data['periode_bulan'])           # Bulan (1-12)
            tahun = int(form.cleaned_data['periode_tahun'])           # Tahun (YYYY)
            tunjangan_makan = form.cleaned_data['tunjangan_makan']       # Tunjangan makan per bulan
            tunjangan_transport = form.cleaned_data['tunjangan_transport'] # Tunjangan transport per bulan
            metode_pembayaran = form.cleaned_data.get('metode_pembayaran') or get_default_payroll_payment_method()

            # Ambil semua karyawan aktif untuk dibuatkan slip
            karyawan_list = Karyawan.objects.filter(aktif=True, status='aktif')
            created_count = 0   # Counter slip yang berhasil dibuat
            skipped_count = 0   # Counter slip yang dilewati (sudah ada)
            created_slips = []

            with transaction.atomic():
                for karyawan in karyawan_list.select_for_update():
                    # Cek apakah slip sudah ada untuk karyawan + periode ini
                    exists = Penggajian.objects.filter(
                        karyawan=karyawan,
                        periode_bulan=bulan,
                        periode_tahun=tahun
                    ).exists()

                    if exists:
                        skipped_count += 1  # Lewati, jangan buat duplikat
                        continue

                    # Buat slip gaji baru
                    # gaji_pokok: prioritas dari karyawan, fallback ke jabatan
                    # tunjangan_jabatan: dari jabatan karyawan (jika ada)
                    slip_baru = Penggajian.objects.create(
                        karyawan=karyawan,
                        periode_bulan=bulan,
                        periode_tahun=tahun,
                        gaji_pokok=karyawan.gaji_pokok or karyawan.jabatan.gaji_pokok,
                        tunjangan_jabatan=karyawan.jabatan.tunjangan_jabatan if karyawan.jabatan else 0,
                        tunjangan_makan=tunjangan_makan,
                        tunjangan_transport=tunjangan_transport,
                        cabang=karyawan.cabang,
                        metode_pembayaran=metode_pembayaran,
                        dibuat_oleh=request.user  # User yang menjalankan generate
                    )
                    created_slips.append(slip_baru)
                    created_count += 1

            for slip_baru in created_slips:
                # Kirim notifikasi Telegram
                try:
                    from apps.automation.signals import kirim_notifikasi_penggajian
                    kirim_notifikasi_penggajian(slip_baru)
                except Exception as e:
                    logger.warning("Gagal kirim notifikasi: %s", e)

            # Tampilkan ringkasan hasil generate
            messages.success(
                request,
                f'Berhasil generate {created_count} slip gaji. {skipped_count} dilewati (sudah ada).'
            )
            # Redirect ke halaman tujuan
            return redirect('hr:penggajian')

        # Form tidak valid - tampilkan ulang dengan error
        context = self.get_context_data()
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = form
        # Render template HTML dengan data konteks
        return render(request, self.template_name, context)



class ImportPenggajianView(CreatePermissionMixin, TemplateView):
    """
    Import penggajian massal dari file Excel/CSV.

    URL: /hr/penggajian/import/
    Permission: hr.create
    Template: hr/penggajian_import.html

    Alur kerja (POST):
    1. Validasi file upload (format, ukuran)
    2. Baca data dari Excel/CSV
    3. Validasi setiap baris (NIK ada, periode valid, tidak duplikat)
    4. Buat slip gaji baru dalam transaction.atomic()
    5. Report: berapa sukses, gagal, dilewati
    """
    template_name = 'hr/penggajian_import.html'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'
    permission_sub_module = 'penggajian_import'

    def get_context_data(self, **kwargs):
        """Menyediakan jumlah karyawan aktif untuk info di template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['karyawan_count'] = Karyawan.objects.filter(aktif=True, status='aktif').count()
        return context

    def post(self, request, *args, **kwargs):
        """Proses import file Excel/CSV untuk membuat slip gaji massal."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        file = request.FILES.get('file')

        if not file:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'File tidak ditemukan. Silakan pilih file untuk diupload.'})
            messages.error(request, 'File tidak ditemukan. Silakan pilih file untuk diupload.')
            return redirect('hr:penggajian-import')

        # Validasi ukuran file (max 5MB)
        if file.size > 5 * 1024 * 1024:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Ukuran file terlalu besar. Maksimal 5MB.'})
            messages.error(request, 'Ukuran file terlalu besar. Maksimal 5MB.')
            return redirect('hr:penggajian-import')

        file_name = file.name.lower()
        rows = []

        try:
            if file_name.endswith(('.xlsx', '.xls')):
                rows = self._read_excel(file)
            elif file_name.endswith('.csv'):
                rows = self._read_csv(file)
            else:
                if is_ajax:
                    return JsonResponse({'success': False, 'message': 'Format file tidak didukung. Gunakan .xlsx, .xls, atau .csv'})
                messages.error(request, 'Format file tidak didukung. Gunakan .xlsx, .xls, atau .csv')
                return redirect('hr:penggajian-import')
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'message': f'Gagal membaca file: {str(e)}'})
            messages.error(request, f'Gagal membaca file: {str(e)}')
            return redirect('hr:penggajian-import')

        if not rows:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'File kosong atau tidak memiliki data yang valid.'})
            messages.error(request, 'File kosong atau tidak memiliki data yang valid.')
            return redirect('hr:penggajian-import')

        # Proses import
        from django.db import transaction
        created_count = 0
        skipped_count = 0
        error_messages = []
        default_metode_pembayaran = get_default_payroll_payment_method()

        for idx, row in enumerate(rows, start=2):  # start=2 karena baris 1 = header
            nik = str(row.get('nik_karyawan', '')).strip()
            periode_bulan = row.get('periode_bulan')
            periode_tahun = row.get('periode_tahun')

            # Validasi field wajib
            if not nik:
                error_messages.append(f'Baris {idx}: NIK Karyawan kosong')
                continue
            if not periode_bulan or not periode_tahun:
                error_messages.append(f'Baris {idx}: Periode bulan/tahun kosong')
                continue

            try:
                periode_bulan = int(float(str(periode_bulan)))
                periode_tahun = int(float(str(periode_tahun)))
            except (ValueError, TypeError):
                error_messages.append(f'Baris {idx}: Periode bulan/tahun tidak valid')
                continue

            if not (1 <= periode_bulan <= 12):
                error_messages.append(f'Baris {idx}: Periode bulan harus 1-12')
                continue

            # Cari karyawan berdasarkan NIK
            try:
                karyawan = Karyawan.objects.get(nik=nik)
            except Karyawan.DoesNotExist:
                error_messages.append(f'Baris {idx}: Karyawan dengan NIK "{nik}" tidak ditemukan')
                continue

            # Cek duplikasi
            exists = Penggajian.objects.filter(
                karyawan=karyawan,
                periode_bulan=periode_bulan,
                periode_tahun=periode_tahun
            ).exists()

            if exists:
                skipped_count += 1
                continue

            # Parse komponen gaji — helper untuk parse decimal
            def parse_decimal(val, default=Decimal('0')):
                if val is None or str(val).strip() == '':
                    return default
                try:
                    return Decimal(str(val).strip().replace(',', ''))
                except Exception:
                    return default

            gaji_pokok_val = parse_decimal(row.get('gaji_pokok'))
            if gaji_pokok_val == 0:
                # Ambil dari data karyawan / jabatan
                gaji_pokok_val = karyawan.gaji_pokok or (karyawan.jabatan.gaji_pokok if karyawan.jabatan else Decimal('0'))

            tunjangan_jabatan_val = parse_decimal(row.get('tunjangan_jabatan'))
            if tunjangan_jabatan_val == 0 and not row.get('tunjangan_jabatan'):
                # Jika tidak disediakan di file, ambil dari jabatan
                tunjangan_jabatan_val = karyawan.jabatan.tunjangan_jabatan if karyawan.jabatan else Decimal('0')

            # Parse status
            status_val = str(row.get('status', 'draft')).strip().lower()
            if status_val not in ('draft', 'diproses', 'dibayar', 'batal'):
                status_val = 'draft'

            try:
                with transaction.atomic():
                    slip = Penggajian.objects.create(
                        karyawan=karyawan,
                        periode_bulan=periode_bulan,
                        periode_tahun=periode_tahun,
                        gaji_pokok=gaji_pokok_val,
                        tunjangan_jabatan=tunjangan_jabatan_val,
                        tunjangan_makan=parse_decimal(row.get('tunjangan_makan')),
                        tunjangan_transport=parse_decimal(row.get('tunjangan_transport')),
                        tunjangan_lainnya=parse_decimal(row.get('tunjangan_lainnya')),
                        lembur=parse_decimal(row.get('lembur')),
                        bonus=parse_decimal(row.get('bonus')),
                        potongan_bpjs_kesehatan=parse_decimal(row.get('bpjs_kesehatan')),
                        potongan_bpjs_ketenagakerjaan=parse_decimal(row.get('bpjs_ketenagakerjaan')),
                        potongan_pph21=parse_decimal(row.get('pph21')),
                        potongan_lainnya=parse_decimal(row.get('potongan_lainnya')),
                        status=status_val,
                        cabang=karyawan.cabang,
                        metode_pembayaran=default_metode_pembayaran,
                        catatan=str(row.get('catatan', '')).strip() or None,
                        dibuat_oleh=request.user,
                    )

                    if slip.status == 'dibayar':
                        create_penggajian_payment_journal(slip, user=request.user)

                    # Kirim notifikasi Telegram
                    try:
                        from apps.automation.signals import kirim_notifikasi_penggajian
                        kirim_notifikasi_penggajian(slip)
                    except Exception as e:
                        logger.warning("Gagal kirim notifikasi: %s", e)

                    created_count += 1
            except Exception as e:
                error_messages.append(f'Baris {idx}: Gagal membuat slip - {str(e)}')

        # Ringkasan hasil
        msg_parts = []
        if created_count > 0:
            msg_parts.append(f'{created_count} slip gaji berhasil diimpor')
        if skipped_count > 0:
            msg_parts.append(f'{skipped_count} dilewati (sudah ada)')
        if error_messages:
            msg_parts.append(f'{len(error_messages)} error')

        result_message = '. '.join(msg_parts) + '.' if msg_parts else 'Tidak ada data yang diproses.'

        # Tambahkan error detail (max 10)
        if error_messages:
            detail = '<br><br><strong>Detail Error:</strong><ul>'
            for err in error_messages[:10]:
                detail += f'<li>{err}</li>'
            if len(error_messages) > 10:
                detail += f'<li>...dan {len(error_messages) - 10} error lainnya</li>'
            detail += '</ul>'
            result_message += detail

        if is_ajax:
            return JsonResponse({
                'success': created_count > 0,
                'message': result_message,
                'created': created_count,
                'skipped': skipped_count,
                'errors': len(error_messages)
            })

        # Fallback untuk non-AJAX request
        if created_count > 0:
            messages.success(request, result_message)
            return redirect('hr:penggajian')
        else:
            messages.error(request, result_message)
            return redirect('hr:penggajian-import')

    def _read_excel(self, file):
        """Baca file Excel (.xlsx/.xls) dan return list of dict."""
        import openpyxl
        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
        rows_data = []
        headers = []
        for idx, row in enumerate(ws.iter_rows(values_only=True)):
            if idx == 0:
                headers = [str(cell).strip().lower().replace(' ', '_') if cell else '' for cell in row]
                continue
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            row_dict = {}
            for col_idx, cell in enumerate(row):
                if col_idx < len(headers) and headers[col_idx]:
                    row_dict[headers[col_idx]] = cell
            if row_dict:
                rows_data.append(row_dict)
        wb.close()
        return rows_data

    def _read_csv(self, file):
        """Baca file CSV dan return list of dict."""
        import csv
        import io
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        rows_data = []
        for row in reader:
            normalized = {}
            for key, value in row.items():
                if key:
                    normalized[key.strip().lower().replace(' ', '_')] = value
            rows_data.append(normalized)
        return rows_data


class PenggajianUpdateStatusView(UpdatePermissionMixin, UpdateView):
    """
    Update status pembayaran slip gaji (diproses → dibayar).

    URL: /hr/penggajian/<pk>/update-status/
    Permission: hr.edit
    Fields: status, tanggal_bayar
    Redirect: /hr/penggajian/
    """
    model = Penggajian
    fields = ['status', 'tanggal_bayar']            # Hanya 2 field yang bisa diubah
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('hr:penggajian')
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'


    def form_valid(self, form):
        """Update status penggajian."""
        with transaction.atomic():
            self.object = form.save(commit=False)
            if self.object.status == 'dibayar' and not self.object.tanggal_bayar:
                self.object.tanggal_bayar = timezone.now().date()
            if self.object.status == 'dibayar':
                if not self.object.cabang_id and self.object.karyawan_id:
                    self.object.cabang = self.object.karyawan.cabang
                if not self.object.metode_pembayaran_id:
                    self.object.metode_pembayaran = get_default_payroll_payment_method()
            self.object.save()

            if self.object.status == 'dibayar':
                create_penggajian_payment_journal(self.object, user=self.request.user)

        messages.success(self.request, 'Status penggajian berhasil diupdate')
        return redirect(self.get_success_url())


@login_required
def penggajian_update_status_ajax(request, pk):
    """
    AJAX endpoint untuk update status slip gaji.
    URL: /hr/penggajian/<pk>/update-status-ajax/
    Method: POST
    Body (form): status, tanggal_bayar (opsional)
    Response: JSON {success, message, status, status_label, status_class}
    """
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'hr'):
        return JsonResponse({'success': False, 'message': 'Tidak memiliki izin.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method tidak diizinkan.'}, status=405)

    slip = get_object_or_404(Penggajian, pk=pk)
    new_status = request.POST.get('status', '').strip()
    STATUS_VALID = ['draft', 'diproses', 'dibayar', 'batal']
    if new_status not in STATUS_VALID:
        return JsonResponse({'success': False, 'message': 'Status tidak valid.'}, status=400)

    try:
        with transaction.atomic():
            old_status = slip.status

            # Validasi MetodePembayaran mapping sebelum bayar (untuk jurnal otomatis)
            if new_status == 'dibayar' and old_status != 'dibayar':
                from apps.core.validators import validate_metode_pembayaran_mapping
                from apps.kas_bank.services import metode_is_credit
                if slip.metode_pembayaran and not metode_is_credit(slip.metode_pembayaran):
                    validate_metode_pembayaran_mapping(slip.metode_pembayaran)

            slip.status = new_status
            if new_status == 'dibayar' and not slip.tanggal_bayar:
                slip.tanggal_bayar = timezone.now().date()
            update_fields = ['status', 'tanggal_bayar', 'diupdate_pada']
            if new_status == 'dibayar':
                if not slip.cabang_id and slip.karyawan_id:
                    slip.cabang = slip.karyawan.cabang
                    update_fields.append('cabang')
                if not slip.metode_pembayaran_id:
                    slip.metode_pembayaran = get_default_payroll_payment_method()
                    if slip.metode_pembayaran_id:
                        update_fields.append('metode_pembayaran')
            slip.save(update_fields=update_fields)
            jurnal = None
            if new_status == 'dibayar' and old_status != 'dibayar':
                jurnal = create_penggajian_payment_journal(slip, user=request.user)

        STATUS_LABELS = {
            'draft': ('Draft', 'secondary'),
            'diproses': ('Diproses', 'warning'),
            'dibayar': ('Dibayar', 'success'),
            'batal': ('Batal', 'danger'),
        }
        label, css_class = STATUS_LABELS.get(new_status, (new_status, 'secondary'))
        return JsonResponse({
            'success': True,
            'message': f'Status berhasil diubah ke {label}.',
            'status': new_status,
            'status_label': label,
            'status_class': css_class,
            'tanggal_bayar': slip.tanggal_bayar.strftime('%d %B %Y') if slip.tanggal_bayar else None,
            'has_journal': jurnal is not None,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Gagal mengubah status: {str(e)}'}, status=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║  FACE RECOGNITION - registrasi, deteksi, clock in/out wajah  ║
# ║  Opsional: tergantung FACE_RECOGNITION_ENABLED flag          ║
# ╚══════════════════════════════════════════════════════════════╝
# Import face utilities
try:
    # Import dari modul internal proyek
    from apps.hr import face_utils
    FACE_RECOGNITION_ENABLED = True
# Tangkap error ImportError - lanjutkan tanpa crash
except ImportError:
    FACE_RECOGNITION_ENABLED = False



class RegistrasiWajahView(CreatePermissionMixin, TemplateView):
    """
    Halaman registrasi wajah karyawan untuk face recognition.

    URL: /hr/registrasi-wajah/
    Permission: hr.create
    Template: hr/registrasi_wajah.html

    Menampilkan daftar karyawan aktif dan foto wajah yang sudah terdaftar.
    User dapat mengambil foto baru dari kamera untuk didaftarkan.
    """
    template_name = 'hr/registrasi_wajah.html'
    # Modul permission yang dicek: 'hr'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """
        Menyediakan data karyawan dan foto wajah terdaftar.
        foto_wajah_per_karyawan: dict {karyawan_pk: queryset_foto}
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database - ambil data karyawan_list yang sesuai filter
        karyawan_list = Karyawan.objects.filter(aktif=True, status='aktif')  # Hanya karyawan aktif
        # Data konteks: karyawan_list - untuk ditampilkan di template
        context['karyawan_list'] = karyawan_list
        # Data konteks: face_recognition_enabled - untuk ditampilkan di template
        context['face_recognition_enabled'] = FACE_RECOGNITION_ENABLED  # Flag: apakah lib tersedia

        # Muat foto wajah terdaftar, grouped by karyawan
        # Hanya foto yang masih aktif, diurutkan terbaru dulu
        foto_wajah_per_karyawan = {}
        for karyawan in karyawan_list:
            fotos = karyawan.foto_wajah_set.filter(aktif=True).order_by('-dibuat_pada')
            if fotos.exists():
                foto_wajah_per_karyawan[karyawan.pk] = fotos
        # Data konteks: foto_wajah_per_karyawan - untuk ditampilkan di template
        context['foto_wajah_per_karyawan'] = foto_wajah_per_karyawan
        return context


# Wajib login - redirect ke login page jika belum login
@login_required
def save_face_encoding(request):
    """
    API endpoint untuk menyimpan encoding wajah karyawan.

    URL: /hr/face/save-encoding/  (POST only)
    Input: karyawan_id (POST), foto_base64 atau foto (FILES)
    Response: JSON {success, message, foto_id, total_foto}

    Alur kerja:
    1. Cek apakah face recognition tersedia (library terinstall)
    2. Ambil foto dari base64 atau file upload
    3. Encode wajah menggunakan face_utils
    4. Simpan FotoWajah dengan encoding ke database
    5. Return jumlah total foto terdaftar
    """
    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'create', 'hr'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mendaftarkan wajah karyawan.'}, status=403)

        # Cek apakah library face_recognition tersedia
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        karyawan_id = request.POST.get('karyawan_id')   # ID karyawan target
        foto_base64 = request.POST.get('foto_base64')   # Foto dari kamera (base64)
        foto_file = request.FILES.get('foto')            # Foto dari file upload

        # Validasi: karyawan harus dipilih
        if not karyawan_id:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak dipilih'
            })

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Query database - ambil satu data karyawan
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)

            # Encode wajah dari foto yang diberikan
            if foto_base64:
                # Dari kamera browser (base64 string)
                encoding = face_utils.encode_face_from_base64(foto_base64)
                # Konversi base64 ke file Django untuk disimpan di storage
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]  # Hapus header "data:image/...;base64,"
                foto_data = base64.b64decode(foto_base64)
                # Import dari framework Django
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'wajah_{karyawan_id}_{timezone.now().timestamp()}.jpg')
            elif foto_file:
                # Dari file upload langsung
                encoding = face_utils.encode_face_from_file(foto_file)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Foto tidak ditemukan'
                })

            # Validasi: wajah harus terdeteksi dalam foto
            if not encoding:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak dapat mendeteksi wajah dalam foto. Pastikan wajah terlihat jelas dan menghadap kamera.'
                })

            # Simpan foto wajah + encoding ke database
            foto_wajah = FotoWajah.objects.create(
                karyawan=karyawan,
                foto=foto_file,       # File foto yang disimpan di storage
                encoding=encoding,    # Vector encoding wajah (untuk matching)
                aktif=True
            )

            # Hitung total foto wajah yang terdaftar aktif
            total_foto = karyawan.foto_wajah_set.filter(aktif=True).count()

            return JsonResponse({
                'success': True,
                'message': f'Wajah {karyawan.nama} berhasil didaftarkan! ({total_foto} foto terdaftar)',
                'foto_id': foto_wajah.pk,
                'total_foto': total_foto
            })

        # Tangkap error Karyawan.DoesNotExist - lanjutkan tanpa crash
        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)

# Wajib login - redirect ke login page jika belum login
@login_required
def delete_face(request, pk):
    """
    API untuk menghapus foto wajah terdaftar (soft delete).

    URL: /hr/face/<pk>/delete/  (DELETE atau POST)
    Response: JSON {success, message}

    Catatan: Tidak menghapus record dari database,
    hanya mengubah field aktif menjadi False (soft delete).
    """
    if request.method == 'DELETE' or request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'delete', 'hr'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus foto wajah karyawan.'}, status=403)

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Query database - ambil satu data foto
            foto = FotoWajah.objects.get(pk=pk)
            karyawan_nama = foto.karyawan.nama
            foto.aktif = False    # Soft delete: nonaktifkan, jangan hapus
            foto.save()
            return JsonResponse({
                'success': True,
                'message': f'Foto wajah {karyawan_nama} berhasil dihapus'
            })
        # Tangkap error FotoWajah.DoesNotExist - lanjutkan tanpa crash
        except FotoWajah.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Foto tidak ditemukan'
            }, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


# Wajib login - redirect ke login page jika belum login
@login_required
def detect_face_api(request):
    """
    API endpoint untuk mendeteksi wajah dan mencocokkan dengan karyawan terdaftar.

    URL: /hr/face/detect/  (POST only)
    Input: foto_base64 atau foto (FILES)
    Response: JSON {success, has_face, karyawan_id, confidence, ...}

    Alur kerja:
    1. Konversi foto ke array numpy
    2. Validasi apakah ada wajah dalam foto
    3. Bandingkan encoding wajah dengan semua karyawan terdaftar
    4. Return karyawan yang paling cocok (jika confidence > threshold=0.55)
    """
    if request.method == 'POST':
        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')  # Dari kamera browser
        foto_file = request.FILES.get('foto')           # Dari file upload

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Konversi foto ke numpy array untuk diproses
            if foto_base64:
                img = face_utils.base64_to_array(foto_base64)
            elif foto_file:
                img = face_utils.image_to_array(foto_file)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Foto tidak ditemukan'
                })

            # Validasi: apakah ada wajah terdeteksi dalam foto
            has_face, face_rect = face_utils.validate_face_exists(img)
            if not has_face:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak dapat mendeteksi wajah dalam foto',
                    'has_face': False
                })

            # Cari karyawan yang cocok dari database
            # prefetch_related() untuk load foto_wajah dalam 1 query
            karyawan_list = Karyawan.objects.filter(
                aktif=True,
                status='aktif'
            ).prefetch_related('foto_wajah_set')

            # Bandingkan wajah dengan semua encoding terdaftar
            # threshold=0.55 = batas minimal kemiripan untuk dianggap cocok
            matched_karyawan, confidence = face_utils.find_matching_karyawan(
                img,
                karyawan_list,
                threshold=0.55
            )

            if matched_karyawan:
                # Wajah cocok - return data karyawan yang ditemukan
                return JsonResponse({
                    'success': True,
                    'message': f'Wajah dikenali: {matched_karyawan.nama}',
                    'has_face': True,
                    'karyawan_id': matched_karyawan.pk,
                    'karyawan_nama': matched_karyawan.nama,
                    'karyawan_nik': matched_karyawan.nik,
                    'confidence': round(confidence * 100, 1),  # Persentase kemiripan
                    'jabatan': matched_karyawan.jabatan.nama if matched_karyawan.jabatan else '-',
                    'departemen': matched_karyawan.departemen.nama if matched_karyawan.departemen else '-'
                })
            else:
                # Wajah tidak dikenali - tidak ada yang cocok
                return JsonResponse({
                    'success': False,
                    'message': 'Wajah tidak dikenali. Pastikan karyawan sudah terdaftar.',
                    'has_face': True,
                    'karyawan_id': None
                })

        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


# Wajib login - redirect ke login page jika belum login
@login_required
def absensi_face_clock_in(request):
    """
    API untuk clock in menggunakan face recognition.

    URL: /hr/absensi/face-clock-in/  (POST only)
    Input: foto_base64 (POST), karyawan_id (opsional), latitude, longitude (opsional)
    Response: JSON {success, karyawan_nama, jam_masuk, status, confidence}

    Alur kerja:
    1. Cek apakah face recognition tersedia
    2. Validasi lokasi (jika fitur wajib_lokasi aktif di pengaturan)
    3. Jika karyawan_id tidak diberikan → deteksi wajah otomatis
    4. Tentukan status hadir/terlambat berdasarkan pengaturan jam masuk
    5. Simpan record absensi dengan foto selfie dan confidence score
    """
    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'create', 'hr', 'absensi'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk membuat data absensi.'}, status=403)

        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')                  # Foto dari kamera
        karyawan_id = request.POST.get('karyawan_id')                  # Opsional: dari auto-detect

        # Ambil lokasi GPS user (untuk validasi radius kantor)
        user_latitude = request.POST.get('latitude')
        user_longitude = request.POST.get('longitude')

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Ambil pengaturan absensi default dulu (untuk validasi lokasi awal)
            # Setelah karyawan teridentifikasi, akan di-fetch ulang sesuai cabang karyawan
            pengaturan = PengaturanAbsensi.get_active()

            # ===== VALIDASI LOKASI =====
            # Jika pengaturan wajib_lokasi diaktifkan, cek GPS user
            if pengaturan and pengaturan.wajib_lokasi:
                if not user_latitude or not user_longitude:
                    return JsonResponse({
                        'success': False,
                        'message': 'Lokasi diperlukan. Silakan aktifkan GPS dan berikan izin lokasi.'
                    })

                # Cek jarak user ke lokasi kantor
                if pengaturan.latitude and pengaturan.longitude and pengaturan.radius_lokasi:
                    is_valid, distance, msg = face_utils.validate_location(
                        user_latitude, user_longitude,
                        pengaturan.latitude, pengaturan.longitude,
                        pengaturan.radius_lokasi
                    )
                    # Simpan jarak untuk disimpan ke record absensi
                    clock_in_distance = distance

                    # Jika di luar radius → tolak absensi
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': f'Absensi gagal! {msg}. Anda harus berada dalam radius {pengaturan.radius_lokasi}m dari kantor.'
                        })

            # ===== DETEKSI WAJAH =====
            # Jika karyawan_id tidak diberikan, deteksi wajah otomatis
            if not karyawan_id:
                if not foto_base64:
                    return JsonResponse({
                        'success': False,
                        'message': 'Foto diperlukan untuk absensi'
                    })

                img = face_utils.base64_to_array(foto_base64)

                # Cari karyawan yang cocok dari semua yang terdaftar
                karyawan_list = Karyawan.objects.filter(
                    aktif=True,
                    status='aktif'
                ).prefetch_related('foto_wajah_set')

                karyawan, confidence = face_utils.find_matching_karyawan(
                    img,
                    karyawan_list,
                    threshold=0.55  # Batas minimal kemiripan
                )

                if not karyawan:
                    return JsonResponse({
                        'success': False,
                        'message': 'Wajah tidak dikenali. Pastikan wajah sudah terdaftar.'
                    })
            else:
                # karyawan_id diberikan langsung (dari auto-detect sebelumnya)
                karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
                confidence = 1.0  # Tidak perlu matching lagi

            today = timezone.now().date()
            now = timezone.now().time()

            # ===== RE-FETCH PENGATURAN BERDASARKAN CABANG KARYAWAN =====
            # Setelah karyawan teridentifikasi, ambil pengaturan sesuai cabang
            pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)

            # ===== TENTUKAN STATUS ABSENSI =====
            # Gunakan pengaturan jam masuk + toleransi untuk menentukan hadir/terlambat
            jam_masuk_pengaturan = pengaturan.jam_masuk if pengaturan else None
            toleransi = pengaturan.toleransi_terlambat if pengaturan else 0

            if jam_masuk_pengaturan:
                # Hitung batas toleransi: jam_masuk + toleransi menit
                batas_terlambat = datetime.combine(today, jam_masuk_pengaturan) + timedelta(minutes=toleransi)
                waktu_sekarang = datetime.combine(today, now)
                status_absensi = 'hadir' if waktu_sekarang <= batas_terlambat else 'terlambat'
            else:
                # Fallback: jam 9 pagi sebagai batas default
                status_absensi = 'hadir' if now.hour < 9 else 'terlambat'

            # ===== SIMPAN FOTO =====
            # Konversi base64 ke file Django untuk disimpan
            foto_file = None
            if foto_base64:
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]  # Hapus header data:image/...
                foto_data = base64.b64decode(foto_base64)
                # Import dari framework Django
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'clockin_{karyawan.pk}_{today}.jpg')

            # ===== HITUNG JARAK (jika lokasi tersedia tapi tidak wajib) =====
            lokasi_masuk_str = None
            if 'clock_in_distance' not in dir():
                clock_in_distance = None
                if user_latitude and user_longitude and pengaturan and pengaturan.latitude and pengaturan.longitude:
                    try:
                        _, clock_in_distance, _ = face_utils.validate_location(
                            user_latitude, user_longitude,
                            pengaturan.latitude, pengaturan.longitude,
                            pengaturan.radius_lokasi or 100
                        )
                    except Exception as e:
                        logger.warning("Error tidak terduga: %s", e)

            # Simpan string koordinat GPS masuk
            if user_latitude and user_longitude:
                try:
                    lokasi_masuk_str = f"{float(user_latitude)},{float(user_longitude)}"
                except (ValueError, TypeError):
                    pass

            # ===== BUAT RECORD ABSENSI =====
            # get_or_create: cek duplikasi (1 karyawan = 1 absensi/hari)
            absensi, created = Absensi.objects.get_or_create(
                karyawan=karyawan,
                tanggal=today,
                defaults={
                    'jam_masuk': now,
                    'status': status_absensi,
                    'foto_masuk': foto_file,
                    'persentase_kemiripan': round(confidence * 100, 1) if confidence else None,  # Simpan confidence
                    'lokasi_masuk': lokasi_masuk_str,  # Simpan koordinat GPS masuk
                    'jarak_masuk': clock_in_distance,  # Simpan jarak dari kantor
                    'cabang': karyawan.cabang,
                    'pengaturan_snapshot': pengaturan,
                }
            )

            # Jika sudah clock in hari ini → tolak
            if not created:
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} sudah melakukan clock in hari ini pada {absensi.jam_masuk.strftime("%H:%M")}'
                })

            # Berhasil clock in
            return JsonResponse({
                'success': True,
                'message': f'Clock In berhasil untuk {karyawan.nama}',
                'karyawan_nama': karyawan.nama,
                'jam_masuk': now.strftime("%H:%M"),
                'status': absensi.status,
                'confidence': round(confidence * 100, 1)
            })

        # Tangkap error Karyawan.DoesNotExist - lanjutkan tanpa crash
        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


# Wajib login - redirect ke login page jika belum login
@login_required
def absensi_face_clock_out(request):
    """
    API untuk clock out menggunakan face recognition.

    URL: /hr/absensi/face-clock-out/  (POST only)
    Input: foto_base64 (POST), karyawan_id (opsional), latitude, longitude (opsional)
    Response: JSON {success, karyawan_nama, jam_keluar, confidence}

    Alur kerja mirip face_clock_in:
    1. Validasi lokasi (jika wajib)
    2. Deteksi wajah (jika karyawan_id tidak diberikan)
    3. Cari record absensi hari ini (harus sudah clock in)
    4. Update jam_keluar dan simpan foto clock out
    """
    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'hr', 'absensi'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengubah data absensi.'}, status=403)

        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')                  # Foto dari kamera
        karyawan_id = request.POST.get('karyawan_id')                  # Opsional

        # Ambil lokasi GPS user
        user_latitude = request.POST.get('latitude')
        user_longitude = request.POST.get('longitude')

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Ambil pengaturan absensi default dulu (untuk validasi lokasi awal)
            pengaturan = PengaturanAbsensi.get_active()

            # ===== VALIDASI LOKASI =====
            if pengaturan and pengaturan.wajib_lokasi:
                if not user_latitude or not user_longitude:
                    return JsonResponse({
                        'success': False,
                        'message': 'Lokasi diperlukan. Silakan aktifkan GPS dan berikan izin lokasi.'
                    })

                if pengaturan.latitude and pengaturan.longitude and pengaturan.radius_lokasi:
                    is_valid, distance, msg = face_utils.validate_location(
                        user_latitude, user_longitude,
                        pengaturan.latitude, pengaturan.longitude,
                        pengaturan.radius_lokasi
                    )
                    # Simpan jarak untuk disimpan ke record absensi
                    clock_out_distance = distance

                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': f'Absensi gagal! {msg}. Anda harus berada dalam radius {pengaturan.radius_lokasi}m dari kantor.'
                        })

            # ===== DETEKSI WAJAH =====
            if not karyawan_id:
                if not foto_base64:
                    return JsonResponse({
                        'success': False,
                        'message': 'Foto diperlukan untuk absensi'
                    })

                img = face_utils.base64_to_array(foto_base64)

                # Cari karyawan yang cocok
                karyawan_list = Karyawan.objects.filter(
                    aktif=True,
                    status='aktif'
                ).prefetch_related('foto_wajah_set')

                karyawan, confidence = face_utils.find_matching_karyawan(
                    img,
                    karyawan_list,
                    threshold=0.55
                )

                if not karyawan:
                    return JsonResponse({
                        'success': False,
                        'message': 'Wajah tidak dikenali. Pastikan wajah sudah terdaftar.'
                    })
            else:
                # Query database - ambil satu data karyawan
                karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
                confidence = 1.0

            today = timezone.now().date()
            now = timezone.now().time()

            # ===== RE-FETCH PENGATURAN BERDASARKAN CABANG KARYAWAN =====
            pengaturan = PengaturanAbsensi.get_active(cabang=karyawan.cabang)

            # ===== SIMPAN FOTO CLOCK OUT =====
            foto_file = None
            if foto_base64:
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]
                foto_data = base64.b64decode(foto_base64)
                # Import dari framework Django
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'clockout_{karyawan.pk}_{today}.jpg')

            # ===== UPDATE ABSENSI =====
            # Cari record absensi hari ini - harus sudah clock in
            try:
                # Query database - ambil satu data absensi
                absensi = Absensi.objects.get(karyawan=karyawan, tanggal=today)

                # Cek apakah sudah clock out
                if absensi.jam_keluar:
                    return JsonResponse({
                        'success': False,
                        'message': f'{karyawan.nama} sudah melakukan clock out hari ini pada {absensi.jam_keluar.strftime("%H:%M")}'
                    })

                # Update jam keluar dan foto
                absensi.jam_keluar = now
                absensi.foto_keluar = foto_file
                # Update persentase kemiripan jika belum ada
                if not absensi.persentase_kemiripan and confidence:
                    absensi.persentase_kemiripan = round(confidence * 100, 1)

                # Simpan jarak clock out
                if 'clock_out_distance' not in dir():
                    clock_out_distance = None
                    if user_latitude and user_longitude and pengaturan and pengaturan.latitude and pengaturan.longitude:
                        try:
                            _, clock_out_distance, _ = face_utils.validate_location(
                                user_latitude, user_longitude,
                                pengaturan.latitude, pengaturan.longitude,
                                pengaturan.radius_lokasi or 100
                            )
                        except Exception as e:
                            logger.warning("Error tidak terduga: %s", e)
                absensi.jarak_keluar = clock_out_distance

                # Simpan string koordinat GPS keluar
                if user_latitude and user_longitude:
                    try:
                        absensi.lokasi_keluar = f"{float(user_latitude)},{float(user_longitude)}"
                    except (ValueError, TypeError):
                        pass

                absensi.save()

                return JsonResponse({
                    'success': True,
                    'message': f'Clock Out berhasil untuk {karyawan.nama}',
                    'karyawan_nama': karyawan.nama,
                    'jam_keluar': now.strftime("%H:%M"),
                    'confidence': round(confidence * 100, 1)
                })

            # Tangkap error Absensi.DoesNotExist - lanjutkan tanpa crash
            except Absensi.DoesNotExist:
                # Belum clock in → tidak bisa clock out
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} belum melakukan clock in hari ini'
                })

        # Tangkap error Karyawan.DoesNotExist - lanjutkan tanpa crash
        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


# ╔══════════════════════════════════════════════════════════════╗
# ║  PENGATURAN ABSENSI - jam masuk/pulang, lokasi, toleransi     ║
# ║  Mendukung multiple pengaturan, hanya 1 yang aktif            ║
# ╚══════════════════════════════════════════════════════════════╝
@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiView(ReadPermissionMixin, TemplateView):
    """
    Halaman pengaturan absensi - kelola jam masuk/pulang, lokasi, toleransi.

    URL: /hr/pengaturan-absensi/
    Template: hr/pengaturan_absensi.html

    Mendukung multiple pengaturan (preset), tapi hanya 1 yang aktif.
    Menampilkan form edit pengaturan aktif + daftar semua pengaturan.
    """
    template_name = 'hr/pengaturan_absensi.html'
    permission_module = 'hr'
    permission_sub_module = 'pengaturan_absensi'

    def get_context_data(self, **kwargs):
        """
        Menyediakan form pengaturan dan daftar semua preset.
        Jika ada pengaturan aktif, form diisi dengan data tersebut.
        Jika tidak, tampilkan form kosong.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Ambil pengaturan yang aktif (atau yang pertama sebagai fallback)
        pengaturan = PengaturanAbsensi.get_active()
        if not pengaturan:
            pengaturan = PengaturanAbsensi.objects.first()

        # Daftar semua pengaturan (untuk tab/dropdown)
        context['pengaturan_list'] = PengaturanAbsensi.objects.all()
        # Data konteks: pengaturan_aktif - untuk ditampilkan di template
        context['pengaturan_aktif'] = PengaturanAbsensi.get_active()

        # Form - pre-fill jika ada pengaturan yang dipilih
        if pengaturan:
            # Data konteks: form - untuk ditampilkan di template
            context['form'] = PengaturanAbsensiForm(instance=pengaturan)
            # Data konteks: pengaturan - untuk ditampilkan di template
            context['pengaturan'] = pengaturan
        else:
            # Data konteks: form - untuk ditampilkan di template
            context['form'] = PengaturanAbsensiForm()
            # Data konteks: pengaturan - untuk ditampilkan di template
            context['pengaturan'] = None

        return context


    def post(self, request, *args, **kwargs):
        """
        Simpan perubahan pengaturan absensi.
        Jika pengaturan_id diberikan → update existing,
        jika tidak → buat baru.
        """
        pengaturan_id = request.POST.get('pengaturan_id')  # ID pengaturan yang diedit

        if pengaturan_id:
            # Update pengaturan yang sudah ada
            pengaturan = get_object_or_404(PengaturanAbsensi, pk=pengaturan_id)
            form = PengaturanAbsensiForm(request.POST, instance=pengaturan)
        else:
            # Buat pengaturan baru
            form = PengaturanAbsensiForm(request.POST)

        if form.is_valid():
            pengaturan = form.save()
            # Tampilkan pesan sukses ke user
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil disimpan!')
            # Redirect ke halaman tujuan
            return redirect('hr:pengaturan-absensi')
        else:
            # Form tidak valid - tampilkan ulang dengan error
            context = self.get_context_data()
            # Data konteks: form - untuk ditampilkan di template
            context['form'] = form
            # Tampilkan pesan error ke user
            messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
            return self.render_to_response(context)


@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiCreateView(CreatePermissionMixin, TemplateView):
    """
    Form untuk membuat pengaturan absensi baru (preset baru).

    URL: /hr/pengaturan-absensi/add/
    Template: hr/pengaturan_absensi_form.html
    """
    template_name = 'hr/pengaturan_absensi_form.html'
    permission_module = 'hr'
    permission_sub_module = 'pengaturan_absensi'

    def get_context_data(self, **kwargs):
        """Menyediakan form kosong dan flag is_new=True."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = PengaturanAbsensiForm()  # Form kosong
        # Data konteks: is_new - untuk ditampilkan di template
        context['is_new'] = True                   # Flag: buat baru (bukan edit)
        return context


    def post(self, request, *args, **kwargs):

        form = PengaturanAbsensiForm(request.POST)
        if form.is_valid():
            pengaturan = form.save()
            # Tampilkan pesan sukses ke user
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil dibuat!')
            # Redirect ke halaman tujuan
            return redirect('hr:pengaturan-absensi')

        # Form tidak valid - tampilkan ulang
        context = self.get_context_data()
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = form
        # Tampilkan pesan error ke user
        messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
        return self.render_to_response(context)


@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiUpdateView(UpdatePermissionMixin, TemplateView):
    """
    Form untuk mengedit pengaturan absensi yang sudah ada.

    URL: /hr/pengaturan-absensi/<pk>/edit/
    Template: hr/pengaturan_absensi_form.html
    """
    template_name = 'hr/pengaturan_absensi_form.html'
    permission_module = 'hr'
    permission_sub_module = 'pengaturan_absensi'

    def get_context_data(self, **kwargs):
        """Menyediakan form yang diisi dengan data pengaturan yang diedit."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        pengaturan = get_object_or_404(PengaturanAbsensi, pk=self.kwargs['pk'])  # Ambil berdasarkan pk
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = PengaturanAbsensiForm(instance=pengaturan)  # Pre-fill form
        # Data konteks: pengaturan - untuk ditampilkan di template
        context['pengaturan'] = pengaturan
        # Data konteks: is_new - untuk ditampilkan di template
        context['is_new'] = False                   # Flag: edit (bukan buat baru)
        return context


    def post(self, request, *args, **kwargs):

        pengaturan = get_object_or_404(PengaturanAbsensi, pk=kwargs['pk'])
        form = PengaturanAbsensiForm(request.POST, instance=pengaturan)
        if form.is_valid():
            pengaturan = form.save()
            # Tampilkan pesan sukses ke user
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil diupdate!')
            # Redirect ke halaman tujuan
            return redirect('hr:pengaturan-absensi')

        # Form tidak valid - tampilkan ulang
        context = self.get_context_data()
        # Data konteks: form - untuk ditampilkan di template
        context['form'] = form
        # Tampilkan pesan error ke user
        messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
        return self.render_to_response(context)


# Wajib login - redirect ke login page jika belum login
@login_required
def pengaturan_absensi_delete(request, pk):
    """
    Hapus pengaturan absensi berdasarkan pk.

    URL: /hr/pengaturan-absensi/<pk>/delete/  (POST only)
    Redirect: /hr/pengaturan-absensi/
    """
    pengaturan = get_object_or_404(PengaturanAbsensi, pk=pk)

    if request.method == 'POST':
        if not request.user.is_superuser and not has_permission(request.user, 'delete', 'hr', 'pengaturan_absensi'):
            messages.error(request, 'Anda tidak memiliki izin untuk menghapus pengaturan absensi.')
            return redirect('hr:pengaturan-absensi')

        nama = pengaturan.nama            # Simpan nama sebelum dihapus
        pengaturan.delete()               # Hapus dari database
        # Tampilkan pesan sukses ke user
        messages.success(request, f'Pengaturan "{nama}" berhasil dihapus!')
        # Redirect ke halaman tujuan
        return redirect('hr:pengaturan-absensi')

    # GET request → redirect tanpa aksi
    return redirect('hr:pengaturan-absensi')


# Wajib login - redirect ke login page jika belum login
@login_required
def pengaturan_absensi_activate(request, pk):
    """
    Aktifkan pengaturan absensi tertentu.

    URL: /hr/pengaturan-absensi/<pk>/activate/

    Catatan: Model PengaturanAbsensi.save() otomatis nonaktifkan
    semua pengaturan lain saat satu diaktifkan (single active).
    """
    pengaturan = get_object_or_404(PengaturanAbsensi, pk=pk)

    if not request.user.is_superuser and not has_permission(request.user, 'update', 'hr', 'pengaturan_absensi'):
        messages.error(request, 'Anda tidak memiliki izin untuk mengaktifkan pengaturan absensi.')
        return redirect('hr:pengaturan-absensi')

    pengaturan.aktif = True
    pengaturan.save()  # save() akan otomatis nonaktifkan yang lain (single active)

    # Tampilkan pesan sukses ke user
    messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil diaktifkan!')
    # Redirect ke halaman tujuan
    return redirect('hr:pengaturan-absensi')


# ╔══════════════════════════════════════════════════════════════╗
# ║              CANCEL PENGGAJIAN                                 ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@require_http_methods(["POST"])
def cancel_penggajian(request, pk):
    """Cancel penggajian yang sudah dibayar. URL: /hr/penggajian/<pk>/cancel/ (POST AJAX)"""
    from django.http import JsonResponse
    from apps.hr.models import Penggajian
    from apps.hr.services import transition_penggajian_status
    from apps.core.permissions import has_permission, is_superuser_role

    if not is_superuser_role(request.user) and not has_permission(request.user, 'write', 'hr'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    try:
        penggajian = Penggajian.objects.get(pk=pk)
    except Penggajian.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Data penggajian tidak ditemukan.'}, status=404)

    if penggajian.status not in ['draft', 'diproses', 'dibayar']:
        return JsonResponse({'success': False, 'message': f'Penggajian dengan status "{penggajian.get_status_display()}" tidak bisa dibatalkan.'}, status=400)

    try:
        transition_penggajian_status(penggajian, 'batal', user=request.user)
        return JsonResponse({'success': True, 'message': f'Penggajian {penggajian.karyawan.nama} berhasil dibatalkan.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Gagal membatalkan: {str(e)}'}, status=400)
