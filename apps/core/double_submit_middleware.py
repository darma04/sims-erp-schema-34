"""
==========================================================================
 DOUBLE SUBMIT MIDDLEWARE - Pencegahan Duplikasi Form Submit
==========================================================================
 Middleware ini mencegah user menekan tombol 'Back' di browser lalu
 menekan 'Simpan' lagi yang menyebabkan data tersimpan ganda (duplikat).

 Pendekatan: WHITELIST TOKEN
 1. Saat GET: Generate token, simpan di session sebagai "token valid",
    dan inject ke form sebagai hidden input.
 2. Saat POST: Cek apakah token dari form ADA di daftar "token valid".
    - Jika ADA → hapus dari daftar (sekali pakai) → proses request.
    - Jika TIDAK ADA → double submit → tolak + pesan warning.

 Mengapa whitelist?
 - Blacklist gagal karena saat browser reload form (setelah Back),
   server menghasilkan token baru yang belum ada di blacklist.
 - Whitelist memastikan token lama yang sudah dipakai DIHAPUS,
   sehingga submit ulang pasti ditolak.

 Fitur tambahan:
 - JavaScript pageshow listener: Paksa reload saat browser load
   halaman dari bfcache (Back-Forward Cache).
 - Anti-Cache header (no-store) sebagai lapisan tambahan.

 Kompatibel dengan: Desktop Browser, Mobile Browser, WebView Android.
==========================================================================
"""

import uuid
import re
from django.shortcuts import redirect
from django.contrib import messages


class PreventDoubleSubmitMiddleware:
    """
    Middleware untuk mencegah form double submit menggunakan
    pendekatan whitelist token (sekali pakai).
    """

    # Script JS untuk mendeteksi bfcache dan memaksa reload
    PAGESHOW_SCRIPT = (
        '<script>'
        'window.addEventListener("pageshow",function(e){'
        'if(e.persisted||'
        '(window.performance&&window.performance.getEntriesByType("navigation").length>0&&'
        'window.performance.getEntriesByType("navigation")[0].type==="back_forward")){'
        'document.querySelectorAll("form").forEach(function(f){f.reset();});'
        'document.querySelectorAll("input[name=_submit_token]").forEach(function(t){t.value="";});'
        'document.querySelectorAll("select").forEach(function(s){'
        'if(s.tomselect){s.tomselect.clear();}'
        'else if(s.slim){s.slim.set("");}'
        'else{s.selectedIndex=0;}'
        '});'
        '}'
        '});'
        '</script>'
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Bypass untuk AJAX, API, dan file statis ──
        if self._should_skip(request):
            return self.get_response(request)

        # ── 2. Validasi Token saat POST ──
        if request.method == 'POST':
            submit_token = request.POST.get('_submit_token')

            if submit_token:
                valid_tokens = request.session.get('_valid_submit_tokens', [])

                if submit_token in valid_tokens:
                    # Token valid → Hapus dari whitelist (sekali pakai)
                    valid_tokens.remove(submit_token)
                    request.session['_valid_submit_tokens'] = valid_tokens
                    request.session.modified = True
                    # Lanjutkan ke view (request diterima)
                else:
                    # Token TIDAK ada di whitelist → Double Submit
                    messages.warning(
                        request,
                        'Data sudah berhasil disimpan sebelumnya. '
                        'Permintaan duplikat ditolak.'
                    )
                    # Redirect ke halaman form (GET) agar mendapat token baru
                    return redirect(request.path)

        # ── 3. Jalankan View ──
        response = self.get_response(request)

        # ── 4. Inject token + Anti-Cache untuk halaman HTML GET ──
        if request.method == 'GET' and self._is_html_response(response):
            self._inject_token_and_nocache(request, response)

        return response

    def _should_skip(self, request):
        """Cek apakah request harus di-bypass (AJAX, API, static files)."""
        # AJAX request
        if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return True
        # Accept header JSON (API)
        accept = request.META.get('HTTP_ACCEPT', '')
        if 'application/json' in accept and 'text/html' not in accept:
            return True
        # API endpoint
        if '/api/' in request.path:
            return True
        # Static / media files
        if request.path.startswith(('/static/', '/media/')):
            return True
        return False

    def _is_html_response(self, response):
        """Cek apakah response berisi HTML dan bisa dimodifikasi."""
        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return False
        if getattr(response, 'streaming', False):
            return False
        if not hasattr(response, 'content'):
            return False
        return True

    def _inject_token_and_nocache(self, request, response):
        """
        Sisipkan hidden _submit_token ke setiap <form method="post">.
        Token disimpan di session sebagai whitelist (token valid).
        Juga sisipkan script pageshow untuk handle bfcache.
        """
        try:
            content = response.content

            # Cek apakah halaman ini mengandung form POST (bytes check)
            content_lower = content.lower()
            if b'<form' not in content_lower or b'method' not in content_lower:
                return

            # Decode untuk regex processing
            html = content.decode('utf-8', errors='ignore')

            # Pattern: cocokkan <form> tag yang memiliki method="post"
            pattern = re.compile(
                r'(<form\b[^>]*?method\s*=\s*["\']post["\'][^>]*?>)',
                re.IGNORECASE | re.DOTALL
            )

            injected = False
            valid_tokens = request.session.get('_valid_submit_tokens', [])

            def _replacer(match):
                nonlocal injected
                form_tag = match.group(1)
                # Jangan inject jika sudah ada _submit_token
                if '_submit_token' in form_tag:
                    return form_tag
                injected = True
                token = str(uuid.uuid4())
                # Simpan token ke whitelist session
                valid_tokens.append(token)
                hidden_input = (
                    '<input type="hidden" name="_submit_token" '
                    'value="' + token + '">'
                )
                return form_tag + '\n' + hidden_input

            new_html = pattern.sub(_replacer, html)

            # Fallback: coba pattern tanpa quotes
            if not injected:
                pattern2 = re.compile(
                    r'(<form\b[^>]*?method\s*=\s*post[^>]*?>)',
                    re.IGNORECASE | re.DOTALL
                )
                new_html = pattern2.sub(_replacer, new_html)

            if injected:
                # Sisipkan script pageshow sebelum </body> (HANYA tag terakhir)
                # Gunakan rsplit untuk menghindari replace </body> di dalam string JS
                if '</body>' in new_html:
                    parts = new_html.rsplit('</body>', 1)
                    new_html = (self.PAGESHOW_SCRIPT + '</body>').join(parts)

                response.content = new_html.encode('utf-8')

                # Simpan valid tokens ke session (max 30 token)
                request.session['_valid_submit_tokens'] = valid_tokens[-30:]
                request.session.modified = True

                # Update Content-Length jika ada
                if response.has_header('Content-Length'):
                    response['Content-Length'] = len(response.content)

                # Set Anti-Cache header
                response['Cache-Control'] = (
                    'no-store, no-cache, must-revalidate, max-age=0'
                )
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'

        except Exception:
            # Jangan sampai middleware error menghancurkan response
            pass
