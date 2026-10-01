"""Transport-level security: pure-ASGI middlewares, security headers, CSRF helpers, proxy handling.

Stack (outermost first), assembled in ``api.main.create_app``::

    ProxyHeadersMiddleware   (only when settings.trust_proxy)  client ip / scheme / host from X-Forwarded-*
    SecurityMiddleware       security headers, no-store on /api, 10 MB cap, JSON 500 safety net
    DbMiddleware             binds settings + opens/closes the per-request sqlite3 connection holder
    SessionMiddleware        signed ``cc_session`` cookie -> request.session
    FastAPI app              (global csrf_protect dependency, routers, error handlers)
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Optional

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api import db as dbmod
from api.settings import Settings, use_settings

logger = logging.getLogger("campusconnect.api")

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

CSRF_HEADER = "x-csrftoken"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


# ---------------------------------------------------------------------------------------
# CSRF helpers

def csrf_tokens_match(expected, supplied) -> bool:
    """Constant-time comparison of the session token and the ``X-CSRFToken`` header."""
    if not isinstance(expected, str) or not expected or not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))


# ---------------------------------------------------------------------------------------
# proxy handling

class ProxyHeadersMiddleware:
    """Trust ``X-Forwarded-*`` from ``hops`` proxies in front of the app (Vercel rewrite + Render LB = 2).
    The client IP is the ``hops``-th entry from the right of X-Forwarded-For (the same rule as
    Werkzeug's ProxyFix); with fewer entries than hops the peer address is kept, so a client cannot
    spoof an address by sending its own header."""

    def __init__(self, app: ASGIApp, hops: int = 1):
        self.app = app
        self.hops = max(1, int(hops or 1))

    def _pick(self, value: str, strict: bool = False) -> str:
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if len(parts) >= self.hops:
            return parts[-self.hops]
        return "" if strict or not parts else parts[0]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = Headers(scope=scope)
            client = self._pick(headers.get("x-forwarded-for", ""), strict=True)
            if client:
                scope["client"] = (client, 0)
            proto = self._pick(headers.get("x-forwarded-proto", "")).lower()
            if proto in ("http", "https"):
                if scope["type"] == "http":
                    scope["scheme"] = proto
                else:
                    scope["scheme"] = "wss" if proto == "https" else "ws"
            host = self._pick(headers.get("x-forwarded-host", ""))
            if host:
                scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"host"] + [
                    (b"host", host.encode("latin-1", "ignore"))]
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------------------
# security headers, request cap, 500 safety net

class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = self.settings
        path = scope.get("path", "")
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                self._add_headers(MutableHeaders(scope=message), scope, path)
            await send(message)

        # ---- request size cap (Content-Length first, then while streaming)
        declared = Headers(scope=scope).get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_request_bytes:
            await self._respond(send_wrapper, 413, "payload_too_large", "The request is too large (10 MB maximum).")
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > settings.max_request_bytes:
                    raise StarletteHTTPException(413, "The request is too large (10 MB maximum).")
            return message

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except Exception:  # noqa: BLE001 - last-resort JSON 500 that still carries the security headers
            logger.exception("Unhandled error on %s %s", scope.get("method"), path)
            if started:
                raise
            await self._respond(send_wrapper, 500, "server_error", "Something went wrong on our end.")

    @staticmethod
    async def _respond(send: Send, status: int, code: str, message: str) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    def _add_headers(self, h: MutableHeaders, scope: Scope, path: str) -> None:
        settings = self.settings
        docs = settings.docs_enabled and path in _DOCS_PATHS
        if not docs:  # Swagger UI needs CDN scripts; only exempt it when DEBUG enables the docs
            h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if settings.is_production or scope.get("scheme") in ("https", "wss"):
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if path == "/api" or path.startswith("/api/"):
            # API responses may carry per-user data (and the CSRF token): never cache them.
            h["Cache-Control"] = "no-store"
            h["Pragma"] = "no-cache"


# ---------------------------------------------------------------------------------------
# per-request database holder

class DbMiddleware:
    """Binds the app's settings and a lazily-opened sqlite3 connection to the request context."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        with use_settings(self.settings):
            holder, token = dbmod.open_holder(self.settings)
            try:
                await self.app(scope, receive, send)
            finally:
                dbmod.close_holder(holder, token)
