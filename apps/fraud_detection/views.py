"""
==========================================================================
 FRAUD DETECTION VIEWS — View untuk Modul Deteksi Kecurangan
==========================================================================
 File ini berisi semua view (halaman & endpoint AJAX) untuk modul
 Fraud Detection. Setiap view terhubung dengan URL di urls.py.

 Daftar View:
 ┌──────────────────────────────────────────────────────────────────┐
 │ View                         │ Tipe       │ Fungsi              │
 ├──────────────────────────────┼────────────┼─────────────────────┤
 │ FraudDashboardView           │ TemplateV  │ Dashboard statistik │
 │ FraudAlertListView           │ ListView   │ Daftar anomali      │
 │ FraudAlertDetailView         │ TemplateV  │ Detail + data linked│
 │ fraud_alert_update_status    │ FBV AJAX   │ Ubah status anomali │
 │ CashReconciliationListView   │ ListView   │ Daftar rekon kas    │
 │ CashReconciliationCreateView │ TemplateV  │ Form blind closing  │
 │ FraudSettingsView            │ TemplateV  │ Pengaturan fraud    │
 │ export_fraud_alerts_excel    │ FBV        │ Export Excel        │
 │ fraud_alert_delete           │ FBV AJAX   │ Hapus anomali       │
 │ cash_recon_delete            │ FBV AJAX   │ Hapus rekon kas     │
 │ cash_recon_edit              │ FBV AJAX   │ Edit uang fisik     │
 │ cash_recon_review            │ FBV AJAX   │ Review + tindak     │
 └──────────────────────────────────────────────────────────────────┘

 Terhubung dengan:
 → urls.py             — Routing URL ke setiap view
 → models.py           — FraudRule, FraudAlert, CashReconciliation
 → signals.py          — Deteksi otomatis (buat FraudAlert)
 → templates/fraud_detection/ — Template HTML untuk setiap halaman
 → activity_log        — Log aktivitas user untuk audit trail
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


# ═══════════════════════════════════════════════════════════════
#  IMPORTS — Library dan modul yang dibutuhkan
# ═══════════════════════════════════════════════════════════════

# Django CBV (Class-Based Views) — base class untuk halaman
from django.views.generic import TemplateView, ListView, CreateView
# Model User bawaan Django — untuk relasi FK ke user
from django.contrib.auth.models import User
# JsonResponse — untuk mengembalikan JSON pada endpoint AJAX
from django.http import JsonResponse
# Decorator: require_POST — hanya terima HTTP POST (tolak GET)
from django.views.decorators.http import require_POST
# Decorator: login_required — wajib login sebelum akses
from django.contrib.auth.decorators import login_required
# Decorator converter: function decorator → method decorator (untuk CBV)
from django.utils.decorators import method_decorator
# Timezone-aware datetime
from django.utils import timezone
# ORM aggregation functions — untuk query statistik
from django.db.models import Count, Sum, Q, F, Avg
# TruncMonth — potong datetime ke bulan (untuk grafik tren bulanan)
from django.db.models.functions import TruncMonth
# Decimal — aritmatika presisi untuk nominal uang
from decimal import Decimal, InvalidOperation
# JSON — untuk serialize data ke format JSON (grafik, snapshot)
import json

# TemplateLayout — helper internal project untuk inisialisasi layout Sneat
from web_project import TemplateLayout
# SubModulePermissionMixin — mixin RBAC yang cek izin akses per sub-modul
from apps.core.mixins import SubModulePermissionMixin
from apps.core.permissions import has_permission
# Model Fraud Detection — 3 model utama
from apps.fraud_detection.models import FraudRule, FraudAlert, CashReconciliation
# Model Activity Log — untuk menampilkan riwayat aktivitas user
from apps.activity_log.models import UserActivity
from django.db import transaction





# ╔══════════════════════════════════════════════════════════════╗
# ║               FRAUD DASHBOARD                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class FraudDashboardView(SubModulePermissionMixin, TemplateView):
    """
    ══════════════════════════════════════════════════════
    Dashboard Utama Fraud Detection.
    ══════════════════════════════════════════════════════
    Menampilkan ringkasan lengkap keamanan bisnis:
    - Summary cards: total anomali, pending, high/critical, potensi kerugian
    - Total aset asli, pemasukan, pengeluaran, selisih keuangan
    - Top 5 karyawan berisiko (paling banyak anomali)
    - Grafik tren anomali bulanan (ApexCharts area chart)
    - Grafik distribusi jenis anomali (ApexCharts donut chart)
    - Tabel 5 rekonsiliasi kas terbaru

    URL: /fraud/
    Template: fraud_detection/dashboard.html
    Permission: fraud_detection.dashboard_fraud.read
    """
    template_name = 'fraud_detection/dashboard.html'
    permission_module = 'fraud_detection'
    permission_sub_module = 'dashboard_fraud'
    permission_action = 'read'

    def get_context_data(self, **kwargs):
        """Menyiapkan SEMUA data yang ditampilkan di dashboard fraud."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # === SUMMARY CARDS — Kartu ringkasan anomali ===
        alerts = FraudAlert.objects.all()
        context['total_alerts'] = alerts.count()  # Total semua anomali
        context['pending_alerts'] = alerts.filter(status='pending').count()  # Belum di-review
        context['high_critical_alerts'] = alerts.filter(
            severity__in=['high', 'critical'], status='pending'
        ).count()  # Anomali tingkat tinggi yang belum ditangani
        context['total_potensi_kerugian'] = alerts.filter(
            status__in=['pending', 'investigated']
        ).aggregate(total=Sum('nominal'))['total'] or 0  # Total potensi kerugian dari anomali aktif

        # === TOTAL ASET ASLI (Termasuk data fraud yang belum dikonfirmasi) ===
        # Menghitung total aset berdasarkan: stok saat ini + stok terjual + stok adjustment
        # Ini adalah aset "seharusnya" jika tidak ada kecurangan
        from apps.produk.models import Produk
        from apps.inventory.models import Stok, AdjustmentStok
        from apps.penjualan.models import SalesOrderItem
        from apps.pos.models import POSTransactionItem

        total_aset = Decimal('0')
        for produk in Produk.objects.all():
            # Stok fisik saat ini di semua gudang
            stok_sekarang = Stok.objects.filter(produk=produk).aggregate(
                total=Sum('jumlah'))['total'] or 0
            # Stok yang sudah terjual via Sales Order (SO)
            total_terjual_so = SalesOrderItem.objects.filter(
                produk=produk,
                sales_order__status__in=['confirmed', 'delivered', 'completed']
            ).aggregate(total=Sum('jumlah'))['total'] or 0
            # Stok yang sudah terjual via Point of Sale (POS)
            total_terjual_pos = POSTransactionItem.objects.filter(
                produk=produk,
                transaction__status='paid'
            ).aggregate(total=Sum('jumlah_konversi'))['total'] or 0
            # Stok yang keluar via adjustment manual
            total_adj_out = AdjustmentStok.objects.filter(
                produk=produk, tipe='out'
            ).aggregate(total=Sum('jumlah'))['total'] or 0
            # Total kuantitas seharusnya = semua stok + semua yang keluar
            qty_total = stok_sekarang + total_terjual_so + total_terjual_pos + total_adj_out
            # Nilai aset = kuantitas × harga beli per unit
            total_aset += Decimal(str(qty_total)) * produk.harga_beli
        context['total_aset_asli'] = total_aset

        # === DATA KEUANGAN — Total pemasukan, pengeluaran, dan selisih ===
        # Digunakan untuk cards keuangan di dashboard yang menunjukkan gambaran finansial
        from apps.pos.models import POSTransaction
        from apps.penjualan.models import SalesOrder
        from apps.pembelian.models import PurchaseOrder
        from apps.biaya.models import TransaksiBiaya

        # Total pemasukan: POS (lunas) + Sales Order (terkonfirmasi/selesai)
        # DIPERBAIKI: Menggunakan aggregate_sales_amounts()['net'] agar konsisten
        # dengan Dashboard utama dan Laporan Keuangan (tanpa PPN, setelah diskon)
        from apps.core.finance_metrics import aggregate_sales_amounts, aggregate_purchase_amounts
        total_pemasukan_pos = aggregate_sales_amounts(
            POSTransaction.objects.filter(status='paid')
        )['net']
        total_pemasukan_so = aggregate_sales_amounts(
            SalesOrder.objects.filter(status__in=['confirmed', 'delivered', 'completed'])
        )['net']
        total_pemasukan = total_pemasukan_pos + total_pemasukan_so
        context['total_pemasukan'] = total_pemasukan

        # Total pengeluaran: Purchase Order (subtotal tanpa PPN) + Biaya operasional (disetujui)
        total_pengeluaran_po = aggregate_purchase_amounts(
            PurchaseOrder.objects.filter(status__in=['approved', 'received'])
        )['subtotal']
        total_pengeluaran_biaya = TransaksiBiaya.objects.filter(
            status='approved'
        ).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
        total_pengeluaran = total_pengeluaran_po + total_pengeluaran_biaya
        context['total_pengeluaran'] = total_pengeluaran

        # Selisih keuangan: pemasukan - pengeluaran
        # Positif = laba, Negatif = rugi
        context['selisih_keuangan'] = total_pemasukan - total_pengeluaran

        # Selisih kas rekonsiliasi: total selisih dari semua tutup shift kasir
        total_selisih_kas = CashReconciliation.objects.aggregate(
            total=Sum('discrepancy'))['total'] or Decimal('0')
        context['total_selisih_kas'] = total_selisih_kas

        # === TOP 5 KARYAWAN BERISIKO ===
        # Karyawan dengan anomali terbanyak (status: pending/investigated/rejected)
        risk_users = FraudAlert.objects.filter(
            user_terkait__isnull=False,
            status__in=['pending', 'investigated', 'rejected']
        ).values(
            'user_terkait__id',
            'user_terkait__username',
            'user_terkait__first_name',
            'user_terkait__last_name',
        ).annotate(
            total_alerts=Count('id'),
            total_nominal=Sum('nominal'),
        ).order_by('-total_alerts')[:5]
        context['risk_users'] = risk_users

        # === TREN ANOMALI BULANAN (6 bulan terakhir) ===
        # Data untuk grafik gelombang (ApexCharts area chart)
        import datetime
        from django.utils import timezone
        
        today = timezone.now().date()
        six_months_ago = timezone.now() - datetime.timedelta(days=180)
        
        trend_data = FraudAlert.objects.filter(
            created_at__gte=six_months_ago
        ).annotate(
            bulan=TruncMonth('created_at')
        ).values('bulan').annotate(
            jumlah=Count('id')
        ).order_by('bulan')

        # Siapkan 6 bulan terakhir dengan nilai 0 agar grafik area terbentuk
        trend_dict = {}
        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            if m <= 0:
                m += 12
                y -= 1
            dt_label = datetime.date(y, m, 1).strftime('%b %Y')
            trend_dict[dt_label] = 0

        # Isi dengan data aktual
        for item in trend_data:
            if item['bulan']:
                dt_label = item['bulan'].strftime('%b %Y')
                if dt_label in trend_dict:
                    trend_dict[dt_label] = item['jumlah']

        trend_labels = list(trend_dict.keys())
        trend_values = list(trend_dict.values())
        
        context['trend_labels'] = json.dumps(trend_labels)
        context['trend_values'] = json.dumps(trend_values)

        # === DISTRIBUSI JENIS ANOMALI ===
        # Data untuk grafik donut (ApexCharts donut chart)
        jenis_dist = FraudAlert.objects.values('jenis').annotate(
            total=Count('id')
        ).order_by('-total')
        jenis_labels = []
        jenis_values = []
        jenis_choices = dict(FraudAlert.JENIS_CHOICES)
        for item in jenis_dist:
            jenis_labels.append(jenis_choices.get(item['jenis'], item['jenis']))
            jenis_values.append(item['total'])
        context['jenis_labels'] = json.dumps(jenis_labels)
        context['jenis_values'] = json.dumps(jenis_values)

        # === REKONSILIASI KAS TERBARU ===
        # 5 data rekonsiliasi terakhir untuk tabel ringkasan
        context['recent_reconciliations'] = CashReconciliation.objects.select_related(
            'kasir', 'gudang'
        ).order_by('-created_at')[:5]

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║               FRAUD ALERT LIST & DETAIL                        ║
# ╚══════════════════════════════════════════════════════════════╝

class FraudAlertListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    ══════════════════════════════════════════════════════
    Daftar Semua Fraud Alert / Anomali.
    ══════════════════════════════════════════════════════
    Menampilkan tabel semua anomali yang terdeteksi sistem.
    Mendukung filter: status, jenis, severity, user.
    Menampilkan statistik ringkasan di atas tabel.

    URL: /fraud/alerts/
    Template: fraud_detection/alert_list.html
    Permission: fraud_detection.daftar_anomali.read
    """
    model = FraudAlert
    template_name = 'fraud_detection/alert_list.html'
    context_object_name = 'alert_list'
    permission_module = 'fraud_detection'
    permission_sub_module = 'daftar_anomali'
    permission_action = 'read'

    def get_queryset(self):
        qs = super().get_queryset().select_related('user_terkait', 'reviewed_by', 'activity')
        # Filter status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        # Filter jenis
        jenis = self.request.GET.get('jenis')
        if jenis:
            qs = qs.filter(jenis=jenis)
        # Filter severity
        severity = self.request.GET.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        # Filter user
        user_id = self.request.GET.get('user')
        if user_id:
            qs = qs.filter(user_terkait_id=user_id)
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        alerts = self.get_queryset()
        context['total_alerts'] = alerts.count()
        context['pending_count'] = alerts.filter(status='pending').count()
        context['total_nominal'] = alerts.aggregate(total=Sum('nominal'))['total'] or 0
        context['jenis_choices'] = FraudAlert.JENIS_CHOICES
        context['severity_choices'] = FraudAlert.SEVERITY_CHOICES
        context['status_choices'] = FraudAlert.STATUS_CHOICES
        context['users'] = User.objects.filter(
            fraud_alerts_terkait__isnull=False
        ).distinct()
        # Current filters
        context['filter_status'] = self.request.GET.get('status', '')
        context['filter_jenis'] = self.request.GET.get('jenis', '')
        context['filter_severity'] = self.request.GET.get('severity', '')
        context['filter_user'] = self.request.GET.get('user', '')
        return context


class FraudAlertDetailView(SubModulePermissionMixin, TemplateView):
    """
    Detail 1 Anomali Fraud + Data Terhubung.
    Menampilkan: detail anomali, data snapshot (JSON), riwayat aktivitas
    user terkait, dan link ke record asli (POS/SO/PO/CashRecon).

    URL: /fraud/alerts/<pk>/
    Template: fraud_detection/alert_detail.html
    Permission: fraud_detection.daftar_anomali.read
    """
    template_name = 'fraud_detection/alert_detail.html'
    permission_module = 'fraud_detection'
    permission_sub_module = 'daftar_anomali'
    permission_action = 'read'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.shortcuts import get_object_or_404
        alert = get_object_or_404(
            FraudAlert.objects.select_related('user_terkait', 'reviewed_by', 'activity'),
            pk=kwargs.get('pk')
        )
        context['alert'] = alert

        # Riwayat activity log terkait user ini
        if alert.user_terkait:
            context['user_activities'] = UserActivity.objects.filter(
                user=alert.user_terkait
            ).order_by('-timestamp')[:20]

        # Data snapshot display
        if alert.data_snapshot:
            context['snapshot_pretty'] = json.dumps(alert.data_snapshot, indent=2, ensure_ascii=False)

        # Resolusi data terkait secara realtime (menautkan alert dengan record asli)
        if alert.model_name and alert.object_id:
            try:
                if alert.model_name == 'POSTransaction':
                    from apps.pos.models import POSTransaction
                    context['related_object_pos'] = POSTransaction.objects.filter(nomor_transaksi=alert.object_id).first()
                elif alert.model_name == 'SalesOrder':
                    from apps.penjualan.models import SalesOrder
                    context['related_object_so'] = SalesOrder.objects.filter(nomor_so=alert.object_id).first()
                elif alert.model_name == 'PurchaseOrder':
                    from apps.pembelian.models import PurchaseOrder
                    context['related_object_po'] = PurchaseOrder.objects.filter(nomor_po=alert.object_id).first()
                elif alert.model_name == 'CashReconciliation':
                    from apps.fraud_detection.models import CashReconciliation
                    context['related_object_cash'] = CashReconciliation.objects.filter(id=alert.object_id).first()
            except Exception as e:
                logger.warning("Error tidak terduga: %s", e)

        return context


@login_required
@require_POST
def fraud_alert_update_status(request, pk):
    """
    Update status fraud alert via AJAX POST.
    Mengubah status anomali: pending → investigated → cleared/rejected.
    Juga menyimpan catatan review dan siapa yang mereview.
    Mencatat perubahan ke Activity Log untuk audit trail.

    Return: JsonResponse {success: bool, message: str}
    """
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'fraud_detection', 'daftar_anomali'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengubah data anomali.'}, status=403)

    try:
        alert = FraudAlert.objects.get(pk=pk)
        new_status = request.POST.get('status')
        catatan = request.POST.get('catatan', '')

        if new_status not in dict(FraudAlert.STATUS_CHOICES):
            return JsonResponse({'success': False, 'message': 'Status tidak valid.'}, status=400)

        alert.status = new_status
        alert.catatan_owner = catatan
        alert.reviewed_by = request.user
        alert.reviewed_at = timezone.now()
        alert.save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Fraud Alert',
            object_id=alert.pk,
            object_repr=str(alert),
            description=f'Mengubah status fraud alert ke: {alert.get_status_display()}'
        )

        return JsonResponse({
            'success': True,
            'message': f'Status anomali berhasil diubah ke "{alert.get_status_display()}".'
        })
    except FraudAlert.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Data tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)



# ╔══════════════════════════════════════════════════════════════╗
# ║           REKONSILIASI KAS (BLIND CASH CLOSING)               ║
# ╚══════════════════════════════════════════════════════════════╝

class CashReconciliationListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    Daftar Semua Rekonsiliasi Kas (Blind Cash Closing).
    Menampilkan tabel semua record tutup shift kasir.
    Ringkasan: total records, total selisih, shortage count, overage count.

    URL: /fraud/cash/
    Template: fraud_detection/cash_list.html
    Permission: fraud_detection.rekonsiliasi_kas.read
    """
    model = CashReconciliation
    template_name = 'fraud_detection/cash_list.html'
    context_object_name = 'reconciliation_list'
    permission_module = 'fraud_detection'
    permission_sub_module = 'rekonsiliasi_kas'
    permission_action = 'read'

    def get_queryset(self):
        return super().get_queryset().select_related('kasir', 'gudang', 'reviewed_by')

    def get_context_data(self, **kwargs):
        """Menyiapkan data ringkasan rekonsiliasi kas untuk template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_records'] = qs.count()  # Jumlah total record tutup shift
        context['total_discrepancy'] = qs.aggregate(total=Sum('discrepancy'))['total'] or 0  # Total selisih
        context['shortage_count'] = qs.filter(discrepancy__lt=0).count()  # Jumlah shift kurang kas
        context['overage_count'] = qs.filter(discrepancy__gt=0).count()  # Jumlah shift lebih kas
        # Total uang yang dicatat sistem (expected) dan uang fisik (actual)
        # Digunakan untuk footer ringkasan tabel
        context['total_expected'] = qs.aggregate(total=Sum('expected_amount'))['total'] or 0
        context['total_actual'] = qs.aggregate(total=Sum('actual_amount'))['total'] or 0
        return context


class CashReconciliationCreateView(SubModulePermissionMixin, TemplateView):
    """
    Form Blind Cash Closing — Kasir Input Uang Fisik.
    Kasir memilih gudang/cabang, input waktu shift, dan jumlah uang fisik.
    Sistem otomatis menghitung expected amount dari transaksi POS cash.
    Jika selisih negatif > Rp 10.000, otomatis buat FraudAlert.

    URL: /fraud/cash/create/
    Template: fraud_detection/cash_form.html
    Permission: fraud_detection.rekonsiliasi_kas.create
    """
    template_name = 'fraud_detection/cash_form.html'
    permission_module = 'fraud_detection'
    permission_sub_module = 'rekonsiliasi_kas'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.produk.models import Gudang
        context['gudang_list'] = Gudang.objects.filter(aktif=True)
        return context


    def post(self, request, *args, **kwargs):
        """Proses submit rekonsiliasi kas."""
        try:
            from apps.produk.models import Gudang
            from apps.pos.models import POSTransaction

            gudang_id = request.POST.get('gudang')
            actual_amount = Decimal(request.POST.get('actual_amount', '0'))
            catatan = request.POST.get('catatan', '')
            shift_start_str = request.POST.get('shift_start', '')
            shift_end_str = request.POST.get('shift_end', '')

            # Parse datetimes
            from datetime import datetime
            shift_start = timezone.make_aware(datetime.strptime(shift_start_str, '%Y-%m-%dT%H:%M'))
            shift_end = timezone.make_aware(datetime.strptime(shift_end_str, '%Y-%m-%dT%H:%M'))

            # Hitung expected amount hanya dari transaksi POS dengan metode CASH
            # Karena uang laci hanya berisi uang tunai, bukan QRIS/Transfer
            from apps.pos.models import MetodePembayaran
            cash_methods = MetodePembayaran.objects.filter(
                Q(kode__iexact='CASH') | Q(nama__icontains='tunai') | Q(nama__iexact='cash')
            )

            pos_filter = Q(tanggal__gte=shift_start, tanggal__lte=shift_end, status='paid')
            if gudang_id:
                pos_filter &= Q(gudang_id=gudang_id)
            if cash_methods.exists():
                pos_filter &= Q(metode_pembayaran__in=cash_methods)

            expected_pos = POSTransaction.objects.filter(pos_filter).aggregate(
                total=Sum('total_harga')
            )['total'] or Decimal('0')

            # Kurangi dengan pengeluaran tunai (biaya operasional yang dibayar dari laci kas)
            from apps.biaya.models import TransaksiBiaya
            biaya_filter = Q(
                tanggal__gte=shift_start.date(), tanggal__lte=shift_end.date(),
                status='approved'
            )
            if cash_methods.exists():
                biaya_filter &= Q(metode_pembayaran__in=cash_methods)
            cash_expenses = TransaksiBiaya.objects.filter(biaya_filter).aggregate(
                total=Sum('jumlah')
            )['total'] or Decimal('0')

            # Expected = total penjualan cash - pengeluaran cash dari laci
            expected = expected_pos - cash_expenses

            gudang = Gudang.objects.get(pk=gudang_id) if gudang_id else None

            recon = CashReconciliation.objects.create(
                kasir=request.user,
                gudang=gudang,
                shift_start=shift_start,
                shift_end=shift_end,
                expected_amount=expected,
                actual_amount=actual_amount,
                catatan=catatan,
                status='closed',
            )

            # Otomatis buat fraud alert jika selisih negatif signifikan (> Rp 10.000)
            if recon.discrepancy < Decimal('-10000'):
                FraudAlert.objects.create(
                    jenis='lainnya',
                    severity='high' if recon.discrepancy < Decimal('-100000') else 'medium',
                    deskripsi=f'Selisih kas negatif Rp {abs(recon.discrepancy):,.0f} pada shift kasir {request.user.get_full_name() or request.user.username}.',
                    user_terkait=request.user,
                    nominal=abs(recon.discrepancy),
                    model_name='CashReconciliation',
                    object_id=str(recon.pk),
                )

            from django.shortcuts import redirect
            from django.contrib import messages
            messages.success(request, f'Rekonsiliasi kas berhasil dicatat. Selisih: Rp {recon.discrepancy:,.0f}')
            return redirect('fraud_detection:cash_list')

        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Gagal menyimpan rekonsiliasi: {str(e)}')
            return self.get(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
# ║            PENGATURAN FRAUD (FRAUD SETTINGS)                   ║
# ╚══════════════════════════════════════════════════════════════╝

class FraudSettingsView(SubModulePermissionMixin, TemplateView):
    """
    Pengaturan Pencegahan Fraud (Toggle ON/OFF).
    Menampilkan form untuk mengubah FraudRule singleton:
    - Blokir hapus data lunas (on/off)
    - Blokir stok minus (on/off)
    - Batas diskon maksimal (%)
    - Jam operasional mulai & selesai

    GET: Tampilkan form dengan data FraudRule saat ini.
    POST: Simpan perubahan via AJAX, return JSON.

    URL: /fraud/settings/
    Template: fraud_detection/settings.html
    Permission: fraud_detection.pengaturan_fraud.read
    """
    template_name = 'fraud_detection/settings.html'
    permission_module = 'fraud_detection'
    permission_sub_module = 'pengaturan_fraud'
    permission_action = 'read'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['fraud_rule'] = FraudRule.load()
        return context

    def post(self, request, *args, **kwargs):
        """Simpan pengaturan fraud."""
        try:
            rule = FraudRule.load()
            rule.block_delete_paid = request.POST.get('block_delete_paid') == 'on'
            rule.block_negative_stock = request.POST.get('block_negative_stock') == 'on'
            rule.max_discount_percent = Decimal(request.POST.get('max_discount_percent', '100'))
            rule.jam_operasional_mulai = request.POST.get('jam_operasional_mulai', '07:00')
            rule.jam_operasional_selesai = request.POST.get('jam_operasional_selesai', '22:00')
            rule.updated_by = request.user
            rule.save()

            # Log activity
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                request,
                action='update',
                model_name='Fraud Rule',
                object_id=rule.pk,
                object_repr=str(rule),
                description='Mengubah pengaturan fraud detection'
            )

            return JsonResponse({'success': True, 'message': 'Pengaturan fraud berhasil disimpan.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║           EXPORT EXCEL / PDF FRAUD ALERTS                     ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
def export_fraud_alerts_excel(request):
    """
    Export semua fraud alerts ke file Excel (.xls).
    Mendukung filter status dan jenis via GET parameter.
    Menggunakan format HTML table yang di-export sebagai .xls
    (Excel bisa membaca HTML table sebagai spreadsheet).

    URL: /fraud/alerts/export/
    Return: HttpResponse dengan file attachment .xls
    """
    import io
    from django.http import HttpResponse

    alerts = FraudAlert.objects.select_related('user_terkait', 'reviewed_by').all()

    # Filter
    status = request.GET.get('status')
    if status:
        alerts = alerts.filter(status=status)
    jenis = request.GET.get('jenis')
    if jenis:
        alerts = alerts.filter(jenis=jenis)

    # Build HTML table
    html = '<html><head><meta charset="utf-8"></head><body>'
    html += '<table border="1">'
    html += '<tr style="background-color:#696CFF;color:#fff;font-weight:bold;">'
    html += '<th>No</th><th>Tanggal</th><th>Jenis</th><th>Tingkat</th><th>User</th>'
    html += '<th>Deskripsi</th><th>Nominal</th><th>Status</th><th>Catatan</th></tr>'

    for i, alert in enumerate(alerts, 1):
        user_name = ''
        if alert.user_terkait:
            user_name = alert.user_terkait.get_full_name() or alert.user_terkait.username
        html += f'<tr><td>{i}</td>'
        html += f'<td>{alert.created_at.strftime("%d/%m/%Y %H:%M") if alert.created_at else "-"}</td>'
        html += f'<td>{alert.get_jenis_display()}</td>'
        html += f'<td>{alert.get_severity_display()}</td>'
        html += f'<td>{user_name}</td>'
        html += f'<td>{alert.deskripsi}</td>'
        html += f'<td>{alert.nominal:,.0f}</td>'
        html += f'<td>{alert.get_status_display()}</td>'
        html += f'<td>{alert.catatan_owner or "-"}</td></tr>'

    html += '</table></body></html>'

    response = HttpResponse(
        '\ufeff' + html,
        content_type='application/vnd.ms-excel; charset=utf-8'
    )
    response['Content-Disposition'] = f'attachment; filename="Fraud_Alerts_{timezone.now().strftime("%Y%m%d")}.xls"'
    return response


# ╔══════════════════════════════════════════════════════════════╗
# ║              DELETE VIEWS (AJAX JSON)                          ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@require_POST
def fraud_alert_delete(request, pk):
    """
    Hapus fraud alert via AJAX POST.
    Return JSON response: success/error + pesan.
    Menangani ProtectedError jika data terkait dengan record lain.

    URL: /fraud/alerts/<pk>/delete/
    """
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'fraud_detection', 'daftar_anomali'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus data anomali.'}, status=403)

    from django.db.models import ProtectedError
    try:
        alert = FraudAlert.objects.get(pk=pk)
        deskripsi = alert.deskripsi[:50]
        alert.delete()
        return JsonResponse({
            'success': True,
            'message': f'Anomali "{deskripsi}" berhasil dihapus.'
        })
    except FraudAlert.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Data anomali tidak ditemukan.'
        }, status=404)
    except ProtectedError:
        return JsonResponse({
            'success': False,
            'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Gagal menghapus data: {str(e)}'
        }, status=500)


@login_required
@require_POST
def cash_recon_delete(request, pk):
    """
    Hapus rekonsiliasi kas via AJAX POST.
    Return JSON response: success/error + pesan.
    Menangani ProtectedError jika data terkait dengan record lain.

    URL: /fraud/cash/<pk>/delete/
    """
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'fraud_detection', 'rekonsiliasi_kas'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk menghapus data rekonsiliasi kas.'}, status=403)

    from django.db.models import ProtectedError
    try:
        recon = CashReconciliation.objects.get(pk=pk)
        recon.delete()
        return JsonResponse({
            'success': True,
            'message': 'Rekonsiliasi kas berhasil dihapus.'
        })
    except CashReconciliation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Data rekonsiliasi tidak ditemukan.'
        }, status=404)
    except ProtectedError:
        return JsonResponse({
            'success': False,
            'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Gagal menghapus data: {str(e)}'
        }, status=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║     EDIT REKONSILIASI KAS (Ubah Uang Fisik)                   ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@require_POST
def cash_recon_edit(request, pk):
    """
    Edit Uang Fisik Rekonsiliasi Kas via AJAX POST.
    Hanya bisa diedit jika status masih 'closed' (belum di-review).
    Setelah edit, model save() otomatis hitung ulang discrepancy.
    Mencatat perubahan ke Activity Log untuk audit trail.

    URL: /fraud/cash/<pk>/edit/
    Return: JsonResponse {success: bool, message: str}
    """
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'fraud_detection', 'rekonsiliasi_kas'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengubah data rekonsiliasi kas.'}, status=403)

    try:
        recon = CashReconciliation.objects.get(pk=pk)
        if recon.status == 'reviewed':
            return JsonResponse({
                'success': False,
                'message': 'Rekonsiliasi yang sudah di-review tidak dapat diubah.'
            }, status=400)

        actual_amount = request.POST.get('actual_amount', '')
        catatan = request.POST.get('catatan', '')

        if not actual_amount:
            return JsonResponse({
                'success': False,
                'message': 'Jumlah uang fisik harus diisi.'
            }, status=400)

        recon.actual_amount = Decimal(actual_amount)
        if catatan:
            reviewer_name = request.user.get_full_name() or request.user.username
            recon.catatan = (recon.catatan or '') + f'\n[Edit oleh {reviewer_name}]: {catatan}'
        recon.save()  # Otomatis hitung ulang discrepancy di model save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Cash Reconciliation',
            object_id=recon.pk,
            object_repr=str(recon),
            description=f'Mengubah uang fisik rekonsiliasi kas menjadi Rp {recon.actual_amount:,.0f}. Selisih baru: Rp {recon.discrepancy:,.0f}'
        )

        return JsonResponse({
            'success': True,
            'message': f'Uang fisik berhasil diubah. Selisih baru: Rp {recon.discrepancy:,.0f}'
        })
    except CashReconciliation.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Data tidak ditemukan.'}, status=404)
    except (ValueError, InvalidOperation) as e:
        return JsonResponse({'success': False, 'message': 'Format nominal tidak valid.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║   REVIEW REKONSILIASI KAS (dengan Tindak Lanjut)              ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@require_POST
def cash_recon_review(request, pk):
    """
    Review/Setujui Rekonsiliasi Kas via AJAX POST.
    Mengubah status dari 'closed' → 'reviewed'.
    Mendukung 2 tindak lanjut:
    1. 'catatan_saja'    → Hanya tambah catatan review
    2. 'biaya_kerugian'  → Otomatis buat TransaksiBiaya kerugian (jika selisih negatif)

    URL: /fraud/cash/<pk>/review/
    Return: JsonResponse {success: bool, message: str}
    """
    if not request.user.is_superuser and not has_permission(request.user, 'update', 'fraud_detection', 'rekonsiliasi_kas'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mereview rekonsiliasi kas.'}, status=403)

    try:
        recon = CashReconciliation.objects.get(pk=pk)
        if recon.status == 'reviewed':
            return JsonResponse({
                'success': False,
                'message': 'Hanya rekonsiliasi berstatus "Shift Ditutup" yang bisa di-review.'
            }, status=400)

        catatan = request.POST.get('catatan', '')
        tindak_lanjut = request.POST.get('tindak_lanjut', 'catatan_saja')

        reviewer_name = request.user.get_full_name() or request.user.username
        recon.status = 'reviewed'
        recon.reviewed_by = request.user
        if catatan:
            recon.catatan = (recon.catatan or '') + f'\n[Review oleh {reviewer_name}]: {catatan}'
        recon.save()

        msg_extra = ''
        # Jika ada selisih negatif dan user pilih catat sebagai biaya kerugian
        if tindak_lanjut == 'biaya_kerugian' and recon.discrepancy < 0:
            from apps.biaya.models import KategoriBiaya, TransaksiBiaya
            from datetime import date

            # Cari atau buat kategori "Selisih Kas / Kerugian"
            kategori, _ = KategoriBiaya.objects.get_or_create(
                nama='Selisih Kas / Kerugian',
                defaults={'deskripsi': 'Kerugian dari selisih kas rekonsiliasi', 'aktif': True}
            )

            # Buat transaksi biaya otomatis
            kasir_name = recon.kasir.get_full_name() or recon.kasir.username
            biaya = TransaksiBiaya(
                tanggal=timezone.now().date(),
                kategori=kategori,
                jumlah=abs(recon.discrepancy),
                deskripsi=f'Selisih kas negatif Rp {abs(recon.discrepancy):,.0f} dari rekonsiliasi kasir {kasir_name} (Shift {recon.shift_start.strftime("%d/%m/%Y %H:%M")})',
                status='approved',
                dibuat_oleh=request.user,
                disetujui_oleh=request.user,
                cabang=recon.gudang,
            )
            biaya.save()
            msg_extra = f' Biaya kerugian Rp {abs(recon.discrepancy):,.0f} otomatis dicatat.'

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Cash Reconciliation',
            object_id=recon.pk,
            object_repr=str(recon),
            description=f'Mereview rekonsiliasi kas kasir {recon.kasir.get_full_name() or recon.kasir.username}. Tindak lanjut: {tindak_lanjut}'
        )

        return JsonResponse({
            'success': True,
            'message': f'Rekonsiliasi kas berhasil di-review.{msg_extra}'
        })
    except CashReconciliation.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Data tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


