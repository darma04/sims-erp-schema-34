# Public Endpoints (Non-RBAC)

Endpoint berikut tidak memiliki proteksi RBAC karena memang untuk publik:

| Endpoint | Method | Tujuan | Justifikasi |
|---|---|---|---|
| `/health/` | GET | Cek status servis | Monitoring |
| `/login/` | GET/POST | Login | Autentikasi |
| `/logout/` | GET | Logout | Autentikasi |
| `/password-reset/` | GET/POST | Reset password | Autentikasi |

**Verifikasi terakhir:** 2026-07-27
- [x] Semua endpoint di atas sengaja publik
- [x] Tidak ada endpoint bisnis tanpa RBAC
