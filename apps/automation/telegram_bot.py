"""
==========================================================================
 TELEGRAM BOT - AI Chatbot Handler + Auto Polling
==========================================================================
 File ini menangani pesan masuk dari Telegram via polling otomatis.
 Bot berjalan otomatis saat Django startup tanpa perintah tambahan.
 User bisa langsung mengetik pertanyaan bebas dan bot akan menjawab
 dengan data real-time dari seluruh modul ERP.

 Fitur:
 1. Auto-polling — bot otomatis aktif saat server berjalan
 2. Free-text AI chat — ketik apapun, dijawab AI dengan data ERP
 3. Command shortcut — /start, /bantuan, /omset, /stok, dll
 4. Akses data penuh — penjualan, stok, biaya, HR, pelanggan, supplier
 5. System prompt kustom dari Pengaturan Telegram

 Keamanan:
 - Rate limiting per chat (max 10 pesan/menit)
 - Thread pool dengan batas max 5 worker (mencegah thread leak)
 - Response di-truncate agar tidak melebihi batas Telegram (4096 chars)
 - Bot token TIDAK pernah dicetak penuh di log
 - Semua error di-handle tanpa crash
==========================================================================
"""

import json
import logging
import time
import ssl
import urllib.request
import urllib.error
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Flag global untuk mencegah polling ganda
_polling_active = False
_polling_lock = threading.Lock()

# Thread pool untuk memproses pesan — MENCEGAH thread leak
# Max 5 worker agar tidak overload server/VPS
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="tg_bot")

# Rate limiting — max 10 pesan per menit per chat
_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()
_rate_last_cleanup = time.time()  # Timestamp terakhir cleanup global
RATE_LIMIT_MAX = 10       # Pesan per window
RATE_LIMIT_WINDOW = 60    # Detik
RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup global setiap 5 menit

# Batas karakter Telegram
TELEGRAM_MAX_LENGTH = 4096


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT DEFAULT — Personality dan perilaku AI Bot
# ═══════════════════════════════════════════════════════════════
TELEGRAM_SYSTEM_PROMPT = """Kamu adalah SERPTECH AI Assistant, asisten bisnis cerdas yang terintegrasi langsung dengan sistem ERP SERPTECH.

IDENTITAS:
- Nama: SERPTECH AI Assistant
- Peran: Asisten bisnis profesional yang membantu pengguna memantau dan menganalisa data bisnis secara real-time
- Platform: Telegram Bot

PERILAKU:
- Selalu gunakan Bahasa Indonesia yang sopan, profesional, dan mudah dipahami
- Sapa pengguna dengan ramah
- Berikan jawaban yang ringkas, padat, dan informatif
- Gunakan emoji secara proporsional untuk memperjelas poin penting
- Gunakan format list/bullet points (• atau -) untuk data yang terstruktur
- JANGAN gunakan tabel markdown karena ini adalah Telegram chat
- Jika data tidak tersedia atau kosong, jelaskan dengan baik dan berikan saran alternatif
- Selalu berikan insight/analisa singkat di akhir jawaban jika memungkinkan
- Format angka uang selalu dalam Rupiah (Rp) dengan pemisah titik, contoh: Rp 1.500.000
- Jika pengguna menyapa (halo, hi, dll), balas dengan ramah DAN berikan ringkasan singkat bisnis hari ini
- Batasi jawaban maksimal 250 kata agar ringkas di layar Telegram/mobile

KEMAMPUAN:
- Mengakses data penjualan (POS & Sales Order)
- Mengakses data pembelian (Purchase Order)
- Mengakses data stok & produk
- Mengakses data biaya/pengeluaran
- Mengakses data penggajian & karyawan
- Mengakses data pelanggan & supplier
- Mengakses data metode pembayaran & saldo
- Memberikan analisa bisnis & rekomendasi
- Memberikan ringkasan eksekutif dan laporan singkat
- Melakukan perbandingan periode (harian, mingguan, bulanan)
- Analisa SWOT, forecasting, rencana aksi
- Deteksi risiko bisnis dan anomali
- Analisa margin produk dan stok kritis
- Analisa pelanggan (top customer, tidak aktif, frekuensi beli)
- Copywriting dan content generator produk

BATASAN:
- Hanya menjawab pertanyaan seputar bisnis dan data ERP
- Tidak melakukan perubahan data (hanya baca/analisa)
- Jika pertanyaan di luar konteks bisnis, arahkan kembali dengan sopan
- Jika diminta hal yang tidak bisa dilakukan, jelaskan dengan jujur"""


