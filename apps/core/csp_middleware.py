"""
==========================================================================
 CONTENT SECURITY POLICY (CSP) MIDDLEWARE
==========================================================================
 Middleware untuk menambahkan header Content-Security-Policy pada response
 guna mencegah serangan Cross-Site Scripting (XSS).
==========================================================================
"""

class CSPMiddleware:
    """
    Middleware yang menambahkan header Content-Security-Policy ke setiap HTTP response.
    Menerapkan strict policy untuk asset eksternal namun menyisakan kelonggaran
    'unsafe-inline' dan 'unsafe-eval' demi mendukung integrasi & library UI Materialize.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Directive CSP yang seimbang antara kemudahan integrasi UI & keamanan
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob: https:",
            "connect-src 'self'",
            "frame-src 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        
        # Tambahkan header CSP
        response['Content-Security-Policy'] = "; ".join(csp_directives)
        return response
