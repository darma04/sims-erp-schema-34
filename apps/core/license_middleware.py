"""
==========================================================================
 LICENSE MIDDLEWARE — Circuit Breaker + Graceful Degradation
==========================================================================
 Middleware lisensi dengan Circuit Breaker untuk mitigasi SPOF.

 Cara kerja:
 1. Cek cache lokal (LicenseConfig). Jika valid → izinkan akses.
 2. Jika cache expired, cek **Circuit Breaker**:
    a. Jika circuit OPEN (>=3 kegagalan beruntun) → SKIP panggilan CLS.
       Izin berdasarkan cache terakhir, inject warning offline.
    b. Jika circuit CLOSED → ping CLS.
 3. CLS timeout/error → record_failure(), izinkan akses dengan cache
    terakhir (graceful degradation), inject warning.
 4. CLS sukses → reset_failures(), update cache.
 5. Installasi baru (no cache) + CLS down → friendly error page.

 URL exempt: static, media, login, logout, license, admin, favicon,
 api/internal (Schema tenant provisioning).
==========================================================================
"""
import json
import logging
import urllib.request
import urllib.error
from datetime import timedelta

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class LicenseMiddleware:
    """
    Middleware lisensi dengan Circuit Breaker dan Graceful Degradation.

    Skip URL yang dikecualikan:
    - Halaman login/logout, aktivasi lisensi, error lisensi
    - Static/media files, admin panel
    - API internal (tenant provisioning untuk variant Schema)
    """

    EXEMPT_PATHS = [
        '/login/',
        '/logout/',
        '/license/',
        '/static/',
        '/media/',
        '/admin/',
        '/favicon.ico',
        '/api/internal/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG:
            return self.get_response(request)

        path = request.path
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS) or getattr(request, '_license_maintenance_redirect', False):
            return self.get_response(request)

        from apps.core.license_models import LicenseConfig, generate_hardware_id

        try:
            config = LicenseConfig.get_config()
        except Exception:
            return self.get_response(request)

        if not config.license_key or not config.is_activated:
            # CLS down saat installasi baru — redirect ke friendly error page
            if self._is_cls_unreachable(config):
                return HttpResponseRedirect(reverse('license_error'))
            return HttpResponseRedirect(reverse('license_activation'))

        def _check_maintenance_or_update(cnf):
            if cnf.min_app_version and cnf.app_version:
                try:
                    def parse_v(vstr):
                        return [int(x) for x in vstr.lower().replace('v', '').split('.') if x.isdigit()]
                    if parse_v(cnf.app_version) < parse_v(cnf.min_app_version):
                        return HttpResponseRedirect(reverse('license_activation') + '?error=force_update')
                except Exception as e:
                    logger.warning("Error tidak terduga: %s", e)
            if cnf.is_maintenance:
                target_url = reverse('pages-misc-under-maintenance')
                if request.path != target_url:
                    return HttpResponseRedirect(target_url)
                return None
            return None

        offline_mode = False

        if config.is_cache_valid():
            if config.validation_cache:
                interception = _check_maintenance_or_update(config)
                if interception:
                    return interception
                return self.get_response(request)
            else:
                return HttpResponseRedirect(reverse('license_activation') + '?error=invalid')

        # Circuit Breaker: jika OPEN, skip panggilan CLS
        if config.is_circuit_open():
            logger.info("Circuit breaker OPEN — skip panggilan CLS, gunakan cache.")
            if config.validation_cache:
                interception = _check_maintenance_or_update(config)
                if interception:
                    return interception
                request.offline_warning = True
                return self.get_response(request)
            else:
                return HttpResponseRedirect(reverse('license_activation') + '?error=invalid')

        # Cache expired → ping CLS
        hardware_id = config.hardware_id or generate_hardware_id()
        cls_url = config.cls_server_url if config.cls_server_url else getattr(
            settings, 'LICENSE_SERVER_URL', 'https://cls.serpgroup.cloud'
        )

        is_valid = self._validate_with_cls(config, hardware_id, cls_url)

        if is_valid:
            interception = _check_maintenance_or_update(config)
            if interception:
                return interception
            return self.get_response(request)

        # Jika CLS offline dan ada cache terakhir yang valid — graceful degradation
        if config.validation_cache and config.last_validated:
            tolerance = timedelta(hours=24)
            if (timezone.now() - config.last_validated) < tolerance:
                logger.warning("CLS offline — graceful degradation (cache < 24 jam).")
                request.offline_warning = True
                return self.get_response(request)

        return HttpResponseRedirect(reverse('license_activation') + '?error=invalid')

    def _is_cls_unreachable(self, config):
        """
        Cek apakah CLS reachable dengan ping cepat.

        Penting: HTTP error (4xx/5xx) tetap berarti server REACHABLE —
        server merespons, hanya endpoint-nya yang bermasalah.
        Hanya network-level errors (timeout, DNS, connection refused)
        yang dianggap server truly unreachable.
        """
        cls_url = config.cls_server_url if config.cls_server_url else getattr(
            settings, 'LICENSE_SERVER_URL', 'https://cls.serpgroup.cloud'
        )
        health_url = f"{cls_url.rstrip('/')}/api/v1/license/status/"
        try:
            req = urllib.request.Request(health_url, method='GET')
            with urllib.request.urlopen(req, timeout=5):
                return False
        except urllib.error.HTTPError:
            # Server merespons (404, 500, dll) — artinya server REACHABLE
            logger.info("CLS reachable tapi endpoint health return HTTP error.")
            return False
        except urllib.error.URLError as e:
            logger.warning(f"CLS tidak terjangkau (URLError): {e.reason}")
            return True
        except Exception as e:
            logger.warning(f"CLS tidak terjangkau (unexpected): {e}")
            return True
    def _validate_with_cls(self, config, hardware_id, cls_url):
        """
        Validasi lisensi ke CLS dengan circuit breaker tracking.
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
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('is_valid', False):
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
                    logger.info(f"Validasi lisensi berhasil: {config.license_key[:8]}***")
                    return True
                else:
                    config.update_validation_cache(
                        is_valid=False,
                        message=data.get('message', 'Lisensi tidak valid.')
                    )
                    logger.warning(f"Validasi gagal: {data.get('message')}")
                    return False

        except urllib.error.HTTPError as e:
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
            config.record_failure()
            logger.error(f"Gagal menghubungi CLS (Offline): {e}")
            return False

        except Exception as e:
            config.record_failure()
            logger.error(f"Error saat validasi lisensi: {e}")
            return False