def _mask_token(token):
    """Mask bot token untuk keamanan log — hanya tampilkan 8 karakter awal."""
    if not token or len(token) < 10:
        return '***'
    return token[:8] + '...'


def _check_rate_limit(chat_id):
    """
    Cek apakah chat sudah melebihi batas rate limit.
    Returns True jika masih diizinkan, False jika terlalu banyak.
    Juga melakukan periodic cleanup untuk mencegah memory leak.
    """
    global _rate_last_cleanup
    now = time.time()
    key = str(chat_id)

    with _rate_lock:
        # ── Periodic cleanup: hapus SEMUA key yang expired ──
        # Ini mencegah memory leak dari chat_id yang tidak pernah
        # mengirim pesan lagi (key menumpuk tanpa dibersihkan)
        if now - _rate_last_cleanup > RATE_LIMIT_CLEANUP_INTERVAL:
            expired_keys = [
                k for k, timestamps in _rate_limits.items()
                if not timestamps or (now - max(timestamps)) > RATE_LIMIT_WINDOW
            ]
            for k in expired_keys:
                del _rate_limits[k]
            _rate_last_cleanup = now

        # Bersihkan entry yang sudah expired untuk key ini
        _rate_limits[key] = [
            t for t in _rate_limits[key]
            if now - t < RATE_LIMIT_WINDOW
        ]
        if len(_rate_limits[key]) >= RATE_LIMIT_MAX:
            return False
        _rate_limits[key].append(now)
        return True


def _truncate_response(text):
    """
    Potong response agar tidak melebihi batas karakter Telegram (4096).
    Jika dipotong, tambahkan indikator di akhir.
    """
    if not text or len(text) <= TELEGRAM_MAX_LENGTH:
        return text
    truncated = text[:TELEGRAM_MAX_LENGTH - 30]
    # Potong di batas kata terakhir agar tidak terpotong di tengah kata
    last_newline = truncated.rfind('\n')
    if last_newline > TELEGRAM_MAX_LENGTH - 200:
        truncated = truncated[:last_newline]
    return truncated + "\n\n_(pesan terpotong)_"


# ═══════════════════════════════════════════════════════════════
# AUTO POLLING — Bot otomatis aktif saat server berjalan
# ═══════════════════════════════════════════════════════════════

def start_polling():
    """
    Mulai polling bot Telegram di background thread.
    Dipanggil dari apps.py ready() saat Django startup.
    Thread berjalan sebagai daemon sehingga otomatis berhenti saat server stop.
    """
    global _polling_active

    with _polling_lock:
        if _polling_active:
            return  # Sudah berjalan
        _polling_active = True

    thread = threading.Thread(target=_polling_loop, daemon=True)
    thread.start()
    print("[TelegramBot] Auto-polling dimulai di background thread")
    logger.info("[TelegramBot] Auto-polling dimulai di background thread")


