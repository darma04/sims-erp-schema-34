"""
==========================================================================
 AI ASSISTANT INTENTS - Deteksi Intent & Pengumpulan Data dari ORM
==========================================================================
 Modul ini menangani:
 1. detect_intent(message) — Deteksi topik dari kata kunci user
 2. gather_data(intent) — Query ORM sesuai intent, return ringkasan

 ARSITEKTUR AMAN:
 - Tidak ada SQL langsung — semua via Django ORM
 - Data yang dikumpulkan hanya angka agregat (total, count, avg)
 - Tidak ada data pelanggan/pribadi yang dikirim ke AI
 - AI hanya menerima ringkasan untuk diformat/dijelaskan
==========================================================================
"""
import logging
from datetime import timedelta
from decimal import Decimal

# Import dari framework Django
from django.utils import timezone
# Import dari framework Django
from django.db.models import Sum, Count, Avg, Q, F, ExpressionWrapper, DecimalField
# Import dari framework Django
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# INTENT DEFINITIONS — Kata kunci per intent
# ═══════════════════════════════════════════════════════════════
INTENT_KEYWORDS = {
    'penjualan': [
        'penjualan', 'jual', 'sales', 'omzet', 'omset', 'revenue',
        'pendapatan', 'pemasukan', 'income', 'sales order',
    ],
    'produk': [
        'produk', 'barang', 'product', 'item', 'katalog', 'kategori',
        'satuan', 'sku', 'barcode',
    ],
    'stok': [
        'stok', 'stock', 'gudang', 'warehouse', 'persediaan', 'inventory',
        'transfer stok', 'adjustment', 'opname',
    ],
    'biaya': [
        'biaya', 'expense', 'pengeluaran', 'cost', 'operasional',
        'listrik', 'gaji', 'sewa',
    ],
    'pembelian': [
        'pembelian', 'beli', 'purchase', 'po', 'supplier', 'pemasok',
        'purchase order',
    ],
    'keuntungan': [
        'keuntungan', 'profit', 'margin', 'laba', 'rugi', 'untung',
        'loss', 'net profit', 'gross profit',
    ],
    'karyawan': [
        'karyawan', 'employee', 'pegawai', 'staff', 'sdm', 'hr',
        'departemen', 'jabatan', 'absensi', 'gaji karyawan', 'penggajian',
    ],
    'pos': [
        'pos', 'kasir', 'transaksi pos', 'point of sale', 'cashier',
        'nota', 'struk',
    ],
    'metode_pembayaran': [
        'metode pembayaran', 'payment', 'bayar', 'transfer', 'cash',
        'tunai', 'qris', 'e-wallet', 'saldo',
    ],
    'pelanggan': [
        'pelanggan', 'customer', 'konsumen', 'pembeli', 'client',
    ],
    'supplier': [
        'supplier', 'pemasok', 'vendor', 'distributor',
    ],
    'bantuan': [
        'bantuan', 'help', 'tolong', 'cara', 'panduan', 'tutorial',
        'fitur', 'menu', 'apa saja', 'bisa apa', 'fungsi',
    ],
    # ═══ ADVANCED INTENTS ═══
    'laporan_meeting': [
        'laporan meeting', 'meeting', 'rapat', 'laporan manajemen',
        'presentasi', 'laporan bulanan', 'notulen', 'report meeting',
    ],
    'executive_summary': [
        'executive summary', 'ringkasan eksekutif', 'summary', 'rangkuman',
        'ringkasan bisnis', 'overview bisnis', 'ikhtisar',
    ],
    'swot': [
        'swot', 'strength', 'weakness', 'opportunity', 'threat',
        'analisa swot', 'kekuatan', 'kelemahan', 'peluang', 'ancaman',
    ],
    'rencana_aksi': [
        'rencana', 'aksi', 'rekomendasi', 'saran', 'strategi',
        'meningkatkan omzet', 'tingkatkan penjualan', 'action plan',
        'apa yang harus', 'langkah', 'solusi',
    ],
    'forecasting': [
        'prediksi', 'forecast', 'proyeksi', 'estimasi',
        'perkiraan', 'tren', 'trend', '30 hari', 'bulan depan',
    ],
    'risiko': [
        'risiko', 'risk', 'bahaya', 'masalah', 'warning', 'peringatan',
        'overstock', 'churn', 'minus', 'negatif', 'rugi',
    ],
    'perbandingan': [
        'bandingkan', 'perbandingan', 'compare', 'vs', 'banding',
        'bulan lalu', 'periode lalu', 'year over year', 'dibanding',
    ],
    'stok_kritis': [
        'stok habis', 'stok kritis', 'hampir habis', 'low stock',
        'stok menipis', 'restock', 'perlu beli', 'stok rendah',
    ],
    'margin_produk': [
        'margin produk', 'margin terendah', 'margin tertinggi',
        'produk profitable', 'produk rugi', 'harga jual',
    ],
    'analisa_pelanggan': [
        'top customer', 'customer terbaik', 'pelanggan terbaik',
        'customer tidak aktif', 'pelanggan tidak aktif', 'customer inactive',
        'analisa pelanggan', 'analisa customer', 'frekuensi beli',
        'frekuensi pembelian', 'total belanja', 'customer loyal',
        'pelanggan loyal', 'ranking pelanggan', 'ranking customer',
    ],
    'laporan_terjadwal': [
        'laporan terjadwal', 'scheduled report', 'laporan otomatis',
        'laporan mingguan', 'laporan senin', 'kirim laporan',
        'weekly report', 'auto report', 'jadwal laporan',
    ],
    'kebocoran_profit': [
        'kebocoran profit', 'profit turun', 'kenapa profit', 'laba turun',
        'profit bocor', 'margin turun', 'revenue bocor', 'profit leak',
        'kenapa rugi', 'profit rendah', 'laba rendah', 'untung turun',
        'profit menurun', 'keuntungan turun', 'keuntungan menurun',
    ],
    'fraud_detection': [
        'fraud', 'curang', 'mencurigakan', 'anomali transaksi',
        'kecurangan', 'refund mencurigakan', 'diskon tidak wajar',
        'kasir curang', 'refund terlalu sering', 'transaksi mencurigakan',
        'suspicious', 'fraud detection', 'deteksi kecurangan',
        'tingkah aneh', 'aktivitas aneh', 'tidak wajar',
    ],
    'copywriter': [
        'copywriter', 'caption', 'deskripsi produk', 'broadcast',
        'whatsapp broadcast', 'promosi produk', 'tuliskan promosi',
        'buat caption', 'generate caption', 'copy writing',
        'buat deskripsi', 'teks promosi', 'buat broadcast',
        'tuliskan deskripsi', 'generate deskripsi',
    ],
    'marketing': [
        'marketing', 'campaign', 'strategi marketing', 'marketing plan',
        'rencana pemasaran', 'promosi', 'strategi promosi',
        'campaign plan', 'ide marketing', 'ide promosi',
        'marketing generator', 'plan marketing', 'pemasaran',
    ],
    # ═══ FITUR AI BARU ═══
    'campaign_planner': [
        'campaign planner', 'rencana campaign', 'plan campaign',
        'campaign bulanan', 'campaign mingguan', 'jadwal campaign',
        'campaign schedule', 'rencana promosi', 'calendar promosi',
        'content calendar', 'jadwal konten', 'social media plan',
    ],
    'business_plan_90hari': [
        'business plan', 'rencana bisnis', 'plan 3 bulan', 'plan 90 hari',
        '90 hari', '3 bulan ke depan', 'quarterly plan', 'rencana kuartal',
        'target 3 bulan', 'roadmap bisnis', 'rencana jangka pendek',
        'strategi 3 bulan', 'growth plan', 'plan kuartal',
    ],
    'multi_branch_analyzer': [
        'cabang', 'branch', 'multi cabang', 'performa cabang',
        'bandingkan cabang', 'compare branch', 'antar cabang',
        'ranking cabang', 'cabang terbaik', 'cabang terburuk',
        'multi branch', 'gudang vs gudang', 'bandingkan gudang',
    ],
    'content_generator': [
        'caption instagram', 'caption ig', 'script tiktok', 'tiktok',
        'deskripsi shopee', 'shopee', 'tokopedia', 'marketplace',
        'broadcast whatsapp', 'broadcast wa', 'wa blast',
        'instagram', 'konten sosmed', 'konten media sosial',
        'generate konten', 'buat konten', 'ide konten',
    ],
    # ═══ MODUL KEUANGAN & AKUNTANSI ═══
    'kas_bank': [
        'kas', 'bank', 'kas bank', 'treasury', 'saldo kas', 'saldo bank',
        'mutasi kas', 'mutasi bank', 'transfer kas', 'transfer bank',
        'rekening', 'arus kas', 'cashflow', 'cash flow',
        'saldo rekening', 'kas masuk', 'kas keluar',
    ],
    'akuntansi': [
        'akuntansi', 'accounting', 'jurnal', 'buku besar', 'ledger',
        'chart of accounts', 'coa', 'neraca', 'balance sheet',
        'laba rugi', 'income statement', 'trial balance', 'neraca saldo',
        'double entry', 'debit kredit', 'posting jurnal', 'tutup buku',
        'closing', 'periode akuntansi',
    ],
    'piutang_hutang': [
        'piutang', 'hutang', 'receivable', 'payable', 'ar', 'ap',
        'tagihan', 'jatuh tempo', 'aging', 'overdue', 'belum bayar',
        'pelunasan', 'pembayaran piutang', 'pembayaran hutang',
        'utang', 'accounts receivable', 'accounts payable',
    ],
    'aset_tetap': [
        'aset tetap', 'fixed asset', 'penyusutan', 'depresiasi',
        'depreciation', 'disposal', 'nilai buku', 'umur ekonomis',
        'akumulasi penyusutan', 'peralatan', 'kendaraan', 'bangunan',
    ],
    'pajak_ppn': [
        'pajak', 'ppn', 'tax', 'vat', 'faktur pajak', 'ppn masukan',
        'ppn keluaran', 'setor pajak', 'rekap ppn', 'dpp',
        'tarif pajak', 'settlement ppn', 'restitusi',
    ],
}


def detect_intent(message):
    """
    Deteksi intent dari pesan user berdasarkan kata kunci.

    Args:
        message (str): Pesan dari user

    Returns:
        str: Nama intent yang terdeteksi
    """
    msg = message.lower().strip()

    # Cek per intent — prioritas: keyword panjang duluan
    best_intent = 'umum'
    best_score = 0

    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in msg:
                # Keyword lebih panjang = lebih spesifik = skor lebih tinggi
                score += len(kw)
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent


def _parse_time_context(message):
    """
    Parse konteks waktu dari pesan user.
    Return (start_date, end_date, label_periode) atau None jika tidak ada konteks waktu.
    """
    msg = message.lower().strip()
    today = timezone.now().date()

    # Hari ini
    if 'hari ini' in msg or 'today' in msg:
        return today, today, 'Hari Ini'

    # Kemarin
    if 'kemarin' in msg or 'yesterday' in msg:
        kemarin = today - timedelta(days=1)
        return kemarin, kemarin, 'Kemarin'

    # Minggu ini
    if 'minggu ini' in msg or 'this week' in msg or 'pekan ini' in msg:
        start_of_week = today - timedelta(days=today.weekday())
        return start_of_week, today, f'Minggu Ini ({start_of_week.strftime("%d/%m")} - {today.strftime("%d/%m/%Y")})'

    # Minggu lalu
    if 'minggu lalu' in msg or 'last week' in msg or 'pekan lalu' in msg:
        end_of_last_week = today - timedelta(days=today.weekday() + 1)
        start_of_last_week = end_of_last_week - timedelta(days=6)
        return start_of_last_week, end_of_last_week, f'Minggu Lalu ({start_of_last_week.strftime("%d/%m")} - {end_of_last_week.strftime("%d/%m/%Y")})'

    # Bulan lalu
    if 'bulan lalu' in msg or 'last month' in msg or 'bulan kemarin' in msg:
        first_this_month = today.replace(day=1)
        end_last_month = first_this_month - timedelta(days=1)
        start_last_month = end_last_month.replace(day=1)
        return start_last_month, end_last_month, f'Bulan Lalu ({start_last_month.strftime("%B %Y")})'

    # 7 hari terakhir
    if '7 hari' in msg or 'seminggu terakhir' in msg:
        return today - timedelta(days=7), today, '7 Hari Terakhir'

    # 30 hari terakhir
    if '30 hari' in msg or 'sebulan terakhir' in msg:
        return today - timedelta(days=30), today, '30 Hari Terakhir'

    # 3 bulan terakhir
    if '3 bulan' in msg or 'kuartal' in msg or 'quarter' in msg:
        return today - timedelta(days=90), today, '3 Bulan Terakhir'

    # Tidak ada konteks waktu spesifik
    return None


def gather_data(intent, message=''):
    """
    Kumpulkan data dari ORM sesuai intent. Return dict ringkasan.

    AMAN: Hanya angka agregat, tidak ada data pribadi/sensitif.
    Mendukung konteks waktu cerdas dari pesan user.
    """
    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Parse konteks waktu dari pesan user
    time_ctx = _parse_time_context(message) if message else None
    if time_ctx:
        month_start, today, _ = time_ctx

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        if intent == 'penjualan':
            return _gather_penjualan(today, month_start)
        elif intent == 'produk':
            return _gather_produk()
        elif intent == 'stok':
            return _gather_stok()
        elif intent == 'biaya':
            return _gather_biaya(today, month_start)
        elif intent == 'pembelian':
            return _gather_pembelian(today, month_start)
        elif intent == 'keuntungan':
            return _gather_keuntungan(today, month_start)
        elif intent == 'karyawan':
            return _gather_karyawan()
        elif intent == 'pos':
            return _gather_pos(today, month_start)
        elif intent == 'metode_pembayaran':
            return _gather_metode_pembayaran()
        elif intent == 'pelanggan':
            return _gather_pelanggan(today, month_start)
        elif intent == 'supplier':
            return _gather_supplier()
        elif intent == 'bantuan':
            return _gather_bantuan()
        elif intent == 'laporan_meeting':
            return _gather_laporan_meeting(today, month_start)
        elif intent == 'executive_summary':
            return _gather_executive_summary(today, month_start)
        elif intent == 'swot':
            return _gather_swot(today, month_start)
        elif intent == 'rencana_aksi':
            return _gather_rencana_aksi(today, month_start)
        elif intent == 'forecasting':
            return _gather_forecasting(today, month_start)
        elif intent == 'risiko':
            return _gather_risiko(today, month_start)
        elif intent == 'perbandingan':
            return _gather_perbandingan(today, month_start)
        elif intent == 'stok_kritis':
            return _gather_stok_kritis()
        elif intent == 'margin_produk':
            return _gather_margin_produk()
        elif intent == 'analisa_pelanggan':
            return _gather_analisa_pelanggan(today, month_start)
        elif intent == 'laporan_terjadwal':
            return _gather_laporan_terjadwal()
        elif intent == 'kebocoran_profit':
            return _gather_kebocoran_profit(today, month_start)
        elif intent == 'fraud_detection':
            return _gather_fraud_detection(today, month_start)
        elif intent == 'copywriter':
            return _gather_copywriter()
        elif intent == 'marketing':
            return _gather_marketing(today, month_start)
        elif intent == 'campaign_planner':
            return _gather_campaign_planner(today, month_start)
        elif intent == 'business_plan_90hari':
            return _gather_business_plan_90hari(today, month_start)
        elif intent == 'multi_branch_analyzer':
            return _gather_multi_branch_analyzer(today, month_start)
        elif intent == 'content_generator':
            return _gather_content_generator()
        elif intent == 'kas_bank':
            return _gather_kas_bank(today, month_start)
        elif intent == 'akuntansi':
            return _gather_akuntansi(today, month_start)
        elif intent == 'piutang_hutang':
            return _gather_piutang_hutang(today, month_start)
        elif intent == 'aset_tetap':
            return _gather_aset_tetap()
        elif intent == 'pajak_ppn':
            return _gather_pajak_ppn(today, month_start)
        else:
            return _gather_umum(today, month_start)
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"[AI INTENT] Error gathering data for intent '{intent}': {e}", exc_info=True)
        return {
            'intent': intent,
            'error': True,
            'ringkasan': f'Terjadi kesalahan saat mengambil data: {str(e)}',
        }


