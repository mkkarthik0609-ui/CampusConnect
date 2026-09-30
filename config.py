"""Application configuration.

Everything deployment-specific is read from environment variables (a local ``.env`` file is
loaded first when python-dotenv is available). See the variable list at the bottom of this file.
"""
import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

try:  # python-dotenv is optional at runtime; real environment variables always win.
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
except ImportError:  # pragma: no cover
    pass

DEV_DEFAULT_SECRET = "dev-secret-key-change-in-production"


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _detect_environment():
    env = (os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
    if env:
        return env
    # Render sets RENDER=true on its services; never run those in "development" mode by accident.
    if os.environ.get("RENDER"):
        return "production"
    return "development"


ENVIRONMENT = _detect_environment()
IS_PRODUCTION = ENVIRONMENT == "production"


def _resolve_secret_key():
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key
    if IS_PRODUCTION:
        return ""  # create_app() refuses to start without one
    # Development convenience: a random key that is persisted locally so sessions survive
    # debug-reloader restarts. Never the published default.
    path = os.path.join(BASE_DIR, ".dev_secret_key")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                stored = f.read().strip()
            if stored:
                return stored
        generated = secrets.token_hex(32)
        with open(path, "w", encoding="utf-8") as f:
            f.write(generated)
        return generated
    except OSError:
        return secrets.token_hex(32)


class Config:
    ENVIRONMENT = ENVIRONMENT
    IS_PRODUCTION = IS_PRODUCTION

    SECRET_KEY = _resolve_secret_key()
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "database.db")

    # On Render point UPLOAD_ROOT at the persistent disk (e.g. /var/data/uploads).
    UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT") or os.path.join(BASE_DIR, "uploads")
    PROFILE_STUDENT_DIR = os.path.join(UPLOAD_ROOT, "profile", "students")
    PROFILE_FACULTY_DIR = os.path.join(UPLOAD_ROOT, "profile", "faculty")
    CHAT_UPLOAD_DIR = os.path.join(UPLOAD_ROOT, "chat")

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB hard cap per request
    MAX_CHAT_ATTACHMENT_SIZE = 8 * 1024 * 1024  # 8 MB
    MAX_PROFILE_PICTURE_SIZE = 3 * 1024 * 1024  # 3 MB

    ALLOWED_CHAT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx"}
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}

    # ---- OTP (student signup) ----
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 10
    OTP_MAX_ATTEMPTS = 5
    OTP_MAX_PER_EMAIL_PER_HOUR = _env_int("OTP_MAX_PER_EMAIL_PER_HOUR", 5)
    OTP_MAX_PER_IP_PER_HOUR = _env_int("OTP_MAX_PER_IP_PER_HOUR", 20)
    OTP_VERIFIED_MAX_AGE_MINUTES = 30  # verified OTP must be used to register within this time
    # On-screen demo OTP. Default on so the project works out of the box; set SHOW_DEMO_OTP=0 in
    # production and configure SMTP_* instead (or accept demo mode knowingly).
    SHOW_DEMO_OTP = _env_bool("SHOW_DEMO_OTP", True)
    SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
    SMTP_PORT = _env_int("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", "")
    SMTP_TLS = os.environ.get("SMTP_TLS", "1").strip().lower()  # "1"/"starttls", "ssl", or "0"

    # ---- login throttling ----
    LOGIN_WINDOW_MINUTES = 15
    LOGIN_MAX_FAILURES_PER_IDENTIFIER = _env_int("LOGIN_MAX_FAILURES_PER_IDENTIFIER", 5)
    LOGIN_MAX_FAILURES_PER_IP = _env_int("LOGIN_MAX_FAILURES_PER_IP", 20)

    # ---- sessions / cookies ----
    SESSION_COOKIE_NAME = "cc_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)  # absolute lifetime of a login
    SESSION_IDLE_TIMEOUT_MINUTES = _env_int("SESSION_IDLE_TIMEOUT_MINUTES", 60)

    # ---- CSRF ----
    WTF_CSRF_TIME_LIMIT = None  # token lives as long as the session
    # Flask-WTF's strict HTTPS Referer check compares Referer with request.host. Behind a rewrite
    # proxy chain (Vercel -> Render) the host may differ, so default it off when TRUST_PROXY is used.
    TRUST_PROXY = _env_bool("TRUST_PROXY", False)
    TRUST_PROXY_HOPS = _env_int("TRUST_PROXY_HOPS", 1)  # number of proxies appending X-Forwarded-For
    WTF_CSRF_SSL_STRICT = _env_bool("CSRF_SSL_STRICT", not TRUST_PROXY)

    # ---- misc ----
    REMINDER_INTERVAL_MINUTES = int(os.environ.get("REMINDER_INTERVAL_MINUTES", "60"))
    ENABLE_SCHEDULER = _env_bool("ENABLE_SCHEDULER", True)
    BOOTSTRAP_ADMIN = _env_bool("BOOTSTRAP_ADMIN", False)


# Environment variables understood by the app (all optional unless noted):
#   APP_ENV / FLASK_ENV      "production" enables Secure cookies, HSTS and the SECRET_KEY check
#   SECRET_KEY               REQUIRED in production (long random string)
#   FLASK_DEBUG              "1" turns the debugger on for `python app.py` (never in production)
#   DATABASE_PATH            SQLite file location (e.g. /var/data/campus.db)
#   UPLOAD_ROOT              uploads directory (e.g. /var/data/uploads)
#   TRUST_PROXY=1            apply ProxyFix (behind Render / Vercel rewrite)
#   TRUST_PROXY_HOPS         proxies in front of the app (default 1; Vercel + Render = 2)
#   SHOW_DEMO_OTP            "1" (default) show OTP on screen when SMTP is not configured
#   SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS   optional real OTP email delivery
#   BOOTSTRAP_ADMIN=1        create ADMIN_NAME/ADMIN_EMAIL/ADMIN_PASSWORD admin at start (idempotent)
#   ENABLE_SCHEDULER=0       disable the reminder scheduler
#   LOGIN_MAX_FAILURES_PER_IDENTIFIER / LOGIN_MAX_FAILURES_PER_IP / SESSION_IDLE_TIMEOUT_MINUTES
#   OTP_MAX_PER_EMAIL_PER_HOUR / OTP_MAX_PER_IP_PER_HOUR / CSRF_SSL_STRICT


def validate_config(config):
    """Raise RuntimeError for unsafe production configuration. `config` is a Flask config mapping."""
    if config.get("TESTING"):
        return
    production = bool(config.get("IS_PRODUCTION")) or config.get("ENVIRONMENT") == "production"
    key = config.get("SECRET_KEY") or ""
    if production and (not key or key == DEV_DEFAULT_SECRET):
        raise RuntimeError(
            "SECRET_KEY must be set to a strong random value when APP_ENV/FLASK_ENV=production."
        )
    if not key or key == DEV_DEFAULT_SECRET:
        raise RuntimeError("SECRET_KEY is missing or set to the insecure development default.")
    if production and len(key) < 24:
        raise RuntimeError("SECRET_KEY is too short; use at least 24 random characters in production.")
