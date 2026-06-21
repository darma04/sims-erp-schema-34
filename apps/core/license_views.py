"""
==========================================================================
 LICENSE VIEWS — View untuk Halaman Aktivasi Lisensi
==========================================================================
 View ini menangani:
 1. Menampilkan halaman aktivasi (form input license key)
 2. Memproses aktivasi: mengirim license_key + hardware_id ke CLS
 3. Menyimpan hasil aktivasi ke database lokal (LicenseConfig)

 Koneksi:
 - apps/core/license_models.py → LicenseConfig
 - apps/core/license_middleware.py → Redirect ke sini jika belum aktif
 - Central License Server → API /api/v1/license/activate/
==========================================================================
"""
import json
import urllib.request
import urllib.error
import logging
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse

from .license_models import LicenseConfig, generate_hardware_id

logger = logging.getLogger(__name__)


@csrf_protect
def license_activation_view(request):
    """
    Halaman aktivasi lisensi.
    GET: Tampilkan form input license key.
    POST: Proses aktivasi ke CLS.
    """
    config = LicenseConfig.get_config()
    hardware_id = config.hardware_id or generate_hardware_id()
    error_message = request.GET.get('error', '')

    # Jika sudah aktif dan cache valid, redirect ke dashboard
    if config.is_activated and config.is_cache_valid() and config.validation_cache:
        return redirect('/')

    if request.method == 'POST':
        license_key = request.POST.get('license_key', '').strip()
        # Jika user mengisi url di form, gunakan itu. Jika tidak, ambil dari config, jika tidak ada, gunakan dari setting/default.
        cls_url = request.POST.get('cls_url', '').strip()
        if not cls_url:
            cls_url = config.cls_server_url if config.cls_server_url else getattr(settings, 'LICENSE_SERVER_URL', "https://cls.serpgroup.cloud")
        
        if not license_key:
            messages.error(request, 'Kunci lisensi wajib diisi!')
            return render(request, 'license/activation.html', {
                'config': config,
                'hardware_id': hardware_id,
            })

        # Update URL CLS jika disediakan
        if cls_url:
            config.cls_server_url = cls_url

        # Simpan hardware_id
        config.hardware_id = hardware_id
        config.save()

        # Kirim request aktivasi ke CLS
        success, message = _activate_with_cls(config, license_key, hardware_id)

        if success:
            config.license_key = license_key
            config.is_activated = True
            config.save()
            messages.success(request, f'Lisensi berhasil diaktifkan! {message}')
            return redirect('/')
        else:
            messages.error(request, f'Aktivasi gagal: {message}')

    context = {
        'config': config,
        'hardware_id': hardware_id,
        'error_message': error_message,
        'product_code': getattr(settings, 'PRODUCT_CODE', 'SIMKOS'),
    }
    return render(request, 'license/activation.html', context)


@csrf_protect
def license_error_view(request):
    """
    Halaman error ramah pengguna saat CLS down di instalasi baru.
    Memberikan instruksi jelas untuk admin.
    """
    config = LicenseConfig.get_config()
    hardware_id = config.hardware_id or generate_hardware_id()
    cls_url = config.cls_server_url if config.cls_server_url else getattr(
        settings, 'LICENSE_SERVER_URL', 'https://cls.serpgroup.cloud'
    )
    return render(request, 'license/error.html', {
        'config': config,
        'hardware_id': hardware_id,
        'cls_url': cls_url,
        'product_code': getattr(settings, 'PRODUCT_CODE', 'SERPTECH'),
    })


def license_status_view(request):
    """Menampilkan status lisensi saat ini (untuk admin)."""
    config = LicenseConfig.get_config()
    return render(request, 'license/status.html', {'config': config})


def license_ping_view(request):
    """
    Endpoint ringan untuk mengecek status maintenance dan aktivasi secara realtime via AJAX.
    Endpoint ini harus dikecualikan dari middleware pemblokir.
    """
    config = LicenseConfig.get_config()
    
    # Cek maintenance lokal
    try:
        from apps.pengaturan.models import PengaturanPerusahaan
        pengaturan = PengaturanPerusahaan.load()
        local_maintenance = getattr(pengaturan, 'maintenance_mode', False)
    except Exception:
        local_maintenance = False

    # Superuser kebal dari local maintenance
    is_superuser = request.user.is_authenticated and request.user.is_superuser
    if is_superuser:
        local_maintenance = False

    is_maintenance_mode = config.is_maintenance or local_maintenance

    return JsonResponse({
        'is_activated': config.is_activated,
        'is_maintenance_mode': bool(is_maintenance_mode)
    })



def _activate_with_cls(config, license_key, hardware_id):
    """
    Mengirim request aktivasi ke Central License Server.

    Returns:
        tuple: (success: bool, message: str)
    """
    cls_url = config.cls_server_url if config.cls_server_url else getattr(settings, 'LICENSE_SERVER_URL', "https://cls.serpgroup.cloud")
    activate_url = f"{cls_url.rstrip('/')}/api/v1/license/activate/"

    payload = json.dumps({
        "license_key": license_key,
        "hardware_id": hardware_id,
        "device_name": getattr(settings, 'DEVICE_NAME', 'Server Klien'),
    }).encode('utf-8')

    req = urllib.request.Request(
        activate_url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

            if data.get('status') == 'success':
                resp_data = data.get('data', {})
                config.update_validation_cache(
                    is_valid=True,
                    message="Aktivasi berhasil.",
                    expires_at=resp_data.get('expires_at'),
                    product_name=resp_data.get('product_name'),
                    client_name=resp_data.get('client_name'),
                    is_maintenance=resp_data.get('is_maintenance', False),
                    maintenance_message=resp_data.get('maintenance_message'),
                    min_app_version=resp_data.get('min_app_version', 'v1.0'),
                    force_update_url=resp_data.get('force_update_url')
                )
                expires_info = ""
                if resp_data.get('expires_at'):
                    expires_info = f" Berlaku sampai: {resp_data['expires_at'][:10]}"
                return True, f"Produk: {resp_data.get('product_name', '-')}{expires_info}"
            else:
                return False, data.get('message', 'Respon tidak dikenali dari server.')

    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode('utf-8'))
            return False, body.get('message', f'HTTP Error {e.code}')
        except Exception:
            return False, f'Gagal koneksi ke server (HTTP {e.code})'

    except urllib.error.URLError as e:
        return False, f'Tidak dapat menghubungi CLS: {e.reason}. Pastikan URL server benar dan server aktif.'

    except Exception as e:
        logger.error(f"Error aktivasi lisensi: {e}")
        return False, f'Terjadi kesalahan: {str(e)}'
