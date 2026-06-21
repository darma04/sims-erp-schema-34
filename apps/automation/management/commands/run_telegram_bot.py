"""
==========================================================================
 TELEGRAM BOT POLLING - Management Command
==========================================================================
 Menjalankan bot Telegram dalam mode polling (long polling).
 Mode ini cocok untuk development dan server yang tidak punya domain publik.

 Cara kerja:
 - Bot secara aktif mengecek pesan baru ke Telegram API (getUpdates)
 - Setiap ada pesan baru, diproses oleh handle_update()
 - Interval polling: setiap 1 detik

 Penggunaan:
   python manage.py run_telegram_bot

 Untuk production dengan domain publik, gunakan webhook mode:
   Daftarkan webhook via halaman Pengaturan Telegram > Set Webhook
==========================================================================
"""
import json
import time
import ssl
import urllib.request
import urllib.error
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Jalankan bot Telegram dalam mode polling (untuk development/lokal)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=float,
            default=1.0,
            help='Interval polling dalam detik (default: 1.0)',
        )

    def handle(self, *args, **options):
        from apps.automation.models import PengaturanTelegram
        from apps.automation.telegram_bot import handle_update

        interval = options['interval']

        # Load pengaturan
        pengaturan = PengaturanTelegram.load()

        if not pengaturan.bot_token:
            self.stderr.write(self.style.ERROR(
                '❌ Bot Token belum dikonfigurasi! '
                'Isi di halaman Pengaturan > Automasi > Telegram'
            ))
            return

        bot_token = pengaturan.bot_token.strip()

        # SSL context
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        # Hapus webhook yang mungkin masih aktif (agar getUpdates berfungsi)
        self._delete_webhook(bot_token, ssl_ctx)

        self.stdout.write(self.style.SUCCESS(
            '\n'
            '══════════════════════════════════════════════\n'
            '  🤖 SERPTECH Telegram Bot — Polling Mode\n'
            '══════════════════════════════════════════════\n'
            f'  Bot Token: {bot_token[:8]}...\n'
            f'  Chat ID: {pengaturan.chat_id}\n'
            f'  Interval: {interval}s\n'
            '══════════════════════════════════════════════\n'
            '  Bot sedang berjalan... Tekan Ctrl+C untuk stop\n'
            '══════════════════════════════════════════════\n'
        ))

        offset = 0  # Tracking update ID terakhir

        while True:
            try:
                url = (
                    f"https://api.telegram.org/bot{bot_token}/getUpdates"
                    f"?offset={offset}&timeout=30&limit=10"
                )
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=35, context=ssl_ctx)
                data = json.loads(resp.read().decode('utf-8'))

                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        update_id = update.get('update_id', 0)
                        offset = update_id + 1  # Skip update ini di request berikutnya

                        # Log pesan masuk
                        msg = update.get('message', {})
                        text = msg.get('text', '')
                        from_name = msg.get('from', {}).get('first_name', 'N/A')
                        chat_id = msg.get('chat', {}).get('id', 'N/A')

                        if text:
                            self.stdout.write(
                                f'  📩 [{chat_id}] {from_name}: {text}'
                            )

                        # Proses update
                        try:
                            handle_update(update)
                            if text:
                                self.stdout.write(
                                    self.style.SUCCESS(f'  ✅ Balasan terkirim')
                                )
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(f'  ❌ Error proses: {e}')
                            )
                            logger.error(f"[Polling] Error handle_update: {e}", exc_info=True)

            except urllib.error.URLError as e:
                self.stderr.write(
                    self.style.WARNING(f'  ⚠️ Koneksi error: {e.reason}')
                )
                time.sleep(5)  # Tunggu lebih lama sebelum retry

            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING(
                    '\n  🛑 Bot dihentikan oleh user (Ctrl+C)\n'
                ))
                break

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'  ❌ Error polling: {e}')
                )
                logger.error(f"[Polling] Error: {e}", exc_info=True)
                time.sleep(3)

            time.sleep(interval)

    def _delete_webhook(self, bot_token, ssl_ctx):
        """Hapus webhook yang aktif agar getUpdates bisa berfungsi."""
        try:
            url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
            req = urllib.request.Request(url, method='POST')
            resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                self.stdout.write(self.style.SUCCESS(
                    '  ✅ Webhook dihapus (beralih ke polling mode)'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Gagal hapus webhook: {data.get("description")}'
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️ Error hapus webhook: {e}'
            ))
