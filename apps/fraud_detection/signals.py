"""
==========================================================================
 FRAUD DETECTION SIGNALS — Deteksi Anomali Otomatis via Django Signals
==========================================================================
 File ini berisi signal handlers yang berjalan OTOMATIS saat event tertentu
 terjadi di database (create, update, delete). Setiap signal mendeteksi
 potensi kecurangan dan otomatis membuat FraudAlert.

 Signal yang terdaftar:
 ┌────────────────────────────────────────────────────────────────────┐
 │ No │ Nama                        │ Trigger     │ Anomali          │
 ├────┼─────────────────────────────┼─────────────┼──────────────────┤
 │ 1  │ detect_hapus_lunas          │ pre_delete  │ Hapus Data Lunas │
 │ 2  │ detect_transaksi_diluar_jam │ post_save   │ Diluar Jam       │
 │ 3  │ detect_diskon_berlebihan    │ post_save   │ Diskon Besar     │
 │ 4  │ detect_adjustment_besar     │ post_save   │ Adj Stok Besar   │
 │ 5  │ blokir_stok_minus_pos       │ pre_save    │ Stok Minus       │
 └────────────────────────────────────────────────────────────────────┘

 Cara kerja signal di Django:
 - pre_delete  → Berjalan SEBELUM record dihapus (bisa cancel delete)
 - post_save   → Berjalan SETELAH record disimpan (hanya logging)
 - pre_save    → Berjalan SEBELUM record disimpan (bisa cancel save)

 Terhubung dengan:
 → models.py   — FraudRule.load() untuk cek aturan, FraudAlert.objects.create()
 → apps.py     — Signal diimport di AppConfig.ready() agar aktif saat startup
 → pos/models  — Signal mendeteksi POSTransaction, POSItem
 → penjualan   — Signal mendeteksi SalesOrder
 → pembelian   — Signal mendeteksi PurchaseOrder
 → inventory   — Signal mendeteksi AdjustmentStok

 Catatan penting:
 - Signal ini GLOBAL — berlaku untuk semua save/delete di semua app
 - Kita filter berdasarkan sender.__name__ agar hanya model tertentu yang didengar
 - Untuk menghindari circular import, model di-import secara lazy di dalam function
==========================================================================
"""

# Import standar Python
import logging          # Logging error ke file/console
import traceback        # Stack trace untuk debugging
from decimal import Decimal  # Aritmatika presisi untuk uang

# Import Django signals framework
from django.db.models.signals import pre_delete, post_save, pre_save  # 3 jenis event
from django.dispatch import receiver  # Decorator untuk mendaftarkan signal handler
from django.utils import timezone     # Timezone-aware datetime

# Import model Fraud Detection
from apps.fraud_detection.models import FraudRule, FraudAlert

# Logger — semua error signal masuk ke log 'apps.fraud_detection.signals'
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  FLAG BYPASS — Untuk menonaktifkan signal saat reset/restore
# ═══════════════════════════════════════════════════════════════
# Flag global yang diset True oleh fungsi reset_data() dan restore_data()
# di pengaturan/views.py SEBELUM melakukan bulk delete.
# Saat True, semua signal handler langsung return tanpa melakukan apapun.
# Ini mencegah FRAUD_BLOCK exception saat menghapus data secara massal.
#
# Penggunaan:
#   from apps.fraud_detection import signals as fraud_signals
#   fraud_signals._BYPASS_FRAUD_SIGNALS = True   # matikan signal
#   ... lakukan bulk delete ...
#   fraud_signals._BYPASS_FRAUD_SIGNALS = False  # nyalakan kembali
_BYPASS_FRAUD_SIGNALS = False

# Thread-local storage untuk menyimpan user yang sedang melakukan delete.
# Digunakan oleh detect_hapus_lunas untuk mengecualikan superuser dari
# FRAUD_BLOCK, sesuai deskripsi UI: "tidak bisa dihapus kecuali superuser".
#
# Penggunaan dari views.py sebelum delete:
#   from apps.fraud_detection import signals as fraud_signals
#   fraud_signals.set_current_delete_user(request.user)
#   instance.delete()
#   fraud_signals.clear_current_delete_user()
import threading
_thread_locals = threading.local()


def set_current_delete_user(user):
    """Set user yang sedang melakukan aksi delete (dipanggil dari views)."""
    _thread_locals.current_delete_user = user


def clear_current_delete_user():
    """Bersihkan user setelah delete selesai."""
    _thread_locals.current_delete_user = None


def _get_current_delete_user():
    """Ambil user yang sedang melakukan delete (internal)."""
    return getattr(_thread_locals, 'current_delete_user', None)


# ═══════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS — Fungsi pendukung yang dipakai oleh signals
# ═══════════════════════════════════════════════════════════════

# Lazy import model dari app lain agar tidak circular import.
# Kenapa lazy? Karena saat signals.py di-load di AppConfig.ready(),
# belum tentu semua model dari app lain sudah terdaftar.
# Dengan lazy import (di dalam fungsi), model baru diakses saat
# signal benar-benar dipanggil (runtime), bukan saat import time.
def _get_model(app_label, model_name):
    """
    Lazy import model dari app lain menggunakan django.apps.
    ──────────────────────────────────────────────────────────
    Contoh: _get_model('pos', 'POSTransaction')
    Return: model class atau None jika tidak ditemukan
    """
    from django.apps import apps
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def check_operasional_time():
    """
    Cek apakah waktu saat ini DILUAR jam operasional toko.
    ────────────────────────────────────────────────────────
    Membaca FraudRule.load() untuk mendapat jam_operasional_mulai
    dan jam_operasional_selesai, lalu bandingkan dengan waktu sekarang.

    Return:
    → (True, rule)  → Saat ini di LUAR jam operasional (anomali)
    → (False, None)  → Saat ini di DALAM jam operasional (normal)

    Digunakan oleh: detect_transaksi_diluar_jam()
    """
    try:
        rule = FraudRule.load()
        now_time = timezone.localtime().time()  # Waktu lokal saat ini (hanya jam:menit)
        # Jika sekarang SEBELUM jam buka ATAU SESUDAH jam tutup → diluar jam
        if now_time < rule.jam_operasional_mulai or now_time > rule.jam_operasional_selesai:
            return True, rule
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)
    return False, None


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 1: HAPUS DATA LUNAS (pre_delete)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali user mencoba menghapus record dari database
# Target model: POSTransaction, SalesOrder, PurchaseOrder
# Aksi:
#   1. Cek apakah status record = lunas/confirmed/completed
#   2. Jika ya → buat FraudAlert jenis 'hapus_lunas' severity 'high'
#   3. Jika FraudRule.block_delete_paid = True → BLOKIR DELETE (raise Exception)
#
# Kenapa penting?
# → Kasir nakal bisa menghapus transaksi yang sudah lunas setelah menerima
#   uang dari customer. Uang masuk kantong, record transaksi hilang.
#   Signal ini mendeteksi dan bisa memblokir aksi tersebut.

