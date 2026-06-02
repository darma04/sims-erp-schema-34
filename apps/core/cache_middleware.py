"""
Invalidasi cache tampilan setelah request mutasi data berhasil.
"""
from apps.core.cache_utils import invalidate_tenant_response_cache


class TenantCacheInvalidationMiddleware:
    """
    Naikkan versi cache tenant aktif setelah request mutasi data sukses.

    Ini menjaga dashboard/laporan tetap cepat saat hanya dibaca, tetapi langsung
    refresh pada request berikutnya setelah POS/PO/SO/biaya/payroll/dll berubah.
    """
    MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
    WATCHED_PREFIXES = (
        '/pos/',
        '/pembelian/',
        '/penjualan/',
        '/biaya/',
        '/hr/',
        '/piutang/',
        '/hutang/',
        '/kas-bank/',
        '/akuntansi/',
        '/inventory/',
        '/produk/',
        '/pajak/',
        '/aset/',
        '/fraud/',
        '/pengaturan/',
        '/service/',
    )
    SKIP_PREFIXES = (
        '/ai/',
        '/activity-log/',
        '/core/cache/refresh/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self._should_invalidate(request, response):
            invalidate_tenant_response_cache(request=request)
            response['X-SERPTECH-Cache-Invalidated'] = '1'
        return response

    def _should_invalidate(self, request, response):
        if request.method not in self.MUTATING_METHODS:
            return False
        if getattr(response, 'status_code', 500) >= 400:
            return False
        path = request.path_info or request.path or ''
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return False
        return any(path.startswith(prefix) for prefix in self.WATCHED_PREFIXES)
