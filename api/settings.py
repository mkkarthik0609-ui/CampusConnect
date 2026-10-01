"""Application settings.

``Settings`` is a plain dataclass. ``Settings.from_env()`` builds it from environment variables
(a local ``.env`` is loaded first; real environment variables always win). Tests build their own
``Settings(...)`` with explicit overrides and pass it to ``create_app(settings)``.

``get_settings()`` returns the settings of the app handling the current request (or, outside a
request, the most recently created app). Framework-agnostic services read configuration through it.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import secrets
from dataclasses import dataclass, replace
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEV_DEFAULT_SECRET = "dev-secret-key-change-in-production"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _detect_environment() -> str:
    env = (os.environ.get("APP_ENV") or "").strip().lower()
    if env:
        return env
    # Render sets RENDER=true on its services; never run those in "development" mode by accident.
    if os.environ.get("RENDER"):
        return "production"
    return "development"


def _dev_secret_key() -> str:
    """Development convenience: a random key persisted locally so sessions survive reloads."""
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


@dataclass(frozen=True)
class Settings:
    """All defaults here are environment-independent, so ``Settings()`` in a test is deterministic."""

    environment: str = "development"
    debug: bool = False
    testing: bool = False  # tests: no scheduler, no admin bootstrap
    secret_key: str = ""

    database_path: str = os.path.join(BASE_DIR, "database.db")
    upload_root: str = os.path.join(BASE_DIR, "uploads")
    frontend_dist: str = os.path.join(BASE_DIR, "frontend", "dist")

    max_request_bytes: int = 10 * 1024 * 1024  # 10 MB hard cap per request
    max_chat_attachment_size: int = 8 * 1024 * 1024
    max_profile_picture_size: int = 3 * 1024 * 1024
    allowed_chat_extensions: frozenset = frozenset({"pdf", "png", "jpg", "jpeg", "docx"})
    allowed_image_extensions: frozenset = frozenset({"png", "jpg", "jpeg"})

    # ---- captcha (signup; login after repeated failures) ----
    captcha_length: int = 6
    captcha_expiry_minutes: int = 5
    captcha_max_per_ip_per_hour: int = 60
    login_captcha_after_failures: int = 3        # per identifier within login_window_minutes
    login_captcha_after_ip_failures: int = 10    # per IP (higher: campus NAT shares one address)

    # ---- login throttling ----
    login_window_minutes: int = 15
    login_max_failures_per_identifier: int = 5
    login_max_failures_per_ip: int = 20

    # ---- sessions / CSRF ----
    session_cookie_name: str = "cc_session"
    session_cookie_secure: Optional[bool] = None  # None -> secure in production
    session_lifetime_seconds: int = 12 * 3600  # absolute lifetime of a login
    session_idle_timeout_minutes: int = 60
    csrf_enabled: bool = True

    # ---- proxy ----
    trust_proxy: bool = False
    trust_proxy_hops: int = 1

    # ---- misc ----
    reminder_interval_minutes: int = 60
    enable_scheduler: bool = True
    bootstrap_admin: bool = False

    # ------------------------------------------------------------------ derived
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production if self.session_cookie_secure is None else bool(self.session_cookie_secure)

    @property
    def profile_student_dir(self) -> str:
        return os.path.join(self.upload_root, "profile", "students")

    @property
    def profile_faculty_dir(self) -> str:
        return os.path.join(self.upload_root, "profile", "faculty")

    @property
    def chat_upload_dir(self) -> str:
        return os.path.join(self.upload_root, "chat")

    @property
    def docs_enabled(self) -> bool:
        return bool(self.debug) and not self.is_production

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        try:  # python-dotenv is optional at runtime; real environment variables always win.
            from dotenv import load_dotenv
            load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
        except ImportError:  # pragma: no cover
            pass
        environment = _detect_environment()
        secret = os.environ.get("SECRET_KEY", "").strip()
        if not secret and environment != "production":
            secret = _dev_secret_key()
        debug = _env_bool("DEBUG", False)
        values = dict(
            environment=environment,
            debug=debug and environment != "production",
            secret_key=secret,
            database_path=os.environ.get("DATABASE_PATH") or cls.database_path,
            upload_root=os.environ.get("UPLOAD_ROOT") or cls.upload_root,
            frontend_dist=os.environ.get("FRONTEND_DIST") or cls.frontend_dist,
            captcha_max_per_ip_per_hour=_env_int("CAPTCHA_MAX_PER_IP_PER_HOUR", cls.captcha_max_per_ip_per_hour),
            login_captcha_after_failures=_env_int("LOGIN_CAPTCHA_AFTER_FAILURES", cls.login_captcha_after_failures),
            login_max_failures_per_identifier=_env_int(
                "LOGIN_MAX_FAILURES_PER_IDENTIFIER", cls.login_max_failures_per_identifier),
            login_max_failures_per_ip=_env_int("LOGIN_MAX_FAILURES_PER_IP", cls.login_max_failures_per_ip),
            session_idle_timeout_minutes=_env_int("SESSION_IDLE_TIMEOUT_MINUTES", cls.session_idle_timeout_minutes),
            trust_proxy=_env_bool("TRUST_PROXY", False),
            trust_proxy_hops=max(1, _env_int("TRUST_PROXY_HOPS", 1)),
            reminder_interval_minutes=_env_int("REMINDER_INTERVAL_MINUTES", 60),
            enable_scheduler=_env_bool("ENABLE_SCHEDULER", True),
            bootstrap_admin=_env_bool("BOOTSTRAP_ADMIN", False),
        )
        values.update(overrides)
        return cls(**values)

    def with_overrides(self, **overrides) -> "Settings":
        return replace(self, **overrides)

    def validate(self) -> None:
        """Raise RuntimeError for unsafe configuration. Skipped for ``testing`` settings."""
        if self.testing:
            return
        key = self.secret_key or ""
        if not key or key == DEV_DEFAULT_SECRET:
            raise RuntimeError(
                "SECRET_KEY must be set to a strong random value"
                + (" when APP_ENV=production." if self.is_production else ".")
            )
        if self.is_production and len(key) < 24:
            raise RuntimeError("SECRET_KEY is too short; use at least 24 random characters in production.")


# ---------------------------------------------------------------------------------------
# "Current settings" accessor used by services (no framework import).

_global_settings: Optional[Settings] = None
_context_settings: contextvars.ContextVar = contextvars.ContextVar("cc_settings", default=None)


def set_settings(settings: Settings) -> None:
    """Make ``settings`` the process-wide default (called by ``create_app``)."""
    global _global_settings
    _global_settings = settings


def get_settings() -> Settings:
    current = _context_settings.get()
    if current is not None:
        return current
    if _global_settings is None:
        set_settings(Settings.from_env())
    return _global_settings


@contextlib.contextmanager
def use_settings(settings: Settings):
    """Bind ``settings`` to the current context (each app binds its own per request)."""
    token = _context_settings.set(settings)
    try:
        yield settings
    finally:
        _context_settings.reset(token)
