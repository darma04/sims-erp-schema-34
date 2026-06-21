"""
==========================================================================
 TELEGRAM SERVICE - Layanan Integrasi Telegram Bot API
==========================================================================
 File ini berisi service layer untuk mengirim pesan ke Telegram.
 Menggunakan urllib bawaan Python (TANPA library eksternal seperti requests).

 Alasan menggunakan urllib, bukan requests:
 - Mengurangi dependensi eksternal
 - urllib sudah built-in di Python — tidak perlu pip install
 - Fungsionalitas cukup untuk REST API sederhana

 Fungsi utama:
 ┌─────────────────────────┬───────────────────────────────────────────┐
 │ Fungsi                  │ Penjelasan                                │
 ├─────────────────────────┼───────────────────────────────────────────┤
 │ kirim_pesan_telegram()  │ Kirim pesan ke Telegram Bot API (sync)    │
 │ format_angka()          │ Format angka ke format Rupiah (1.000.000) │
 │ render_template()       │ Ganti placeholder {{var}} dengan data     │
 │ kirim_notifikasi_async()│ Wrapper async — kirim di thread terpisah  │
 │ _kirim_notifikasi_sync()│ Proses internal kirim + log hasil         │
 └─────────────────────────┴───────────────────────────────────────────┘

 Alur pengiriman notifikasi:
 1. kirim_notifikasi_async() → Buat thread baru (daemon=True)
 2. _kirim_notifikasi_sync() → Load pengaturan, cek toggle, render template
 3. kirim_pesan_telegram() → HTTP POST ke api.telegram.org
 4. Simpan log hasil (sukses/gagal) ke LogNotifikasi

 Mengapa async (thread terpisah)?
 - Agar proses save transaksi TIDAK menunggu response dari Telegram
 - User tidak perlu menunggu API Telegram yang kadang lambat
 - Jika kirim gagal, transaksi tetap berhasil tersimpan

 Terhubung dengan:
 - models.py → PengaturanTelegram, TemplatePesan, LogNotifikasi
 - signals.py → Memanggil kirim_notifikasi_async()
 - views.py → test_kirim_telegram() untuk test koneksi
==========================================================================
"""
import json
import os
import urllib.request
import urllib.parse
import urllib.error
import ssl
import logging
import threading

logger = logging.getLogger(__name__)


