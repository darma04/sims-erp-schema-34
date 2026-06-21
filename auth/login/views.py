"""
==========================================================================
 LOGIN VIEW - Halaman Login User
==========================================================================
 File ini menangani proses login user ke sistem.

 Alur login:
 1. User mengakses /login/ → tampilkan form login (GET)
 2. User mengisi email/username + password → submit form (POST)
 3. Validasi input, cari user di database
 4. Authenticate (cek password) → jika valid, login dan redirect
 5. Jika gagal → tampilkan pesan error

 Fitur:
 - Login bisa pakai USERNAME atau EMAIL
 - Redirect ke halaman yang dituju sebelum login (parameter 'next')
 - User yang sudah login otomatis redirect ke dashboard

 Koneksi:
 - auth/views.py → AuthView (base class dengan layout blank)
 - auth/urls.py → path("login/", ..., name="login")
 - templates/auth/login.html → Template form login
 - django.contrib.auth → authenticate() dan login() bawaan Django
 - dashboard/urls.py → Redirect setelah login berhasil
==========================================================================
"""

from django.shortcuts import redirect                  # Fungsi untuk redirect ke URL lain
from django.contrib.auth import authenticate, login     # Fungsi autentikasi Django
from django.contrib.auth.models import User             # Model User bawaan Django
from django.contrib import messages                     # Framework pesan flash Django
from django.utils.decorators import method_decorator    # Decorator untuk CBV
from auth.views import AuthView                         # Base class untuk view autentikasi
from django.utils.http import url_has_allowed_host_and_scheme  # Validasi URL redirect
from auth.rate_limit import rate_limit_view             # Rate limit decorator


class LoginView(AuthView):
    """
    View untuk halaman login.

    Mewarisi AuthView → otomatis menggunakan layout_blank.html.
    Template form login ditentukan di urls.py: template_name="auth/login.html"

    Method:
    - get(): Menampilkan form login
    - post(): Memproses submit form login

    Rate Limit:
    - POST dibatasi 5 percobaan per 5 menit per IP
    - Mencegah serangan brute-force (tebak password)
    """

    def get(self, request):
        """
        Menampilkan halaman login (method GET).

        Logika:
        - Jika user sudah login (is_authenticated) → redirect ke dashboard
        - Jika belum login → render form login
        - Force rotate CSRF token agar tidak ada duplicate cookie
        """
        if request.user.is_authenticated:
            # User sudah login → redirect ke dashboard, tidak perlu login lagi
            return redirect("dashboard:index")

        # ================================================================
        # FIX: Force rotate CSRF token setiap kali halaman login dimuat.
        # Ini mencegah duplicate CSRF cookie yang menyebabkan:
        # - Android WebView mengirim token lama → 403 CSRF Failure
        # - Login gagal di aplikasi mobile meskipun kredensial benar
        # ================================================================
        from django.middleware.csrf import rotate_token
        rotate_token(request)

        # User belum login → tampilkan halaman login
        # super().get() memanggil TemplateView.get() yang me-render template
        response = super().get(request)

        # Hapus cookie CSRF lama dengan path/domain yang mungkin berbeda
        # agar hanya ada SATU cookie CSRF yang valid
        from django.conf import settings
        cookie_name = getattr(settings, 'CSRF_COOKIE_NAME', 'csrftoken')
        response.delete_cookie(cookie_name, path='/')
        response.delete_cookie(cookie_name, path='/login/')
        response.delete_cookie(cookie_name, path='/login')
        # Juga hapus nama cookie default Django jika pernah digunakan sebelumnya
        if cookie_name != 'csrftoken':
            response.delete_cookie('csrftoken', path='/')

        return response

    @method_decorator(rate_limit_view(max_attempts=5, period=300, redirect_url='login'))
    def post(self, request):
        """
        Memproses form login (method POST).

        Alur detail:
        1. Ambil input dari form (email-username dan password)
        2. Validasi: pastikan kedua field terisi
        3. Cek apakah input adalah email (ada '@') atau username
        4. Jika email → cari User berdasarkan email, ambil username-nya
        5. Jika username → cari User berdasarkan username
        6. authenticate() → cek apakah password cocok
        7. Jika cocok → login() dan redirect ke dashboard
        8. Jika tidak → tampilkan pesan error

        Kenapa pakai authenticate() bukan cek manual?
        - authenticate() meng-hash password dan membandingkan
        - Password di database TIDAK pernah disimpan plain text
        - Django menggunakan PBKDF2 hashing algorithm
        """
        if request.method == "POST":
            # Ambil input dari form HTML
            # Name field di template: name="email-username" dan name="password"
            username = request.POST.get("email-username")
            password = request.POST.get("password")

            # Validasi: field tidak boleh kosong
            if not (username and password):
                messages.error(request, "Silakan masukkan username dan kata sandi Anda.")
                return redirect("login")

            # Cek apakah input berupa EMAIL (mengandung '@')
            if "@" in username:
                # Cari user berdasarkan email
                user_email = User.objects.filter(email=username).first()
                if user_email is None:
                    messages.error(request, "Email tidak ditemukan dalam sistem.")
                    return redirect("login")
                # Ambil username dari user yang ditemukan
                # (karena authenticate() butuh username, bukan email)
                username = user_email.username

            # Cek apakah username ada di database
            user_email = User.objects.filter(username=username).first()
            if user_email is None:
                messages.error(request, "Username tidak ditemukan dalam sistem.")
                return redirect("login")

            # Proses autentikasi: cek apakah password cocok
            # authenticate() mengembalikan User object jika cocok, None jika tidak
            authenticated_user = authenticate(request, username=username, password=password)
            if authenticated_user is not None:
                # Password cocok → login user (buat session)
                # login() menyimpan user ID di session Django
                login(request, authenticated_user)

                # Cek parameter 'next' — URL yang dituju sebelum redirect ke login
                # Contoh: user akses /produk/ tapi belum login → redirect ke /login/?next=/produk/
                # Setelah login → redirect kembali ke /produk/
                if "next" in request.POST:
                    next_url = request.POST["next"]
                    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                        return redirect(next_url)
                    else:
                        return redirect("dashboard:index")
                else:
                    # Tidak ada 'next' → redirect ke dashboard
                    return redirect("dashboard:index")
            else:
                # Password tidak cocok → tampilkan error
                messages.error(request, "Username atau kata sandi salah.")
                return redirect("login")