# ═══════════════════════════════════════════════════════════════
# DATA GATHERERS — Satu fungsi per intent
# ═══════════════════════════════════════════════════════════════

def _gather_penjualan(today, month_start):
    """Data penjualan: omzet, total transaksi, top produk, growth."""
    from apps.penjualan.models import SalesOrder, SalesOrderItem
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction

    # Sales Order bulan ini
    so_qs = SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=month_start, tanggal__date__lte=today
    )
    so_count = so_qs.count()
    so_revenue = float(so_qs.aggregate(t=Sum('total_harga'))['t'] or 0)

    # POS bulan ini
    pos_qs = POSTransaction.objects.filter(
        status='paid',
        tanggal__date__gte=month_start, tanggal__date__lte=today
    )
    pos_count = pos_qs.count()
    pos_revenue = float(pos_qs.aggregate(t=Sum('total_harga'))['t'] or 0)

    total_revenue = so_revenue + pos_revenue
    total_trx = so_count + pos_count

    # Bulan lalu untuk growth
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    # Query database — ambil data prev_so yang sesuai filter
    prev_so = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=prev_month_start, tanggal__date__lte=prev_month_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data prev_pos yang sesuai filter
    prev_pos = float(POSTransaction.objects.filter(
        status='paid',
        tanggal__date__gte=prev_month_start, tanggal__date__lte=prev_month_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    prev_total = prev_so + prev_pos
    growth = round(((total_revenue - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0

    # Top 5 produk terlaris bulan ini
    from collections import defaultdict
    product_sales = defaultdict(lambda: {'qty': 0, 'revenue': 0})

    # Query database — ambil data so_items yang sesuai filter
    so_items = SalesOrderItem.objects.filter(
        sales_order__status__in=['confirmed', 'delivered', 'completed'],
        sales_order__tanggal__date__gte=month_start
    ).values('produk__nama').annotate(
        total_qty=Sum('jumlah'), total_rev=Sum('subtotal')
    ).order_by('-total_rev')[:5]

    for item in so_items:
        nama = item['produk__nama']
        product_sales[nama]['qty'] += int(item['total_qty'] or 0)
        product_sales[nama]['revenue'] += float(item['total_rev'] or 0)

    top_products = []
    for nama, data in sorted(product_sales.items(), key=lambda x: x[1]['revenue'], reverse=True)[:5]:
        top_products.append(f"- {nama}: {data['qty']} terjual (Rp {data['revenue']:,.0f})")

    # Label periode
    time_ctx = _parse_time_context('') if month_start == timezone.now().date().replace(day=1) else None
    label = f'Bulan Ini ({month_start.strftime("%B %Y")})' if not time_ctx else 'Periode Terpilih'
    if month_start != timezone.now().date().replace(day=1):
        label = f'{month_start.strftime("%d/%m/%Y")} s/d {today.strftime("%d/%m/%Y")}'

    ringkasan = f"""Data Penjualan {label}:
- Total Omzet: Rp {total_revenue:,.0f}
- Total Transaksi: {total_trx} transaksi
- Sales Order: {so_count} SO (Rp {so_revenue:,.0f})
- Transaksi POS: {pos_count} POS (Rp {pos_revenue:,.0f})
- Growth vs bulan lalu: {'+' if growth >= 0 else ''}{growth}%
- Omzet bulan lalu: Rp {prev_total:,.0f}

Top Produk Terlaris:
{chr(10).join(top_products) if top_products else '- Belum ada data penjualan'}"""

    return {'intent': 'penjualan', 'ringkasan': ringkasan}


def _gather_produk():
    """Data produk: total, kategori, stok rendah."""
    from apps.produk.models import Produk, Kategori, Satuan, Stok

    # Query database — ambil data total_produk yang sesuai filter
    total_produk = Produk.objects.filter(aktif=True).count()
    # Hitung jumlah data yang cocok
    total_kategori = Kategori.objects.count()
    # Hitung jumlah data yang cocok
    total_satuan = Satuan.objects.count()
    # Query database — ambil data total_non_aktif yang sesuai filter
    total_non_aktif = Produk.objects.filter(aktif=False).count()

    # Produk tanpa stok
    produk_ids_with_stock = Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True).distinct()
    # Query database — ambil data produk_habis yang sesuai filter
    produk_habis = Produk.objects.filter(aktif=True).exclude(id__in=produk_ids_with_stock).count()

    # Rata-rata harga
    avg_beli = float(Produk.objects.filter(aktif=True).aggregate(a=Avg('harga_beli'))['a'] or 0)
    # Query database — ambil data avg_jual yang sesuai filter
    avg_jual = float(Produk.objects.filter(aktif=True).aggregate(a=Avg('harga_jual'))['a'] or 0)

    # Top 5 kategori
    top_kat = Kategori.objects.annotate(
        jml=Count('produk', filter=Q(produk__aktif=True))
    ).order_by('-jml')[:5]
    kat_list = [f"- {k.nama}: {k.jml} produk" for k in top_kat]

    ringkasan = f"""Data Produk:
- Total Produk Aktif: {total_produk}
- Total Produk Non-Aktif: {total_non_aktif}
- Total Kategori: {total_kategori}
- Total Satuan: {total_satuan}
- Produk Stok Habis: {produk_habis}
- Rata-rata Harga Beli: Rp {avg_beli:,.0f}
- Rata-rata Harga Jual: Rp {avg_jual:,.0f}
- Estimasi Margin Rata-rata: {round((avg_jual - avg_beli) / avg_jual * 100, 1) if avg_jual > 0 else 0}%

Top Kategori:
{chr(10).join(kat_list) if kat_list else '- Belum ada kategori'}"""

    return {'intent': 'produk', 'ringkasan': ringkasan}


def _gather_stok():
    """Data stok dan gudang."""
    from apps.produk.models import Gudang, Stok, Produk
    # Import dari modul internal proyek
    from apps.inventory.models import TransferStok, AdjustmentStok

    # Query database — ambil data total_gudang yang sesuai filter
    total_gudang = Gudang.objects.filter(aktif=True).count()
    total_stok_record = Stok.objects.count()
    total_unit = float(Stok.objects.aggregate(t=Sum('jumlah'))['t'] or 0)

    # Stok per gudang
    gudang_list = Gudang.objects.filter(aktif=True).order_by('nama')[:7]
    gudang_info = []
    for g in gudang_list:
        # Query database — ambil data stok_g yang sesuai filter
        stok_g = float(Stok.objects.filter(gudang=g).aggregate(t=Sum('jumlah'))['t'] or 0)
        # Query database — ambil data produk_count yang sesuai filter
        produk_count = Stok.objects.filter(gudang=g, jumlah__gt=0).values('produk').distinct().count()
        gudang_info.append(f"- {g.nama}: {stok_g:,.0f} unit ({produk_count} jenis produk)")

    # Transfer stok bulan ini
    today = timezone.now().date()
    month_start = today.replace(day=1)
    # Query database — ambil data transfer_count yang sesuai filter
    transfer_count = TransferStok.objects.filter(dibuat_pada__date__gte=month_start).count()
    # Query database — ambil data adjustment_count yang sesuai filter
    adjustment_count = AdjustmentStok.objects.filter(dibuat_pada__date__gte=month_start).count()

    ringkasan = f"""Data Stok & Gudang:
- Total Gudang Aktif: {total_gudang}
- Total Unit Stok: {total_unit:,.0f}
- Transfer Stok Bulan Ini: {transfer_count}
- Adjustment Stok Bulan Ini: {adjustment_count}

Stok per Gudang:
{chr(10).join(gudang_info) if gudang_info else '- Belum ada gudang'}"""

    return {'intent': 'stok', 'ringkasan': ringkasan}


def _gather_biaya(today, month_start):
    """Data biaya operasional."""
    from apps.biaya.models import TransaksiBiaya, KategoriBiaya

    # Hitung aggregasi data (SUM/COUNT/AVG)
    total_biaya = float(TransaksiBiaya.objects.aggregate(t=Sum('jumlah'))['t'] or 0)
    # Query database — ambil data biaya_bulan_ini yang sesuai filter
    biaya_bulan_ini = float(TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).aggregate(t=Sum('jumlah'))['t'] or 0)
    # Query database — ambil data jumlah_trx yang sesuai filter
    jumlah_trx = TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).count()

    # Per kategori
    per_kat = TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).values('kategori__nama').annotate(
        total=Sum('jumlah')
    ).order_by('-total')[:7]
    kat_list = [f"- {k['kategori__nama'] or 'Lainnya'}: Rp {float(k['total']):,.0f}" for k in per_kat]

    ringkasan = f"""Data Biaya Operasional:
- Total Biaya Keseluruhan: Rp {total_biaya:,.0f}
- Biaya Bulan Ini: Rp {biaya_bulan_ini:,.0f}
- Jumlah Transaksi Bulan Ini: {jumlah_trx}

Biaya per Kategori (Bulan Ini):
{chr(10).join(kat_list) if kat_list else '- Belum ada biaya bulan ini'}"""

    return {'intent': 'biaya', 'ringkasan': ringkasan}


def _gather_pembelian(today, month_start):
    """Data pembelian / Purchase Order."""
    from apps.pembelian.models import PurchaseOrder, Supplier

    # Hitung jumlah data yang cocok
    total_po = PurchaseOrder.objects.exclude(status='cancelled').count()
    # Query database — ambil data po_bulan_ini yang sesuai filter
    po_bulan_ini = PurchaseOrder.objects.filter(
        tanggal__date__gte=month_start
    ).exclude(status='cancelled').count()
    # Query database — ambil data total_nilai yang sesuai filter
    total_nilai = float(PurchaseOrder.objects.filter(
        status__in=['approved', 'received']
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data nilai_bulan_ini yang sesuai filter
    nilai_bulan_ini = float(PurchaseOrder.objects.filter(
        tanggal__date__gte=month_start,
        status__in=['approved', 'received']
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data total_supplier yang sesuai filter
    total_supplier = Supplier.objects.filter(aktif=True).count()

    # Status PO
    draft = PurchaseOrder.objects.filter(status='draft').count()
    # Query database — ambil data approved yang sesuai filter
    approved = PurchaseOrder.objects.filter(status='approved').count()
    # Query database — ambil data received yang sesuai filter
    received = PurchaseOrder.objects.filter(status='received').count()

    ringkasan = f"""Data Pembelian:
- Total Supplier Aktif: {total_supplier}
- Total PO: {total_po}
- PO Bulan Ini: {po_bulan_ini}
- Total Nilai PO (approved+received): Rp {total_nilai:,.0f}
- Nilai PO Bulan Ini: Rp {nilai_bulan_ini:,.0f}

Status PO Saat Ini:
- Draft: {draft}
- Approved: {approved}
- Received: {received}"""

    return {'intent': 'pembelian', 'ringkasan': ringkasan}


def _gather_keuntungan(today, month_start):
    """Data keuntungan / profit."""
    from apps.penjualan.models import SalesOrder, SalesOrderItem
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction, POSTransactionItem
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya

    # Keuntungan dari SO
    keuntungan_so = float(SalesOrderItem.objects.filter(
        sales_order__status__in=['confirmed', 'delivered', 'completed']
    ).annotate(
        margin=ExpressionWrapper(
            (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah'),
            output_field=DecimalField()
        )
    ).aggregate(t=Sum('margin'))['t'] or 0)

    # Keuntungan dari POS
    keuntungan_pos = float(POSTransactionItem.objects.filter(
        transaction__status='paid'
    ).annotate(
        margin=ExpressionWrapper(
            (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah_konversi'),
            output_field=DecimalField()
        )
    ).aggregate(t=Sum('margin'))['t'] or 0)

    gross_profit = keuntungan_so + keuntungan_pos

    # Total revenue
    revenue_so = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed']
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data revenue_pos yang sesuai filter
    revenue_pos = float(POSTransaction.objects.filter(
        status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    total_revenue = revenue_so + revenue_pos

    # Total biaya
    total_biaya = float(TransaksiBiaya.objects.aggregate(t=Sum('jumlah'))['t'] or 0)
    net_profit = gross_profit - total_biaya

    margin_pct = round((gross_profit / total_revenue * 100), 1) if total_revenue > 0 else 0

    ringkasan = f"""Data Keuntungan:
- Total Revenue: Rp {total_revenue:,.0f}
- Keuntungan Kotor (Gross Profit): Rp {gross_profit:,.0f}
- Total Biaya Operasional: Rp {total_biaya:,.0f}
- Keuntungan Bersih (Net Profit): Rp {net_profit:,.0f}
- Profit Margin: {margin_pct}%
- Status: {'✅ UNTUNG' if net_profit > 0 else '❌ RUGI'}

Rincian Keuntungan:
- Dari Sales Order: Rp {keuntungan_so:,.0f}
- Dari POS: Rp {keuntungan_pos:,.0f}"""

    return {'intent': 'keuntungan', 'ringkasan': ringkasan}


def _gather_karyawan():
    """Data karyawan / HR."""
    from apps.hr.models import Karyawan, Departemen, Jabatan

    # Query database — ambil data total_karyawan yang sesuai filter
    total_karyawan = Karyawan.objects.filter(aktif=True).count()
    # Query database — ambil data total_non_aktif yang sesuai filter
    total_non_aktif = Karyawan.objects.filter(aktif=False).count()
    # Hitung jumlah data yang cocok
    total_departemen = Departemen.objects.count()
    # Hitung jumlah data yang cocok
    total_jabatan = Jabatan.objects.count()

    # Per departemen
    dept_info = Departemen.objects.annotate(
        jml=Count('karyawan', filter=Q(karyawan__aktif=True))
    ).order_by('-jml')[:5]
    dept_list = [f"- {d.nama}: {d.jml} karyawan" for d in dept_info]

    ringkasan = f"""Data Karyawan & HR:
- Total Karyawan Aktif: {total_karyawan}
- Total Karyawan Non-Aktif: {total_non_aktif}
- Total Departemen: {total_departemen}
- Total Jabatan: {total_jabatan}

Karyawan per Departemen:
{chr(10).join(dept_list) if dept_list else '- Belum ada departemen'}"""

    return {'intent': 'karyawan', 'ringkasan': ringkasan}


def _gather_pos(today, month_start):
    """Data transaksi POS."""
    from apps.pos.models import POSTransaction

    # Query database — ambil data total_pos yang sesuai filter
    total_pos = POSTransaction.objects.filter(status='paid').count()
    # Query database — ambil data pos_bulan_ini yang sesuai filter
    pos_bulan_ini = POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start
    ).count()
    # Query database — ambil data revenue_bulan_ini yang sesuai filter
    revenue_bulan_ini = float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data revenue_total yang sesuai filter
    revenue_total = float(POSTransaction.objects.filter(
        status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0)

    # Hari ini
    pos_hari_ini = POSTransaction.objects.filter(
        status='paid', tanggal__date=today
    ).count()
    # Query database — ambil data revenue_hari_ini yang sesuai filter
    revenue_hari_ini = float(POSTransaction.objects.filter(
        status='paid', tanggal__date=today
    ).aggregate(t=Sum('total_harga'))['t'] or 0)

    ringkasan = f"""Data Transaksi POS:
- Total Transaksi (semua): {total_pos}
- Transaksi Hari Ini: {pos_hari_ini} (Rp {revenue_hari_ini:,.0f})
- Transaksi Bulan Ini: {pos_bulan_ini} (Rp {revenue_bulan_ini:,.0f})
- Total Revenue POS: Rp {revenue_total:,.0f}"""

    return {'intent': 'pos', 'ringkasan': ringkasan}


def _gather_metode_pembayaran():
    """Data metode pembayaran."""
    from apps.pos.models import MetodePembayaran

    # Query database — ambil data methods yang sesuai filter
    methods = MetodePembayaran.objects.filter(aktif=True)
    method_info = []
    for m in methods:
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            saldo = float(m.saldo or 0)
            pendapatan = float(m.total_pendapatan or 0)
            pengeluaran = float(m.total_pengeluaran or 0)
            method_info.append(
                f"- {m.nama}: Saldo Rp {saldo:,.0f} | "
                f"Masuk Rp {pendapatan:,.0f} | Keluar Rp {pengeluaran:,.0f}"
            )
        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception:
            method_info.append(f"- {m.nama}: Data tidak tersedia")

    ringkasan = f"""Data Metode Pembayaran:
- Total Metode Aktif: {methods.count()}

Detail per Metode:
{chr(10).join(method_info) if method_info else '- Belum ada metode pembayaran'}"""

    return {'intent': 'metode_pembayaran', 'ringkasan': ringkasan}


def _gather_pelanggan(today, month_start):
    """Data pelanggan/customer — diperkaya dengan analisa."""
    from apps.penjualan.models import Customer, SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction

    # Query database — ambil data total yang sesuai filter
    total = Customer.objects.filter(aktif=True).count()
    # Hitung jumlah data yang cocok
    total_all = Customer.objects.count()

    # Top 5 customer berdasarkan total belanja (SO)
    top_customers = []
    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Query database — ambil data top_so yang sesuai filter
        top_so = SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=month_start, tanggal__date__lte=today
        ).values('customer__nama', 'customer__kode').annotate(
            total=Sum('total_harga'), jumlah_trx=Count('id')
        ).order_by('-total')[:5]

        for c in top_so:
            top_customers.append(
                f"- {c['customer__nama']} ({c['customer__kode']}): "
                f"Rp {float(c['total']):,.0f} ({c['jumlah_trx']} trx)"
            )
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)

    # Customer dengan transaksi POS terbanyak
    top_pos_customers = []
    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Query database — ambil data top_pos yang sesuai filter
        top_pos = POSTransaction.objects.filter(
            status='paid',
            customer__isnull=False,
            tanggal__date__gte=month_start, tanggal__date__lte=today
        ).values('customer__nama', 'customer__kode').annotate(
            total=Sum('total_harga'), jumlah_trx=Count('id')
        ).order_by('-total')[:5]

        for c in top_pos:
            top_pos_customers.append(
                f"- {c['customer__nama']} ({c['customer__kode']}): "
                f"Rp {float(c['total']):,.0f} ({c['jumlah_trx']} trx)"
            )
    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)

    ringkasan = f"""Data Pelanggan:
- Total Customer Aktif: {total}
- Total Customer (termasuk non-aktif): {total_all}

Top 5 Customer (Sales Order) Periode Ini:
{chr(10).join(top_customers) if top_customers else '- Belum ada data transaksi'}

Top 5 Customer (POS) Periode Ini:
{chr(10).join(top_pos_customers) if top_pos_customers else '- Belum ada data transaksi POS'}"""

    return {'intent': 'pelanggan', 'ringkasan': ringkasan}


def _gather_supplier():
    """Data supplier."""
    from apps.pembelian.models import Supplier

    # Query database — ambil data total yang sesuai filter
    total = Supplier.objects.filter(aktif=True).count()
    # Hitung jumlah data yang cocok
    total_all = Supplier.objects.count()

    ringkasan = f"""Data Supplier:
- Total Supplier Aktif: {total}
- Total Supplier (termasuk non-aktif): {total_all}"""

    return {'intent': 'supplier', 'ringkasan': ringkasan}


def _gather_bantuan():
    """Panduan fitur ERP secara detail termasuk fitur AI."""
    ringkasan = """Panduan Lengkap Sistem ERP SERPTECH:

═══════════════════════════════════════════
MODUL-MODUL ERP YANG TERSEDIA:
═══════════════════════════════════════════

1. Dashboard — Ringkasan data bisnis secara real-time: grafik penjualan, total keuntungan, produk terlaris, aktivitas terkini, dan statistik gudang & produk.

2. Produk — Kelola produk, kategori, dan satuan. Fitur: SKU otomatis, harga beli & jual, foto produk, stok minimum, import produk dari Excel, serta laporan produk lengkap.

3. Inventory — Manajemen gudang dan stok. Fitur: multi-gudang, transfer stok antar gudang, adjustment/opname stok, riwayat pergerakan stok, dan laporan stok real-time.

4. Pembelian — Kelola supplier dan Purchase Order (PO). Fitur: buat PO, terima barang parsial/penuh, riwayat pembelian per supplier, dan laporan pembelian.

5. Penjualan — Kelola customer dan Sales Order (SO). Fitur: buat SO, konfirmasi order, cek ketersediaan stok, riwayat penjualan per customer, dan laporan penjualan.

6. POS / Kasir — Transaksi kasir retail. Fitur: pencarian produk cepat, multi metode pembayaran (tunai, transfer, QRIS, e-wallet), cetak struk, invoice, dan rekapitulasi harian.

7. Biaya — Catat biaya operasional per kategori: listrik, gaji, sewa, transportasi, marketing, dll. Fitur: laporan biaya bulanan, tren pengeluaran, dan export Excel/PDF.

8. Laporan — Laporan lengkap: produk, stok, penjualan, pembelian, keuangan, laba rugi, arus kas, dan metode pembayaran. Fitur: filter periode, export Excel & PDF, grafik visual.

9. HR Management — Departemen, jabatan, data karyawan, absensi harian, dan penggajian otomatis. Fitur: slip gaji, rekap absensi, dan laporan penggajian.

10. Automasi — Notifikasi Telegram otomatis untuk stok rendah, pesanan baru, dan event penting lainnya.

11. Pengaturan — Profil perusahaan, logo, alamat, metode pembayaran, template cetak invoice/struk, dan backup database.

12. User & Access Management — Kelola user, role, dan permission. Fitur: multi-role, permission per modul dan sub-modul (view, create, edit, delete).

═══════════════════════════════════════════
FITUR AI ASSISTANT:
═══════════════════════════════════════════

A. BUSINESS INTELLIGENCE — Tanya apa saja tentang data bisnis:
   Contoh: "analisa penjualan", "status stok", "berapa keuntungan", "biaya operasional"
   - Analisa penjualan: omzet, top produk, growth bulan ini vs lalu
   - Status stok gudang: stok per gudang, produk habis/rendah
   - Keuntungan: revenue - HPP - biaya operasional
   - Biaya: total pengeluaran per kategori

B. ANALISA PELANGGAN — Contoh: "analisa pelanggan", "top customer"
   - Top 10 customer berdasarkan total belanja
   - Customer tidak aktif (30+ hari tanpa transaksi)
   - Frekuensi pembelian dan total belanja per customer

C. DETEKSI KEBOCORAN PROFIT — Contoh: "kebocoran profit", "kenapa profit turun?"
   - Produk dengan margin rendah (di bawah 15%)
   - Perbandingan biaya bulan ini vs bulan lalu
   - Produk slow moving (stok tinggi tapi tidak terjual)
   - Revenue comparison antar periode

D. FRAUD DETECTION — Contoh: "deteksi kecurangan", "transaksi mencurigakan"
   - Diskon tidak wajar (di atas 20%)
   - Transaksi dengan nilai sangat rendah (kemungkinan test/dummy)
   - Transaksi di luar jam operasional (sebelum 06:00 / setelah 22:00)
   - Sales Order yang sering dibatalkan
   - Skor risiko fraud per kategori

E. AI COPYWRITER — Contoh: "buat caption", "deskripsi produk", "broadcast WA"
   - Generate caption promosi untuk sosial media
   - Generate deskripsi produk untuk marketplace
   - Generate template broadcast WhatsApp
   - Generate campaign plan berbasis data produk

F. AI MARKETING GENERATOR — Contoh: "strategi marketing", "campaign plan"
   - Campaign plan bulanan dengan timeline
   - Strategi promosi: diskon, bundling, flash sale, loyalty
   - Content calendar mingguan untuk sosial media
   - Customer retention dan reactivation strategy
   - Product launch plan dan seasonal campaign

G. AI CAMPAIGN PLANNER — Contoh: "rencana campaign", "content calendar"
   - Campaign plan lengkap dengan timeline harian/mingguan
   - Content calendar untuk semua platform
   - Budget allocation dan ROI projection
   - A/B testing strategy

H. 90 DAYS BUSINESS PLAN — Contoh: "plan 3 bulan", "business plan"
   - Roadmap bisnis 90 hari dengan milestone
   - Target revenue, customer, dan produk per bulan
   - Growth strategy dengan action plan detail
   - KPI tracking dan evaluation plan

I. AI MULTI-BRANCH ANALYZER — Contoh: "bandingkan cabang", "performa cabang"
   - Perbandingan performa antar gudang/cabang
   - Ranking cabang berdasarkan revenue, transaksi, stok
   - Rekomendasi optimasi per cabang
   - Distribusi produk antar cabang

J. AI CONTENT GENERATOR — Contoh: "caption ig", "script tiktok", "deskripsi shopee"
   - Generate caption Instagram dengan hashtag
   - Generate script TikTok (hook, isi, CTA)
   - Generate deskripsi produk Shopee/Tokopedia
   - Generate broadcast WhatsApp promosi

K. KONTEKS WAKTU CERDAS — AI memahami permintaan waktu:
   - "Penjualan hari ini" → Data hari ini
   - "Omzet minggu ini" → Data Senin-Minggu
   - "Revenue bulan lalu" → Data bulan sebelumnya
   - "Biaya 3 bulan terakhir" → Data 90 hari ke belakang

L. QUICK ACTION LINKS — Setiap jawaban berisi link langsung:
   - Link navigasi langsung ke halaman ERP terkait
   - Contoh: "Lihat Daftar Produk" → langsung ke /produk/list/

M. LAPORAN TERJADWAL — Contoh: "laporan terjadwal", "scheduled report"
   - Cara setup laporan otomatis setiap Senin pagi
   - Preview data laporan mingguan
   - Konfigurasi via Windows Task Scheduler atau crontab

N. ANALISA BISNIS LANJUTAN:
   - "Laporan meeting" → Data lengkap untuk rapat manajemen
   - "Executive summary" → Ringkasan eksekutif kuartal
   - "SWOT analysis" → Kekuatan, kelemahan, peluang, ancaman
   - "Stok kritis" → Produk stok habis/hampir habis
   - "Margin produk" → Margin profit per produk

O. AI DASHBOARD (/ai/dashboard/):
   - Skor Kesehatan Bisnis (0-100) dengan indikator
   - Prediksi revenue bulan depan
   - Deteksi anomali otomatis
   - Grafik tren revenue 6 bulan
   - Distribusi stok (habis/rendah/normal)
   - Insight dan rekomendasi otomatis

P. MODUL KEUANGAN & AKUNTANSI:
   - "Kas bank" → Saldo semua akun kas/bank, arus kas masuk/keluar
   - "Akuntansi" / "Neraca" / "Laba rugi" → Data jurnal, neraca, laba rugi
   - "Piutang" / "Hutang" → Status piutang/hutang, overdue, aging
   - "Aset tetap" / "Penyusutan" → Daftar aset, nilai buku, akumulasi
   - "Pajak" / "PPN" → Faktur pajak, rekap PPN keluaran/masukan, setor

TIPS PENGGUNAAN:
- Ketik dengan bahasa alami, AI akan memahami maksud Anda
- Gunakan kata kunci seperti: penjualan, stok, keuntungan, biaya, customer
- AI mendukung Bahasa Indonesia dan Inggris
- Riwayat chat tersimpan otomatis dan bisa di-download sebagai file TXT"""

    return {'intent': 'bantuan', 'ringkasan': ringkasan}


def _gather_umum(today, month_start):
    """Ringkasan umum semua modul."""
    from apps.produk.models import Produk, Gudang
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder, Customer
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.pembelian.models import PurchaseOrder, Supplier
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.hr.models import Karyawan

    ringkasan = f"""Ringkasan Umum Sistem ERP ({today.strftime('%d %B %Y')}):
- Total Produk Aktif: {Produk.objects.filter(aktif=True).count()}
- Total Gudang: {Gudang.objects.filter(aktif=True).count()}
- Total Customer: {Customer.objects.filter(aktif=True).count()}
- Total Supplier: {Supplier.objects.filter(aktif=True).count()}
- Total Karyawan: {Karyawan.objects.filter(aktif=True).count()}
- Sales Order: {SalesOrder.objects.exclude(status='cancelled').count()}
- Transaksi POS: {POSTransaction.objects.filter(status='paid').count()}
- Purchase Order: {PurchaseOrder.objects.exclude(status='cancelled').count()}
- Total Biaya: Rp {float(TransaksiBiaya.objects.aggregate(t=Sum('jumlah'))['t'] or 0):,.0f}

Sistem ini adalah ERP SERPTECH yang mengelola seluruh operasi bisnis: produk, inventory, penjualan, pembelian, biaya, HR, dan laporan keuangan."""

    return {'intent': 'umum', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# ADVANCED DATA GATHERERS — Business Intelligence
# ═══════════════════════════════════════════════════════════════

def _gather_laporan_meeting(today, month_start):
    """Data lengkap untuk laporan meeting manajemen."""
    from apps.penjualan.models import SalesOrder, SalesOrderItem
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.pembelian.models import PurchaseOrder
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.produk.models import Produk, Stok, Gudang
    # Import dari modul internal proyek
    from apps.hr.models import Karyawan

    # Revenue
    so_rev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=month_start, tanggal__date__lte=today
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data pos_rev yang sesuai filter
    pos_rev = float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start, tanggal__date__lte=today
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    total_rev = so_rev + pos_rev
    # Query database — ambil data total_trx yang sesuai filter
    total_trx = SalesOrder.objects.filter(
        tanggal__date__gte=month_start, status__in=['confirmed', 'delivered', 'completed']
    ).count() + POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start
    ).count()

    # Bulan lalu
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    # Query database — ambil data prev_rev yang sesuai filter
    prev_rev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    growth = round(((total_rev - prev_rev) / prev_rev * 100), 1) if prev_rev > 0 else 0

    # Biaya
    biaya = float(TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).aggregate(t=Sum('jumlah'))['t'] or 0)

    # Pembelian
    po_val = float(PurchaseOrder.objects.filter(
        tanggal__date__gte=month_start, status__in=['approved', 'received']
    ).aggregate(t=Sum('total_harga'))['t'] or 0)

    # Stok
    total_stok = float(Stok.objects.aggregate(t=Sum('jumlah'))['t'] or 0)
    # Query database — ambil data produk_habis yang sesuai filter
    produk_habis = Produk.objects.filter(aktif=True).exclude(
        id__in=Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True)
    ).count()

    # Top 5 produk
    top_items = SalesOrderItem.objects.filter(
        sales_order__status__in=['confirmed', 'delivered', 'completed'],
        sales_order__tanggal__date__gte=month_start
    ).values('produk__nama').annotate(
        rev=Sum('subtotal'), qty=Sum('jumlah')
    ).order_by('-rev')[:5]
    top_list = [f"- {i['produk__nama']}: {int(i['qty'])} unit (Rp {float(i['rev']):,.0f})" for i in top_items]

    ringkasan = f"""LAPORAN MEETING MANAJEMEN — {month_start.strftime('%B %Y')}

📊 RINGKASAN PENJUALAN:
- Total Omzet: Rp {total_rev:,.0f}
- Omzet Bulan Lalu: Rp {prev_rev:,.0f}
- Growth: {'+' if growth >= 0 else ''}{growth}%
- Total Transaksi: {total_trx}

💰 CASHFLOW:
- Pendapatan: Rp {total_rev:,.0f}
- Biaya Operasional: Rp {biaya:,.0f}
- Pembelian (PO): Rp {po_val:,.0f}
- Net Cashflow: Rp {total_rev - biaya - po_val:,.0f}

📦 INVENTORY:
- Total Stok: {total_stok:,.0f} unit
- Produk Stok Habis: {produk_habis}
- Total Karyawan: {Karyawan.objects.filter(aktif=True).count()}

🏆 TOP 5 PRODUK:
{chr(10).join(top_list) if top_list else '- Belum ada data'}

INSTRUKSI: Buatkan laporan meeting profesional dengan format narasi, tabel ringkasan, analisa performa, area masalah, dan 3-5 rekomendasi strategi."""

    return {'intent': 'laporan_meeting', 'ringkasan': ringkasan}


def _gather_executive_summary(today, month_start):
    """Executive summary tingkat kuartal."""
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.produk.models import Produk, Stok
    # Import dari modul internal proyek
    from apps.pembelian.models import PurchaseOrder

    # Data 3 bulan terakhir
    months_data = []
    for i in range(3):
        m_start = (month_start - timedelta(days=30*i)).replace(day=1)
        m_end = (m_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if m_end > today:
            m_end = today
        # Query database — ambil data rev yang sesuai filter
        rev = float(SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
            status='paid', tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        # Query database — ambil data biaya yang sesuai filter
        biaya = float(TransaksiBiaya.objects.filter(
            tanggal__gte=m_start, tanggal__lte=m_end
        ).aggregate(t=Sum('jumlah'))['t'] or 0)
        months_data.append({
            'bulan': m_start.strftime('%B %Y'),
            'revenue': rev,
            'biaya': biaya,
            'profit': rev - biaya,
        })

    total_rev = sum(m['revenue'] for m in months_data)
    total_biaya = sum(m['biaya'] for m in months_data)
    total_profit = total_rev - total_biaya

    monthly_lines = []
    for m in months_data:
        monthly_lines.append(
            f"- {m['bulan']}: Revenue Rp {m['revenue']:,.0f} | "
            f"Biaya Rp {m['biaya']:,.0f} | Profit Rp {m['profit']:,.0f}"
        )

    ringkasan = f"""EXECUTIVE SUMMARY — 3 BULAN TERAKHIR

📈 TOTAL PERFORMANCE:
- Total Revenue: Rp {total_rev:,.0f}
- Total Biaya: Rp {total_biaya:,.0f}
- Total Profit: Rp {total_profit:,.0f}
- Profit Margin: {round(total_profit/total_rev*100,1) if total_rev > 0 else 0}%
- Total Produk Aktif: {Produk.objects.filter(aktif=True).count()}
- Total Stok: {float(Stok.objects.aggregate(t=Sum('jumlah'))['t'] or 0):,.0f} unit

📊 DATA PER BULAN:
{chr(10).join(monthly_lines)}

INSTRUKSI: Buatkan executive summary profesional dengan tabel perbandingan bulanan, growth rate, area risiko, dan 3-5 saran perbaikan strategis."""

    return {'intent': 'executive_summary', 'ringkasan': ringkasan}


def _gather_swot(today, month_start):
    """Auto SWOT analysis dari data ERP."""
    from apps.penjualan.models import SalesOrder, SalesOrderItem
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction, POSTransactionItem
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.produk.models import Produk, Stok

    # Revenue & growth
    rev_now = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=month_start, tanggal__date__lte=today
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start, tanggal__date__lte=today
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    # Query database — ambil data rev_prev yang sesuai filter
    rev_prev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    growth = round(((rev_now - rev_prev) / rev_prev * 100), 1) if rev_prev > 0 else 0

    # Margin
    from django.db.models import F, ExpressionWrapper, DecimalField
    # Query database — ambil data margins yang sesuai filter
    margins = POSTransactionItem.objects.filter(
        transaction__status='paid'
    ).annotate(
        margin=ExpressionWrapper(
            (F('harga_satuan') - F('produk__harga_beli')) * F('jumlah_konversi'),
            output_field=DecimalField()
        )
    ).aggregate(t=Sum('margin'))
    gross_margin = float(margins['t'] or 0)

    # Query database — ambil data biaya yang sesuai filter
    biaya = float(TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).aggregate(t=Sum('jumlah'))['t'] or 0)

    # Stok kritis
    stok_habis = Produk.objects.filter(aktif=True).exclude(
        id__in=Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True)
    ).count()

    ringkasan = f"""DATA UNTUK ANALISA SWOT:

📊 FAKTA BISNIS:
- Revenue bulan ini: Rp {rev_now:,.0f}
- Revenue bulan lalu: Rp {rev_prev:,.0f}
- Growth: {'+' if growth >= 0 else ''}{growth}%
- Gross Margin: Rp {gross_margin:,.0f}
- Biaya bulan ini: Rp {biaya:,.0f}
- Net Profit: Rp {rev_now - biaya:,.0f}
- Produk aktif: {Produk.objects.filter(aktif=True).count()}
- Produk stok habis: {stok_habis}
- Total stok: {float(Stok.objects.aggregate(t=Sum('jumlah'))['t'] or 0):,.0f}

INSTRUKSI: Buatkan analisa SWOT lengkap (Strengths, Weaknesses, Opportunities, Threats) dalam format tabel berdasarkan data di atas. Setiap kategori minimal 2-3 poin."""

    return {'intent': 'swot', 'ringkasan': ringkasan}


def _gather_rencana_aksi(today, month_start):
    """Rencana aksi berdasarkan data aktual."""
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.produk.models import Produk, Stok

    # Query database — ambil data rev yang sesuai filter
    rev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=month_start
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data biaya yang sesuai filter
    biaya = float(TransaksiBiaya.objects.filter(
        tanggal__gte=month_start
    ).aggregate(t=Sum('jumlah'))['t'] or 0)
    # Query database — ambil data stok_habis yang sesuai filter
    stok_habis = Produk.objects.filter(aktif=True).exclude(
        id__in=Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True)
    ).count()
    # Query database — ambil data so_count yang sesuai filter
    so_count = SalesOrder.objects.filter(
        status='draft', tanggal__date__gte=month_start
    ).count()

    ringkasan = f"""DATA UNTUK RENCANA AKSI:
- Omzet bulan ini: Rp {rev:,.0f}
- Biaya operasional: Rp {biaya:,.0f}
- Profit: Rp {rev - biaya:,.0f}
- Produk stok habis: {stok_habis}
- SO masih draft: {so_count}
- Total produk aktif: {Produk.objects.filter(aktif=True).count()}

INSTRUKSI: Buatkan rencana aksi detail (action plan) untuk meningkatkan performa bisnis. Gunakan tabel prioritas (Tinggi/Sedang/Rendah) dengan kolom: Aksi, Prioritas, Target, Deadline."""

    return {'intent': 'rencana_aksi', 'ringkasan': ringkasan}


def _gather_forecasting(today, month_start):
    """Forecasting/prediksi berdasarkan tren."""
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.produk.models import Stok

    # Data 4 bulan terakhir untuk tren
    trends = []
    for i in range(4):
        m_start = (month_start - timedelta(days=30*i)).replace(day=1)
        m_end = (m_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if m_end > today:
            m_end = today
        # Query database — ambil data rev yang sesuai filter
        rev = float(SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
            status='paid', tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        # Query database — ambil data trx yang sesuai filter
        trx = SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).count() + POSTransaction.objects.filter(
            status='paid', tanggal__date__gte=m_start, tanggal__date__lte=m_end
        ).count()
        trends.append({'bulan': m_start.strftime('%B %Y'), 'revenue': rev, 'trx': trx})

    trend_lines = [f"- {t['bulan']}: Rp {t['revenue']:,.0f} ({t['trx']} trx)" for t in trends]

    ringkasan = f"""DATA TREN 4 BULAN TERAKHIR (untuk forecasting):

📈 TREN REVENUE:
{chr(10).join(trend_lines)}

📦 STOK SAAT INI: {float(Stok.objects.aggregate(t=Sum('jumlah'))['t'] or 0):,.0f} unit

INSTRUKSI: Berdasarkan data tren di atas, buatkan prediksi/forecasting untuk 30 hari ke depan dalam tabel. Sertakan: prediksi revenue, prediksi kebutuhan stok, dan prediksi cashflow. Berikan confidence level (tinggi/sedang/rendah)."""

    return {'intent': 'forecasting', 'ringkasan': ringkasan}


def _gather_risiko(today, month_start):
    """Analisa risiko bisnis dari data ERP."""
    from apps.produk.models import Produk, Stok
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction, POSTransactionItem
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya

    # Stok habis
    produk_ids_stok = Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True)
    # Query database — ambil data stok_habis yang sesuai filter
    stok_habis = Produk.objects.filter(aktif=True).exclude(id__in=produk_ids_stok).count()

    # Overstock (stok > 100 unit per produk)
    overstock = Stok.objects.filter(jumlah__gt=100).values('produk__nama').annotate(
        total=Sum('jumlah')
    ).order_by('-total')[:5]
    over_list = [f"- {o['produk__nama']}: {float(o['total']):,.0f} unit" for o in overstock]

    # Produk margin negatif
    from django.db.models import F, ExpressionWrapper, DecimalField
    # Query database — ambil data margin_neg yang sesuai filter
    margin_neg = Produk.objects.filter(
        aktif=True, harga_jual__lt=F('harga_beli')
    ).count()

    # Revenue trend (turun?)
    rev_now = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=month_start
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=month_start
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    # Query database — ambil data rev_prev yang sesuai filter
    rev_prev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0) + float(POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=prev_start, tanggal__date__lte=prev_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)

    # Query database — ambil data biaya yang sesuai filter
    biaya = float(TransaksiBiaya.objects.filter(
        tanggal__gte=month_start
    ).aggregate(t=Sum('jumlah'))['t'] or 0)

    ringkasan = f"""ANALISA RISIKO BISNIS:

⚠️ STOK:
- Produk stok habis: {stok_habis}
- Produk overstock (>100 unit):
{chr(10).join(over_list) if over_list else '- Tidak ada'}

❌ MARGIN:
- Produk margin negatif (harga jual < harga beli): {margin_neg}

📉 REVENUE:
- Bulan ini: Rp {rev_now:,.0f}
- Bulan lalu: Rp {rev_prev:,.0f}
- Perubahan: {'TURUN' if rev_now < rev_prev else 'NAIK'} {abs(round(((rev_now-rev_prev)/rev_prev*100),1)) if rev_prev > 0 else 0}%

💸 BIAYA:
- Total biaya bulan ini: Rp {biaya:,.0f}
- Rasio biaya/revenue: {round(biaya/rev_now*100,1) if rev_now > 0 else 0}%

INSTRUKSI: Analisa setiap area risiko, beri level risiko (🔴Tinggi/🟡Sedang/🟢Rendah) dalam tabel, dan berikan rekomendasi mitigasi untuk setiap risiko."""

    return {'intent': 'risiko', 'ringkasan': ringkasan}


def _gather_perbandingan(today, month_start):
    """Perbandingan bulan ini vs bulan lalu."""
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya
    # Import dari modul internal proyek
    from apps.pembelian.models import PurchaseOrder

    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    # Fungsi get_period
    def get_period(start, end):
        # Query database — ambil data so_rev yang sesuai filter
        so_rev = float(SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=start, tanggal__date__lte=end
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        # Query database — ambil data pos_rev yang sesuai filter
        pos_rev = float(POSTransaction.objects.filter(
            status='paid', tanggal__date__gte=start, tanggal__date__lte=end
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        # Query database — ambil data so_c yang sesuai filter
        so_c = SalesOrder.objects.filter(
            status__in=['confirmed', 'delivered', 'completed'],
            tanggal__date__gte=start, tanggal__date__lte=end
        ).count()
        # Query database — ambil data pos_c yang sesuai filter
        pos_c = POSTransaction.objects.filter(
            status='paid', tanggal__date__gte=start, tanggal__date__lte=end
        ).count()
        # Query database — ambil data biaya yang sesuai filter
        biaya = float(TransaksiBiaya.objects.filter(
            tanggal__gte=start, tanggal__lte=end
        ).aggregate(t=Sum('jumlah'))['t'] or 0)
        # Query database — ambil data po_val yang sesuai filter
        po_val = float(PurchaseOrder.objects.filter(
            tanggal__date__gte=start, tanggal__date__lte=end,
            status__in=['approved', 'received']
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        return {
            'revenue': so_rev + pos_rev, 'trx': so_c + pos_c,
            'biaya': biaya, 'po': po_val,
            'profit': so_rev + pos_rev - biaya,
        }

    now_data = get_period(month_start, today)
    prev_data = get_period(prev_start, prev_end)

    # Fungsi delta
    def delta(curr, prev):
        if prev > 0:
            return f"{'+' if curr >= prev else ''}{round((curr-prev)/prev*100,1)}%"
        return 'N/A'

    ringkasan = f"""PERBANDINGAN BULAN INI vs BULAN LALU:

| Metrik | {prev_start.strftime('%B %Y')} | {month_start.strftime('%B %Y')} | Perubahan |
|--------|------------|------------|-----------|
| Revenue | Rp {prev_data['revenue']:,.0f} | Rp {now_data['revenue']:,.0f} | {delta(now_data['revenue'], prev_data['revenue'])} |
| Transaksi | {prev_data['trx']} | {now_data['trx']} | {delta(now_data['trx'], prev_data['trx'])} |
| Biaya | Rp {prev_data['biaya']:,.0f} | Rp {now_data['biaya']:,.0f} | {delta(now_data['biaya'], prev_data['biaya'])} |
| Pembelian | Rp {prev_data['po']:,.0f} | Rp {now_data['po']:,.0f} | {delta(now_data['po'], prev_data['po'])} |
| Profit | Rp {prev_data['profit']:,.0f} | Rp {now_data['profit']:,.0f} | {delta(now_data['profit'], prev_data['profit'])} |

INSTRUKSI: Analisa perbandingan di atas, jelaskan perubahan signifikan, identifikasi area yang membaik dan yang menurun, dan berikan 3 rekomendasi untuk bulan depan."""

    return {'intent': 'perbandingan', 'ringkasan': ringkasan}


def _gather_stok_kritis():
    """Data stok kritis yang perlu segera direstok."""
    from apps.produk.models import Produk, Stok, Gudang

    # Produk tanpa stok
    produk_ids_stok = Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True)
    # Query database — ambil data habis yang sesuai filter
    habis = Produk.objects.filter(aktif=True).exclude(id__in=produk_ids_stok)
    habis_list = [f"- {p.nama} (SKU: {p.sku or '-'})" for p in habis[:10]]

    # Produk stok rendah (< 10 unit total)
    low_stock = Stok.objects.values('produk__nama', 'produk__sku').annotate(
        total=Sum('jumlah')
    ).filter(total__gt=0, total__lt=10).order_by('total')[:10]
    low_list = [f"- {s['produk__nama']}: {int(s['total'])} unit" for s in low_stock]

    # Ringkasan per gudang
    gudangs = Gudang.objects.filter(aktif=True)
    gudang_info = []
    for g in gudangs:
        # Query database — ambil data total yang sesuai filter
        total = float(Stok.objects.filter(gudang=g).aggregate(t=Sum('jumlah'))['t'] or 0)
        # Query database — ambil data kritis yang sesuai filter
        kritis = Stok.objects.filter(gudang=g, jumlah__gt=0, jumlah__lt=5).count()
        gudang_info.append(f"- {g.nama}: {total:,.0f} unit (Kritis: {kritis} produk)")

    ringkasan = f"""STATUS STOK KRITIS:

🔴 STOK HABIS ({habis.count()} produk):
{chr(10).join(habis_list) if habis_list else '- Tidak ada'}

🟡 STOK RENDAH (<10 unit):
{chr(10).join(low_list) if low_list else '- Tidak ada'}

📦 PER GUDANG:
{chr(10).join(gudang_info) if gudang_info else '- Tidak ada gudang'}

INSTRUKSI: Buatkan tabel rekomendasi restock dengan kolom: Produk, Stok Saat Ini, Rekomendasi Beli, Prioritas (🔴/🟡/🟢), Gudang Tujuan."""

    return {'intent': 'stok_kritis', 'ringkasan': ringkasan}


def _gather_margin_produk():
    """Analisa margin per produk."""
    from apps.produk.models import Produk
    # Import dari framework Django
    from django.db.models import F, ExpressionWrapper, DecimalField

    # Semua produk aktif dengan margin
    produk_qs = Produk.objects.filter(aktif=True, harga_jual__gt=0).annotate(
        margin_rp=ExpressionWrapper(F('harga_jual') - F('harga_beli'), output_field=DecimalField()),
        margin_pct=ExpressionWrapper(
            (F('harga_jual') - F('harga_beli')) * 100 / F('harga_jual'),
            output_field=DecimalField()
        ),
    )

    # Top 5 margin tertinggi
    top_margin = produk_qs.order_by('-margin_pct')[:5]
    top_list = [
        f"- {p.nama}: Beli Rp {float(p.harga_beli):,.0f} | Jual Rp {float(p.harga_jual):,.0f} | Margin {float(p.margin_pct):.1f}%"
        for p in top_margin
    ]

    # Bottom 5 margin terendah
    low_margin = produk_qs.order_by('margin_pct')[:5]
    low_list = [
        f"- {p.nama}: Beli Rp {float(p.harga_beli):,.0f} | Jual Rp {float(p.harga_jual):,.0f} | Margin {float(p.margin_pct):.1f}%"
        for p in low_margin
    ]

    # Margin negatif
    negatif = produk_qs.filter(harga_jual__lt=F('harga_beli'))
    neg_list = [f"- {p.nama}: RUGI Rp {float(p.margin_rp):,.0f} per unit" for p in negatif[:5]]

    # Rata-rata
    avg_margin = produk_qs.aggregate(avg=Avg('margin_pct'))
    avg_pct = float(avg_margin['avg'] or 0)

    ringkasan = f"""ANALISA MARGIN PRODUK:

📊 RINGKASAN:
- Total Produk Aktif: {produk_qs.count()}
- Rata-rata Margin: {avg_pct:.1f}%
- Produk Margin Negatif: {negatif.count()}

🏆 TOP 5 MARGIN TERTINGGI:
{chr(10).join(top_list) if top_list else '- Tidak ada data'}

⚠️ TOP 5 MARGIN TERENDAH:
{chr(10).join(low_list) if low_list else '- Tidak ada data'}

❌ PRODUK MARGIN NEGATIF (RUGI):
{chr(10).join(neg_list) if neg_list else '- Tidak ada'}

INSTRUKSI: Buatkan tabel analisa margin lengkap, identifikasi produk mana yang perlu dinaikkan harga atau dihentikan, dan berikan rekomendasi harga."""

    return {'intent': 'margin_produk', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# ANALISA PELANGGAN — Customer Analysis
# ═══════════════════════════════════════════════════════════════

def _gather_analisa_pelanggan(today, month_start):
    """Analisa pelanggan mendalam: top customer, customer tidak aktif, frekuensi beli."""
    from apps.penjualan.models import Customer, SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction

    # Query database — ambil data total_customer yang sesuai filter
    total_customer = Customer.objects.filter(aktif=True).count()

    # ─── Top 10 Customer berdasarkan Total Belanja (SO + POS) ───
    top_so = list(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
    ).values('customer__nama', 'customer__kode', 'customer_id').annotate(
        total=Sum('total_harga'), jumlah_trx=Count('id')
    ).order_by('-total')[:10])

    top_so_lines = []
    for i, c in enumerate(top_so, 1):
        top_so_lines.append(
            f"{i}. {c['customer__nama']} ({c['customer__kode']}): "
            f"Rp {float(c['total']):,.0f} — {c['jumlah_trx']} transaksi"
        )

    # ─── Customer Tidak Aktif (tidak ada transaksi 30+ hari) ───
    from datetime import datetime
    cutoff = today - timedelta(days=30)

    # Customer yang punya SO sebelum cutoff tapi TIDAK ada SO setelah cutoff
    active_customer_ids_so = set(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=cutoff,
    ).values_list('customer_id', flat=True))

    # Query database — ambil data active_customer_ids_pos yang sesuai filter
    active_customer_ids_pos = set(POSTransaction.objects.filter(
        status='paid',
        customer__isnull=False,
        tanggal__date__gte=cutoff,
    ).values_list('customer_id', flat=True))

    active_ids = active_customer_ids_so | active_customer_ids_pos

    # Customer yang pernah transaksi tapi sudah tidak aktif 30+ hari
    all_customer_ids_ever = set(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
    # Query database — ambil data ).values_list('customer_id', flat yang sesuai filter
    ).values_list('customer_id', flat=True)) | set(POSTransaction.objects.filter(
        status='paid', customer__isnull=False,
    ).values_list('customer_id', flat=True))

    inactive_ids = all_customer_ids_ever - active_ids
    # Query database — ambil data inactive_customers yang sesuai filter
    inactive_customers = Customer.objects.filter(id__in=inactive_ids, aktif=True)[:10]
    inactive_lines = [f"- {c.nama} ({c.kode})" for c in inactive_customers]

    # ─── Frekuensi Pembelian Rata-rata ───
    from django.db.models import Max, Min
    # Query database — ambil data so_freq yang sesuai filter
    so_freq = SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
    ).values('customer__nama').annotate(
        total_trx=Count('id'),
        total_belanja=Sum('total_harga'),
        first_trx=Min('tanggal'),
        last_trx=Max('tanggal'),
    ).order_by('-total_trx')[:10]

    freq_lines = []
    for c in so_freq:
        rata2 = float(c['total_belanja'] or 0) / max(c['total_trx'], 1)
        freq_lines.append(
            f"- {c['customer__nama']}: {c['total_trx']} trx, "
            f"Rp {float(c['total_belanja']):,.0f} total, "
            f"Avg Rp {rata2:,.0f}/trx"
        )

    ringkasan = f"""ANALISA PELANGGAN MENDALAM:

📊 RINGKASAN:
- Total Customer Aktif: {total_customer}
- Customer Pernah Transaksi: {len(all_customer_ids_ever)}
- Customer Aktif (30 hari terakhir): {len(active_ids)}
- Customer Tidak Aktif (30+ hari): {len(inactive_ids)}

🏆 TOP 10 CUSTOMER (Total Belanja Sepanjang Waktu):
{chr(10).join(top_so_lines) if top_so_lines else '- Belum ada data'}

😴 CUSTOMER TIDAK AKTIF (30+ hari tanpa transaksi):
{chr(10).join(inactive_lines) if inactive_lines else '- Semua customer masih aktif'}

📈 FREKUENSI PEMBELIAN (Top 10):
{chr(10).join(freq_lines) if freq_lines else '- Belum ada data'}

INSTRUKSI: Buatkan analisa pelanggan dalam format tabel dengan kolom: Ranking, Nama Customer, Total Belanja, Jumlah Transaksi, Status, Rekomendasi. Berikan juga strategi untuk mengaktifkan kembali customer yang tidak aktif dan meningkatkan loyalitas customer terbaik."""

    return {'intent': 'analisa_pelanggan', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# LAPORAN TERJADWAL — Scheduled Reports Info
# ═══════════════════════════════════════════════════════════════

def _gather_laporan_terjadwal():
    """Info tentang fitur laporan terjadwal."""
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.produk.models import Produk, Stok

    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = today

    # Data minggu ini untuk preview
    so_rev = float(SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=week_start, tanggal__date__lte=week_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data pos_rev yang sesuai filter
    pos_rev = float(POSTransaction.objects.filter(
        status='paid',
        tanggal__date__gte=week_start, tanggal__date__lte=week_end
    ).aggregate(t=Sum('total_harga'))['t'] or 0)
    # Query database — ambil data total_trx yang sesuai filter
    total_trx = SalesOrder.objects.filter(
        status__in=['confirmed', 'delivered', 'completed'],
        tanggal__date__gte=week_start
    ).count() + POSTransaction.objects.filter(
        status='paid', tanggal__date__gte=week_start
    ).count()

    # Query database — ambil data stok_habis yang sesuai filter
    stok_habis = Produk.objects.filter(aktif=True).exclude(
        id__in=list(Stok.objects.filter(jumlah__gt=0).values_list('produk_id', flat=True))
    ).count()

    ringkasan = f"""FITUR LAPORAN TERJADWAL (SCHEDULED REPORTS):

📋 STATUS FITUR:
Laporan terjadwal dapat dikirim otomatis setiap Senin pagi melalui management command Django.

🔧 CARA SETUP:
1. Gunakan management command: python manage.py send_weekly_report
2. Jadwalkan via Windows Task Scheduler atau crontab (Linux):
   - Windows: Task Scheduler → Action: python manage.py send_weekly_report
   - Linux: crontab -e → 0 7 * * 1 cd /path/to/project && python manage.py send_weekly_report
3. Laporan akan digenerate otomatis dari data ERP

📊 PREVIEW LAPORAN MINGGU INI ({week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m/%Y')}):
- Revenue Minggu Ini: Rp {so_rev + pos_rev:,.0f}
- Total Transaksi: {total_trx}
- Sales Order Revenue: Rp {so_rev:,.0f}
- POS Revenue: Rp {pos_rev:,.0f}
- Produk Stok Habis: {stok_habis}

📧 FORMAT LAPORAN:
Setiap Senin pagi, sistem akan menggenerate laporan yang berisi:
- Ringkasan revenue minggu sebelumnya
- Top 5 produk terlaris
- Status stok kritis
- Perbandingan dengan minggu sebelumnya
- Rekomendasi aksi untuk minggu depan

INSTRUKSI: Jelaskan fitur laporan terjadwal ini kepada user dengan bahasa yang mudah dipahami. Sertakan preview data minggu ini dan cara setup-nya."""

    return {'intent': 'laporan_terjadwal', 'ringkasan': ringkasan}


def _gather_kebocoran_profit(today, month_start):
    """Deteksi kebocoran profit: produk low margin, biaya naik, slow moving."""
    from apps.produk.models import Produk
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.biaya.models import TransaksiBiaya

    # 1. Produk dengan margin rendah (harga_jual - harga_beli) / harga_jual
    produk_low_margin = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True, harga_jual__gt=0):
        margin = ((p.harga_jual - p.harga_beli) / p.harga_jual * 100) if p.harga_jual > 0 else 0
        if margin < 15:  # Margin di bawah 15%
            produk_low_margin.append({
                'nama': p.nama,
                'margin': round(margin, 1),
                'harga_beli': float(p.harga_beli),
                'harga_jual': float(p.harga_jual),
            })
    produk_low_margin.sort(key=lambda x: x['margin'])

    # 2. Perbandingan biaya bulan ini vs bulan lalu
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    # Query database — ambil data biaya_bulan_ini yang sesuai filter
    biaya_bulan_ini = TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).aggregate(total=Sum('jumlah'))['total'] or 0

    # Query database — ambil data biaya_bulan_lalu yang sesuai filter
    biaya_bulan_lalu = TransaksiBiaya.objects.filter(
        tanggal__gte=prev_month_start, tanggal__lte=prev_month_end
    ).aggregate(total=Sum('jumlah'))['total'] or 0

    biaya_change = 0
    if biaya_bulan_lalu > 0:
        biaya_change = round((float(biaya_bulan_ini) - float(biaya_bulan_lalu)) / float(biaya_bulan_lalu) * 100, 1)

    # 3. Produk slow moving (ada stok tapi tidak terjual 30 hari terakhir)
    thirty_days_ago = today - timedelta(days=30)
    sold_product_ids = set(
        SalesOrder.objects.filter(
            tanggal__date__gte=thirty_days_ago
        ).values_list('items__produk_id', flat=True).distinct()
    )

    slow_moving = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True, stok__gt=5):
        if p.id not in sold_product_ids:
            slow_moving.append({'nama': p.nama, 'stok': p.stok})
    slow_moving.sort(key=lambda x: x['stok'], reverse=True)

    # 4. Revenue comparison
    from apps.pos.models import POSTransaction
    # Query database — ambil data so_rev_now yang sesuai filter
    so_rev_now = SalesOrder.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today,
        status__in=['confirmed', 'delivered', 'completed']
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    # Query database — ambil data pos_rev_now yang sesuai filter
    pos_rev_now = POSTransaction.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today, status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    rev_now = float(so_rev_now) + float(pos_rev_now)

    # Query database — ambil data so_rev_prev yang sesuai filter
    so_rev_prev = SalesOrder.objects.filter(
        tanggal__date__gte=prev_month_start, tanggal__date__lte=prev_month_end,
        status__in=['confirmed', 'delivered', 'completed']
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    # Query database — ambil data pos_rev_prev yang sesuai filter
    pos_rev_prev = POSTransaction.objects.filter(
        tanggal__date__gte=prev_month_start, tanggal__date__lte=prev_month_end, status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    rev_prev = float(so_rev_prev) + float(pos_rev_prev)

    rev_change = 0
    if rev_prev > 0:
        rev_change = round((rev_now - rev_prev) / rev_prev * 100, 1)

    low_margin_text = '\n'.join([f"  - {p['nama']}: margin {p['margin']}% (beli Rp {p['harga_beli']:,.0f}, jual Rp {p['harga_jual']:,.0f})" for p in produk_low_margin[:10]])
    slow_text = '\n'.join([f"  - {p['nama']}: stok {p['stok']} (tidak terjual 30 hari)" for p in slow_moving[:10]])

    ringkasan = f"""ANALISA KEBOCORAN PROFIT:

1. PERBANDINGAN REVENUE:
   - Revenue bulan ini: Rp {rev_now:,.0f}
   - Revenue bulan lalu: Rp {rev_prev:,.0f}
   - Perubahan: {rev_change:+.1f}%

2. PERBANDINGAN BIAYA:
   - Biaya bulan ini: Rp {float(biaya_bulan_ini):,.0f}
   - Biaya bulan lalu: Rp {float(biaya_bulan_lalu):,.0f}
   - Perubahan biaya: {biaya_change:+.1f}%

3. PRODUK MARGIN RENDAH (di bawah 15%):
   Total: {len(produk_low_margin)} produk
{low_margin_text if low_margin_text else '   Tidak ada produk dengan margin di bawah 15%'}

4. PRODUK SLOW MOVING (stok > 5, tidak terjual 30 hari):
   Total: {len(slow_moving)} produk
{slow_text if slow_text else '   Tidak ada produk slow moving'}

INSTRUKSI: Analisis data kebocoran profit di atas. Jelaskan penyebab utama profit turun/rendah, dan berikan rekomendasi spesifik untuk memperbaikinya. Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'kebocoran_profit', 'ringkasan': ringkasan}


def _gather_fraud_detection(today, month_start):
    """Deteksi aktivitas mencurigakan: refund, diskon tidak wajar, transaksi aneh."""
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder

    # 1. Analisa transaksi POS dengan diskon tinggi (> 20%)
    high_discount_invoices = []
    # Query database — ambil data for inv in POSTransaction.objects.filter(tanggal__date__gte yang sesuai filter
    for inv in POSTransaction.objects.filter(tanggal__date__gte=month_start, tanggal__date__lte=today):
        if inv.diskon and inv.subtotal and float(inv.subtotal) > 0:
            diskon_pct = float(inv.diskon) / float(inv.subtotal) * 100
            if diskon_pct > 20:
                high_discount_invoices.append({
                    'no': inv.nomor if inv.nomor else str(inv.id),
                    'tanggal': inv.tanggal.strftime('%d/%m/%Y') if inv.tanggal else '-',
                    'diskon_pct': round(diskon_pct, 1),
                    'total': float(inv.total_harga),
                })

    # 2. Transaksi dengan nilai sangat rendah (mungkin test/dummy)
    low_value_trx = POSTransaction.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today,
        total_harga__lt=1000
    ).count()

    # 3. Transaksi di luar jam kerja (sebelum 06:00 atau setelah 22:00)
    odd_hours_count = 0
    # Query database — ambil data for inv in POSTransaction.objects.filter(tanggal__date__gte yang sesuai filter
    for inv in POSTransaction.objects.filter(tanggal__date__gte=month_start, tanggal__date__lte=today):
        if inv.dibuat_pada:
            hour = inv.dibuat_pada.hour
            if hour < 6 or hour > 22:
                odd_hours_count += 1

    # 4. Sales Order dengan perubahan status mencurigakan (cancelled setelah confirmed)
    cancelled_after_confirm = SalesOrder.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today,
        status='cancelled'
    ).count()

    # 5. Total transaksi untuk konteks
    total_pos = POSTransaction.objects.filter(tanggal__date__gte=month_start, tanggal__date__lte=today).count()
    # Query database — ambil data total_so yang sesuai filter
    total_so = SalesOrder.objects.filter(tanggal__date__gte=month_start, tanggal__date__lte=today).count()

    high_disc_text = '\n'.join([f"  - Invoice #{d['no']} ({d['tanggal']}): diskon {d['diskon_pct']}%, total Rp {d['total']:,.0f}" for d in high_discount_invoices[:10]])

    ringkasan = f"""ANALISA FRAUD DETECTION & AKTIVITAS MENCURIGAKAN:

Periode: {month_start.strftime('%d/%m/%Y')} - {today.strftime('%d/%m/%Y')}
Total Transaksi POS: {total_pos}
Total Sales Order: {total_so}

1. DISKON TIDAK WAJAR (> 20%):
   Jumlah: {len(high_discount_invoices)} transaksi
{high_disc_text if high_disc_text else '   Tidak ada transaksi dengan diskon di atas 20%'}

2. TRANSAKSI NILAI SANGAT RENDAH (< Rp 1.000):
   Jumlah: {low_value_trx} transaksi
   {'⚠️ PERLU INVESTIGASI - kemungkinan transaksi test/dummy' if low_value_trx > 0 else 'Tidak ada transaksi mencurigakan'}

3. TRANSAKSI DI LUAR JAM KERJA (sebelum 06:00 / setelah 22:00):
   Jumlah: {odd_hours_count} transaksi
   {'⚠️ PERLU INVESTIGASI - transaksi di luar jam operasional' if odd_hours_count > 0 else 'Tidak ada transaksi di luar jam kerja'}

4. SALES ORDER DIBATALKAN:
   Jumlah SO cancelled: {cancelled_after_confirm}
   {'⚠️ PERLU INVESTIGASI - pembatalan perlu diperiksa alasannya' if cancelled_after_confirm > 3 else 'Dalam batas normal'}

SKOR RISIKO FRAUD:
- Diskon tidak wajar: {'TINGGI' if len(high_discount_invoices) > 5 else 'SEDANG' if len(high_discount_invoices) > 0 else 'RENDAH'}
- Transaksi dummy: {'TINGGI' if low_value_trx > 3 else 'SEDANG' if low_value_trx > 0 else 'RENDAH'}
- Jam tidak wajar: {'TINGGI' if odd_hours_count > 5 else 'SEDANG' if odd_hours_count > 0 else 'RENDAH'}
- Pembatalan SO: {'TINGGI' if cancelled_after_confirm > 5 else 'SEDANG' if cancelled_after_confirm > 2 else 'RENDAH'}

INSTRUKSI: Analisis data fraud detection di atas secara detail. Jelaskan temuan yang mencurigakan, tingkat risikonya, dan berikan rekomendasi langkah yang harus diambil. Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'fraud_detection', 'ringkasan': ringkasan}


def _gather_copywriter():
    """AI Copywriter: generate caption, deskripsi, broadcast dari data produk."""
    from apps.produk.models import Produk

    # Ambil produk aktif untuk inspirasi copywriting
    produk_list = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True).order_by('-stok')[:15]:
        produk_list.append({
            'nama': p.nama,
            'harga': float(p.harga_jual),
            'kategori': p.kategori.nama if p.kategori else 'Umum',
            'stok': p.stok,
        })

    produk_text = '\n'.join([f"  - {p['nama']} (Kategori: {p['kategori']}, Harga: Rp {p['harga']:,.0f}, Stok: {p['stok']})" for p in produk_list])

    # Produk perlu promo (stok tinggi)
    promo_candidates = [p for p in produk_list if p['stok'] > 20]
    promo_text = '\n'.join([f"  - {p['nama']} (stok: {p['stok']}, harga: Rp {p['harga']:,.0f})" for p in promo_candidates[:5]])

    ringkasan = f"""AI COPYWRITER - DATA PRODUK UNTUK GENERATE KONTEN:

PRODUK TERSEDIA ({len(produk_list)} produk):
{produk_text if produk_text else '  Belum ada data produk'}

PRODUK KANDIDAT PROMO (stok tinggi, perlu digerakkan):
{promo_text if promo_text else '  Tidak ada produk dengan stok tinggi'}

INSTRUKSI COPYWRITER:
Berdasarkan data produk di atas, buatkan konten marketing yang menarik. User mungkin meminta salah satu dari:

1. CAPTION SOSIAL MEDIA — Buat 3-5 variasi caption Instagram/Facebook yang catchy dan menarik, dengan hashtag relevan
2. DESKRIPSI PRODUK — Buat deskripsi produk yang profesional dan menjual untuk marketplace (Shopee/Tokopedia)
3. BROADCAST WHATSAPP — Buat pesan broadcast WhatsApp promosi yang personal dan persuasif
4. CAMPAIGN PLAN — Buat rencana kampanye promosi mingguan/bulanan

Jika user tidak spesifik, tanyakan jenis konten apa yang dibutuhkan dan untuk produk mana.
Gunakan bahasa Indonesia yang natural, menarik, dan persuasif.
Sertakan emoji yang relevan di konten marketing.
Sertakan link [Lihat Daftar Produk](/produk/list/) di akhir."""

    return {'intent': 'copywriter', 'ringkasan': ringkasan}


def _gather_marketing(today, month_start):
    """AI Marketing Generator: strategi marketing berdasarkan data bisnis."""
    from apps.produk.models import Produk
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction

    # 1. Top selling products untuk highlight marketing
    top_products = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True).order_by('-stok')[:10]:
        top_products.append({
            'nama': p.nama,
            'harga': float(p.harga_jual),
            'kategori': p.kategori.nama if p.kategori else 'Umum',
            'stok': p.stok,
        })

    # 2. Revenue trend
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    # Query database — ambil data so_rev yang sesuai filter
    so_rev = SalesOrder.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today,
        status__in=['confirmed', 'delivered', 'completed']
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    # Query database — ambil data pos_rev yang sesuai filter
    pos_rev = POSTransaction.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today, status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    rev_now = float(so_rev) + float(pos_rev)

    # Total customers
    from apps.penjualan.models import Customer
    # Hitung jumlah data yang cocok
    total_customers = Customer.objects.count()

    # Produk slow moving (kandidat promo)
    thirty_days_ago = today - timedelta(days=30)
    sold_ids = set(
        SalesOrder.objects.filter(
            tanggal__date__gte=thirty_days_ago
        ).values_list('items__produk_id', flat=True).distinct()
    )
    slow_moving = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True, stok__gt=5):
        if p.id not in sold_ids:
            slow_moving.append({'nama': p.nama, 'stok': p.stok, 'harga': float(p.harga_jual)})
    slow_moving.sort(key=lambda x: x['stok'], reverse=True)

    top_text = '\n'.join([f"  - {p['nama']} ({p['kategori']}) — Rp {p['harga']:,.0f}" for p in top_products[:5]])
    slow_text = '\n'.join([f"  - {p['nama']} (stok: {p['stok']}) — Rp {p['harga']:,.0f}" for p in slow_moving[:5]])

    ringkasan = f"""AI MARKETING GENERATOR - DATA BISNIS UNTUK STRATEGI MARKETING:

DATA BISNIS:
- Revenue bulan ini: Rp {rev_now:,.0f}
- Total customer terdaftar: {total_customers}
- Total produk aktif: {Produk.objects.filter(aktif=True).count()}

PRODUK UTAMA (untuk highlight marketing):
{top_text if top_text else '  Belum ada data produk'}

PRODUK PERLU PROMO (slow moving / stok tinggi):
{slow_text if slow_text else '  Tidak ada produk slow moving'}

INSTRUKSI MARKETING GENERATOR:
Berdasarkan data bisnis di atas, bantu user membuat strategi marketing. User mungkin meminta:

1. CAMPAIGN PLAN BULANAN — Rencana kampanye lengkap: tema, target audience, channel, budget allocation, KPI
2. STRATEGI PROMOSI — Ide promosi spesifik: diskon, bundling, flash sale, loyalty program
3. CONTENT CALENDAR — Jadwal konten mingguan untuk sosial media
4. CUSTOMER RETENTION — Strategi mempertahankan pelanggan lama dan reactivation
5. PRODUCT LAUNCH — Rencana launching produk baru
6. SEASONAL CAMPAIGN — Campaign berdasarkan momen (Ramadan, Harbolnas, dll)

Buatkan strategi yang actionable, dengan timeline jelas dan target terukur.
Fokus pada produk slow moving yang perlu digerakkan.
Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'marketing', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# AI CAMPAIGN PLANNER — Rencana Campaign Lengkap
# ═══════════════════════════════════════════════════════════════

def _gather_campaign_planner(today, month_start):
    """AI Campaign Planner: rencana campaign lengkap dengan timeline dan budget."""
    from apps.produk.models import Produk
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder, Customer
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction

    # Revenue data
    so_rev = SalesOrder.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today,
        status__in=['confirmed', 'delivered', 'completed']
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    # Query database — ambil data pos_rev yang sesuai filter
    pos_rev = POSTransaction.objects.filter(
        tanggal__date__gte=month_start, tanggal__date__lte=today, status='paid'
    ).aggregate(t=Sum('total_harga'))['t'] or 0
    rev_now = float(so_rev) + float(pos_rev)

    # Total pelanggan dan produk
    total_customers = Customer.objects.count()
    # Query database — ambil data total_produk yang sesuai filter
    total_produk = Produk.objects.filter(aktif=True).count()

    # Top 5 produk terlaris (paling banyak terjual 30 hari terakhir)
    thirty_days_ago = today - timedelta(days=30)
    # Import dari modul internal proyek
    from apps.pos.models import POSTransactionItem
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrderItem
    # Query database — ambil data top_sold yang sesuai filter
    top_sold = POSTransactionItem.objects.filter(
        transaksi__tanggal__date__gte=thirty_days_ago,
        transaksi__status='paid'
    ).values('produk__nama').annotate(
        total_qty=Sum('jumlah')
    ).order_by('-total_qty')[:5]

    top_text = '\n'.join([f"  - {p['produk__nama']} ({p['total_qty']} terjual)" for p in top_sold])

    # Produk slow moving (kandidat promo agresif)
    sold_ids = set(
        POSTransactionItem.objects.filter(
            transaksi__tanggal__date__gte=thirty_days_ago
        ).values_list('produk_id', flat=True).distinct()
    )
    slow_moving = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True, stok__gt=5):
        if p.id not in sold_ids:
            slow_moving.append({'nama': p.nama, 'stok': p.stok, 'harga': float(p.harga_jual)})
    slow_moving.sort(key=lambda x: x['stok'], reverse=True)
    slow_text = '\n'.join([f"  - {p['nama']} (stok: {p['stok']})" for p in slow_moving[:5]])

    # Hari & tanggal penting ke depan
    import calendar
    next_month = today.month % 12 + 1
    next_month_year = today.year + (1 if today.month == 12 else 0)

    ringkasan = f"""AI CAMPAIGN PLANNER - DATA UNTUK PERENCANAAN CAMPAIGN:

