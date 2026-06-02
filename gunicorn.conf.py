"""
==========================================================================
 GUNICORN PRODUCTION CONFIG — SIMS-Software-Isolated-Schema-34
==========================================================================
 Panduan deploy:
   gunicorn -c gunicorn.conf.py config.wsgi:application

 Untuk systemd service:
   ExecStart=/path/to/env/bin/gunicorn -c gunicorn.conf.py config.wsgi:application
==========================================================================
"""
import multiprocessing

# ===== SOCKET / BIND =====
# Bind ke semua interface port 8000 (Nginx akan proxy ke sini)
bind = "0.0.0.0:8000"

# ===== WORKERS =====
# Formula standar: (2 x CPU cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"      # sync untuk Django standard (ganti ke gevent jika butuh async)
worker_connections = 1000  # Koneksi per worker (relevan untuk gevent)
timeout = 120              # Kill worker jika request >120 detik
keepalive = 5              # Detik Nginx keep-alive connection

# ===== WORKER RESTART (mencegah memory leak) =====
max_requests = 1000        # Restart worker setelah 1000 requests
max_requests_jitter = 100  # Random jitter agar worker tidak restart bersamaan

# ===== LOGGING =====
accesslog = "-"            # stdout (systemd/Docker akan capture)
errorlog  = "-"            # stderr
loglevel  = "info"         # debug | info | warning | error | critical
capture_output = True      # Capture Django print() ke errorlog

# ===== PROCESS NAMING =====
proc_name = "sims_erp_schema"

# ===== SECURITY =====
limit_request_line   = 4096   # Max panjang URL
limit_request_fields = 100    # Max HTTP headers
forwarded_allow_ips  = "*"    # Trust X-Forwarded-For dari Nginx (sesuaikan IP Nginx di prod)

# ===== GRACEFUL SHUTDOWN =====
graceful_timeout = 30          # Tunggu 30 detik sebelum force-kill worker
