"""FastAPI dependencies and small helpers shared by every router.

Public names (stable): ``get_current_user``, ``current_user_optional``, ``require_role``,
``csrf_protect``, ``client_ip``, ``service_errors``, ``ok``, ``items``, ``ApiModel``, ``Stripped``,
``Page``, ``CurrentUser``. ``ApiError`` lives in ``api.errors`` and ``get_db`` in ``api.db``
(both re-exported here for convenience).
"""
from __future__ import annotations

import functools
import inspect
from typing import Annotated, Any, Optional

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.db import get_db  # noqa: F401  (re-export)
from api.errors import ApiError, map_service_error
from api.security import CSRF_HEADER, SAFE_METHODS, csrf_tokens_match
from api.settings import get_settings  # noqa: F401  (re-export)
from services import session_service


# ---------------------------------------------------------------------------------------
# current user

class CurrentUser(dict):
    """The signed-in user, freshly loaded from the database on every request.

    A ``dict`` (so ``user["id"]`` works like a row) that also allows attribute access
    (``user.id``, ``user.role``). Keys: every ``users`` column except ``password_hash`` plus
    ``user_id`` (== ``id``), ``student_id`` and ``faculty_id`` (None when not applicable),
    ``theme`` (== ``theme_preference``). ``password_hash`` is deliberately absent.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _build_current_user(row) -> CurrentUser:
    from models import queries
    data = {k: row[k] for k in row.keys() if k != "password_hash"}
    data["user_id"] = row["id"]
    data["theme"] = row["theme_preference"]
    data["student_id"] = data["faculty_id"] = None
    if row["role"] == "STUDENT":
        student = queries.get_student_by_user_id(row["id"])
        data["student_id"] = student["id"] if student else None
    elif row["role"] == "FACULTY":
        faculty = queries.get_faculty_by_user_id(row["id"])
        data["faculty_id"] = faculty["id"] if faculty else None
    return CurrentUser(data)


def _load_user(request: Request) -> tuple:
    """Session -> (CurrentUser | None, expiry_reason | None). Result is cached on request.state."""
    cached = getattr(request.state, "cc_user", None)
    if cached is not None:
        return cached
    settings = get_settings()
    row, reason = session_service.resolve_session_user(
        request.session, settings.session_lifetime_seconds, settings.session_idle_timeout_minutes)
    result = (_build_current_user(row) if row is not None else None, reason)
    request.state.cc_user = result
    return result


def current_user_optional(request: Request) -> Optional[CurrentUser]:
    """The signed-in user or ``None`` (expired / deactivated / anonymous). Never raises."""
    return _load_user(request)[0]


def get_current_user(request: Request) -> CurrentUser:
    """Signed-in user or ApiError 401. Enforces idle (60 min) + absolute (12 h) timeouts and that the
    user still exists and is active; role/name/ids always come from the database, not the cookie."""
    user, reason = _load_user(request)
    if user is None:
        message = session_service.MESSAGES.get(reason, "Please sign in to continue.")
        raise ApiError(401, "unauthenticated", message)
    return user


def require_role(*roles: str):
    """Dependency factory: ``user: CurrentUser = Depends(require_role("ADMIN"))`` (401 / 403)."""
    allowed = frozenset(roles)

    def dependency(request: Request) -> CurrentUser:
        user = get_current_user(request)
        if user["role"] not in allowed:
            raise ApiError(403, "forbidden", "You do not have permission to do that.")
        return user

    dependency.__name__ = "require_role_" + "_".join(r.lower() for r in roles)
    return dependency


# ---------------------------------------------------------------------------------------
# CSRF (registered GLOBALLY on the app; routers cannot forget it)

async def csrf_protect(request: Request) -> None:
    if request.method in SAFE_METHODS or not get_settings().csrf_enabled:
        return
    expected = request.session.get("csrf_token")
    supplied = request.headers.get(CSRF_HEADER, "")
    if not csrf_tokens_match(expected, supplied):
        raise ApiError(
            400, "csrf_failed",
            "Your session could not be verified. Please reload the page and try again.",
        )


# ---------------------------------------------------------------------------------------
# client address (proxy-aware: ProxyHeadersMiddleware already rewrote scope["client"] when trusted)

def client_ip(request: Request) -> str:
    client = request.client
    return client.host if client and client.host else ""


# ---------------------------------------------------------------------------------------
# service error mapping

class service_errors:
    """Map service-layer exceptions to ``ApiError``. Context manager *and* decorator::

        with service_errors():
            meeting_service.request_meeting(...)

        @service_errors()
        def endpoint(...): ...

    (Unmapped exceptions propagate; the global handlers also map service errors, so forgetting
    this is not fatal, but explicit use keeps the intent visible.)"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            return False
        mapped = map_service_error(exc)
        if mapped is None:
            return False
        raise mapped from exc

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with service_errors():
                return func(*args, **kwargs)

        # keep FastAPI's signature introspection working
        wrapper.__signature__ = inspect.signature(func)
        return wrapper


# ---------------------------------------------------------------------------------------
# response + request-model helpers

def ok(message: Optional[str] = None, **extra: Any) -> dict:
    """Standard mutation envelope ``{"ok": true, "message"?, ...extra}``."""
    body: dict = {"ok": True}
    if message is not None:
        body["message"] = message
    body.update(extra)
    return body


def items(rows, **extra: Any) -> dict:
    """List envelope ``{"items": [...], ...extra}``."""
    body: dict = {"items": list(rows)}
    body.update(extra)
    return body


# A string field that is whitespace-stripped. Do NOT use it for passwords.
Stripped = Annotated[str, StringConstraints(strip_whitespace=True)]


class ApiModel(BaseModel):
    """Base for request bodies: unknown fields are rejected (400 with the field name)."""

    model_config = ConfigDict(extra="forbid")


class Page(BaseModel):
    """Query parameters for simple paging: ``page: Page = Depends()``."""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