DATA BISNIS SAAT INI:
- Revenue bulan ini: Rp {rev_now:,.0f}
- Total customer: {total_customers}
- Total produk aktif: {total_produk}
- Periode data: {month_start.strftime('%d/%m/%Y')} - {today.strftime('%d/%m/%Y')}

TOP 5 PRODUK TERLARIS (30 hari terakhir):
{top_text if top_text else '  Belum ada data penjualan'}

PRODUK PERLU CAMPAIGN KHUSUS (slow moving):
{slow_text if slow_text else '  Tidak ada produk slow moving'}

INSTRUKSI CAMPAIGN PLANNER:
Berdasarkan data di atas, buatkan CAMPAIGN PLAN LENGKAP yang mencakup:

1. CAMPAIGN CALENDAR (4 minggu ke depan):
   - Minggu 1-4 dengan tema, target, dan channel distribusi
   - Jadwal posting konten harian (kapan posting, platform mana)

2. BUDGET ALLOCATION:
   - Alokasi budget per channel (sosial media, marketplace, offline)
   - Estimasi ROI per campaign

3. TARGET & KPI:
   - Target revenue, traffic, engagement per campaign
   - Metode tracking dan evaluasi

4. CREATIVE BRIEF:
   - Tema visual, tone of voice, key message
   - Variasi konten: promo, edukasi, testimonial, behind the scene

