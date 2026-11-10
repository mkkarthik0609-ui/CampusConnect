"""Durable file storage in PostgreSQL (table ``file_blobs``).

Render Free's disk is wiped on every restart and deploy, so uploads cannot live there. Blobs are written on
the request's own connection: the INSERT commits (or rolls back) together with the message / profile row
that references it, which also means a failed database write can never leave an orphaned upload behind.

shortcut: bytea in Neon Free (0.5 GB total). Fine for a campus-sized app with 8 MB attachment / 3 MB picture
caps; move ``put/get/delete`` to R2 / S3 (same three functions) when storage approaches the quota.
"""
from typing import Optional

from api.db import get_db

CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def content_type_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def put(path: str, data: bytes) -> None:
    get_db().execute(
        "INSERT INTO file_blobs (path, content, content_type, size_bytes) VALUES (?, ?, ?, ?)",
        (path, data, content_type_for(path), len(data)),
    )


def get(path: str) -> Optional[tuple]:
    """``(bytes, content_type)`` or None."""
    row = get_db().execute("SELECT content, content_type FROM file_blobs WHERE path = ?", (path,)).fetchone()
    return (bytes(row["content"]), row["content_type"]) if row else None


def exists(path: str) -> bool:
    return get_db().execute("SELECT 1 FROM file_blobs WHERE path = ?", (path,)).fetchone() is not None


def delete(path: str) -> None:
    get_db().execute("DELETE FROM file_blobs WHERE path = ?", (path,))
