"""FastAPI application factory.

    venv\\Scripts\\python.exe -m uvicorn api.main:app --port 5000

``create_app(settings=None)`` builds an isolated app (tests pass their own ``Settings``).
``api.main.app`` is created lazily on first access so importing this module has no side effects
(uvicorn's ``api.main:app`` triggers it).
"""
from __future__ import annotations

import contextlib
import importlib
import logging
import os
import secrets
import sys
from dataclasses import replace
from typing import Optional

from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from api import db as dbmod
from api.deps import csrf_protect
from api.errors import install_error_handlers
from api.security import DbMiddleware, ProxyHeadersMiddleware, SecurityMiddleware
from api.settings import Settings, set_settings

logger = logging.getLogger("campusconnect.api")

# Registered in this order. Modules that do not exist yet are skipped (see _register_routers).
ROUTER_MODULES = [
    "system", "auth", "account", "academic", "notifications", "uploads",
    "admin", "admin_academic", "faculty", "student", "chat", "meetings", "supporting", "research",
]


def _configure_logging(debug: bool) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)


class _ImmutableStaticFiles(StaticFiles):
    """Vite emits content-hashed file names under /assets, so they can be cached forever."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _register_routers(app: FastAPI) -> None:
    for name in ROUTER_MODULES:
        module_name = f"api.routers.{name}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:  # the router simply is not written yet
                logger.info("Router %s not present; skipped", module_name)
                continue
            raise
        app.include_router(module.router)


def _prepare_storage_and_db(settings: Settings) -> None:
    for path in (settings.upload_root, settings.profile_student_dir, settings.profile_faculty_dir,
                 settings.chat_upload_dir):
        os.makedirs(path, exist_ok=True)
    dbmod.init_db(settings)  # idempotent (CREATE IF NOT EXISTS + additive migrations + academic seed)
    if settings.bootstrap_admin and not settings.testing:
        from services import auth_service
        try:
            with dbmod.db_session(settings):
                status = auth_service.bootstrap_admin_from_env()
            logger.info("Admin bootstrap: %s", status)
        except Exception as exc:  # noqa: BLE001 - misconfiguration must not stop the site
            logger.error("Admin bootstrap failed: %s", exc)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.testing and not settings.secret_key:
        settings = replace(settings, secret_key=secrets.token_hex(32))
    settings.validate()
    set_settings(settings)
    _configure_logging(settings.debug)
    _prepare_storage_and_db(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if settings.enable_scheduler and not settings.testing:
            # Exactly one process runs the app (SQLite single writer), so one scheduler is safe.
            from apscheduler.schedulers.background import BackgroundScheduler
            from services.meeting_service import send_due_reminders

            scheduler = BackgroundScheduler(daemon=True)
            scheduler.add_job(
                func=lambda: send_due_reminders(settings),
                trigger="interval",
                minutes=settings.reminder_interval_minutes,
                id="meeting_reminders",
                replace_existing=True,
            )
            scheduler.start()
            app.state.scheduler = scheduler
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    docs = settings.docs_enabled
    app = FastAPI(
        title="Campus Connect API",
        lifespan=lifespan,
        dependencies=[Depends(csrf_protect)],  # CSRF on every unsafe method; no router can forget it
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    # Convenience for scripts/tests that use `app.app_context()`: `with app.app_context(): ...`
    # opens a db_session bound to this app's settings.
    app.app_context = lambda: dbmod.db_session(settings)  # type: ignore[attr-defined]

    # add_middleware: the LAST one added is the OUTERMOST.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_lifetime_seconds,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    app.add_middleware(DbMiddleware, settings=settings)
    app.add_middleware(SecurityMiddleware, settings=settings)
    if settings.trust_proxy:
        app.add_middleware(ProxyHeadersMiddleware, hops=settings.trust_proxy_hops)

    install_error_handlers(app)
    _register_routers(app)

    assets = os.path.join(settings.frontend_dist, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", _ImmutableStaticFiles(directory=assets), name="assets")
    return app


_app: Optional[FastAPI] = None


def __getattr__(name: str):
    """Lazy module-level ``app`` so ``import api.main`` never touches the real database."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
