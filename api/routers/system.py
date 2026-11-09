"""GET /healthz and GET /api/meta."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.db import get_db

logger = logging.getLogger("campusconnect.api")

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
def health():
    """External keep-alive ping (cron-job.org). Deliberately touches nothing: no DB, disk, session or
    network, so it stays cheap. Use /healthz (below) when you want a real readiness check."""
    return {"status": "ok"}


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
    """Public, non-sensitive app metadata for the SPA."""
    return {"app": "Campus Connect"}
