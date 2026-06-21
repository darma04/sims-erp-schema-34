"""
==========================================================================
 POS VIEWS - View untuk Point of Sale (Kasir) dan Invoice
==========================================================================
 File ini berisi views untuk modul POS:

 HALAMAN POS:
   POSIndexView → Halaman utama POS/Kasir (grid produk + keranjang)

 API ENDPOINTS (JSON — dipanggil via AJAX dari frontend POS):
   create_transaction()    → Buat transaksi POS baru + kurangi stok
   check_stock()           → Cek stok produk di gudang tertentu
   search_products()       → Search produk autocomplete
   get_stocks_by_gudang()  → Ambil semua stok per gudang

 INVOICE CRUD:
   InvoiceListView    → Daftar semua invoice/transaksi POS
   InvoiceDetailView  → Detail invoice
   InvoicePrintView   → Cetak struk (tanpa TemplateLayout agar bersih)
   InvoiceDeleteView  → Hapus invoice (JSON response)

 ALUR TRANSAKSI POS:
 1. User pilih gudang → frontend load stok via get_stocks_by_gudang()
 2. User pilih produk dari grid → tambah ke keranjang
 3. User klik Bayar → frontend kirim JSON ke create_transaction()
 4. Backend: validasi stok → buat POSTransaction + items → kurangi stok
 5. Return: redirect ke halaman invoice/struk

 ⚠ Semua proses create_transaction() dalam db.transaction.atomic()
   artinya jika ada error, semua perubahan di-rollback.
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


from django.shortcuts import render
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, ListView, DetailView
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from web_project import TemplateLayout
from apps.pos.models import POSTransaction, POSTransactionItem, MetodePembayaran
from apps.produk.models import Produk, Gudang, Stok
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from apps.core.permissions import permission_required
import json
import logging  # Modul logging standar Python — pengganti print() untuk production
from decimal import Decimal

# Inisialisasi logger untuk modul POS
# Menggunakan __name__ agar nama logger sesuai nama modul (apps.pos.views)


# ╔══════════════════════════════════════════════════════════════╗
# ║                HALAMAN UTAMA POS                               ║
# ╚══════════════════════════════════════════════════════════════╝

class POSIndexView(CreatePermissionMixin, TemplateView):
    """
    Halaman utama POS/Kasir — menampilkan grid produk + keranjang.
    URL: /pos/
    
    Context:
    - produk_list: Semua produk diurutkan per kategori
    - kategori_list: Kategori unik dari produk (untuk tab filter)
    - metode_pembayaran: Daftar metode pembayaran aktif
    - gudang_list: Daftar gudang aktif + info pajak persen
    """
    template_name = 'pos/index.html'
    permission_module = 'pos'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Produk diurutkan per kategori agar tidak duplikat di regroup template
        produk_list = Produk.objects.select_related('kategori', 'satuan').order_by('kategori__nama', 'nama')
        context['produk_list'] = produk_list
        
        # Kategori unik dari produk yang ada (bukan semua kategori)
        from apps.produk.models import Kategori
        kategori_ids = produk_list.values_list('kategori_id', flat=True).distinct()
        context['kategori_list'] = Kategori.objects.filter(id__in=kategori_ids).order_by('nama')
        
        # Metode pembayaran aktif (cash, transfer, dll)
        context['metode_pembayaran'] = MetodePembayaran.objects.filter(aktif=True)
        # Metode pembayaran dipisah per tipe untuk 2 dropdown di POS payment modal
        context['metode_tunai'] = MetodePembayaran.objects.filter(aktif=True, tipe='tunai')
        context['metode_non_tunai'] = MetodePembayaran.objects.filter(aktif=True, tipe='non_tunai')
        # Gudang aktif + pajak persen (dipakai untuk kalkulasi di frontend)
        # Gudang aktif + pajak persen efektif (dengan fallback ke pengaturan perusahaan)
        gudang_qs = Gudang.objects.filter(aktif=True)
        gudang_data = []
        for g in gudang_qs:
            gudang_data.append({
                'id': g.id, 'nama': g.nama, 'kode': g.kode,
                'pajak_persen': float(g.get_tarif_ppn())
            })
        context['gudang_list'] = gudang_data
        # Customer terdaftar dari modul penjualan (untuk dropdown di modal pembayaran)
        from apps.penjualan.models import Customer
        context['customer_list'] = Customer.objects.filter(aktif=True).order_by('nama')
        # Daftar user aktif (untuk dropdown Pilih Kasir)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        context['user_list'] = User.objects.filter(is_active=True).order_by('first_name', 'username')
        
        # ═══════════════════════════════════════════════════════════════════
        # RATING PRODUK — Bintang 1-5 Berdasarkan Jumlah Pembelian (Qty Terjual)
        # ═══════════════════════════════════════════════════════════════════
        #
        # ALUR:
        # 1. Query POSTransactionItem yang transaksinya sudah lunas (status='paid')
        # 2. Group by produk_id → hitung total qty terjual (Sum jumlah)
        # 3. Cari produk paling laris (max_sold) sebagai patokan 100%
        # 4. Hitung rasio setiap produk terhadap max_sold
        # 5. Mapping rasio ke rating 1-5 (persentil):
        #    ≥80% → 5 bintang, ≥60% → 4, ≥40% → 3, ≥20% → 2, <20% → 1
        # 6. Produk yang belum pernah terjual → default 1 bintang
        # 7. Kirim sebagai JSON ke template → di-render oleh JavaScript
        #
        # CONTOH:
        # iPhone 17 Pro terjual 50 unit (paling laris) → rasio 100% → 5 bintang
        # iPhone 12 Pro terjual 30 unit → rasio 60% → 4 bintang
        # Beras terjual 5 unit → rasio 10% → 1 bintang
        # iPhone 15 Pro belum pernah terjual → default 1 bintang
        #
        # TERHUBUNG DENGAN:
        # - Model: POSTransactionItem (apps/pos/models.py) → sumber data qty terjual
        # - Template: pos/index.html → product_ratings_json dipakai oleh JS
        # - CSS: .product-stars .star-filled/.star-empty → styling bintang
        # ═══════════════════════════════════════════════════════════════════
        import json
        from django.db.models import Sum
        
        # LANGKAH 1: Query total qty terjual per produk dari transaksi POS lunas
        # - filter(transaction__status='paid') → hanya transaksi yang sudah dibayar
        # - values('produk_id') → group by produk
        # - annotate(total_sold=Sum('jumlah')) → hitung total qty terjual
        # - order_by('-total_sold') → urutkan dari paling laris
        purchase_counts = (
            POSTransactionItem.objects
            .filter(transaction__status='paid')
            .values('produk_id')
            .annotate(total_sold=Sum('jumlah'))
            .order_by('-total_sold')
        )
        
        # LANGKAH 2: Buat dictionary {produk_id: total_sold}
        # Contoh: {1: 50.0, 2: 30.0, 3: 5.0}
        sold_map = {item['produk_id']: float(item['total_sold']) for item in purchase_counts}
        
        # LANGKAH 3: Hitung rating 1-5 berdasarkan persentil terhadap max_sold
        if sold_map:
            max_sold = max(sold_map.values())  # Produk paling laris = patokan 100%
            rating_map = {}
            for produk_id, total in sold_map.items():
                if max_sold > 0:
                    ratio = total / max_sold   # Rasio terhadap produk paling laris
                    # Mapping rasio ke rating bintang (persentil)
                    if ratio >= 0.8:
                        rating_map[produk_id] = 5   # Top 20% → 5 bintang ⭐⭐⭐⭐⭐
                    elif ratio >= 0.6:
                        rating_map[produk_id] = 4   # 60-80% → 4 bintang ⭐⭐⭐⭐
                    elif ratio >= 0.4:
                        rating_map[produk_id] = 3   # 40-60% → 3 bintang ⭐⭐⭐
                    elif ratio >= 0.2:
                        rating_map[produk_id] = 2   # 20-40% → 2 bintang ⭐⭐
                    else:
                        rating_map[produk_id] = 1   # <20% → 1 bintang ⭐
                else:
                    rating_map[produk_id] = 1       # Edge case: max = 0
        else:
            rating_map = {}  # Tidak ada data penjualan sama sekali
        
        # LANGKAH 4: Kirim rating sebagai JSON string ke template
        # Format: {"1": 5, "2": 4, "3": 1} → diparse oleh JavaScript di template
        # Produk yang tidak ada di rating_map → JS default ke 1 bintang
        context['product_ratings_json'] = json.dumps(rating_map)
        
        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║              API ENDPOINTS (JSON via AJAX)                     ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@permission_required('create', 'pos')
@require_http_methods(["POST"])
def create_transaction(request):
    """
    API: Buat transaksi POS baru via AJAX POST.
    URL: /pos/api/create-transaction/

    Input JSON:
    {
      "items": [{"id": 1, "qty": 2, "price": 50000, "diskon": 0}, ...],
      "gudang_id": 1,
      "metode_pembayaran_id": 1,
      "customer_name": "Umum",
      "diskon": 0,
      "pajak": 0,
      "jumlah_bayar": 100000,
      "catatan": ""
    }

    Alur proses:
    1. Validasi: keranjang tidak kosong, gudang dipilih
    2. Validasi stok: cek setiap produk punya stok cukup
    3. Buat POSTransaction + items dalam atomic transaction
    4. Kurangi stok per item
    5. Hitung ulang total
    6. Kirim notifikasi Telegram
    7. Log activity stok keluar
    """
    try:
        data = json.loads(request.body)
        
        # Validasi keranjang
        if not data.get('items') or len(data['items']) == 0:
            return JsonResponse({
                'success': False,
                'message': 'Keranjang kosong! Tambahkan produk terlebih dahulu.'
            }, status=400)
        
        # Validasi gudang
        gudang_id = data.get('gudang_id')
        if not gudang_id:
            return JsonResponse({
                'success': False,
                'message': 'Pilih gudang terlebih dahulu!'
            }, status=400)
        
        gudang = get_object_or_404(Gudang, pk=gudang_id, aktif=True)
        metode_pembayaran_id = data.get('metode_pembayaran_id')
        metode_pembayaran = get_object_or_404(MetodePembayaran, pk=metode_pembayaran_id, aktif=True)
        
        # Import konversi satuan untuk handle unit berbeda
        from apps.produk.models import KonversiSatuan, Satuan

        # ===== HELPER: Hitung qty dalam satuan dasar produk =====
        def hitung_qty_stok(item_data, produk):
            """
            Konversi qty transaksi ke satuan dasar produk untuk pengurangan stok.

            Kenapa perlu konversi?
            - Produk disimpan dalam satuan dasar (misal: kilogram)
            - Tapi bisa dijual dalam satuan lain (misal: gram, ons)
            - Contoh: Jual 500 gram Beras → stok berkurang 0.5 kg

            Alur konversi:
            1. Jika satuan transaksi = satuan asli produk → tanpa konversi
            2. Jika berbeda → cari tabel KonversiSatuan:
               a. Cari konversi langsung (dari → ke)
               b. Jika tidak ada → cari konversi terbalik (ke → dari)
            3. Hitung: qty_stok = qty_input / faktor_konversi

            Args:
                item_data: Dict item dari request JSON (qty, satuan_id, satuan_id_asli)
                produk: Instance Produk terkait

            Returns:
                Decimal: Qty dalam satuan dasar produk (untuk kurangi stok)
            """
            qty_input = Decimal(str(item_data['qty']))
            satuan_id = item_data.get('satuan_id')
            satuan_id_asli = item_data.get('satuan_id_asli')
            qty_stok = qty_input  # Default: tanpa konversi

            if satuan_id and satuan_id_asli and int(satuan_id) != int(satuan_id_asli):
                konversi = KonversiSatuan.objects.filter(
                    dari_satuan_id=satuan_id_asli,
                    ke_satuan_id=satuan_id,
                    produk=produk
                ).first() or KonversiSatuan.objects.filter(
                    dari_satuan_id=satuan_id_asli,
                    ke_satuan_id=satuan_id,
                    produk__isnull=True
                ).first()

                if konversi:
                    qty_stok = qty_input / konversi.faktor_konversi
                else:
                    konversi_balik = KonversiSatuan.objects.filter(
                        dari_satuan_id=satuan_id,
                        ke_satuan_id=satuan_id_asli,
                        produk=produk
                    ).first() or KonversiSatuan.objects.filter(
                        dari_satuan_id=satuan_id,
                        ke_satuan_id=satuan_id_asli,
                        produk__isnull=True
                    ).first()
                    if konversi_balik:
                        qty_stok = qty_input * konversi_balik.faktor_konversi

            return qty_stok

        # ===== PROSES TRANSAKSI (atomic — rollback jika error) =====
        # PENTING: Validasi stok DAN pengurangan stok dalam SATU atomic block
        # dengan select_for_update() untuk mencegah race condition
        logger.info("Memulai proses transaksi POS — user: %s, gudang: %s, jumlah items: %d",
                    request.user.username, gudang.id, len(data['items']))

        with transaction.atomic():
            # VALIDASI STOK DENGAN LOCK — semua item dicek dalam atomic block
            for item_data in data['items']:
                produk = get_object_or_404(Produk, pk=item_data['id'])
                qty_stok = hitung_qty_stok(item_data, produk)

                try:
                    # select_for_update() mengunci baris stok agar thread lain menunggu
                    stok = Stok.objects.select_for_update().get(produk=produk, gudang=gudang)
                    if stok.jumlah < qty_stok:
                        satuan_nama = produk.satuan.singkatan if produk.satuan else 'pcs'
                        return JsonResponse({
                            'success': False,
                            'message': f'Stok {produk.nama} tidak mencukupi! Tersedia: {stok.jumlah} {satuan_nama}'
                        }, status=400)
                except Stok.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': f'Stok {produk.nama} tidak ditemukan di gudang {gudang.nama}!'
                    }, status=400)

            # Buat transaksi header
            pos_transaction = POSTransaction(
                kasir=request.user,
                gudang=gudang,
                nama_customer=data.get('customer_name', 'Umum'),
                diskon=max(Decimal('0'), Decimal(str(data.get('diskon', 0)))),
                pajak=max(Decimal('0'), Decimal(str(data.get('pajak', 0)))),
                metode_pembayaran=metode_pembayaran,
                jumlah_bayar=max(Decimal('0'), Decimal(str(data.get('jumlah_bayar', 0)))),
                status=data.get('status', 'paid'),  # Support kasbon: 'unpaid' jika dikirim dari frontend
                catatan=data.get('catatan', '')
            )

            # Jika status kasbon (unpaid), set jatuh tempo
            if pos_transaction.status == 'unpaid':
                from datetime import timedelta
                jatuh_tempo_str = data.get('jatuh_tempo', '')
                if jatuh_tempo_str:
                    from datetime import datetime as dt
                    try:
                        pos_transaction.jatuh_tempo = dt.strptime(jatuh_tempo_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pos_transaction.jatuh_tempo = timezone.now().date() + timedelta(days=30)
                else:
                    pos_transaction.jatuh_tempo = timezone.now().date() + timedelta(days=30)

            # Hubungkan dengan customer terdaftar jika ada
            customer_id = data.get('customer_id')
            if customer_id:
                from apps.penjualan.models import Customer
                try:
                    customer_obj = Customer.objects.get(pk=customer_id, aktif=True)
                    pos_transaction.customer = customer_obj
                    # Otomatis isi nama_customer dari data customer terdaftar
                    pos_transaction.nama_customer = customer_obj.nama
                except Customer.DoesNotExist:
                    pass  # Customer tidak ditemukan, lanjut dengan nama manual
                
            # Save dulu untuk generate PK dan nomor_transaksi
            pos_transaction.save()
            logger.info("Transaksi berhasil disave — ID: %s, Nomor: %s",
                        pos_transaction.id, pos_transaction.nomor_transaksi)
                
            # Buat items + kurangi stok dalam atomic block yang sama
            for idx, item_data in enumerate(data['items'], 1):
                produk = Produk.objects.get(pk=item_data['id'])
                qty_input = Decimal(str(item_data['qty']))

                logger.debug("Processing item %d/%d — Produk: %s, Qty: %s",
                             idx, len(data['items']), produk.nama, item_data['qty'])

                # Hitung qty dalam satuan dasar untuk stok
                qty_stok = hitung_qty_stok(item_data, produk)

                # Tentukan satuan transaksi
                from apps.produk.models import Satuan
                satuan_trx_id = item_data.get('satuan_id')
                satuan_trx_obj = None
                if satuan_trx_id:
                    try:
                        satuan_trx_obj = Satuan.objects.get(pk=satuan_trx_id)
                    except Satuan.DoesNotExist:
                        pass
                    
                # Buat item transaksi (harga & qty sesuai satuan transaksi)
                POSTransactionItem.objects.create(
                    transaction=pos_transaction,
                    produk=produk,
                    jumlah=qty_input,
                    harga_satuan=Decimal(str(item_data['price'])),
                    diskon=Decimal(str(item_data.get('diskon', 0))),
                    satuan_transaksi=satuan_trx_obj,
                    jumlah_konversi=qty_stok
                )
                logger.debug("Item transaksi berhasil dibuat untuk produk: %s (jumlah_konversi: %s)", produk.nama, qty_stok)
                    
                # Kurangi stok (dalam satuan dasar produk) — baris sudah ter-lock
                stok = Stok.objects.select_for_update().get(produk=produk, gudang=gudang)
                stok_awal = stok.jumlah
                logger.debug("Stok awal: %s", stok_awal)
                stok.jumlah -= qty_stok
                stok.save()
                logger.debug("Stok akhir: %s — dikurangi sebanyak %s (satuan dasar)", stok.jumlah, qty_stok)

                # Update cabang produk ke gudang dengan stok terbanyak
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                    produk.cabang = stok_terbanyak.gudang
                    produk.save(update_fields=['cabang'])
                
            logger.info("Transaksi %s BERHASIL!", pos_transaction.nomor_transaksi)
                
            # Hitung ulang total
            pos_transaction.calculate_total()
            pos_transaction.save()
        
        # Notifikasi dan log di luar atomic (opsional, tidak boleh rollback transaksi)
        try:
            from apps.automation.signals import kirim_notifikasi_pos
            kirim_notifikasi_pos(pos_transaction)
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            logger.warning("Gagal kirim notifikasi Telegram: %s", e)
        
        try:
            from apps.activity_log.stock_signals import log_pos_stock_out
            log_pos_stock_out(pos_transaction, request.user, request)
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            logger.warning("Gagal log activity stok keluar: %s", e)
        
        return JsonResponse({
            'success': True,
            'message': 'Transaksi berhasil!',
            'transaction_id': pos_transaction.id,
            'nomor_transaksi': pos_transaction.nomor_transaksi,
            'redirect_url': f'/pos/invoice/{pos_transaction.id}/'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Format data tidak valid!'
        }, status=400)
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        }, status=500)

@login_required
@permission_required('read', 'pos')
def check_stock(request, produk_id):
    """
    API: Cek stok produk di gudang tertentu.
    URL: /pos/api/check-stock/<produk_id>/?gudang_id=1
    Digunakan: saat user klik produk di grid POS
    """
    gudang_id = request.GET.get('gudang_id')
    
    if not gudang_id:
        return JsonResponse({
            'success': False,
            'message': 'Gudang tidak dipilih'
        }, status=400)
    
    try:
        produk = get_object_or_404(Produk, pk=produk_id)
        stok = Stok.objects.get(produk=produk, gudang_id=gudang_id)
        
        return JsonResponse({
            'success': True,
            'stok': float(stok.jumlah),
            'satuan': produk.satuan.nama if produk.satuan else 'pcs'
        })
    except Stok.DoesNotExist:
        return JsonResponse({
            'success': True,
            'stok': 0,
            'satuan': produk.satuan.nama if produk.satuan else 'pcs'
        })

@login_required
@permission_required('read', 'pos')
def search_products(request):
    """
    API: Search produk untuk autocomplete di POS.
    URL: /pos/api/search-products/?q=keyword&gudang_id=1
    Minimal 2 karakter untuk trigger search.
    """
    query = request.GET.get('q', '')
    gudang_id = request.GET.get('gudang_id')
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    products = Produk.objects.filter(
        nama__icontains=query
    ).select_related('kategori', 'satuan')[:10]
    
    results = []
    for produk in products:
        stok_tersedia = 0
        if gudang_id:
            try:
                stok = Stok.objects.get(produk=produk, gudang_id=gudang_id)
                stok_tersedia = float(stok.jumlah)
            except Stok.DoesNotExist:
                stok_tersedia = 0
        
        results.append({
            'id': produk.id,
            'nama': produk.nama,
            'sku': produk.sku,
            'harga': float(produk.harga_jual),
            'stok': stok_tersedia,
            'satuan': produk.satuan.nama if produk.satuan else 'pcs',
            'kategori': produk.kategori.nama if produk.kategori else '',
            'gambar': produk.gambar.url if produk.gambar else ''
        })
    
    return JsonResponse({'results': results})


@login_required
@permission_required('read', 'pos')
def get_stocks_by_gudang(request):
    """
    API: Ambil SEMUA stok produk berdasarkan gudang yang dipilih.
    URL: /pos/api/get-stocks-by-gudang/?gudang_id=1
    
    Digunakan: saat user pindah gudang di POS → update badge stok di grid.
    Return: dictionary produk_id → {jumlah, satuan}
    """
    gudang_id = request.GET.get('gudang_id')
    
    if not gudang_id:
        return JsonResponse({
            'success': False,
            'message': 'Gudang tidak dipilih'
        }, status=400)
    
    try:
        stoks = Stok.objects.filter(gudang_id=gudang_id).select_related('produk', 'produk__satuan')
        
        # Build dictionary: produk_id → info stok
        stock_data = {}
        for stok in stoks:
            stock_data[stok.produk_id] = {
                'jumlah': float(stok.jumlah),
                'satuan': stok.produk.satuan.nama if stok.produk.satuan else 'pcs'
            }
        
        return JsonResponse({
            'success': True,
            'gudang_id': int(gudang_id),
            'stocks': stock_data
        })
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        }, status=500)


@login_required
@permission_required('read', 'pos')
def lookup_barcode(request):
    """
    API: Cari produk berdasarkan barcode atau SKU.
    URL: /pos/api/lookup-barcode/?code=xxxxx
    Digunakan oleh scanner barcode kamera di halaman POS.
    
    Alur pencarian (prioritas):
    1. Cari exact match di field barcode
    2. Cari exact match di field SKU
    3. Jika tidak ditemukan → return error
    """
    code = request.GET.get('code', '').strip()
    
    if not code:
        return JsonResponse({
            'success': False,
            'message': 'Kode barcode kosong'
        }, status=400)
    
    # Cari berdasarkan barcode terlebih dahulu
    produk = Produk.objects.filter(barcode=code).select_related('kategori', 'satuan').first()
    
    # Jika tidak ditemukan, cari berdasarkan SKU
    if not produk:
        produk = Produk.objects.filter(sku=code).select_related('kategori', 'satuan').first()
    
    if not produk:
        return JsonResponse({
            'success': False,
            'message': f'Produk dengan barcode/SKU "{code}" tidak ditemukan'
        })
    
    return JsonResponse({
        'success': True,
        'produk': {
            'id': produk.id,
            'nama': produk.nama,
            'sku': produk.sku,
            'barcode': produk.barcode or '',
            'harga_jual': float(produk.harga_jual),
            'gambar': produk.gambar.url if produk.gambar else '',
            'satuan': produk.satuan.nama if produk.satuan else 'pcs',
            'satuan_id': produk.satuan.id if produk.satuan else None,
            'kategori': produk.kategori.nama if produk.kategori else '',
        }
    })


# ╔══════════════════════════════════════════════════════════════╗
# ║                  INVOICE CRUD                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class InvoiceListView(ReadPermissionMixin, ListView):
    """
    Daftar semua invoice/transaksi POS.
    URL: /pos/invoice/
    Paginated: 10 per halaman, urut terbaru dulu.
    """
    model = POSTransaction
    template_name = 'pos/invoice_list.html'
    context_object_name = 'transactions'
    ordering = ['-dibuat_pada']
    paginate_by = 10
    permission_module = 'pos'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'kasir', 'gudang', 'metode_pembayaran', 'customer'
        ).prefetch_related('items__produk')

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.db.models import Sum
        context['metode_pembayaran'] = MetodePembayaran.objects.filter(aktif=True)
        queryset = self.get_queryset()
        context['total_invoice'] = queryset.count()
        context['total_amount_invoice'] = queryset.filter(status='paid').aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        return context


class InvoiceDetailView(ReadPermissionMixin, DetailView):
    """Detail invoice POS. URL: /pos/invoice/<pk>/"""
    model = POSTransaction
    template_name = 'pos/invoice_detail.html'
    context_object_name = 'transaction'
    permission_module = 'pos'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.db.models import Sum
        queryset = self.get_queryset()
        context['total_invoice'] = queryset.count()
        context['total_amount_invoice'] = queryset.aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        return context


class InvoicePrintView(ReadPermissionMixin, DetailView):
    """
    Cetak struk invoice — TANPA TemplateLayout agar halaman bersih untuk print.
    URL: /pos/invoice/<pk>/print/
    URL: /pos/invoice/<pk>/print/?format=thermal — Cetak struk thermal 58mm/80mm
    URL: /pos/invoice/<pk>/print/?format=thermal&paper=58 — Kertas 58mm
    URL: /pos/invoice/<pk>/print/?format=thermal&paper=80 — Kertas 80mm (default)
    Menggunakan data perusahaan + template cetak dari pengaturan.
    """
    model = POSTransaction
    template_name = 'pos/invoice_print.html'
    context_object_name = 'transaction'
    permission_module = 'pos'

    def get_template_names(self):
        """Pilih template berdasarkan format: thermal atau standar."""
        fmt = self.request.GET.get('format', '')
        if fmt == 'thermal':
            return ['pos/invoice_print_thermal.html']
        return [self.template_name]
    
    def get_context_data(self, **kwargs):
        # TIDAK pakai TemplateLayout.init() — halaman print harus bersih
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        from apps.pengaturan.models import PengaturanPerusahaan, TemplateCetak
        context['perusahaan'] = PengaturanPerusahaan.load()
        context['template'] = TemplateCetak.get_template('invoice')

        # Parameter thermal
        fmt = self.request.GET.get('format', '')
        context['is_thermal'] = (fmt == 'thermal')
        paper = self.request.GET.get('paper', '80')
        context['paper_width'] = paper if paper in ('58', '80') else '80'

        return context


class InvoiceDeleteView(DeletePermissionMixin, DetailView):
    """
    Hapus invoice POS — return JSON untuk AJAX.
    URL: /pos/invoice/<pk>/delete/
    ⚠ Extends DetailView (bukan DeleteView) tapi punya method delete()
    """
    model = POSTransaction
    permission_module = 'pos'

    def get(self, request, *args, **kwargs):
        from django.http import JsonResponse
        return JsonResponse({
            'success': False,
            'message': 'Gunakan POST untuk menghapus invoice.'
        }, status=405)

    def post(self, request, *args, **kwargs):


        """Override post() agar memanggil delete() yang return JSON."""
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        from django.http import JsonResponse
        from django.db import transaction as db_transaction
        from apps.produk.models import Stok
        from apps.fraud_detection.signals import set_current_delete_user, clear_current_delete_user
        self.object = self.get_object()
        
        try:
            nomor_transaksi = self.object.nomor_transaksi

            # Reversal jurnal + cancel mutasi/piutang (propagation service)
            from apps.core.propagation import handle_document_delete
            handle_document_delete(self.object, user=request.user)

            if self.object.status in ('paid', 'unpaid'):
                with db_transaction.atomic():
                    for item in self.object.items.select_related('produk'):
                        qty_rollback = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
                        stok, _ = Stok.objects.select_for_update().get_or_create(
                            produk=item.produk,
                            gudang=self.object.gudang,
                            defaults={'jumlah': 0}
                        )
                        stok.jumlah += qty_rollback
                        stok.save()

                        # Update cabang produk ke gudang dengan stok terbanyak
                        produk = item.produk
                        stok_terbanyak = Stok.objects.filter(
                            produk=produk, jumlah__gt=0
                        ).order_by('-jumlah').first()
                        if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                            produk.cabang = stok_terbanyak.gudang
                            produk.save(update_fields=['cabang'])

                    set_current_delete_user(request.user)
                    self.object.delete()
                    clear_current_delete_user()
            else:
                set_current_delete_user(request.user)
                self.object.delete()
                clear_current_delete_user()
            return JsonResponse({
                'success': True, 
                'message': f'Invoice {nomor_transaksi} berhasil dihapus'
            })
        except ProtectedError:
            clear_current_delete_user()
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            clear_current_delete_user()
            return JsonResponse({
                'success': False, 
                'message': f'Gagal menghapus invoice: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
# ║              CANCEL POS TRANSACTION                            ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
@require_http_methods(["POST"])
def cancel_pos_transaction(request, pk):
    """Cancel POS transaction. URL: /pos/invoice/<pk>/cancel/ (POST AJAX)"""
    from django.http import JsonResponse
    from apps.pos.models import POSTransaction
    from apps.pos.services import transition_pos_status
    from apps.core.permissions import has_permission, is_superuser_role

    if not is_superuser_role(request.user) and not has_permission(request.user, 'write', 'pos'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    try:
        pos = POSTransaction.objects.get(pk=pk)
    except POSTransaction.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Transaksi POS tidak ditemukan.'}, status=404)

    if pos.status not in ['paid', 'unpaid']:
        return JsonResponse({'success': False, 'message': f'POS dengan status "{pos.get_status_display()}" tidak bisa dibatalkan.'}, status=400)

    try:
        transition_pos_status(pos, 'cancelled', user=request.user)
        return JsonResponse({'success': True, 'message': f'POS {pos.nomor_transaksi} berhasil dibatalkan. Jurnal pembalik dibuat, stok dikembalikan.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Gagal membatalkan: {str(e)}'}, status=400)