@receiver(pre_delete)
def detect_hapus_lunas(sender, instance, **kwargs):
    """
    Deteksi dan blokir penghapusan data transaksi lunas.
    ─────────────────────────────────────────────────────
    sender   = Model class yang dihapus (POSTransaction, SalesOrder, dll)
    instance = Record spesifik yang akan dihapus
    """
    model_name = sender.__name__
    # BYPASS: Jika flag bypass aktif (saat reset/restore data), skip semua pengecekan
    if _BYPASS_FRAUD_SIGNALS:
        return
    # Hanya pantau model transaksi utama (termasuk OrderService)
    if model_name in ['POSTransaction', 'SalesOrder', 'PurchaseOrder', 'OrderService']:
        try:
            # OrderService punya 2 jenis status: status (workflow) dan status_bayar (pembayaran)
            # Untuk deteksi fraud hapus-lunas, gunakan status_bayar pada OrderService
            if model_name == 'OrderService':
                status = getattr(instance, 'status_bayar', '')
            else:
                status = getattr(instance, 'status', '')
            # Hanya cek jika status = lunas/dikonfirmasi/selesai
            if status in ['paid', 'confirmed', 'delivered', 'completed', 'lunas', 'selesai', 'diambil']:
                rule = FraudRule.load()

                # Ambil user pelaku (kasir/pembuat) — berbeda field per model
                user = getattr(instance, 'kasir',
                    getattr(instance, 'created_by',
                        getattr(instance, 'dibuat_oleh',
                            getattr(instance, 'diterima_oleh', None))))
                # Ambil nominal transaksi
                nominal = getattr(instance, 'total_harga',
                    getattr(instance, 'grand_total',
                        getattr(instance, 'biaya_akhir', 0)))

                # BUAT FRAUD ALERT — record anomali di database
                FraudAlert.objects.create(
                    jenis='hapus_lunas',
                    severity='high',
                    deskripsi=f"Percobaan menghapus data lunas: {model_name} ID {instance.pk}",
                    user_terkait=user,
                    nominal=nominal,
                    model_name=model_name,
                    object_id=str(instance.pk)
                )

                # BLOKIR DELETE jika pengaturan aktif DAN user bukan superuser
                # Superuser dikecualikan sesuai deskripsi UI:
                # "tidak bisa dihapus oleh siapapun kecuali superuser"
                if rule.block_delete_paid:
                    current_user = _get_current_delete_user()
                    if current_user and getattr(current_user, 'is_superuser', False):
                        # Superuser diizinkan hapus — alert tetap tercatat
                        pass
                    else:
                        raise Exception("FRAUD_BLOCK: Penghapusan transaksi lunas diblokir oleh sistem keamanan Fraud Rule.")

        except Exception as e:
            # Jika exception berasal dari FRAUD_BLOCK → lempar kembali
            # agar delete benar-benar gagal (ini yang memblokir)
            if "FRAUD_BLOCK" in str(e):
                raise  # Re-raise agar delete dibatalkan
            # Jika error lain (database error, dll) → hanya log, jangan crash
            logger.error(f"Error in detect_hapus_lunas: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 2: TRANSAKSI DILUAR JAM OPERASIONAL (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali record BARU disimpan (created=True)
# Target model: POSTransaction, SalesOrder, PurchaseOrder
# Aksi: Buat FraudAlert jenis 'diluar_jam' severity 'medium'
#
# Kenapa penting?
# → Transaksi yang dibuat di luar jam operasional bisa mengindikasikan
#   akses tidak sah atau karyawan yang bekerja tanpa izin.
#   Contoh: transaksi jam 2 pagi → sangat mencurigakan.

@receiver(post_save)
def detect_transaksi_diluar_jam(sender, instance, created, **kwargs):
    """
    Deteksi transaksi yang dibuat di luar jam operasional.
    ─────────────────────────────────────────────────────
    Hanya berjalan saat record BARU dibuat (created=True),
    agar tidak trigger saat update data lama.
    """
    # Hanya untuk record BARU dari model transaksi utama (termasuk OrderService)
    if created and sender.__name__ in ['POSTransaction', 'SalesOrder', 'PurchaseOrder', 'OrderService']:
        try:
            is_outside, rule = check_operasional_time()
            if is_outside:
                now_time = timezone.localtime().time().strftime('%H:%M')
                user = getattr(instance, 'kasir',
                    getattr(instance, 'created_by',
                        getattr(instance, 'dibuat_oleh', None)))
                nominal = getattr(instance, 'total_harga',
                    getattr(instance, 'grand_total', 0))

                FraudAlert.objects.create(
                    jenis='diluar_jam',
                    severity='medium',
                    deskripsi=f"Transaksi dibuat diluar jam operasional ({now_time}): {sender.__name__} ID {instance.pk}",
                    user_terkait=user,
                    nominal=nominal,
                    model_name=sender.__name__,
                    object_id=str(instance.pk)
                )
        except Exception as e:
            logger.error(f"Error in detect_transaksi_diluar_jam: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 3: DISKON BERLEBIHAN (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali POSTransaction disimpan (create atau update)
# Target model: POSTransaction
# Aksi: Buat FraudAlert jenis 'diskon_besar' severity 'high'
#
# Kenapa penting?
# → Kasir bisa memberikan diskon berlebihan untuk teman/keluarga,
#   atau memberikan diskon lalu mengantongi selisihnya.
#   Contoh: Barang Rp 1.000.000 di-diskon 80% → kasir bayar sendiri Rp 200.000.

@receiver(post_save)
def detect_diskon_berlebihan(sender, instance, created, **kwargs):
    """
    Deteksi diskon yang melebihi batas FraudRule.max_discount_percent.
    ──────────────────────────────────────────────────────────────────
    Berlaku untuk create DAN update (bukan hanya created=True),
    karena kasir bisa edit diskon setelah transaksi dibuat.
    """
    if sender.__name__ == 'POSTransaction':
        try:
            rule = FraudRule.load()
            # Ambil subtotal (sebelum diskon)
            subtotal = getattr(instance, 'subtotal', 0)
            if not subtotal and hasattr(instance, 'get_subtotal'):
                subtotal = instance.get_subtotal()

            # Ambil nominal diskon (bisa field 'diskon' atau 'potongan')
            diskon_nominal = getattr(instance, 'diskon', getattr(instance, 'potongan', 0))

            # Hitung persentase diskon
            if subtotal and subtotal > 0 and diskon_nominal > 0:
                diskon_percent = (Decimal(str(diskon_nominal)) / Decimal(str(subtotal))) * Decimal('100.0')

                # Bandingkan dengan batas dari FraudRule
                if diskon_percent > rule.max_discount_percent:
                    user = getattr(instance, 'kasir', getattr(instance, 'created_by', None))

                    # Cegah duplikat alert untuk transaksi yang sama
                    alert_exists = FraudAlert.objects.filter(
                        jenis='diskon_besar',
                        model_name=sender.__name__,
                        object_id=str(instance.pk)
                    ).exists()

                    if not alert_exists:
                        FraudAlert.objects.create(
                            jenis='diskon_besar',
                            severity='high',
                            deskripsi=f"Diskon {diskon_percent:.2f}% melebihi batas {rule.max_discount_percent:.2f}% pada POS ID {instance.pk}",
                            user_terkait=user,
                            nominal=diskon_nominal,
                            model_name=sender.__name__,
                            object_id=str(instance.pk)
                        )
        except Exception as e:
            logger.error(f"Error in detect_diskon_berlebihan: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 4: ADJUSTMENT STOK BESAR (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali AdjustmentStok BARU dibuat (created=True)
# Target model: AdjustmentStok
# Threshold: qty > 50 unit ATAU nominal > Rp 1.000.000
# Aksi: Buat FraudAlert jenis 'adjustment_besar' severity 'high'
#
# Kenapa penting?
# → Adjustment stok adalah celah kecurangan klasik.
#   Karyawan gudang bisa menambah/mengurangi stok di sistem
#   tanpa perpindahan fisik barang → barang hilang secara diam-diam.
#   Threshold 50 pcs / Rp 1 juta untuk menangkap adjustment abnormal.

@receiver(post_save)
def detect_adjustment_besar(sender, instance, created, **kwargs):
    """
    Deteksi adjustment stok yang besar (qty > 50 atau nominal > Rp 1 juta).
    ───────────────────────────────────────────────────────────────────────
    Hanya untuk record BARU (created=True) agar tidak trigger saat update.
    """
    if created and sender.__name__ == 'AdjustmentStok':
        try:
            qty = getattr(instance, 'jumlah', 0)
            produk = getattr(instance, 'produk', None)
            harga = getattr(produk, 'harga_beli', 0) if produk else 0
            nominal = Decimal(str(qty)) * Decimal(str(harga))

            # Threshold: qty > 50 unit ATAU nominal > Rp 1.000.000
            if qty > 50 or nominal > Decimal('1000000'):
                user = getattr(instance, 'dibuat_oleh', getattr(instance, 'created_by', None))
                FraudAlert.objects.create(
                    jenis='adjustment_besar',
                    severity='high',
                    deskripsi=f"Adjustment stok besar terpantau pada produk {produk} sejumlah {qty} ({getattr(instance, 'tipe', '')})",
                    user_terkait=user,
                    nominal=nominal,
                    model_name=sender.__name__,
                    object_id=str(instance.pk)
                )
        except Exception as e:
            logger.error(f"Error in detect_adjustment_besar: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 5: BLOKIR STOK MINUS — POS ITEM (pre_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali POSItem (item baris POS) AKAN disimpan
# Target model: POSItem (baris item dalam transaksi POS)
# Aksi:
#   1. Cek apakah FraudRule.block_negative_stock = True
#   2. Jika ya, cek stok produk di gudang terkait
#   3. Jika qty > stok tersedia → BLOKIR SAVE (raise Exception)
#   4. Buat FraudAlert jenis 'stok_minus'
#
# Kenapa pre_save (bukan post_save)?
# → Karena kita perlu MENCEGAH save, bukan hanya melaporkan.
#   pre_save berjalan SEBELUM data masuk database.
#   Jika raise Exception di pre_save → record tidak jadi tersimpan.

@receiver(pre_save)
def blokir_stok_minus_pos(sender, instance, **kwargs):
    """
    Blokir item POS jika stok tidak mencukupi.
    ──────────────────────────────────────────────
    Hanya aktif jika FraudRule.block_negative_stock = True.
    Hanya cek untuk record BARU (instance.pk belum ada).

    Target model: POSTransactionItem (bukan POSItem — nama model aktual di pos/models.py)
    Field mapping:
        - instance.jumlah     = qty yang dibeli
        - instance.transaction = FK ke POSTransaction (parent)
        - instance.transaction.gudang = gudang terkait
    """
    if _BYPASS_FRAUD_SIGNALS:
        return

    if sender.__name__ == 'POSTransactionItem':
        try:
            rule = FraudRule.load()
            # Hanya berlaku jika flag block_negative_stock aktif
            if rule.block_negative_stock:
                produk = getattr(instance, 'produk', None)
                qty = getattr(instance, 'jumlah', 0)

                if produk and qty and qty > 0:
                    # Ambil gudang dari transaksi POS parent
                    transaksi = getattr(instance, 'transaction', None)
                    gudang = getattr(transaksi, 'gudang', None) if transaksi else None

                    if gudang:
                        # Cek stok tersedia di gudang terkait via Stok model
                        from apps.produk.models import Stok
                        try:
                            stok_obj = Stok.objects.get(produk=produk, gudang=gudang)
                            stok_tersedia = stok_obj.jumlah
                        except Stok.DoesNotExist:
                            stok_tersedia = 0

                        # Jika record BARU dan qty > stok → BLOKIR
                        if not instance.pk and qty > stok_tersedia:
                            # Catat anomali dulu
                            user = getattr(transaksi, 'kasir', None)
                            FraudAlert.objects.create(
                                jenis='stok_minus',
                                severity='medium',
                                deskripsi=f"POS Item diblokir: Kuantitas {qty} melebihi stok tersedia ({stok_tersedia}) untuk produk {produk.nama}",
                                user_terkait=user,
                                nominal=0,
                                model_name='POSTransactionItem',
                                object_id=''
                            )
                            # Raise exception → cancel save
                            raise Exception(f"FRAUD_BLOCK: Stok {produk.nama} tidak mencukupi (tersedia: {stok_tersedia}, diminta: {qty}).")
        except Exception as e:
            if "FRAUD_BLOCK" in str(e):
                raise  # Re-raise agar save dibatalkan
            logger.error(f"Error in blokir_stok_minus_pos: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 6: PENGGUNAAN SPAREPART ANOMALI (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali PenggunaanSparepart disimpan (create)
# Target model: PenggunaanSparepart (dari service_center)
# Aksi:
#   1. Deteksi jumlah sparepart yang sangat besar (> 10 unit per item)
#   2. Deteksi jika harga jual sparepart ke pelanggan LEBIH RENDAH dari harga modal
#
# Kenapa penting?
# → Teknisi bisa mengklaim penggunaan sparepart berlebihan untuk dijual kembali.
# → Harga jual sparepart di bawah modal bisa mengindikasikan manipulasi harga.

@receiver(post_save)
def detect_sparepart_anomali(sender, instance, created, **kwargs):
    """
    Deteksi penggunaan sparepart anomali pada service center.
    ─────────────────────────────────────────────────────────
    Hanya berjalan saat record BARU dibuat (created=True).
    """
    if _BYPASS_FRAUD_SIGNALS:
        return

    if created and sender.__name__ == 'PenggunaanSparepart':
        try:
            rule = FraudRule.load()

            # Ambil user teknisi dari order service
            order_service = getattr(instance, 'order_service', None)
            user = None
            if order_service:
                user = getattr(order_service, 'teknisi', None) or getattr(order_service, 'diterima_oleh', None)

            produk = getattr(instance, 'produk', None)
            jumlah = float(getattr(instance, 'jumlah', 0))
            harga_satuan = float(getattr(instance, 'harga_satuan', 0))

            produk_nama = produk.nama if produk else 'Unknown'
            order_nomor = order_service.nomor_service if order_service else 'N/A'

            # DIPERBAIKI #19: Baca threshold dari FraudRule (configurable via admin)
            max_qty = getattr(rule, 'max_sparepart_qty', None) or 10  # fallback ke 10 jika 0/null

            # 1. Deteksi jumlah sparepart yang sangat besar (> threshold)
            if jumlah > max_qty:
                FraudAlert.objects.create(
                    jenis='anomali_lainnya',
                    severity='medium',
                    deskripsi=(
                        f"Penggunaan sparepart dalam jumlah besar: {produk_nama} x{jumlah} "
                        f"pada Order Service {order_nomor}. "
                        f"Jumlah ini melebihi batas wajar (>{max_qty} unit per item)."
                    ),
                    user_terkait=user,
                    nominal=Decimal(str(jumlah * harga_satuan)),
                    model_name='PenggunaanSparepart',
                    object_id=str(instance.pk)
                )

            # 2. Deteksi harga jual LEBIH RENDAH dari harga modal
            if produk and hasattr(produk, 'harga_beli'):
                harga_modal = float(produk.harga_beli or 0)
                if harga_modal > 0 and harga_satuan < harga_modal:
                    selisih = harga_modal - harga_satuan
                    FraudAlert.objects.create(
                        jenis='anomali_lainnya',
                        severity='high',
                        deskripsi=(
                            f"Harga sparepart di bawah modal: {produk_nama} dijual Rp {harga_satuan:,.0f} "
                            f"(modal: Rp {harga_modal:,.0f}, selisih: Rp {selisih:,.0f}) "
                            f"pada Order Service {order_nomor}."
                        ),
                        user_terkait=user,
                        nominal=Decimal(str(selisih * jumlah)),
                        model_name='PenggunaanSparepart',
                        object_id=str(instance.pk)
                    )

        except Exception as e:
            logger.error(f"Error in detect_sparepart_anomali: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 7: BIAYA SERVICE ANOMALI (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali OrderService disimpan (update biaya_akhir)
# Deteksi: Biaya akhir = Rp 0 padahal sudah status selesai/diambil
#
# Kenapa penting?
# → Teknisi bisa menyelesaikan service tanpa mencatat biaya,
#   lalu menerima pembayaran langsung dari pelanggan secara tunai.

@receiver(post_save)
def detect_biaya_service_anomali(sender, instance, created, **kwargs):
    """
    Deteksi order service selesai tanpa biaya (gratis mencurigakan).
    """
    if _BYPASS_FRAUD_SIGNALS:
        return

    if sender.__name__ == 'OrderService' and not created:
        try:
            status = getattr(instance, 'status', '')
            biaya_akhir = float(getattr(instance, 'biaya_akhir', 0) or 0)

            # Order selesai/diambil tapi biaya Rp 0 → mencurigakan
            if status in ['selesai', 'diambil'] and biaya_akhir == 0:
                user = getattr(instance, 'teknisi', None) or getattr(instance, 'diterima_oleh', None)

                FraudAlert.objects.create(
                    jenis='anomali_lainnya',
                    severity='medium',
                    deskripsi=(
                        f"Order Service {instance.nomor_service} berstatus '{instance.get_status_display()}' "
                        f"tetapi biaya akhir Rp 0. Kemungkinan biaya tidak dicatat ke sistem."
                    ),
                    user_terkait=user,
                    nominal=Decimal('0'),
                    model_name='OrderService',
                    object_id=str(instance.pk)
                )
        except Exception as e:
            logger.error(f"Error in detect_biaya_service_anomali: {e}")



# ═══════════════════════════════════════════════════════════════
#  SIGNAL 6: ANOMALI PEMBAYARAN PIUTANG (post_save)
# ═══════════════════════════════════════════════════════════════
# Trigger: Setiap kali PembayaranPiutang BARU disimpan (created=True)
# Target model: PembayaranPiutang
# Aksi: Buat FraudAlert jenis 'anomali_lainnya' severity 'medium'/'high'
#
# Kenapa penting?
# → Pembayaran piutang melebihi sisa hutang bisa mengindikasikan:
#   - Salah input nominal (typo, salah desimal)
#   - Kecurangan: kasir memasukkan pembayaran palsu untuk "menutup" piutang
#   - Pembayaran ganda (double entry)

@receiver(post_save)
def detect_anomali_pembayaran_piutang(sender, instance, created, **kwargs):
    """
    Deteksi anomali pada pembayaran piutang:
    1. Jumlah bayar > sisa piutang (overpayment)
    2. Pembayaran di luar jam operasional
    """
    if _BYPASS_FRAUD_SIGNALS:
        return
    if sender.__name__ != 'PembayaranPiutang':
        return
    if not created:
        return

    try:
        piutang = getattr(instance, 'piutang', None)
        if not piutang:
            return

        from decimal import Decimal
        jumlah_bayar = Decimal(str(getattr(instance, 'jumlah', 0) or 0))
        # Hitung sisa SEBELUM pembayaran ini (jumlah_dibayar di piutang sudah include pembayaran ini)
        sisa_setelah = piutang.jumlah_total - piutang.jumlah_dibayar

        # 1. Cek overpayment: jika jumlah_dibayar > jumlah_total → anomali
        if piutang.jumlah_dibayar > piutang.jumlah_total:
            user = getattr(instance, 'created_by', None)
            FraudAlert.objects.create(
                jenis='anomali_lainnya',
                severity='high',
                deskripsi=(
                    f"Overpayment Piutang {piutang.nomor}: "
                    f"Total dibayar Rp {piutang.jumlah_dibayar:,.0f} "
                    f"melebihi piutang Rp {piutang.jumlah_total:,.0f}"
                ),
                user_terkait=user,
                nominal=jumlah_bayar,
                model_name='PembayaranPiutang',
                object_id=str(instance.pk)
            )

        # 2. Cek pembayaran di luar jam operasional
        is_outside, rule = check_operasional_time()
        if is_outside:
            now_time = timezone.localtime().time().strftime('%H:%M')
            user = getattr(instance, 'created_by', None)
            FraudAlert.objects.create(
                jenis='diluar_jam',
                severity='medium',
                deskripsi=(
                    f"Pembayaran piutang di luar jam operasional ({now_time}): "
                    f"Piutang {piutang.nomor}, jumlah Rp {jumlah_bayar:,.0f}"
                ),
                user_terkait=user,
                nominal=jumlah_bayar,
                model_name='PembayaranPiutang',
                object_id=str(instance.pk)
            )
    except Exception as e:
        logger.error(f"Error in detect_anomali_pembayaran_piutang: {e}")


# ═══════════════════════════════════════════════════════════════
#  SIGNAL 7: HAPUS PIUTANG ATAU PEMBAYARAN PIUTANG (pre_delete)
# ═══════════════════════════════════════════════════════════════
# Trigger: pre_delete pada Piutang / PembayaranPiutang
# Target: blokir penghapusan piutang yang sudah lunas/sebagian dibayar,
#         kecuali oleh superuser. Hindari "menghapus jejak" piutang lunas.

@receiver(pre_delete)
def detect_hapus_piutang_lunas(sender, instance, **kwargs):
    """
    Deteksi dan blokir penghapusan Piutang yang sudah ada pembayaran-nya,
    kecuali oleh superuser.
    """
    if _BYPASS_FRAUD_SIGNALS:
        return
    if sender.__name__ != 'Piutang':
        return

    try:
        status = getattr(instance, 'status', '')
        if status in ['lunas', 'sebagian']:
            rule = FraudRule.load()
            user = getattr(instance, 'created_by', None)
            nominal = getattr(instance, 'jumlah_total', 0)

            # Catat alert
            FraudAlert.objects.create(
                jenis='hapus_lunas',
                severity='high',
                deskripsi=(
                    f"Percobaan menghapus Piutang dengan status '{status}': "
                    f"{getattr(instance, 'nomor', instance.pk)}, "
                    f"sudah dibayar Rp {getattr(instance, 'jumlah_dibayar', 0):,.0f}"
                ),
                user_terkait=user,
                nominal=nominal,
                model_name='Piutang',
                object_id=str(instance.pk)
            )

            # Blokir untuk non-superuser jika rule aktif
            if getattr(rule, 'block_delete_paid', False):
                current_user = _get_current_delete_user()
                if current_user and getattr(current_user, 'is_superuser', False):
                    pass  # superuser diizinkan
                else:
                    raise Exception(
                        f"FRAUD_BLOCK: Penghapusan Piutang dengan status '{status}' "
                        "diblokir oleh sistem keamanan."
                    )
    except Exception as e:
        if "FRAUD_BLOCK" in str(e):
            raise
        logger.error(f"Error in detect_hapus_piutang_lunas: {e}")
