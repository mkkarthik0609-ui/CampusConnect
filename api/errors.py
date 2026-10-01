"""Error model: every non-2xx response from this app is ``{"error": {"code", "message", "fields"?}}``.

* ``ApiError(status, code, message, fields=None)`` - raise it anywhere in a request.
* ``map_service_error(exc)`` - turns a service-layer exception into an ``ApiError`` (or ``None``).
* ``install_error_handlers(app)`` - registers handlers for ApiError, service errors, request
  validation (422 -> 400), HTTPException (incl. 404/405), and unexpected exceptions (500, logged,
  nothing leaked). For a non-API ``GET`` 404 the built SPA ``index.html`` is served when available.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.settings import get_settings

logger = logging.getLogger("campusconnect.api")

RESERVED_PREFIXES = ("/api", "/uploads", "/healthz", "/assets", "/docs", "/redoc", "/openapi.json")

_STATUS_CODES = {
    400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type",
    422: "validation_error", 429: "rate_limited", 500: "server_error", 503: "service_unavailable",
}


class ApiError(Exception):
    """Raise anywhere inside a request to return the standard JSON error shape."""

    def __init__(self, status: int, code: str, message: str, fields: Optional[Dict[str, str]] = None,
                 headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or None
        self.headers = headers


def error_body(code: str, message: str, fields: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return {"error": body}


def error_response(status: int, code: str, message: str, fields=None, headers=None) -> JSONResponse:
    return JSONResponse(error_body(code, message, fields), status_code=status, headers=headers)


# ---------------------------------------------------------------------------------------
# service exception mapping

_NOT_FOUND_RE = re.compile(r"\bnot found\b|does not exist|no such", re.I)
_FORBIDDEN_RE = re.compile(
    r"not authori[sz]ed|do not have (?:permission|access)|don't have (?:permission|access)|"
    r"only (?:an )?admins? may|no longer assigned|no longer in one of your|you can only (?:message|send|edit)|"
    r"permission to",
    re.I,
)
_CONFLICT_RE = re.compile(r"already", re.I)
_TOO_LARGE_RE = re.compile(r"too large", re.I)


def _classify(message: str, default_status: int = 400):
    """Status/code for a plain business-rule exception, from its message."""
    if _NOT_FOUND_RE.search(message):
        return 404, "not_found"
    if _FORBIDDEN_RE.search(message):
        return 403, "forbidden"
    if _CONFLICT_RE.search(message):
        return 409, "conflict"
    return default_status, "validation_error"


def _service_classes():
    """(class, kind) pairs, most specific first. Imported lazily: services import api.db/api.settings."""
    from services import (academic_service, assignment_service, auth_service, captcha_service, chat_service,
                          file_service,
                          meeting_service, permission_service, supporting_service)
    from services.errors import ServiceError
    return [
        (ServiceError, "service"),
        (auth_service.LockoutError, "rate"),
        (captcha_service.CaptchaRateLimitError, "rate"),
        (auth_service.ConflictError, "conflict"),
        (auth_service.ValidationError, "validation"),
        (chat_service.ChatAccessError, "access"),
        (chat_service.ChatEditError, "plain"),
        (meeting_service.MeetingError, "plain"),
        (supporting_service.SupportingError, "plain"),
        (permission_service.PermissionError_, "plain"),
        (assignment_service.AssignmentError, "plain"),
        (academic_service.AcademicError, "plain"),
        (file_service.FileValidationError, "file"),
    ]


def map_service_error(exc: BaseException) -> Optional[ApiError]:
    """Translate a service-layer exception into an ApiError; ``None`` if it is not one of ours."""
    message = str(exc) or "The request could not be processed."
    for cls, kind in _service_classes():
        if not isinstance(exc, cls):
            continue
        if kind == "service":
            return ApiError(getattr(exc, "http_status", 400), getattr(exc, "code", "bad_request"), message)
        if kind == "rate":
            return ApiError(429, "rate_limited", message)
        if kind == "conflict":
            field = getattr(exc, "field", None)
            return ApiError(409, "conflict", message, {field: message} if field else None)
        if kind == "validation":
            field = getattr(exc, "field", None)
            return ApiError(400, "validation_error", message, {field: message} if field else None)
        if kind == "access":
            status, code = _classify(message, 403)
            return ApiError(status if status in (403, 404) else 403, code if status in (403, 404) else "forbidden",
                            message)
        if kind == "file":
            if _TOO_LARGE_RE.search(message):
                return ApiError(413, "payload_too_large", message)
            return ApiError(400, "validation_error", message)
        status, code = _classify(message)
        return ApiError(status, code, message)
    return None


# ---------------------------------------------------------------------------------------
# request validation

def _friendly(err: dict) -> str:
    kind = err.get("type", "")
    msg = str(err.get("msg", "Invalid value."))
    if kind == "missing":
        return "This field is required."
    if msg.startswith("Value error, "):
        return msg[len("Value error, "):]
    if kind in ("string_too_short",):
        return "This field is too short."
    if kind in ("string_too_long",):
        return "This field is too long."
    if kind == "string_type":
        return "Enter a valid text value."
    return msg[0].upper() + msg[1:] if msg else "Invalid value."


def validation_error_response(exc: RequestValidationError) -> JSONResponse:
    fields: Dict[str, str] = {}
    body_problem = None
    for err in exc.errors():
        loc = [p for p in err.get("loc", ()) if p not in ("body", "query", "path", "header", "cookie")]
        kind = err.get("type", "")
        if kind == "json_invalid" or (kind in ("model_attributes_type", "dict_type") and not loc):
            body_problem = "The request body must be valid JSON."
            continue
        if kind == "missing" and not loc:
            body_problem = "The request body is required."
            continue
        key = ".".join(str(p) for p in loc) if loc else "_"
        fields.setdefault(key, _friendly(err))
    fields.pop("_", None)
    if body_problem and not fields:
        return error_response(400, "bad_request", body_problem)
    first = next(iter(fields.items()), None)
    message = f"{first[1]}" if first and len(fields) == 1 else "Please correct the highlighted fields."
    return error_response(400, "validation_error", message, fields or None)


# ---------------------------------------------------------------------------------------
# SPA fallback

def _is_reserved(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in RESERVED_PREFIXES)


def spa_index_path() -> Optional[str]:
    index = os.path.join(get_settings().frontend_dist, "index.html")
    return index if os.path.isfile(index) else None


def spa_response(path: str) -> Optional[FileResponse]:
    """index.html (or a real file from frontend/dist) for a client-side route, or None if no build."""
    index = spa_index_path()
    if not index:
        return None
    dist = os.path.realpath(get_settings().frontend_dist)
    rel = path.lstrip("/")
    if rel:
        candidate = os.path.realpath(os.path.join(dist, rel))
        if candidate.startswith(dist + os.sep) and os.path.isfile(candidate):
            media = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
            return FileResponse(candidate, media_type=media, headers={"Cache-Control": "public, max-age=3600"})
    return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------------------------

def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.fields, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return validation_error_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and request.method in ("GET", "HEAD") and not _is_reserved(path):
            spa = spa_response(path)
            if spa is not None:
                return spa
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else None
        messages = {
            401: "Please sign in to continue.", 403: "You do not have permission to do that.",
            404: "Not found.", 405: "That method is not allowed here.",
        }
        message = messages.get(exc.status_code) or detail or "The request could not be processed."
        return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    async def _service(request: Request, exc: Exception):
        mapped = map_service_error(exc)
        if mapped is None:  # pragma: no cover - defensive
            return await _unhandled(request, exc)
        return error_response(mapped.status, mapped.code, mapped.message, mapped.fields)

    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return error_response(500, "server_error", "Something went wrong on our end.")

    for cls, _kind in _service_classes():
        app.add_exception_handler(cls, _service)
    app.add_exception_handler(Exception, _unhandled)
