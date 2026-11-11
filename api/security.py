"""Transport-level security: pure-ASGI middlewares, security headers, CSRF helpers, proxy handling.

Stack (outermost first), assembled in ``api.main.create_app``::

    ProxyHeadersMiddleware   (only when settings.trust_proxy)  client ip / scheme / host from X-Forwarded-*
    SecurityMiddleware       security headers, no-store on /api, 10 MB cap, JSON 500 safety net
    DbMiddleware             binds settings + opens/closes the per-request database connection holder
    SessionMiddleware        signed ``cc_session`` cookie -> request.session
    FastAPI app              (global csrf_protect dependency, routers, error handlers)
"""
from __future__ import annotations

import asyncio
import weakref

import anyio

import hmac
import json
import logging

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
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

_CLOSE_LIMITER = None


def _close_limiter():
    global _CLOSE_LIMITER
    if _CLOSE_LIMITER is None:
        _CLOSE_LIMITER = anyio.CapacityLimiter(32)
    return _CLOSE_LIMITER


_NO_ADMISSION_PREFIXES = ("/health", "/assets/")


async def _buffer_body(receive, send, scope, timeout):
    """Returns a ``receive`` that replays the fully-read body, or None after answering 408 / on disconnect."""
    messages = []

    async def read_all():
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return False
            messages.append(message)
            if not message.get("more_body", False):
                return True

    try:
        complete = await asyncio.wait_for(read_all(), timeout=timeout)
    except asyncio.TimeoutError:
        response = JSONResponse({"error": {"code": "request_timeout", "message": "The request took too long to arrive."}},
                                status_code=408, headers={"Connection": "close"})
        await response(scope, receive, send)
        return None
    if not complete:
        return None
    queue = list(messages)

    async def replay():
        if queue:
            return queue.pop(0)
        return await receive()  # afterwards: the real stream (disconnect notifications)

    return replay


class DbMiddleware:
    """Binds the app's settings and a lazily-checked-out PostgreSQL connection to the request context.

    ADMISSION CONTROL: at most ``db_pool_max`` requests are processed at once; the rest wait here (cheap, on the
    event loop) and get a 503 + Retry-After after ``db_pool_timeout`` seconds. Without it, FastAPI's 40 worker
    threads can all block waiting for one of the few pooled connections while the requests that HOLD connections
    wait for a free worker thread to continue: a deadlock that only ends through timeouts (observed in the load
    test at 60 concurrent users). With admitted requests <= pool size every admitted request can always finish."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings
        self._slots = weakref.WeakKeyDictionary()  # one semaphore per event loop (production has exactly one)

    def _slot_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        sem = self._slots.get(loop)
        if sem is None:
            sem = self._slots[loop] = asyncio.Semaphore(max(1, self.settings.db_pool_max))
        return sem

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        gated = not path.startswith(_NO_ADMISSION_PREFIXES)
        slots = self._slot_semaphore() if gated else None
        if gated and scope.get("method") in ("POST", "PUT", "PATCH", "DELETE"):
            # Read the whole body BEFORE taking a slot, under a deadline: a client trickling a body (slowloris)
            # must not be able to occupy the few slots that serve everybody else.
            receive = await _buffer_body(receive, send, scope, self.settings.body_read_timeout)
            if receive is None:
                return
        if gated:
            try:
                await asyncio.wait_for(slots.acquire(), timeout=self.settings.db_pool_timeout)
            except asyncio.TimeoutError:
                response = JSONResponse(
                    {"error": {"code": "service_unavailable",
                               "message": "The service is busy right now. Please try again in a moment."}},
                    status_code=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})
                await response(scope, receive, send)
                return
        try:
            with use_settings(self.settings):
                holder, token = dbmod.open_holder(self.settings)
                try:
                    await self.app(scope, receive, send)
                finally:
                    # Returning the connection rolls back any open read transaction (a network round trip): do it
                    # off the event loop, on a DEDICATED limiter so it can never queue behind blocked endpoints.
                    with anyio.CancelScope(shield=True):  # a cancelled request must still return its connection
                        await anyio.to_thread.run_sync(holder.close, limiter=_close_limiter())
                    dbmod._holder_var.reset(token)
        finally:
            if gated:
                slots.release()