5. A/B TESTING:
   - Variasi yang bisa dicoba (caption, visual, timing)
   - Strategi optimasi berdasarkan hasil

Fokuskan campaign pada produk slow moving yang perlu digerakkan.
Sesuaikan dengan budget UMKM yang terbatas.
Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'campaign_planner', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# 90 DAYS BUSINESS PLAN — Rencana Bisnis 3 Bulan
# ═══════════════════════════════════════════════════════════════

def _gather_business_plan_90hari(today, month_start):
    """90 Days Business Plan Generator: rencana bisnis 3 bulan dengan milestone."""
    from apps.produk.models import Produk
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder, Customer
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.pembelian.models import PurchaseOrder, Supplier

    # Revenue 3 bulan terakhir (untuk tren)
    months_data = []
    for i in range(3):
        m_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        if i == 0:
            m_end = today
        else:
            import calendar as cal
            _, last_day = cal.monthrange(m_start.year, m_start.month)
            m_end = m_start.replace(day=last_day)

        # Query database — ambil data so_rev yang sesuai filter
        so_rev = SalesOrder.objects.filter(
            tanggal__date__gte=m_start, tanggal__date__lte=m_end,
            status__in=['confirmed', 'delivered', 'completed']
        ).aggregate(t=Sum('total_harga'))['t'] or 0
        # Query database — ambil data pos_rev yang sesuai filter
        pos_rev = POSTransaction.objects.filter(
            tanggal__date__gte=m_start, tanggal__date__lte=m_end, status='paid'
        ).aggregate(t=Sum('total_harga'))['t'] or 0
        months_data.append({
            'bulan': m_start.strftime('%B %Y'),
            'revenue': float(so_rev) + float(pos_rev)
        })

    rev_text = '\n'.join([f"  - {m['bulan']}: Rp {m['revenue']:,.0f}" for m in months_data])
    avg_rev = sum(m['revenue'] for m in months_data) / 3 if months_data else 0

    # Statistik bisnis
    total_produk = Produk.objects.filter(aktif=True).count()
    # Hitung jumlah data yang cocok
    total_customer = Customer.objects.count()
    # Hitung jumlah data yang cocok
    total_supplier = Supplier.objects.count()

    # Biaya rata-rata
    from apps.biaya.models import TransaksiBiaya
    # Query database — ambil data total_biaya yang sesuai filter
    total_biaya = TransaksiBiaya.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).aggregate(t=Sum('jumlah'))['t'] or 0

    ringkasan = f"""90 DAYS BUSINESS PLAN GENERATOR - DATA UNTUK PERENCANAAN:

REVENUE TREND (3 bulan terakhir):
{rev_text}
- Rata-rata revenue/bulan: Rp {avg_rev:,.0f}

STATISTIK BISNIS SAAT INI:
- Total produk aktif: {total_produk}
- Total customer: {total_customer}
- Total supplier: {total_supplier}
- Biaya operasional bulan ini: Rp {float(total_biaya):,.0f}
- Estimasi profit bulan ini: Rp {months_data[0]['revenue'] - float(total_biaya):,.0f}

INSTRUKSI BUSINESS PLAN GENERATOR:
Berdasarkan data di atas, buatkan RENCANA BISNIS 90 HARI (3 BULAN):

BULAN 1 — STABILISASI & FONDASI:
- Target revenue, action plan harian/mingguan
- Optimasi produk existing dan evaluasi margin
- Perbaikan operasional dan efisiensi biaya

BULAN 2 — PERTUMBUHAN:
- Target revenue (growth 15-25% dari bulan sebelumnya)
- Strategi akuisisi customer baru
- Ekspansi produk atau kategori baru
- Campaign marketing aktif

BULAN 3 — SKALA & OPTIMASI:
- Target revenue dan proyeksi profit
- Scale up channel distribusi
- Evaluasi menyeluruh dan pivot jika perlu
- KPI review dan perencanaan kuartal berikutnya

MILESTONE TRACKING:
- Minggu 1-2: [milestone]
- Minggu 3-4: [milestone]
- Minggu 5-8: [milestone]
- Minggu 9-12: [milestone]

KPI YANG HARUS DIMONITOR:
- Revenue growth (%), customer growth, rata-rata transaksi, produk terjual
- Biaya operasional vs revenue ratio
- Inventory turnover rate

Buat plan yang REALISTIS berdasarkan data aktual.
Sertakan target angka spesifik berdasarkan tren historis.
Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'business_plan_90hari', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# AI MULTI-BRANCH ANALYZER — Analisa Performa Cabang/Gudang
# ═══════════════════════════════════════════════════════════════

def _gather_multi_branch_analyzer(today, month_start):
    """AI Multi-Branch Analyzer: bandingkan performa antar gudang/cabang."""
    from apps.inventory.models import Gudang, Stok
    # Import dari modul internal proyek
    from apps.pos.models import POSTransaction
    # Import dari modul internal proyek
    from apps.penjualan.models import SalesOrder
    # Import dari modul internal proyek
    from apps.produk.models import Produk

    # Data per gudang
    gudang_list = Gudang.objects.all()
    branches = []

    for g in gudang_list:
        # Stok di gudang ini
        stok_data = Stok.objects.filter(gudang=g)
        total_stok_items = stok_data.count()
        total_stok_qty = stok_data.aggregate(t=Sum('jumlah'))['t'] or 0
        stok_habis = stok_data.filter(jumlah=0).count()
        stok_rendah = stok_data.filter(jumlah__gt=0, jumlah__lte=5).count()

        # Nilai stok (estimasi berdasarkan harga beli)
        nilai_stok = 0
        for s in stok_data.select_related('produk'):
            if s.produk and s.produk.harga_beli:
                nilai_stok += float(s.produk.harga_beli) * float(s.jumlah)

        # Revenue dari POS di gudang ini
        pos_rev = POSTransaction.objects.filter(
            gudang=g, tanggal__date__gte=month_start,
            tanggal__date__lte=today, status='paid'
        ).aggregate(
            total=Sum('total_harga'),
            count=Count('id')
        )

        # Revenue dari SO di gudang ini
        so_rev = SalesOrder.objects.filter(
            gudang=g, tanggal__date__gte=month_start,
            tanggal__date__lte=today,
            status__in=['confirmed', 'delivered', 'completed']
        ).aggregate(
            total=Sum('total_harga'),
            count=Count('id')
        )

        branches.append({
            'nama': g.nama,
            'alamat': g.alamat or '-',
            'total_produk': total_stok_items,
            'total_stok': float(total_stok_qty),
            'stok_habis': stok_habis,
            'stok_rendah': stok_rendah,
            'nilai_stok': nilai_stok,
            'pos_revenue': float(pos_rev['total'] or 0),
            'pos_transaksi': pos_rev['count'] or 0,
            'so_revenue': float(so_rev['total'] or 0),
            'so_transaksi': so_rev['count'] or 0,
            'total_revenue': float(pos_rev['total'] or 0) + float(so_rev['total'] or 0),
        })

    # Ranking berdasarkan revenue
    branches.sort(key=lambda x: x['total_revenue'], reverse=True)

    branch_text = ''
    for i, b in enumerate(branches, 1):
        branch_text += f"""
{i}. {b['nama']} ({b['alamat']}):
   - Revenue bulan ini: Rp {b['total_revenue']:,.0f}
     * POS: Rp {b['pos_revenue']:,.0f} ({b['pos_transaksi']} transaksi)
     * SO: Rp {b['so_revenue']:,.0f} ({b['so_transaksi']} order)
   - Total produk: {b['total_produk']} item, Total stok: {b['total_stok']:,.0f}
   - Stok habis: {b['stok_habis']}, Stok rendah: {b['stok_rendah']}
   - Nilai stok: Rp {b['nilai_stok']:,.0f}
