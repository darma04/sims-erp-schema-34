"""
==========================================================================
 MAINTENANCE MIDDLEWARE
==========================================================================
 Middleware untuk memblokir akses ke aplikasi jika Mode Maintenance aktif.
 Hanya superuser (Admin) yang diizinkan mengakses aplikasi.
 Pengaturan dibaca dari model PengaturanPerusahaan.
==========================================================================
"""
from django.shortcuts import redirect
from django.urls import reverse

import logging

logger = logging.getLogger(__name__)


class MaintenanceMiddleware:
    """
    Mengecek status maintenance_mode di database.
    Jika aktif, lempar ke halaman maintenance, kecuali:
    1. Superuser
    2. Path yang dikecualikan (static, media, maintenance page, login, logout, admin)
    """
    EXEMPT_PATHS = [
        '/static/',
        '/media/',
        '/admin/',
        '/login/',
        '/logout/',
        '/license/',
        '/license/ping/',
        '/pages/misc/under_maintenance/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        
        # Mengecualikan prefix statis atau halaman tertentu
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return self.get_response(request)

        # Cek jika mode maintenance berjalan di database
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            pengaturan = PengaturanPerusahaan.load()
            if hasattr(pengaturan, 'maintenance_mode') and pengaturan.maintenance_mode:
                # Bypass untuk superuser (harus login terlebih dahulu)
                if request.user.is_authenticated and request.user.is_superuser:
                    return self.get_response(request)
                
                # Lempar semua akses lain ke halaman maintenance
                return redirect(reverse('pages-misc-under-maintenance'))
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
            
        return self.get_response(request)
