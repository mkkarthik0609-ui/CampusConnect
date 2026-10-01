"""GET /healthz and GET /api/meta."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.db import get_db
from services import otp_service

logger = logging.getLogger("campusconnect.api")

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz():
    """Unauthenticated liveness/readiness probe (Render health check)."""
    try:
        get_db().execute("SELECT 1").fetchone()
    except Exception:  # noqa: BLE001 - any DB failure means "not healthy"
        logger.exception("Health check failed")
        return JSONResponse({"status": "error"}, status_code=503)
    return {"status": "ok"}


@router.get("/api/meta")
def meta():
    """Public, non-sensitive app metadata for the SPA (e.g. whether the signup OTP is shown on screen)."""
    return {"app": "Campus Connect", "demo_otp_enabled": otp_service.delivery_mode() == "demo"}
