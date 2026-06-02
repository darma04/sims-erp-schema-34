"""
Endpoint manual refresh cache tenant aktif.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.core.cache_utils import invalidate_tenant_response_cache
from apps.core.permissions import has_exact_submodule_permission


def _can_refresh_cache(user):
    return has_exact_submodule_permission(user, 'read', 'dashboard', 'refresh_cache')


@login_required
@require_POST
def refresh_cache_view(request):
    """Refresh cache dashboard/laporan/context tenant aktif."""
    if not _can_refresh_cache(request.user):
        return JsonResponse({
            'ok': False,
            'message': 'Anda tidak memiliki izin untuk refresh cache.',
        }, status=403)

    result = invalidate_tenant_response_cache(request=request)
    return JsonResponse({
        'ok': True,
        'message': 'Cache berhasil di bersihkan',
        'scope': result['scope'],
        'versions': result['versions'],
    })
