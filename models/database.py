"""Compatibility shim: the database layer now lives in ``api.db`` (framework-agnostic sqlite3).

Existing modules keep importing ``from models.database import get_db``; new code should import
from ``api.db`` directly.
"""
from api.db import (  # noqa: F401
    connect,
    db_session,
    get_db,
    init_db,
)
