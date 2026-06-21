"""
==========================================================================
 AUTOMATION VIEWS - Views Pengaturan & Monitoring Notifikasi Telegram
==========================================================================
 Views untuk mengelola notifikasi Telegram dari antarmuka web:

 Class-Based Views (CBV):
 ┌────────────────────────┬──────────────────────────────────────────────┐
 │ View                   │ Penjelasan                                   │
 ├────────────────────────┼──────────────────────────────────────────────┤
 │ PengaturanTelegramView │ Halaman pengaturan bot (token, chat_id, dll) │
 │ TemplatePesanListView  │ Daftar template pesan notifikasi              │
 │ TemplatePesanUpdateView│ Edit template pesan (placeholder {{var}})     │
 │ LogNotifikasiView      │ Riwayat + statistik pengiriman notifikasi    │
 └────────────────────────┴──────────────────────────────────────────────┘

 Function-Based Views (FBV) — API Endpoints:
 ┌────────────────────┬────────────────────────────────────────────────┐
 │ Fungsi             │ Penjelasan                                      │
 ├────────────────────┼────────────────────────────────────────────────┤
 │ test_kirim_telegram│ POST API — Kirim pesan test untuk cek koneksi   │
 │ deteksi_chat_id    │ POST API — Auto-detect Chat ID via getUpdates   │
 │ reset_template     │ POST API — Reset template ke default            │
 └────────────────────┴────────────────────────────────────────────────┘

 Terhubung dengan:
 - models.py → PengaturanTelegram, TemplatePesan, LogNotifikasi
 - telegram_service.py → kirim_pesan_telegram() untuk test
 - urls.py → Routing URL modul automation
 - apps/core/mixins.py → ReadPermissionMixin, UpdatePermissionMixin
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

import json
# Import dari framework Django
from django.shortcuts import render, redirect, get_object_or_404
# Import dari framework Django
from django.contrib.auth.mixins import LoginRequiredMixin
# Import dari framework Django
from django.views.generic import TemplateView, ListView, UpdateView
# Import dari framework Django
from django.http import JsonResponse
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.contrib import messages
# Import dari framework Django
from django.urls import reverse_lazy
from web_project import TemplateLayout

# Import dari modul internal proyek
from .models import PengaturanTelegram, TemplatePesan, LogNotifikasi
# Import dari modul internal proyek
from .telegram_service import kirim_pesan_telegram

# Import dari modul internal proyek
from apps.core.permissions import has_permission, get_user_role
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, UpdatePermissionMixin
# Import dari modul internal proyek
from apps.pengaturan.models import TemplateCetak
from django.db import transaction


class PengaturanTelegramView(ReadPermissionMixin, TemplateView):
    """View untuk pengaturan bot Telegram"""
    template_name = 'automation/pengaturan_telegram.html'
    # Modul permission yang dicek: 'automation'
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: pengaturan — untuk ditampilkan di template
        context['pengaturan'] = PengaturanTelegram.load()
        # Statistik log
        context['total_terkirim'] = LogNotifikasi.objects.filter(status='sukses').count()
        # Query database — ambil data context['total_gagal'] yang sesuai filter
        # Data konteks: total_gagal — untuk ditampilkan di template
        context['total_gagal'] = LogNotifikasi.objects.filter(status='gagal').count()
        # Query database — ambil semua data context['log_terbaru']
        # Data konteks: log_terbaru — untuk ditampilkan di template
        context['log_terbaru'] = LogNotifikasi.objects.all()[:5]
        return context

    # Handle HTTP POST request
    def post(self, request, *args, **kwargs):
        # Cek permission edit
        """Handle HTTP POST request."""
        if not has_permission(request.user, 'update', 'automation'):
            # Tampilkan pesan error ke user
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah pengaturan ini.')
            # Redirect ke halaman tujuan
            return redirect('automation:pengaturan_telegram')

        pengaturan = PengaturanTelegram.load()
        pengaturan.bot_token = request.POST.get('bot_token', '').strip()
        pengaturan.chat_id = request.POST.get('chat_id', '').strip()
        pengaturan.aktif = request.POST.get('aktif') == 'on'
        pengaturan.notif_pos = request.POST.get('notif_pos') == 'on'
        pengaturan.notif_sales_order = request.POST.get('notif_sales_order') == 'on'
        pengaturan.notif_purchase_order = request.POST.get('notif_purchase_order') == 'on'
        pengaturan.notif_biaya = request.POST.get('notif_biaya') == 'on'
        pengaturan.notif_penggajian = request.POST.get('notif_penggajian') == 'on'
        pengaturan.kirim_pdf = request.POST.get('kirim_pdf') == 'on'
        pengaturan.system_prompt_bot = request.POST.get('system_prompt_bot', '').strip()
        pengaturan.save()

        # Tampilkan pesan sukses ke user
        messages.success(request, 'Pengaturan Telegram berhasil disimpan!')
        # Redirect ke halaman tujuan
        return redirect('automation:pengaturan_telegram')


class TemplatePesanListView(ReadPermissionMixin, ListView):
    """View untuk daftar template pesan"""
    model = TemplatePesan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'automation/template_pesan_list.html'
    context_object_name = 'templates'
    # Urutan default data
    ordering = ['jenis']
    # Modul permission yang dicek: 'automation'
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Pastikan semua template default ada
        for jenis, label in TemplatePesan.JENIS_CHOICES:
            TemplatePesan.get_template(jenis)
        # Query database — ambil semua data context['templates']
        # Data konteks: templates — untuk ditampilkan di template
        context['templates'] = TemplatePesan.objects.all().order_by('jenis')
        return context


class TemplatePesanUpdateView(ReadPermissionMixin, UpdateView):
    """View untuk edit template pesan"""
    model = TemplatePesan
    # Template HTML yang digunakan untuk render halaman
    template_name = 'automation/template_pesan_form.html'
    fields = ['nama', 'template_pesan', 'aktif']
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('automation:template_pesan_list')
    # Modul permission yang dicek: 'automation'
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Variabel yang tersedia per jenis
        variabel_map = {
            'pos': ['nomor_transaksi', 'tanggal', 'kasir', 'gudang', 'detail_items', 'subtotal', 'diskon', 'pajak', 'total', 'metode_pembayaran', 'status', 'customer'],
            'sales_order': ['nomor_so', 'tanggal', 'customer', 'gudang', 'detail_items', 'subtotal', 'diskon', 'pajak', 'total', 'status', 'dibuat_oleh'],
            'purchase_order': ['nomor_po', 'tanggal', 'supplier', 'gudang', 'detail_items', 'subtotal', 'pajak', 'total', 'status', 'dibuat_oleh'],
            'biaya': ['nomor_transaksi', 'tanggal', 'kategori', 'jumlah', 'deskripsi', 'status', 'dibuat_oleh', 'metode_pembayaran'],
        }
        # Data konteks: variabel_tersedia — untuk ditampilkan di template
        context['variabel_tersedia'] = variabel_map.get(self.object.jenis, [])
        return context

    def post(self, request, *args, **kwargs):
        if not has_permission(request.user, 'update', 'automation'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah template ini.')
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        messages.success(self.request, f'Template "{form.instance.nama}" berhasil diupdate!')
        return super().form_valid(form)


class LogNotifikasiView(ReadPermissionMixin, ListView):
    """View untuk log pengiriman notifikasi"""
    model = LogNotifikasi
    # Template HTML yang digunakan untuk render halaman
    template_name = 'automation/log_notifikasi.html'
    context_object_name = 'logs'
    # Jumlah item per halaman untuk pagination
    paginate_by = 50
    # Modul permission yang dicek: 'automation'
    permission_module = 'automation'

    def get_queryset(self):
        """Override queryset — filter atau optimasi query data."""
        qs = super().get_queryset()
        # Filter berdasarkan jenis transaksi
        jenis = self.request.GET.get('jenis')
        if jenis:
            qs = qs.filter(jenis_transaksi=jenis)
        # Filter berdasarkan status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Query database — ambil data context['total_sukses'] yang sesuai filter
        # Data konteks: total_sukses — untuk ditampilkan di template
        context['total_sukses'] = LogNotifikasi.objects.filter(status='sukses').count()
        # Query database — ambil data context['total_gagal'] yang sesuai filter
        # Data konteks: total_gagal — untuk ditampilkan di template
        context['total_gagal'] = LogNotifikasi.objects.filter(status='gagal').count()
        # Hitung jumlah data yang cocok
        # Data konteks: total_semua — untuk ditampilkan di template
        context['total_semua'] = LogNotifikasi.objects.count()
        # Data konteks: jenis_filter — untuk ditampilkan di template
        context['jenis_filter'] = self.request.GET.get('jenis', '')
        # Data konteks: status_filter — untuk ditampilkan di template
        context['status_filter'] = self.request.GET.get('status', '')
        # Context untuk export PDF
        try:
            # Data konteks: export_pdf_template — untuk ditampilkan di template
            context['export_pdf_template'] = TemplateCetak.objects.first()
        # Tangkap error Exception — lanjutkan tanpa crash
        except Exception:
            # Data konteks: export_pdf_template — untuk ditampilkan di template
            context['export_pdf_template'] = None
        return context


# Wajib login — redirect ke login page jika belum login
@login_required
def test_kirim_telegram(request):
    """API untuk test kirim pesan ke Telegram"""
    if request.method != 'POST':
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token or not pengaturan.chat_id:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token dan Chat ID harus diisi terlebih dahulu!'
        })

    pesan_test = (
        "✅ *Test Koneksi Berhasil!*\n"
        "━━━━━━━━━━━━━━━\n"
        "🤖 Bot Telegram terhubung dengan sistem ERP\n"
        "📊 Notifikasi otomatis siap digunakan\n\n"
        "Pengaturan Aktif:\n"
        f"  • POS: {'✅' if pengaturan.notif_pos else '❌'}\n"
        f"  • Sales Order: {'✅' if pengaturan.notif_sales_order else '❌'}\n"
        f"  • Purchase Order: {'✅' if pengaturan.notif_purchase_order else '❌'}\n"
        f"  • Biaya: {'✅' if pengaturan.notif_biaya else '❌'}\n"
    )

    success, response = kirim_pesan_telegram(
        pengaturan.bot_token,
        pengaturan.chat_id,
        pesan_test
    )

    # Simpan log
    LogNotifikasi.objects.create(
        jenis_transaksi='pos',  # Gunakan pos sebagai default test
        nomor_referensi='TEST',
        pesan=pesan_test,
        status='sukses' if success else 'gagal',
        respons=json.dumps(response) if isinstance(response, dict) else None,
        error_message=response if not success and isinstance(response, str) else None,
    )

    if success:
        return JsonResponse({
            'success': True,
            'message': 'Pesan test berhasil dikirim ke Telegram! Cek chat Anda.'
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f'Gagal mengirim: {response}'
        })


    # Wajib login — redirect ke login page jika belum login
@login_required
def deteksi_chat_id(request):
    """API untuk mendeteksi chat_id dari pesan yang masuk ke bot via getUpdates"""
    import urllib.request
    import urllib.error
    import ssl

    if request.method != 'POST':
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token harus diisi terlebih dahulu!'
        })

    bot_token = pengaturan.bot_token.strip()
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=10&offset=-10"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Blok penanganan error — coba jalankan kode di bawah
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get('ok') and result.get('result'):
            updates = result['result']
            chat_ids_found = []

            for update in updates:
                msg = update.get('message') or update.get('channel_post') or {}
                chat = msg.get('chat', {})
                chat_id = chat.get('id')
                chat_type = chat.get('type', '')
                chat_title = chat.get('title') or chat.get('first_name') or chat.get('username') or str(chat_id)

                if chat_id:
                    entry = {
                        'chat_id': str(chat_id),
                        'title': chat_title,
                        'type': chat_type
                    }
                    # Hindari duplikat
                    if not any(c['chat_id'] == entry['chat_id'] for c in chat_ids_found):
                        chat_ids_found.append(entry)

            if chat_ids_found:
                # Tampilkan chat_id yang ditemukan (TIDAK auto-save ke DB)
                # User harus klik "Simpan Pengaturan" untuk menyimpannya
                first_chat_id = chat_ids_found[0]['chat_id']

                return JsonResponse({
                    'success': True,
                    'message': f'Chat ID berhasil dideteksi: {first_chat_id} ({chat_ids_found[0]["title"]})',
                    'chat_id': first_chat_id,
                    'all_chats': chat_ids_found
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak ditemukan pesan masuk. Kirim pesan /start ke bot Anda terlebih dahulu, lalu klik "Deteksi Chat ID" lagi.'
                })
        elif result.get('ok') and not result.get('result'):
            return JsonResponse({
                'success': False,
                'message': 'Bot belum menerima pesan dari siapapun. Kirim pesan /start ke bot Anda terlebih dahulu.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Error: {result.get("description", "Unknown error")}'
            })

    # Tangkap error urllib.error.HTTPError — lanjutkan tanpa crash
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('description', str(e))
        except Exception:
            error_msg = f"HTTP {e.code}: {error_body[:200]}"

        if e.code == 401:
            error_msg = "Bot Token tidak valid. Pastikan token benar dari @BotFather."
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': error_msg})

    # Tangkap error Exception — lanjutkan tanpa crash
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })


    # Wajib login — redirect ke login page jika belum login
@login_required
def reset_template(request, pk):
    """Reset template ke default"""
    if request.method != 'POST':
        # Kembalikan respons JSON gagal ke klien
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        # Tampilkan pesan error ke user
        messages.error(request, 'Anda tidak memiliki akses untuk mereset template.')
        # Redirect ke halaman tujuan
        return redirect('automation:template_pesan_list')

    template = get_object_or_404(TemplatePesan, pk=pk)
    template.template_pesan = TemplatePesan._get_default_template(template.jenis)
    template.save()

    # Tampilkan pesan sukses ke user
    messages.success(request, f'Template "{template.nama}" berhasil direset ke default!')
    # Redirect ke halaman tujuan
    return redirect('automation:template_pesan_list')


# ╔══════════════════════════════════════════════════════════════╗
# ║          TELEGRAM WEBHOOK & AI BOT                            ║
# ╚══════════════════════════════════════════════════════════════╝

from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_webhook(request):
    """
    Endpoint webhook yang dipanggil oleh Telegram saat ada pesan masuk.
    URL: POST /automation/telegram/webhook/

    Alur:
    1. Telegram mengirim POST dengan JSON body berisi pesan user
    2. Endpoint ini validasi dulu secret token dari header
    3. Jika valid, meneruskan ke telegram_bot.handle_update() via thread pool
    4. Bot memproses pesan dan mengirim balasan

    Keamanan:
    - csrf_exempt karena Telegram mengirim POST tanpa CSRF token
    - Validasi secret token via header X-Telegram-Bot-Api-Secret-Token
    - Menggunakan thread pool (max 5 worker) untuk mencegah thread leak
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'ok'})

    try:
        # ── VALIDASI SECRET TOKEN ──────────────────────────────
        # Telegram mengirim header ini jika secret_token di-set saat setWebhook
        # Ini mencegah siapapun mengirim request palsu ke endpoint ini
        pengaturan = PengaturanTelegram.load()
        expected_token = _generate_webhook_secret(pengaturan.bot_token)

        received_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if expected_token and received_token != expected_token:
            logger.warning(f"[Webhook] Request ditolak — secret token tidak valid")
            return JsonResponse({'status': 'unauthorized'}, status=403)

        body = json.loads(request.body.decode('utf-8'))

        # ── PROSES VIA THREAD POOL ─────────────────────────────
        # Gunakan thread pool dari telegram_bot (max 5 worker)
        # agar tidak terjadi thread leak saat banyak request masuk
        from .telegram_bot import handle_update, _executor
        try:
            _executor.submit(handle_update, body)
        except RuntimeError:
            # Thread pool sudah shutdown — proses langsung
            handle_update(body)

        return JsonResponse({'status': 'ok'})

    except Exception as e:
        logger.error(f"[Webhook] Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error'}, status=500)


def _generate_webhook_secret(bot_token):
    """
    Generate secret token dari bot_token untuk validasi webhook.
    Menggunakan hash SHA-256 agar token asli tidak terexpose.
    Secret ini harus di-set saat memanggil setWebhook API.
    """
    if not bot_token:
        return ''
    import hashlib
    return hashlib.sha256(f"serptech_webhook_{bot_token}".encode()).hexdigest()[:32]


@login_required
def set_webhook(request):
    """
    Mendaftarkan webhook URL ke Telegram Bot API.
    URL: POST /automation/telegram/set-webhook/

    Ini hanya perlu dipanggil SEKALI saat setup pertama kali.
    Setelah terdaftar, Telegram akan otomatis mengirim pesan ke webhook URL kita.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    import urllib.request
    import urllib.error
    import ssl

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token harus diisi terlebih dahulu!'
        })

    # URL webhook yang akan didaftarkan ke Telegram
    webhook_url = request.POST.get('webhook_url', '').strip()
    if not webhook_url:
        # Auto-detect dari domain
        webhook_url = f"https://serptech.serpgroup.cloud/automation/telegram/webhook/"

    bot_token = pengaturan.bot_token.strip()
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        import urllib.parse
        # Kirim secret_token agar Telegram menyertakannya di setiap webhook request
        # Ini melengkapi validasi di telegram_webhook()
        secret_token = _generate_webhook_secret(bot_token)
        params = {'url': webhook_url, 'secret_token': secret_token}
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get('ok'):
            return JsonResponse({
                'success': True,
                'message': f'Webhook berhasil terdaftar: {webhook_url}'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Gagal: {result.get("description", "Unknown error")}'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })
