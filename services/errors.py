"""Shared base class for business-rule errors raised by the services.

The JSON routes turn any ``ServiceError`` into the standard error body
``{"error": {"code", "message"}}`` using ``http_status`` / ``code`` so services stay free of Flask/HTTP
concerns while still telling the API layer whether a failure is a validation problem (400), an
authorization failure (403), a missing row (404) or a state conflict (409)."""


class ServiceError(Exception):
    http_status = 400
    code = "bad_request"

    def __init__(self, message="", status=None, code=None):
        super().__init__(message)
        if status is not None:
            self.http_status = status
        if code is not None:
            self.code = code


def not_found(error_cls, message):
    return error_cls(message, 404, "not_found")


def forbidden(error_cls, message):
    return error_cls(message, 403, "forbidden")


def conflict(error_cls, message, code="conflict"):
    return error_cls(message, 409, code)
