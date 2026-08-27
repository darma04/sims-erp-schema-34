"""
==========================================================================
 VERIFY EMAIL VIEWS - Halaman Verifikasi Email
==========================================================================
 File ini berisi 3 view untuk proses verifikasi email:

 1. VerifyEmailTokenView → Proses klik link verifikasi dari email
 2. VerifyEmailView → Halaman informasi "Cek email Anda"
 3. SendVerificationView → Kirim ulang email verifikasi

 Alur verifikasi email:
 1. User registrasi → email verifikasi dikirim (berisi link dengan token)
 2. User klik link → VerifyEmailTokenView memproses token
 3. Profile.is_verified = True → user bisa login
 4. Jika email tidak sampai → user bisa kirim ulang via SendVerificationView

 Koneksi:
 - auth/views.py → AuthView (base class)
 - auth/helpers.py → send_verification_email()
 - auth/models.py → Profile (field email_token, is_verified)
 - auth/urls.py → 3 URL pattern untuk 3 view ini
==========================================================================
"""

from django.shortcuts import redirect          # Fungsi redirect
from django.contrib import messages             # Framework pesan flash
from django.conf import settings                # Akses pengaturan Django
from django.utils.decorators import method_decorator  # Decorator untuk CBV
from auth.views import AuthView                 # Base class autentikasi
from auth.models import Profile                 # Model Profile
from auth.helpers import send_verification_email  # Fungsi kirim email verifikasi
from auth.rate_limit import rate_limit_view     # Rate limit decorator
import uuid                                    # Modul generate token unik


class VerifyEmailTokenView(AuthView):
    """
    View untuk memproses token verifikasi email.

    URL: /verify/email/{token}/
    Dipanggil saat user klik link verifikasi di email mereka.

    Alur:
    1. Cari Profile dengan email_token yang sesuai
    2. Set is_verified = True
    3. Hapus token (agar tidak bisa dipakai ulang)
    4. Redirect ke halaman login
    """

    def get(self, request, token):
        """
        Proses verifikasi email menggunakan token dari URL.

        Parameter:
        - token: String UUID dari link verifikasi email

        Langkah:
        1. Cari Profile berdasarkan token
        2. Set is_verified = True → email terverifikasi
        3. Hapus token → one-time use
        4. Tampilkan pesan sukses
        5. Redirect ke login
        """
        try:
            # Cari Profile dengan token yang sesuai
            profile = Profile.objects.filter(email_token=token).first()

            if profile is None:
                # Token tidak ditemukan / sudah dipakai -> perlakukan sebagai invalid
                messages.error(request, "Token tidak valid, silakan coba lagi")
                return redirect("verify-email-page")

            # Update status verifikasi
            profile.is_verified = True
            profile.email_token = ""  # Hapus token (sudah dipakai)
            profile.save()

            if not request.user.is_authenticated:
                # User belum login → tampilkan pesan sukses
                messages.success(request, "Email berhasil diverifikasi")

            # Redirect ke halaman login
            return redirect("login")

        except Profile.DoesNotExist:
            # Token tidak ditemukan → invalid atau sudah dipakai
            messages.error(request, "Token tidak valid, silakan coba lagi")
            return redirect("verify-email-page")


class VerifyEmailView(AuthView):
    """
    View untuk halaman informasi verifikasi email.

    URL: /verify_email/
    Menampilkan pesan "Silakan cek email Anda untuk link verifikasi".
    Hanya render template saja, tidak ada logika tambahan.
    """

    def get(self, request):
        """Render halaman informasi verifikasi email."""
        return super().get(request)


class SendVerificationView(AuthView):
    """
    View untuk mengirim ulang email verifikasi.

    URL: /send_verification/
    Digunakan saat user tidak menerima email verifikasi pertama.

    Mendukung 2 skenario:
    1. User sudah login → ambil email dari profile
    2. User belum login → ambil email dari session (disimpan saat registrasi)

    Rate Limit:
    - GET dibatasi 3 percobaan per 10 menit per IP
    - Mencegah spam pengiriman email verifikasi
    """

    @method_decorator(rate_limit_view(max_attempts=3, period=600, redirect_url='verify-email-page'))
    def get(self, request):
        """
        Kirim ulang email verifikasi (GET).

        Alur:
        1. Ambil email dan pesan dari helper method
        2. Jika email ditemukan:
           a. Generate token UUID baru
           b. Update token di Profile
           c. Kirim email verifikasi baru
        3. Jika email tidak ditemukan → tampilkan error
        4. Redirect ke halaman verifikasi
        """
        # Ambil email dan pesan berdasarkan status autentikasi user
        email, message = self.get_email_and_message(request)

        if email:
            # Generate token baru (token lama sudah tidak valid)
            token = str(uuid.uuid4())

            # Update token di Profile user
            user_profile = Profile.objects.filter(email=email).first()
            user_profile.email_token = token
            user_profile.save()

            # Kirim email verifikasi dengan token baru
            send_verification_email(email, token)
            messages.success(request, message)
        else:
            # Email tidak ditemukan di session atau profile
            messages.error(request, "Email tidak ditemukan di sesi")

        return redirect("verify-email-page")

    def get_email_and_message(self, request):
        """
        Mendapatkan email user dan pesan sukses berdasarkan status autentikasi.

        Dua skenario:
        1. User SUDAH LOGIN:
           - Email diambil dari request.user.profile.email
           - Cek apakah SMTP sudah dikonfigurasi

        2. User BELUM LOGIN (biasanya baru registrasi):
           - Email diambil dari session (disimpan di register view)
           - Cek apakah SMTP sudah dikonfigurasi

        Return:
        - Tuple (email, message) → email tujuan dan pesan untuk user
        """
        if request.user.is_authenticated:
            # User sudah login → ambil email dari profile
            email = request.user.profile.email

            # Cek apakah pengaturan email SMTP sudah dikonfigurasi
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                message = messages.success(request, "Email verifikasi berhasil dikirim")
            else:
                message = messages.error(request, "Pengaturan email belum dikonfigurasi. Tidak dapat mengirim email verifikasi.")
        else:
            # User belum login → ambil email dari session
            email = request.session.get('email')

            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                message = "Email verifikasi berhasil dikirim ulang" if email else None
            else:
                 message = messages.error(request, "Pengaturan email belum dikonfigurasi. Tidak dapat mengirim email verifikasi.")

        return email, message