"""

    total_rev = sum(b['total_revenue'] for b in branches)

    ringkasan = f"""AI MULTI-BRANCH ANALYZER - PERBANDINGAN PERFORMA CABANG/GUDANG:

PERIODE: {month_start.strftime('%d/%m/%Y')} - {today.strftime('%d/%m/%Y')}
TOTAL CABANG/GUDANG: {len(branches)}
TOTAL REVENUE SEMUA CABANG: Rp {total_rev:,.0f}

RANKING PERFORMA PER CABANG:
{branch_text if branch_text else '  Belum ada data gudang'}

INSTRUKSI MULTI-BRANCH ANALYZER:
Berdasarkan data di atas, buatkan ANALISA PERBANDINGAN CABANG yang mencakup:

1. RANKING & PERFORMA:
   - Cabang mana yang paling menguntungkan dan kenapa
   - Cabang mana yang perlu perhatian khusus
   - Gap revenue antar cabang dan cara memperkecilnya

2. REKOMENDASI PER CABANG:
   - Strategi untuk cabang top performer (maintain/scale)
   - Strategi untuk cabang underperformer (perbaikan operasional)
   - Produk apa yang harus ditambah/dikurangi per cabang

3. DISTRIBUSI & STOK:
   - Apakah distribusi stok sudah optimal
   - Produk yang perlu di-transfer antar cabang
   - Rebalancing stok untuk efisiensi