def kirim_pesan_telegram(bot_token, chat_id, pesan, parse_mode='Markdown'):
    """
    Kirim pesan ke Telegram menggunakan Bot API.

    Args:
        bot_token: Token bot dari @BotFather
        chat_id: Chat ID tujuan
        pesan: Teks pesan yang akan dikirim
        parse_mode: Format pesan (Markdown/HTML)

    Returns:
        tuple: (success: bool, response_data: dict atau error_message: str)
    """
    if not bot_token or not chat_id:
        return False, "Bot Token atau Chat ID belum dikonfigurasi"

    # Bersihkan whitespace
    bot_token = bot_token.strip()
    chat_id = str(chat_id).strip()

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Buat SSL context yang aman dengan verifikasi sertifikat
    ssl_context = ssl.create_default_context()

    # Pertama coba dengan parse_mode, jika gagal karena formatting coba tanpa
    for attempt_parse_mode in [parse_mode, None]:
        data = {
            'chat_id': chat_id,
            'text': pesan,
        }
        if attempt_parse_mode:
            data['parse_mode'] = attempt_parse_mode

        # Blok penanganan error — coba jalankan kode di bawah
        try:
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(url, data=encoded_data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get('ok'):
                    return True, result
                else:
                    error_desc = result.get('description', 'Unknown error')
                    # Jika error karena parsing markdown, coba tanpa parse_mode
                    if attempt_parse_mode and 'parse' in error_desc.lower():
                        logger.warning(f"Markdown parse error, retrying without parse_mode: {error_desc}")
                        continue
                    return False, error_desc

        # Tangkap error urllib.error.HTTPError — lanjutkan tanpa crash
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            # Blok penanganan error — coba jalankan kode di bawah
            try:
                error_data = json.loads(error_body)
                error_msg = error_data.get('description', str(e))
                error_code = error_data.get('error_code', e.code)

                # Sediakan pesan error yang mudah dipahami pengguna
                if error_code == 401:
                    error_msg = "Bot Token tidak valid. Pastikan token yang Anda masukkan benar dari @BotFather."
                elif error_code == 400:
                    if 'chat not found' in error_msg.lower():
                        error_msg = (
                            "Chat ID tidak ditemukan. Pastikan:\n"
                            "1. Bot sudah ditambahkan ke grup/channel, atau\n"
                            "2. Anda sudah mengirim pesan /start ke bot terlebih dahulu.\n"
                            "3. Chat ID yang digunakan benar (gunakan @userinfobot untuk mendapatkan Chat ID Anda)."
                        )
                    elif 'parse' in error_msg.lower() and attempt_parse_mode:
                        # Coba lagi tanpa parse mode
                        logger.warning(f"Parse error, retrying without parse_mode: {error_msg}")
                        continue

                return False, error_msg
            # Tangkap error (json.JSONDecodeError, ValueError) — lanjutkan tanpa crash
            except (json.JSONDecodeError, ValueError):
                error_msg = f"HTTP {e.code}: {error_body[:200]}"
            logger.error(f"Telegram API HTTP Error: {error_msg}")
            return False, error_msg

        # Tangkap error urllib.error.URLError — lanjutkan tanpa crash
        except urllib.error.URLError as e:
            error_msg = f"Koneksi gagal ke server Telegram: {str(e.reason)}"
            logger.error(f"Telegram API URL Error: {error_msg}")
            return False, error_msg

        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception as e:
            error_msg = f"Error tidak terduga: {str(e)}"
            logger.error(f"Telegram API Error: {error_msg}")
            return False, error_msg

    # Jika semua percobaan gagal
    return False, "Gagal mengirim pesan setelah beberapa percobaan."


def kirim_dokumen_telegram(bot_token, chat_id, file_path, caption='', parse_mode='Markdown'):
    """
    Kirim file dokumen (PDF) ke Telegram menggunakan Bot API sendDocument.

    Args:
        bot_token: Token bot dari @BotFather
        chat_id: Chat ID tujuan
        file_path: Path absolut ke file yang akan dikirim
        caption: Teks caption untuk dokumen
        parse_mode: Format caption (Markdown/HTML)

    Returns:
        tuple: (success: bool, response_data: dict atau error_message: str)
    """
    import mimetypes

    if not bot_token or not chat_id:
        return False, "Bot Token atau Chat ID belum dikonfigurasi"

    if not file_path or not os.path.exists(file_path):
        return False, f"File tidak ditemukan: {file_path}"

    bot_token = bot_token.strip()
    chat_id = str(chat_id).strip()

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    ssl_context = ssl.create_default_context()

    try:
        # Baca file untuk dikirim via multipart/form-data
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or 'application/pdf'

        # Buat boundary unik untuk multipart
        import uuid
        boundary = str(uuid.uuid4())

        # Buat body multipart/form-data
        body = b''

        # Field: chat_id
        body += f'--{boundary}\r\n'.encode()
        body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
        body += f'{chat_id}\r\n'.encode()

        # Field: caption (opsional)
        if caption:
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
            body += f'{caption}\r\n'.encode()

            # Field: parse_mode
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'.encode()
            body += f'{parse_mode}\r\n'.encode()

        # Field: document (file)
        body += f'--{boundary}\r\n'.encode()
        body += f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode()
        body += f'Content-Type: {content_type}\r\n\r\n'.encode()

        with open(file_path, 'rb') as f:
            body += f.read()

        body += f'\r\n--{boundary}--\r\n'.encode()

        # Kirim request
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('ok'):
                return True, result
            else:
                return False, result.get('description', 'Unknown error')

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('description', str(e))
        except (json.JSONDecodeError, ValueError):
            error_msg = f"HTTP {e.code}: {error_body[:200]}"
        logger.error(f"Telegram sendDocument HTTP Error: {error_msg}")
        return False, error_msg

    except urllib.error.URLError as e:
        error_msg = f"Koneksi gagal ke server Telegram: {str(e.reason)}"
        logger.error(f"Telegram sendDocument URL Error: {error_msg}")
        return False, error_msg

    except Exception as e:
        error_msg = f"Error tidak terduga: {str(e)}"
        logger.error(f"Telegram sendDocument Error: {error_msg}")
        return False, error_msg


def kirim_dokumen_async(jenis_transaksi, nomor_referensi, instance, pdf_generator_func, data_transaksi=None):
    """
    Kirim dokumen PDF ke Telegram secara asynchronous (background thread).
    Jika data_transaksi disertakan, template pesan akan digunakan sebagai caption PDF
    sehingga teks notifikasi dan PDF menjadi 1 pesan tunggal.

    Args:
        jenis_transaksi: Jenis transaksi ('sales_order', 'purchase_order', dll)
        nomor_referensi: Nomor referensi transaksi
        instance: Instance model transaksi
        pdf_generator_func: Fungsi yang meng-generate PDF dari instance
        data_transaksi: Dict data untuk render template pesan (opsional)
    """
    thread = threading.Thread(
        target=_kirim_dokumen_sync,
        args=(jenis_transaksi, nomor_referensi, instance, pdf_generator_func, data_transaksi),
        daemon=True
    )
    thread.start()


def _kirim_dokumen_sync(jenis_transaksi, nomor_referensi, instance, pdf_generator_func, data_transaksi=None):
    """Proses kirim dokumen PDF yang berjalan di thread terpisah.
    Menggunakan template pesan sebagai caption PDF agar 1 pesan saja di Telegram.
    Jika PDF gagal di-generate, fallback ke pesan teks biasa (tidak pernah gagal diam)."""
    from .models import PengaturanTelegram, TemplatePesan, LogNotifikasi
    import traceback as tb
    from django.db import close_old_connections

    try:
        # PENTING: Bersihkan koneksi DB lama sebelum memulai.
        # Background thread bisa mendapat koneksi yang sudah ditutup oleh Django
        # setelah HTTP request selesai. Ini menyebabkan error intermittent.
        close_old_connections()

        pengaturan = PengaturanTelegram.load()

        # Cek apakah notifikasi aktif dan kirim_pdf aktif
        if not pengaturan.aktif:
            return
        if not getattr(pengaturan, 'kirim_pdf', False):
            return
        if not pengaturan.bot_token or not pengaturan.chat_id:
            return

        # Render template pesan untuk digunakan sebagai caption DAN fallback teks
        pesan_teks = f"📄 {jenis_transaksi.replace('_', ' ').upper()} - {nomor_referensi}"
        if data_transaksi:
            try:
                template = TemplatePesan.get_template(jenis_transaksi)
                if template and template.aktif:
                    pesan_teks = render_template(template.template_pesan, data_transaksi)
            except Exception:
                pass  # fallback ke pesan default

        # Generate PDF
        pdf_path = None
        try:
            logger.info(f"[PDF] Generating PDF for {jenis_transaksi}: {nomor_referensi}")
            pdf_path = pdf_generator_func(instance)
            logger.info(f"[PDF] Result: {pdf_path}")
        except Exception as pdf_err:
            logger.error(f"[PDF] Exception saat generate PDF: {pdf_err}")
            logger.error(f"[PDF] Traceback: {tb.format_exc()}")


        if pdf_path:
            # PDF berhasil → kirim sebagai dokumen + caption (1 pesan)
            caption = pesan_teks
            # Telegram caption max 1024 chars
            if len(caption) > 1024:
                caption = caption[:1020] + '...'

            success, response = kirim_dokumen_telegram(
                pengaturan.bot_token,
                pengaturan.chat_id,
                pdf_path,
                caption
            )

            LogNotifikasi.objects.create(
                jenis_transaksi=jenis_transaksi,
                nomor_referensi=nomor_referensi,
                pesan=caption,
                status='sukses' if success else 'gagal',
                respons=json.dumps(response) if isinstance(response, dict) else None,
                error_message=response if not success and isinstance(response, str) else None,
            )

            # Cleanup file temporary
            from .pdf_generator import cleanup_pdf
            cleanup_pdf(pdf_path)
        else:
            # PDF GAGAL → fallback kirim pesan teks biasa agar notifikasi tetap terkirim
            logger.warning(f"[PDF] Gagal generate PDF untuk {jenis_transaksi}: {nomor_referensi}, fallback ke teks")
            pesan_fallback = pesan_teks + "\n\n⚠️ _PDF gagal di-generate, mengirim teks saja._"

            success, response = kirim_pesan_telegram(
                pengaturan.bot_token,
                pengaturan.chat_id,
                pesan_fallback
            )

            LogNotifikasi.objects.create(
                jenis_transaksi=jenis_transaksi,
                nomor_referensi=nomor_referensi,
                pesan=f"[Fallback Teks] {pesan_teks[:200]}",
                status='sukses' if success else 'gagal',
                respons=json.dumps(response) if isinstance(response, dict) else None,
                error_message=response if not success and isinstance(response, str) else None,
            )

    except Exception as e:
        logger.error(f"Error kirim dokumen Telegram: {str(e)}")
        try:
            from .models import LogNotifikasi
            LogNotifikasi.objects.create(
                jenis_transaksi=jenis_transaksi,
                nomor_referensi=nomor_referensi,
                pesan=f"[Error] {str(e)}",
                status='gagal',
                error_message=str(e),
            )
        except Exception as e:
            logger.warning("Gagal mencatat activity log: %s", e)


def format_angka(angka):
    """Format angka ke format rupiah (titik sebagai pemisah ribuan)"""
    try:
        return f"{float(angka):,.0f}".replace(",", ".")
    # Tangkap error (ValueError, TypeError) — lanjutkan tanpa crash
    except (ValueError, TypeError):
        return "0"


def render_template(template_str, data):
    """
    Render template pesan dengan data menggunakan format {{variabel}}.

    Args:
        template_str: String template dengan placeholder {{variabel}}
        data: Dictionary berisi nilai variabel

    Returns:
        str: Pesan yang sudah di-render
    """
    result = template_str
    for key, value in data.items():
        placeholder = "{{" + key + "}}"
        result = result.replace(placeholder, str(value))
    return result


def kirim_notifikasi_async(jenis_transaksi, nomor_referensi, data_transaksi):
    """
    Kirim notifikasi Telegram secara asynchronous (dalam thread terpisah).
    Jadi tidak memblokir proses utama (save transaksi).
    """
    thread = threading.Thread(
        target=_kirim_notifikasi_sync,
        args=(jenis_transaksi, nomor_referensi, data_transaksi),
        daemon=True
    )
    thread.start()


def _kirim_notifikasi_sync(jenis_transaksi, nomor_referensi, data_transaksi):
    """Proses kirim notifikasi yang berjalan di thread terpisah"""
    from .models import PengaturanTelegram, TemplatePesan, LogNotifikasi

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        pengaturan = PengaturanTelegram.load()

        # Cek apakah notifikasi aktif
        if not pengaturan.aktif:
            return

        if not pengaturan.bot_token or not pengaturan.chat_id:
            return

        # Cek apakah jenis transaksi ini diaktifkan
        toggle_map = {
            'pos': pengaturan.notif_pos,
            'sales_order': pengaturan.notif_sales_order,
            'purchase_order': pengaturan.notif_purchase_order,
            'biaya': pengaturan.notif_biaya,
            'penggajian': pengaturan.notif_penggajian,
        }

        if not toggle_map.get(jenis_transaksi, False):
            return

        # Ambil template pesan
        template = TemplatePesan.get_template(jenis_transaksi)
        if not template.aktif:
            return

        # Render pesan
        pesan = render_template(template.template_pesan, data_transaksi)

        # Kirim ke Telegram
        success, response = kirim_pesan_telegram(
            pengaturan.bot_token,
            pengaturan.chat_id,
            pesan
        )

        # Simpan log
        LogNotifikasi.objects.create(
            jenis_transaksi=jenis_transaksi,
            nomor_referensi=nomor_referensi,
            pesan=pesan,
            status='sukses' if success else 'gagal',
            respons=json.dumps(response) if isinstance(response, dict) else None,
            error_message=response if not success and isinstance(response, str) else None,
        )

    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        logger.error(f"Error kirim notifikasi Telegram: {str(e)}")
        # Tetap simpan log jika memungkinkan
        try:
            # Import dari modul internal proyek
            from .models import LogNotifikasi
            LogNotifikasi.objects.create(
                jenis_transaksi=jenis_transaksi,
                nomor_referensi=nomor_referensi,
                pesan=f"[Error] {str(e)}",
                status='gagal',
                error_message=str(e),
            )
        except Exception as e:
            logger.warning("Gagal mencatat activity log: %s", e)
