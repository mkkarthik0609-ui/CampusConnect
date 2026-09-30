"""Gunicorn settings for Render.

IMPORTANT: keep `workers = 1`.
  * The meeting-reminder job runs in-process (APScheduler BackgroundScheduler); with several
    workers every worker would start its own scheduler and send duplicate reminders.
  * SQLite allows a single writer at a time; one process + threads avoids cross-process lock
    contention. Concurrency comes from threads (I/O bound app), not processes.
Do NOT add `preload_app = True` (the scheduler thread would be created before the fork).
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"  # Render injects PORT (default 10000)

workers = 1                      # hard-coded on purpose; ignores WEB_CONCURRENCY
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

timeout = 60                     # allow for 10 MB uploads on slow links
graceful_timeout = 30
keepalive = 5                    # Render's load balancer reuses connections

# Render (and the Vercel proxy in front of it) terminate TLS; trust their X-Forwarded-* headers
# so gunicorn reports the right scheme. The proxy IPs are not static, hence "*". The service
# is only reachable through Render's load balancer.
forwarded_allow_ips = "*"

accesslog = "-"                  # stdout -> Render log stream
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
