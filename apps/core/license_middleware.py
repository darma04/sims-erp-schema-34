"""
==========================================================================
 LICENSE MIDDLEWARE — Middleware Pengecekan Lisensi Otomatis
==========================================================================
 Middleware ini adalah "jantung" perlindungan software terhadap pembajakan.

 Cara kerja:
 1. Setiap request HTTP masuk, middleware mengecek status lisensi.
 2. Jika belum ada license_key → redirect ke halaman aktivasi.
 3. Jika sudah ada license_key:
    a. Cek cache lokal (24 jam). Jika masih valid → lanjut.
    b. Jika cache expired → ping CLS API /api/v1/license/validate/
    c. Jika CLS bilang valid → update cache 24 jam, lanjut.
    d. Jika CLS bilang invalid → blokir akses, tampilkan pesan.
    e. Jika CLS tidak bisa dihubungi (offline) → toleransi pakai cache lama.

 Koneksi:
 - apps/core/license_models.py → LicenseConfig (data lisensi lokal)
 - apps/core/license_views.py → View untuk halaman aktivasi
 - config/settings.py → LICENSE_SERVER_URL, PRODUCT_CODE
==========================================================================
"""
import json
import logging
import urllib.request
import urllib.error
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class LicenseMiddleware:
    """
    Django Middleware untuk memverifikasi lisensi software.

    Skip URL yang dikecualikan:
    - Halaman login dan logout
    - Halaman aktivasi lisensi
    - Static files dan media files
    - Admin panel (opsional)
    """

    # URL yang tidak perlu pengecekan lisensi
    EXEMPT_PATHS = [
        '/login/',
        '/logout/',
        '/license/',           # Halaman aktivasi
        '/static/',
        '/media/',
        '/admin/',
        '/favicon.ico',
        '/api/internal/',      # Internal API untuk CLS tenant provisioning
        # Halaman maintenance sengaja DIKELUARKAN dari exempt agar middleware bisa mendeteksi saat statusnya OFF
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        # Memastikan tidak ada infinite redirect di halaman khusus
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS) or getattr(request, '_license_maintenance_redirect', False):
            return self.get_response(request)

        # ============================================================
        # PENGECEKAN LISENSI HARUS TERJADI SEBELUM LOGIN!
        # Pembeli baru yang pertama kali akses aplikasi WAJIB melihat
        # halaman aktivasi lisensi terlebih dahulu, BUKAN halaman login.
        # ============================================================

        # Import model di sini (lazy import untuk menghindari circular import)
        from apps.core.license_models import LicenseConfig, generate_hardware_id

        try:
            config = LicenseConfig.get_config()
        except Exception:
            # Database belum siap (migration belum jalan) — skip
            return self.get_response(request)

        # Jika belum ada license key → redirect ke halaman aktivasi
        # Ini berlaku untuk SEMUA pengunjung (login maupun belum login)
        if not config.license_key or not config.is_activated:
            return HttpResponseRedirect(reverse('license_activation'))
            
        def _check_maintenance_or_update(cnf):
            # Cek Force Update
            if cnf.min_app_version and cnf.app_version:
                try:
                    def parse_v(vstr): return [int(x) for x in vstr.lower().replace('v','').split('.') if x.isdigit()]
                    if parse_v(cnf.app_version) < parse_v(cnf.min_app_version):
                        return HttpResponseRedirect(reverse('license_activation') + '?error=force_update')
                except Exception: pass
            
            # Cek Remote Maintenance (dari CLS)
            # Berlaku untuk SEMUA user termasuk superuser — hanya bisa di-off dari CLS
            if cnf.is_maintenance:
                target_url = reverse('pages-misc-under-maintenance')
                if request.path != target_url:
                    return HttpResponseRedirect(target_url)
                return None
                
            return None

        # Cek cache validasi
        if config.is_cache_valid():
            if config.validation_cache:
                # Cache masih valid DAN lisensi valid → cek maintenance/update
                interception = _check_maintenance_or_update(config)
                if interception: return interception
                return self.get_response(request)
            else:
                # Cache masih valid TAPI lisensi INVALID (CLS bilang invalid)
                # → langsung redirect ke halaman aktivasi
                return HttpResponseRedirect(
                    reverse('license_activation') + '?error=invalid'
                )

        # ============================================================
        # Cache expired atau belum ada → ping CLS untuk validasi ulang
        # PENTING: Pengecekan ini dilakukan untuk SEMUA user,
        # baik yang sudah login maupun belum, agar perubahan status
        # di CLS (suspend, expired) langsung berdampak realtime.
        # ============================================================
        hardware_id = config.hardware_id or generate_hardware_id()
        cls_url = config.cls_server_url if config.cls_server_url else getattr(settings, 'LICENSE_SERVER_URL', 'https://cls.serpgroup.cloud')

        is_valid = self._validate_with_cls(config, hardware_id, cls_url)

        if is_valid:
            interception = _check_maintenance_or_update(config)
            if interception: return interception
            return self.get_response(request)

        # Jika validasi gagal DAN CLS tidak bisa dihubungi (offline)
        # Toleransi HANYA jika cache terakhir valid DAN belum terlalu lama (maks 1 jam)
        if config.validation_cache and config.last_validated:
            from datetime import timedelta
            offline_tolerance = timedelta(hours=1)
            if (timezone.now() - config.last_validated) < offline_tolerance:
                logger.warning("CLS tidak bisa dihubungi, toleransi offline (cache < 1 jam).")
                return self.get_response(request)

        # Benar-benar invalid → redirect ke halaman aktivasi dengan pesan error
        return HttpResponseRedirect(
            reverse('license_activation') + '?error=invalid'
        )

    def _validate_with_cls(self, config, hardware_id, cls_url):
        """
        Mengirim request validasi ke Central License Server.

        Returns:
            bool: True jika lisensi valid, False jika tidak.
        """
        validate_url = f"{cls_url.rstrip('/')}/api/v1/license/validate/"

        payload = json.dumps({
            "license_key": config.license_key,
            "hardware_id": hardware_id,
        }).encode('utf-8')

        req = urllib.request.Request(
            validate_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('is_valid', False):
                    # Validasi berhasil — update cache
                    resp_data = data.get('data', {})
                    config.update_validation_cache(
                        is_valid=True,
                        message="Lisensi valid.",
                        expires_at=resp_data.get('expires_at'),
                        product_name=resp_data.get('product_name'),
                        client_name=resp_data.get('client_name'),
                        is_maintenance=resp_data.get('is_maintenance', False),
                        maintenance_message=resp_data.get('maintenance_message'),
                        min_app_version=resp_data.get('min_app_version', 'v1.0'),
                        force_update_url=resp_data.get('force_update_url')
                    )
                    logger.info(f"Validasi lisensi berhasil: {config.license_key}")
                    return True
                else:
                    # CLS mengatakan invalid
                    config.update_validation_cache(
                        is_valid=False,
                        message=data.get('message', 'Lisensi tidak valid.')
                    )
                    logger.warning(f"Validasi gagal: {data.get('message')}")
                    return False

        except urllib.error.HTTPError as e:
            # CLS mengembalikan status error (403 Forbidden, 404 Not Found, dll)
            # Ini berarti response sampai, tapi lisensi invalid/ada masalah.
            try:
                error_data = json.loads(e.read().decode('utf-8'))
                config.update_validation_cache(
                    is_valid=False,
                    message=error_data.get('message', 'Lisensi ditolak oleh server.')
                )
                logger.warning(f"Validasi ditolak server: {error_data.get('message')}")
            except Exception:
                config.update_validation_cache(is_valid=False, message="Lisensi tidak dikenali.")
            return False

        except urllib.error.URLError as e:
            # Gagal koneksi (server benar-benar mati / jaringan putus)
            # Biarkan status cache lama tetap ada agar masuk mode toleransi offline
            logger.error(f"Gagal menghubungi CLS (Offline): {e}")
            return False

        except Exception as e:
            logger.error(f"Error saat validasi lisensi: {e}")
            return False
