"""
Health check endpoint for monitoring.
Add to urls.py: path('health/', include('apps.core.health_urls'))
"""
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Health check for uptime monitoring."""
    checks = {}
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {str(e)[:50]}'
    
    # Overall status
    all_ok = all(v == 'ok' for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return JsonResponse({
        'status': 'healthy' if all_ok else 'unhealthy',
        'checks': checks,
    }, status=status_code)