4. EXPANSION STRATEGY:
   - Apakah perlu buka cabang baru atau tutup cabang
   - Area yang berpotensi untuk ekspansi

Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'multi_branch_analyzer', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# AI CONTENT GENERATOR — IG, TikTok, Shopee, WhatsApp
# ═══════════════════════════════════════════════════════════════

def _gather_content_generator():
    """AI Content Generator: generate konten untuk berbagai platform."""
    from apps.produk.models import Produk

    # Ambil produk-produk untuk bahan konten
    products = []
    # Query database — ambil data for p in Produk.objects.filter(aktif yang sesuai filter
    for p in Produk.objects.filter(aktif=True).order_by('-harga_jual')[:10]:
        products.append({
            'nama': p.nama,
            'harga': float(p.harga_jual),
            'kategori': p.kategori.nama if p.kategori else 'Umum',
            'deskripsi': p.deskripsi or '',
            'stok': p.stok,
        })

    prod_text = '\n'.join([
        f"  - {p['nama']} ({p['kategori']}) — Rp {p['harga']:,.0f}"
        + (f" | {p['deskripsi'][:50]}..." if p['deskripsi'] else '')
        for p in products
    ])

    ringkasan = f"""AI CONTENT GENERATOR - DATA PRODUK UNTUK PEMBUATAN KONTEN:

PRODUK YANG TERSEDIA:
{prod_text if prod_text else '  Belum ada data produk'}

INSTRUKSI CONTENT GENERATOR:
Berdasarkan data produk di atas, bantu user membuat konten untuk platform berikut.
User mungkin meminta salah satu atau beberapa format:

1. CAPTION INSTAGRAM:
   - Hook yang menarik di baris pertama (bikin orang berhenti scroll)
   - Body: highlight benefit dan keunggulan produk (bukan hanya fitur)
   - CTA (Call to Action) yang jelas: DM, link di bio, klik, dll
   - Hashtag relevan (10-15 hashtag campuran populer dan niche)
   - Emoji yang sesuai tapi tidak berlebihan
   - Format: Pendek (1 slide), Medium (carousel), atau Story

2. SCRIPT TIKTOK:
   - HOOK (0-3 detik): Pertanyaan atau statement yang bikin penasaran
   - ISI (3-30 detik): Tunjukkan produk, benefit, tutorial singkat
   - CTA (30-60 detik): Ajak follow, like, atau beli
   - Trending sound suggestion
   - Format: Review, Tutorial, Unboxing, GRWM, Day in my life

3. DESKRIPSI SHOPEE/TOKOPEDIA:
   - Judul produk SEO-friendly (keyword utama di depan)
   - Deskripsi lengkap: spesifikasi, benefit, cara pakai, garansi
   - Bullet point key features
   - FAQ singkat (3-5 pertanyaan umum)
   - Template: bisa copy-paste langsung ke marketplace

4. BROADCAST WHATSAPP:
   - Opening personal (bukan spam)
   - Info promo/produk yang ringkas dan menarik
   - CTA langsung (reply angka, klik link, atau balas pesan)
   - Format: template yang bisa di-personalisasi per customer
   - Variasi: promo, launch produk, reminder, ucapan + promo

Buat konten yang SIAP PAKAI dan sesuai tone yang natural.
Jangan terlalu formal atau terlalu santai — sesuaikan dengan target market UMKM.
Jika user menyebut produk spesifik, fokuskan konten pada produk tersebut.
Sertakan link ke halaman terkait menggunakan format [Teks](/url/)."""

    return {'intent': 'content_generator', 'ringkasan': ringkasan}