def _polling_loop():
    """Loop utama polling — cek pesan baru dari Telegram secara berkala."""
    global _polling_active

    # Tunggu agar Django selesai startup dan DB siap
    time.sleep(3)

    try:
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()

        if not pengaturan.bot_token:
            logger.warning("[TelegramBot] Bot Token belum dikonfigurasi, polling tidak dimulai")
            print("[TelegramBot] Bot Token belum dikonfigurasi")
            _polling_active = False
            return

        bot_token = pengaturan.bot_token.strip()

        # SSL context
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        # Hapus webhook agar getUpdates berfungsi
        _delete_webhook(bot_token, ssl_ctx)

        # Skip pesan lama yang menumpuk — mulai dari update terbaru saja
        offset = _get_latest_offset(bot_token, ssl_ctx)

        print(f"[TelegramBot] Polling aktif - Token: {_mask_token(bot_token)}")
        logger.info(f"[TelegramBot] Polling aktif — Token: {_mask_token(bot_token)}")

        conflict_count = 0
        conflict_logged = False
        consecutive_errors = 0

        while _polling_active:
            try:
                url = (
                    f"https://api.telegram.org/bot{bot_token}/getUpdates"
                    f"?offset={offset}&timeout=30&limit=10"
                )
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=35, context=ssl_ctx)
                data = json.loads(resp.read().decode('utf-8'))

                # Reset error counters setelah sukses
                conflict_count = 0
                conflict_logged = False
                consecutive_errors = 0

                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        update_id = update.get('update_id', 0)
                        offset = update_id + 1

                        # Proses update via thread pool (bukan spawn thread baru)
                        try:
                            _executor.submit(handle_update, update)
                        except RuntimeError:
                            # Thread pool sudah di-shutdown (server stop)
                            _polling_active = False
                            return

            except urllib.error.HTTPError as e:
                error_body = ''
                try:
                    error_body = e.read().decode('utf-8', errors='replace')
                except Exception:
                    pass

                if e.code == 409 or 'conflict' in error_body.lower():
                    conflict_count += 1
                    wait = min(conflict_count * 10, 35)
                    # Hanya log SEKALI, jangan spam terminal
                    if not conflict_logged:
                        print("[TelegramBot] Ada sesi polling lain yang aktif, menunggu...")
                        conflict_logged = True
                    time.sleep(wait)
                    continue
                else:
                    consecutive_errors += 1
                    logger.warning(f"[TelegramBot] HTTP error {e.code}: {error_body[:200]}")
                    time.sleep(min(consecutive_errors * 5, 30))

            except urllib.error.URLError as e:
                # URLError membungkus banyak jenis error termasuk timeout
                reason_str = str(e.reason).lower() if e.reason else ''
                if 'timed out' in reason_str or isinstance(e.reason, TimeoutError):
                    # Timeout adalah NORMAL untuk long polling
                    # getUpdates timeout=30 → jika tidak ada pesan, timeout
                    continue
                consecutive_errors += 1
                logger.warning(f"[TelegramBot] Koneksi error: {e.reason}")
                time.sleep(min(consecutive_errors * 5, 60))

            except (TimeoutError, ConnectionError) as e:
                # TimeoutError langsung dari socket — NORMAL long polling
                if 'timed out' in str(e).lower():
                    continue
                consecutive_errors += 1
                logger.warning(f"[TelegramBot] Koneksi terputus, retry...")
                time.sleep(min(consecutive_errors * 5, 60))

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[TelegramBot] Polling error: {e}")
                time.sleep(min(consecutive_errors * 5, 60))

            time.sleep(1)

    except Exception as e:
        logger.error(f"[TelegramBot] Fatal polling error: {e}", exc_info=True)
    finally:
        _polling_active = False