def _gather_fraud_detection(today, month_start):
    """
    Data fraud detection: anomali, rekonsiliasi kas, ringkasan keamanan.
    ═══════════════════════════════════════════════════════════════════
    Fungsi ini mengumpulkan data dari 2 model utama Fraud Detection:
    - FraudAlert       → Log anomali kecurangan (diskon besar, hapus lunas, dll)
    - CashReconciliation → Rekonsiliasi kas kasir (blind cash closing)

    Data yang dikumpulkan (hanya angka agregat, AMAN dikirim ke AI):
    - Jumlah anomali per status (pending, investigated, cleared, rejected)
    - Jumlah anomali per severity (low, medium, high, critical)
    - Total nominal fraud terdeteksi
    - Statistik rekonsiliasi kas (selisih, shortage, overage)
    - Top 5 anomali terbaru untuk konteks

    Terhubung dengan:
    - apps.fraud_detection.models.FraudAlert
    - apps.fraud_detection.models.CashReconciliation
    - apps.activity_log.models.UserActivity (via FraudAlert.activity FK)
    ═══════════════════════════════════════════════════════════════════
    """
    # Import model Fraud Detection
    from apps.fraud_detection.models import FraudAlert, CashReconciliation

    # ── STATISTIK ANOMALI (FraudAlert) ──
    total_alert = FraudAlert.objects.count()
    alert_bulan_ini = FraudAlert.objects.filter(
        created_at__date__gte=month_start, created_at__date__lte=today
    ).count()

    # Hitung per status — untuk mengetahui berapa yang belum ditindaklanjuti
    pending = FraudAlert.objects.filter(status='pending').count()
    investigated = FraudAlert.objects.filter(status='investigated').count()
    cleared = FraudAlert.objects.filter(status='cleared').count()
    rejected = FraudAlert.objects.filter(status='rejected').count()

    # Hitung per severity — untuk mengetahui tingkat keparahan
    sev_low = FraudAlert.objects.filter(severity='low').count()
    sev_medium = FraudAlert.objects.filter(severity='medium').count()
    sev_high = FraudAlert.objects.filter(severity='high').count()
    sev_critical = FraudAlert.objects.filter(severity='critical').count()

    # Total nominal fraud terdeteksi (semua anomali)
    total_nominal = float(FraudAlert.objects.aggregate(
        t=Sum('nominal'))['t'] or 0
    )
    # Nominal khusus yang terbukti fraud (status=rejected)
    nominal_fraud = float(FraudAlert.objects.filter(
        status='rejected'
    ).aggregate(t=Sum('nominal'))['t'] or 0)

    # Top 5 anomali terbaru (untuk konteks)
    top_alerts = FraudAlert.objects.select_related(
        'user_terkait'
    ).order_by('-created_at')[:5]
    alert_list = []
    for a in top_alerts:
        user_name = (a.user_terkait.get_full_name() or
                     a.user_terkait.username) if a.user_terkait else '-'
        alert_list.append(
            f"  - [{a.get_severity_display()}] {a.get_jenis_display()} "
            f"oleh {user_name} — Rp {float(a.nominal):,.0f} "
            f"({a.get_status_display()})"
        )

    # Hitung per jenis anomali (top 5 jenis terbanyak)
    jenis_stats = FraudAlert.objects.values('jenis').annotate(
        total=Count('id')
    ).order_by('-total')[:5]
    jenis_list = [
        f"  - {dict(FraudAlert.JENIS_CHOICES).get(j['jenis'], j['jenis'])}: "
        f"{j['total']} kasus"
        for j in jenis_stats
    ]

    # ── STATISTIK REKONSILIASI KAS (CashReconciliation) ──
    total_rekon = CashReconciliation.objects.count()
    rekon_bulan_ini = CashReconciliation.objects.filter(
        created_at__date__gte=month_start, created_at__date__lte=today
    ).count()

    # Per status rekonsiliasi
    rekon_open = CashReconciliation.objects.filter(status='open').count()
    rekon_closed = CashReconciliation.objects.filter(status='closed').count()
    rekon_reviewed = CashReconciliation.objects.filter(status='reviewed').count()

    # Selisih kas — hitung total shortage dan overage
    total_selisih = float(CashReconciliation.objects.aggregate(
        t=Sum('discrepancy'))['t'] or 0
    )
    # Jumlah record dengan selisih negatif (uang kurang / shortage)
    shortage_count = CashReconciliation.objects.filter(
        discrepancy__lt=0
    ).count()
    shortage_total = float(CashReconciliation.objects.filter(
        discrepancy__lt=0
    ).aggregate(t=Sum('discrepancy'))['t'] or 0)
    # Jumlah record dengan selisih positif (uang lebih / overage)
    overage_count = CashReconciliation.objects.filter(
        discrepancy__gt=0
    ).count()
    overage_total = float(CashReconciliation.objects.filter(
        discrepancy__gt=0
    ).aggregate(t=Sum('discrepancy'))['t'] or 0)

    ringkasan = f"""Data Fraud Detection & Keamanan:

═══ ANOMALI TERDETEKSI ═══
- Total Anomali: {total_alert} (bulan ini: {alert_bulan_ini})
- Menunggu Review: {pending}
- Sedang Diinvestigasi: {investigated}
- Aman/Wajar (Cleared): {cleared}
- Terbukti Fraud: {rejected}

Tingkat Keparahan:
- Rendah: {sev_low} | Sedang: {sev_medium} | Tinggi: {sev_high} | Kritis: {sev_critical}

Nominal:
- Total Nominal Anomali: Rp {total_nominal:,.0f}
- Nominal Terbukti Fraud: Rp {nominal_fraud:,.0f}

Jenis Anomali Terbanyak:
{chr(10).join(jenis_list) if jenis_list else '  Belum ada data anomali'}

Anomali Terbaru:
{chr(10).join(alert_list) if alert_list else '  Belum ada data anomali'}

═══ REKONSILIASI KAS (Blind Cash Closing) ═══
- Total Rekonsiliasi: {total_rekon} (bulan ini: {rekon_bulan_ini})
- Shift Berjalan: {rekon_open}
- Shift Ditutup: {rekon_closed}
- Sudah Direview: {rekon_reviewed}

Selisih Kas:
- Total Selisih Bersih: Rp {total_selisih:,.0f}
- Shortage (Kurang): {shortage_count} kali (total Rp {abs(shortage_total):,.0f})
- Overage (Lebih): {overage_count} kali (total Rp {overage_total:,.0f})
- Status: {'🔴 Ada potensi kerugian' if shortage_count > 0 else '🟢 Tidak ada shortage'}"""

    return {'intent': 'fraud_detection', 'ringkasan': ringkasan}


# ═══════════════════════════════════════════════════════════════
# MODUL KEUANGAN & AKUNTANSI — Data Gatherers
# ═══════════════════════════════════════════════════════════════

def _gather_kas_bank(today, month_start):
    """Data Kas & Bank: saldo, mutasi, transfer."""
    from apps.kas_bank.models import KasBankAccount, KasBankTransaction, KasBankTransfer

    accounts = KasBankAccount.objects.filter(aktif=True)
    total_accounts = accounts.count()

    # Saldo per akun
    account_info = []
    total_saldo = Decimal('0')
    for acc in accounts.order_by('kode')[:10]:
        saldo = acc.saldo_terhitung
        total_saldo += saldo
        account_info.append(f"  - {acc.nama} ({acc.get_tipe_display()}): Rp {saldo:,.0f}")

    # Mutasi bulan ini
    mutasi_posted = KasBankTransaction.objects.filter(status='posted')
    mutasi_bulan = mutasi_posted.filter(tanggal__date__gte=month_start, tanggal__date__lte=today)
    total_masuk = float(mutasi_bulan.filter(
        tipe__in=['masuk', 'transfer_masuk', 'penyesuaian_masuk']
    ).aggregate(t=Sum('jumlah'))['t'] or 0)
    total_keluar = float(mutasi_bulan.filter(
        tipe__in=['keluar', 'transfer_keluar', 'penyesuaian_keluar']
    ).aggregate(t=Sum('jumlah'))['t'] or 0)
    net_cashflow = total_masuk - total_keluar

    # Transfer bulan ini
    transfer_count = KasBankTransfer.objects.filter(
        status='posted', tanggal__date__gte=month_start
    ).count()

    # Pending reconciliation
    from apps.kas_bank.models import KasBankReconciliation
    pending_rekon = KasBankReconciliation.objects.filter(status='draft').count()

    ringkasan = f"""═══ DATA KAS & BANK (Treasury) ═══
Periode: {month_start.strftime('%d/%m/%Y')} s/d {today.strftime('%d/%m/%Y')}

Ringkasan Saldo:
- Total Akun Aktif: {total_accounts}
- Total Saldo Semua Akun: Rp {total_saldo:,.0f}

Detail Saldo per Akun:
{chr(10).join(account_info) if account_info else '  Belum ada akun kas/bank'}

Arus Kas Bulan Ini:
- Total Kas Masuk: Rp {total_masuk:,.0f}
- Total Kas Keluar: Rp {total_keluar:,.0f}
- Net Cashflow: Rp {net_cashflow:,.0f} ({'surplus' if net_cashflow >= 0 else 'defisit'})

Aktivitas:
- Transfer Antar Akun: {transfer_count} transaksi
- Rekonsiliasi Pending: {pending_rekon}"""

    return {'intent': 'kas_bank', 'ringkasan': ringkasan}


def _gather_akuntansi(today, month_start):
    """Data Akuntansi: jurnal, neraca, laba rugi."""
    from apps.akuntansi.models import Akun, JurnalEntry, JurnalLine, PeriodeAkuntansi
    from apps.akuntansi.services import get_laba_rugi, get_neraca

    # Statistik jurnal
    total_jurnal = JurnalEntry.objects.count()
    jurnal_posted = JurnalEntry.objects.filter(is_posted=True).count()
    jurnal_draft = JurnalEntry.objects.filter(is_posted=False).count()
    jurnal_bulan_ini = JurnalEntry.objects.filter(
        tanggal__gte=month_start, tanggal__lte=today
    ).count()

    # Laba Rugi bulan ini
    laba_rugi = get_laba_rugi(month_start, today)
    pendapatan = float(laba_rugi['total_pendapatan'])
    hpp = float(laba_rugi['total_hpp'])
    beban = float(laba_rugi['total_beban'])
    laba_kotor = float(laba_rugi['laba_kotor'])
    laba_bersih = float(laba_rugi['laba_bersih'])

    # Neraca saat ini
    neraca = get_neraca(today)
    total_aktiva = float(neraca['total_aktiva'])
    total_pasiva = float(neraca['total_pasiva'])
    is_balanced = neraca['is_balanced']

    # Periode aktif
    periode_aktif = PeriodeAkuntansi.objects.filter(is_aktif=True).first()
    periode_info = f"{periode_aktif.nama}" if periode_aktif else "Tidak ada periode aktif"

    # CoA
    total_akun = Akun.objects.filter(is_active=True).count()

    # Jurnal per sumber (top 5)
    sumber_top = JurnalEntry.objects.filter(
        is_posted=True, tanggal__gte=month_start
    ).values('sumber').annotate(jml=Count('id')).order_by('-jml')[:5]
    sumber_list = [f"  - {s['sumber'] or 'manual'}: {s['jml']} jurnal" for s in sumber_top]

    ringkasan = f"""═══ DATA AKUNTANSI ═══
Periode: {month_start.strftime('%d/%m/%Y')} s/d {today.strftime('%d/%m/%Y')}

Statistik Jurnal:
- Total Jurnal: {total_jurnal} (Posted: {jurnal_posted}, Draft: {jurnal_draft})
- Jurnal Bulan Ini: {jurnal_bulan_ini}
- Total Akun (CoA): {total_akun}
- Periode Aktif: {periode_info}

Laporan Laba Rugi (Bulan Ini):
- Pendapatan: Rp {pendapatan:,.0f}
- HPP: Rp {hpp:,.0f}
- Laba Kotor: Rp {laba_kotor:,.0f}
- Beban Operasional: Rp {beban:,.0f}
- Laba Bersih: Rp {laba_bersih:,.0f}
- Status: {'✅ LABA' if laba_bersih >= 0 else '❌ RUGI'}

Neraca (Balance Sheet) per Hari Ini:
- Total Aktiva (Aset): Rp {total_aktiva:,.0f}
- Total Pasiva (Kewajiban + Modal + Laba): Rp {total_pasiva:,.0f}
- Balance: {'✅ SEIMBANG' if is_balanced else '⚠️ TIDAK SEIMBANG'}

Jurnal per Sumber (Bulan Ini):
{chr(10).join(sumber_list) if sumber_list else '  Belum ada jurnal bulan ini'}"""

    return {'intent': 'akuntansi', 'ringkasan': ringkasan}


def _gather_piutang_hutang(today, month_start):
    """Data Piutang & Hutang."""
    from apps.piutang.models import Piutang
    from apps.hutang.models import Hutang

    # Piutang
    piutang_all = Piutang.objects.exclude(status='lunas')
    total_piutang = piutang_all.count()
    nominal_piutang = float(piutang_all.aggregate(
        t=Sum('jumlah_total'))['t'] or 0)
    dibayar_piutang = float(piutang_all.aggregate(
        t=Sum('jumlah_dibayar'))['t'] or 0)
    sisa_piutang = nominal_piutang - dibayar_piutang

    # Aging piutang
    piutang_overdue = piutang_all.filter(
        jatuh_tempo__lt=today, status='belum_bayar'
    ).count()

    # Hutang
    hutang_all = Hutang.objects.exclude(status='lunas')
    total_hutang = hutang_all.count()
    nominal_hutang = float(hutang_all.aggregate(
        t=Sum('jumlah_total'))['t'] or 0)
    dibayar_hutang = float(hutang_all.aggregate(
        t=Sum('jumlah_dibayar'))['t'] or 0)
    sisa_hutang = nominal_hutang - dibayar_hutang

    # Aging hutang
    hutang_overdue = hutang_all.filter(
        jatuh_tempo__lt=today, status='belum_bayar'
    ).count()

    ringkasan = f"""═══ DATA PIUTANG & HUTANG ═══

PIUTANG USAHA (Accounts Receivable):
- Total Piutang Belum Lunas: {total_piutang}
- Nominal Total: Rp {nominal_piutang:,.0f}
- Sudah Dibayar: Rp {dibayar_piutang:,.0f}
- Sisa Piutang: Rp {sisa_piutang:,.0f}
- Overdue (Lewat Jatuh Tempo): {piutang_overdue} piutang
- Status: {'⚠️ Ada piutang overdue' if piutang_overdue > 0 else '✅ Semua dalam tempo'}

HUTANG USAHA (Accounts Payable):
- Total Hutang Belum Lunas: {total_hutang}
- Nominal Total: Rp {nominal_hutang:,.0f}
- Sudah Dibayar: Rp {dibayar_hutang:,.0f}
- Sisa Hutang: Rp {sisa_hutang:,.0f}
- Overdue (Lewat Jatuh Tempo): {hutang_overdue} hutang
- Status: {'⚠️ Ada hutang overdue' if hutang_overdue > 0 else '✅ Semua dalam tempo'}

POSISI BERSIH:
- Net Position: Rp {(sisa_piutang - sisa_hutang):,.0f}
- Keterangan: {'Piutang > Hutang (positif)' if sisa_piutang > sisa_hutang else 'Hutang > Piutang (negatif)'}"""

    return {'intent': 'piutang_hutang', 'ringkasan': ringkasan}


def _gather_aset_tetap():
    """Data Aset Tetap & Penyusutan."""
    from apps.aset.models import AsetTetap, Penyusutan

    aset_aktif = AsetTetap.objects.filter(status='aktif')
    total_aktif = aset_aktif.count()
    total_perolehan = float(aset_aktif.aggregate(t=Sum('harga_perolehan'))['t'] or 0)
    total_akumulasi = float(Penyusutan.objects.filter(
        aset__status='aktif'
    ).aggregate(t=Sum('jumlah'))['t'] or 0)
    total_nilai_buku = total_perolehan - total_akumulasi

    # Per kategori
    kategori_info = []
    for kat_code, kat_name in AsetTetap.KATEGORI_CHOICES:
        count = aset_aktif.filter(kategori=kat_code).count()
        if count > 0:
            nilai = float(aset_aktif.filter(kategori=kat_code).aggregate(
                t=Sum('harga_perolehan'))['t'] or 0)
            kategori_info.append(f"  - {kat_name}: {count} unit (Rp {nilai:,.0f})")

    # Aset yang sudah habis umur
    habis_umur = 0
    for aset in aset_aktif:
        if aset.sisa_umur_bulan <= 0:
            habis_umur += 1

    # Disposed
    total_disposed = AsetTetap.objects.exclude(status='aktif').count()

    ringkasan = f"""═══ DATA ASET TETAP ═══

Ringkasan:
- Total Aset Aktif: {total_aktif}
- Total Harga Perolehan: Rp {total_perolehan:,.0f}
- Total Akumulasi Penyusutan: Rp {total_akumulasi:,.0f}
- Total Nilai Buku: Rp {total_nilai_buku:,.0f}
- Aset Habis Umur Ekonomis: {habis_umur}
- Aset Disposed/Dijual: {total_disposed}

Per Kategori:
{chr(10).join(kategori_info) if kategori_info else '  Belum ada aset tetap'}

Rasio:
- Penyusutan vs Perolehan: {round(total_akumulasi / total_perolehan * 100, 1) if total_perolehan > 0 else 0}%"""

    return {'intent': 'aset_tetap', 'ringkasan': ringkasan}


def _gather_pajak_ppn(today, month_start):
    """Data Pajak PPN."""
    from apps.pajak.models import FakturPajak, SettingPajak, PembayaranPPN

    # Setting PPN
    setting = SettingPajak.get_setting()
    tarif = float(setting.tarif_ppn) if setting else 11

    # Faktur bulan ini
    faktur_keluaran = FakturPajak.objects.filter(
        tipe='keluaran', tanggal__gte=month_start, tanggal__lte=today
    )
    faktur_masukan = FakturPajak.objects.filter(
        tipe='masukan', tanggal__gte=month_start, tanggal__lte=today
    )

    count_keluaran = faktur_keluaran.count()
    count_masukan = faktur_masukan.count()
    ppn_keluaran = float(faktur_keluaran.aggregate(t=Sum('ppn'))['t'] or 0)
    ppn_masukan = float(faktur_masukan.aggregate(t=Sum('ppn'))['t'] or 0)
    selisih_ppn = ppn_keluaran - ppn_masukan

    # Total DPP
    dpp_keluaran = float(faktur_keluaran.aggregate(t=Sum('dpp'))['t'] or 0)
    dpp_masukan = float(faktur_masukan.aggregate(t=Sum('dpp'))['t'] or 0)

    # Pembayaran PPN
    total_setor = PembayaranPPN.objects.count()
    total_nominal_setor = float(PembayaranPPN.objects.aggregate(
        t=Sum('jumlah_setor'))['t'] or 0)

    ringkasan = f"""═══ DATA PAJAK (PPN) ═══
Periode: {month_start.strftime('%d/%m/%Y')} s/d {today.strftime('%d/%m/%Y')}
Tarif PPN: {tarif}%

Faktur Pajak Bulan Ini:
- PPN Keluaran: {count_keluaran} faktur (DPP: Rp {dpp_keluaran:,.0f}, PPN: Rp {ppn_keluaran:,.0f})
- PPN Masukan: {count_masukan} faktur (DPP: Rp {dpp_masukan:,.0f}, PPN: Rp {ppn_masukan:,.0f})

Rekap PPN:
- PPN Keluaran (harus disetor): Rp {ppn_keluaran:,.0f}
- PPN Masukan (kredit pajak): Rp {ppn_masukan:,.0f}
- Selisih (Kurang/Lebih Bayar): Rp {selisih_ppn:,.0f}
- Status: {'Kurang Bayar → Harus Setor' if selisih_ppn > 0 else 'Lebih Bayar → Restitusi' if selisih_ppn < 0 else 'Nihil'}

Riwayat Setor PPN:
- Total Setor: {total_setor} kali
- Total Nominal Disetor: Rp {total_nominal_setor:,.0f}"""

    return {'intent': 'pajak_ppn', 'ringkasan': ringkasan}