def _delete_webhook(bot_token, ssl_ctx):
    """Hapus webhook agar getUpdates berfungsi."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        req = urllib.request.Request(url, method='POST')
        resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('ok'):
            logger.info("[TelegramBot] Webhook dihapus (beralih ke polling)")
    except Exception as e:
        logger.warning(f"[TelegramBot] Gagal hapus webhook: {e}")


def _get_latest_offset(bot_token, ssl_ctx):
    """
    Ambil offset terbaru agar pesan lama yang menumpuk di-skip.
    Saat server restart, bot tidak akan memproses pesan lama,
    hanya pesan baru setelah bot aktif.
    """
    for attempt in range(5):
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&limit=1&timeout=1"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5, context=ssl_ctx)
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok') and data.get('result'):
                latest_id = data['result'][-1].get('update_id', 0)
                print(f"[TelegramBot] Skip pesan lama, mulai dari offset {latest_id + 1}")
                return latest_id + 1
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 409:
                wait = (attempt + 1) * 10
                print(f"[TelegramBot] Menunggu sesi lama selesai ({wait}s)...")
                time.sleep(wait)
                continue
            print(f"[TelegramBot] HTTP error saat ambil offset: {e.code}")
            return 0
        except Exception as e:
            print(f"[TelegramBot] Gagal ambil latest offset: {e}")
            return 0
    return 0


# ═══════════════════════════════════════════════════════════════
# HANDLER UTAMA — Proses setiap pesan masuk
# ═══════════════════════════════════════════════════════════════

def handle_update(update_data):
    """
    Handler utama untuk setiap update dari Telegram.
    Dipanggil dari polling loop atau webhook.
    """
    try:
        from django.db import close_old_connections
        close_old_connections()

        message = update_data.get('message', {})
        if not message:
            return

        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        user_name = message.get('from', {}).get('first_name', 'User')

        if not chat_id or not text:
            return

        # Rate limiting — cegah spam/abuse
        if not _check_rate_limit(chat_id):
            logger.warning(f"[TelegramBot] Rate limit exceeded: [{chat_id}]")
            _send_reply(chat_id, "⚠️ Terlalu banyak pesan. Mohon tunggu sebentar.")
            return

        logger.info(f"[TelegramBot] 📩 [{chat_id}] {user_name}: {text[:100]}")

        # Proses command atau free-text
        if text.startswith('/'):
            response_text = _handle_command(text, user_name)
        else:
            response_text = _handle_free_text(text, user_name)

        # Kirim balasan
        if response_text:
            # Truncate response agar tidak melebihi batas Telegram
            response_text = _truncate_response(response_text)
            _send_reply(chat_id, response_text)

    except Exception as e:
        logger.error(f"[TelegramBot] Error handle update: {e}", exc_info=True)


def _send_reply(chat_id, text):
    """Kirim balasan ke chat Telegram."""
    try:
        from .telegram_service import kirim_pesan_telegram
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()

        if pengaturan.bot_token:
            success, _ = kirim_pesan_telegram(
                pengaturan.bot_token,
                str(chat_id),
                text
            )
            if success:
                logger.info(f"[TelegramBot] Balasan terkirim ke [{chat_id}]")
            else:
                logger.error(f"[TelegramBot] Gagal kirim ke [{chat_id}]")
    except Exception as e:
        logger.error(f"[TelegramBot] Error kirim reply: {e}")


# ═══════════════════════════════════════════════════════════════
# COMMAND HANDLER
# ═══════════════════════════════════════════════════════════════

def _handle_command(text, user_name):
    """Proses command Telegram (/start, /bantuan, dll)"""
    command = text.split()[0].lower().split('@')[0]

    if command == '/start':
        return (
            f"👋 Halo {user_name}!\n\n"
            "🤖 Saya adalah *SERPTECH AI Assistant*\n"
            "Saya bisa membantu Anda memantau dan menganalisa bisnis "
            "langsung dari Telegram.\n\n"
            "💬 *Langsung ketik pertanyaan Anda!*\n"
            "Saya bisa menjawab apapun tentang data bisnis Anda.\n\n"
            "Contoh:\n"
            "  • _Berapa omset hari ini?_\n"
            "  • _Produk apa yang paling laris?_\n"
            "  • _Analisa pengeluaran bulan ini_\n"
            "  • _Ringkasan bisnis hari ini_\n"
            "  • _Stok mana yang hampir habis?_\n\n"
            "📋 *Command cepat:*\n"
            "━━━━━━━━━━━━━━━\n"
            "/omset — Omset hari ini\n"
            "/stok — Stok rendah\n"
            "/pengeluaran — Biaya hari ini\n"
            "/gaji — Penggajian\n"
            "/produk — Info produk\n"
            "/pelanggan — Data pelanggan\n"
            "/supplier — Data supplier\n"
            "/laporan — Laporan AI\n"
            "/bantuan — Menu bantuan"
        )

    elif command in ('/bantuan', '/help'):
        return (
            "📚 *BANTUAN SERPTECH AI BOT*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "💬 *Ketik pertanyaan bebas:*\n"
            "Saya terhubung ke seluruh data sistem ERP.\n"
            "Tanya apapun dan saya akan menjawab!\n\n"
            "Contoh:\n"
            "  • _Berapa total penjualan minggu ini?_\n"
            "  • _Produk mana yang paling laris?_\n"
            "  • _Analisa pengeluaran bulan ini_\n"
            "  • _Executive summary bisnis_\n"
            "  • _Berapa keuntungan bulan ini?_\n"
            "  • _Siapa pelanggan terbesar?_\n"
            "  • _Analisa SWOT bisnis_\n"
            "  • _Stok yang hampir habis?_\n"
            "  • _Prediksi penjualan bulan depan_\n"
            "  • _Buat caption promosi produk_\n\n"
            "📋 *Command cepat:*\n"
            "/omset • /stok • /pengeluaran\n"
            "/gaji • /produk • /pelanggan\n"
            "/supplier • /laporan"
        )

    elif command == '/omset':
        return _handle_free_text("Berikan ringkasan omset hari ini dari POS dan Sales Order secara detail", user_name)

    elif command == '/stok':
        return _handle_free_text("Tampilkan data stok produk, terutama yang stok rendah atau habis", user_name)

    elif command == '/pengeluaran':
        return _handle_free_text("Berikan data pengeluaran dan biaya operasional hari ini secara detail", user_name)

    elif command == '/gaji':
        return _handle_free_text("Tampilkan ringkasan data penggajian dan karyawan bulan ini", user_name)

    elif command == '/produk':
        return _handle_free_text("Tampilkan ringkasan data produk, kategori, dan stok secara detail", user_name)

    elif command == '/pelanggan':
        return _handle_free_text("Tampilkan data pelanggan, top customer, dan analisa pelanggan", user_name)

    elif command == '/supplier':
        return _handle_free_text("Tampilkan data supplier dan purchase order terkini", user_name)

    elif command == '/laporan':
        return _handle_free_text(
            "Berikan laporan ringkasan bisnis hari ini meliputi omset, "
            "pengeluaran, stok kritis, dan status operasional secara lengkap",
            user_name
        )

    else:
        # Command tidak dikenal → langsung proses sebagai free-text
        clean_text = text.lstrip('/')
        return _handle_free_text(clean_text, user_name)


# ═══════════════════════════════════════════════════════════════
# FREE-TEXT AI HANDLER — Pembahasan luas dengan data ERP penuh
# ═══════════════════════════════════════════════════════════════

def _gather_comprehensive_data():
    """
    Kumpulkan data dari SELURUH modul ERP untuk memberikan konteks
    yang luas ke AI. Ini memastikan bot bisa menjawab pertanyaan
    apapun tentang bisnis tanpa terbatas pada satu intent saja.
    """
    from django.utils import timezone
    from django.db.models import Sum, Count
    today = timezone.now().date()
    month_start = today.replace(day=1)
    sections = []

    # ── OMSET & PENJUALAN ────────────────────────
    try:
        from apps.pos.models import POSTransaction
        from apps.penjualan.models import SalesOrder

        pos_today = POSTransaction.objects.filter(tanggal__date=today, status='paid')
        pos_count = pos_today.count()
        pos_total = float(pos_today.aggregate(t=Sum('total_harga'))['t'] or 0)

        pos_month = POSTransaction.objects.filter(tanggal__date__gte=month_start, status='paid')
        pos_month_total = float(pos_month.aggregate(t=Sum('total_harga'))['t'] or 0)
        pos_month_count = pos_month.count()

        so_today = SalesOrder.objects.filter(tanggal__date=today).exclude(status='cancelled')
        so_count = so_today.count()
        so_total = float(so_today.aggregate(t=Sum('total_harga'))['t'] or 0)

        so_month = SalesOrder.objects.filter(
            tanggal__date__gte=month_start,
            status__in=['confirmed', 'delivered', 'completed']
        )
        so_month_total = float(so_month.aggregate(t=Sum('total_harga'))['t'] or 0)
        so_month_count = so_month.count()

        sections.append(f"""PENJUALAN:
- Omset POS hari ini: Rp {pos_total:,.0f} ({pos_count} transaksi)
- Omset Sales Order hari ini: Rp {so_total:,.0f} ({so_count} order)
- Total omset hari ini: Rp {pos_total + so_total:,.0f}
- Omset POS bulan ini: Rp {pos_month_total:,.0f} ({pos_month_count} transaksi)
- Omset SO bulan ini: Rp {so_month_total:,.0f} ({so_month_count} order)
- Total omset bulan ini: Rp {pos_month_total + so_month_total:,.0f}""")
    except Exception as e:
        sections.append(f"PENJUALAN: Data tidak tersedia")

    # ── PRODUK & STOK ────────────────────────────
    try:
        from apps.produk.models import Produk
        total_produk = Produk.objects.filter(aktif=True).count()
        stok_habis = Produk.objects.filter(aktif=True, stok__lte=0).count()
        stok_rendah = Produk.objects.filter(aktif=True, stok__gt=0, stok__lt=10).count()

        produk_list = ""
        low = Produk.objects.filter(aktif=True, stok__lt=10).order_by('stok')[:5]
        for p in low:
            produk_list += f"\n  - {p.nama}: stok {p.stok}"

        sections.append(f"""PRODUK & STOK:
- Total produk aktif: {total_produk}
- Stok habis (0): {stok_habis} produk
- Stok rendah (<10): {stok_rendah} produk
- Produk stok terendah:{produk_list if produk_list else ' (semua cukup)'}""")
    except Exception:
        sections.append("PRODUK: Data tidak tersedia")

    # ── BIAYA / PENGELUARAN ────────────────────────
    try:
        from apps.biaya.models import TransaksiBiaya
        biaya_today = TransaksiBiaya.objects.filter(tanggal=today)
        biaya_today_total = float(biaya_today.aggregate(t=Sum('jumlah'))['t'] or 0)
        biaya_today_count = biaya_today.count()

        biaya_month = TransaksiBiaya.objects.filter(tanggal__gte=month_start, tanggal__lte=today)
        biaya_month_total = float(biaya_month.aggregate(t=Sum('jumlah'))['t'] or 0)

        sections.append(f"""BIAYA & PENGELUARAN:
- Biaya hari ini: Rp {biaya_today_total:,.0f} ({biaya_today_count} transaksi)
- Biaya bulan ini: Rp {biaya_month_total:,.0f}""")
    except Exception:
        sections.append("BIAYA: Data tidak tersedia")

    # ── PELANGGAN ────────────────────────────
    try:
        from apps.penjualan.models import Customer
        total_customer = Customer.objects.count()
        aktif_customer = Customer.objects.filter(aktif=True).count()
        sections.append(f"""PELANGGAN:
- Total pelanggan: {total_customer}
- Pelanggan aktif: {aktif_customer}""")
    except Exception:
        sections.append("PELANGGAN: Data tidak tersedia")

    # ── SUPPLIER & PEMBELIAN ────────────────────
    try:
        from apps.pembelian.models import Supplier, PurchaseOrder
        total_supplier = Supplier.objects.filter(aktif=True).count()
        po_draft = PurchaseOrder.objects.filter(status='draft').count()
        po_month = PurchaseOrder.objects.filter(tanggal__date__gte=month_start).exclude(status='cancelled').count()
        po_month_val = float(PurchaseOrder.objects.filter(
            tanggal__date__gte=month_start, status__in=['approved', 'received']
        ).aggregate(t=Sum('total_harga'))['t'] or 0)
        sections.append(f"""SUPPLIER & PEMBELIAN:
- Supplier aktif: {total_supplier}
- PO bulan ini: {po_month} (Rp {po_month_val:,.0f})
- PO draft/pending: {po_draft}""")
    except Exception:
        sections.append("PEMBELIAN: Data tidak tersedia")

    # ── HR & PENGGAJIAN ────────────────────────
    try:
        from apps.hr.models import Karyawan, Penggajian
        now = datetime.now()
        total_karyawan = Karyawan.objects.filter(aktif=True).count()
        gaji_qs = Penggajian.objects.filter(periode_bulan=now.month, periode_tahun=now.year)
        total_gaji = float(gaji_qs.aggregate(t=Sum('gaji_bersih'))['t'] or 0)
        gaji_dibayar = gaji_qs.filter(status='dibayar').count()
        gaji_pending = gaji_qs.exclude(status='dibayar').count()
        sections.append(f"""HR & PENGGAJIAN:
- Karyawan aktif: {total_karyawan}
- Slip gaji bulan ini: {gaji_qs.count()} (total Rp {total_gaji:,.0f})
- Sudah dibayar: {gaji_dibayar}, pending: {gaji_pending}""")
    except Exception:
        sections.append("HR: Data tidak tersedia")

    return "\n\n".join(sections)


def _handle_free_text(text, user_name):
    """
    Proses pertanyaan bebas menggunakan AI dengan akses data ERP penuh.
    Bot mengumpulkan data dari SEMUA modul untuk memberikan jawaban
    yang komprehensif, tidak terbatas pada satu topik saja.
    """
    try:
        from django.db import close_old_connections
        close_old_connections()

        from apps.ai_assistant.models import AIAssistantConfig
        from apps.ai_assistant.intents import detect_intent, gather_data
        from .models import PengaturanTelegram

        config = AIAssistantConfig.load()
        tg_config = PengaturanTelegram.load()

        if not config.api_key:
            return (
                "⚠️ AI Assistant belum dikonfigurasi.\n"
                "Silakan atur API Key di halaman Pengaturan AI Assistant."
            )

        # Deteksi intent untuk data spesifik
        intent = detect_intent(text)

        # Kumpulkan data sesuai intent
        # Untuk intent spesifik: hanya ambil data yang relevan (hemat query DB)
        # Untuk intent umum/bantuan: ambil data dari SEMUA modul
        if intent in ('umum', 'bantuan'):
            # Intent umum → kumpulkan data lengkap dari SEMUA modul ERP
            ringkasan = _gather_comprehensive_data()
        else:
            # Intent spesifik → ambil data spesifik dari intent + ringkasan singkat
            data_specific = gather_data(intent, text)
            if isinstance(data_specific, dict):
                ringkasan_spesifik = data_specific.get('ringkasan', '')
            else:
                ringkasan_spesifik = str(data_specific)

            # Tambahkan data pendukung yang RINGAN (tanpa query tambahan)
            # agar AI tetap punya konteks bisnis umum
            ringkasan_lengkap = _gather_comprehensive_data()
            ringkasan = f"{ringkasan_spesifik}\n\n--- Data Pendukung ---\n{ringkasan_lengkap}"

        # Build system prompt
        system_prompt = TELEGRAM_SYSTEM_PROMPT
        if tg_config.system_prompt_bot:
            system_prompt += f"\n\nINSTRUKSI KUSTOM TELEGRAM:\n{tg_config.system_prompt_bot}"
        if config.system_prompt:
            system_prompt += f"\n\nINSTRUKSI TAMBAHAN:\n{config.system_prompt}"

        prompt = f"Data Sistem ERP (real-time):\n{ringkasan}\n\nPesan dari {user_name}: {text}"

        # Panggil AI
        ai_response = None
        provider = config.provider
        api_key = config.api_key
        model = config.model_name

        if provider == 'groq':
            from apps.ai_assistant.views import _call_groq
            ai_response = _call_groq(api_key, model, prompt, system_prompt, config)
        elif provider == 'gemini':
            from apps.ai_assistant.views import _call_gemini
            ai_response = _call_gemini(api_key, model, prompt, system_prompt, config)
        elif provider == 'openai':
            from apps.ai_assistant.views import _call_openai
            ai_response = _call_openai(api_key, model, prompt, system_prompt, config)

        if ai_response:
            return f"🤖 *AI Assistant:*\n\n{ai_response}"
        else:
            return "⚠️ Maaf, AI tidak bisa memproses pertanyaan Anda saat ini. Coba lagi nanti."

    except Exception as e:
        logger.error(f"[TelegramBot] Error AI response: {e}", exc_info=True)
        return f"⚠️ Terjadi kesalahan saat memproses. Silakan coba lagi."
