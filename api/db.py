"""SQLite access (raw sqlite3, SQLite only).

Request model: ``DbMiddleware`` (api/security.py) puts an empty ``_Holder`` into a ContextVar for
every request. ``get_db()`` lazily opens the connection into that holder on first use and the
middleware closes it when the request ends. Because the *holder* (a mutable object) is what lives
in the ContextVar, sync ``def`` endpoints and dependencies running in FastAPI's threadpool (which
copy the context) all see the same connection, and so do the legacy ``models/*queries.py``
functions that simply call ``get_db()``.

Outside a request (scripts, scheduler, tests, startup) use ``with db_session() as db:``.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import sqlite3
from typing import Iterator, Optional

from api.settings import Settings, get_settings, use_settings

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "schema.sql")


class _Holder:
    __slots__ = ("conn", "settings")

    def __init__(self, settings: Optional[Settings] = None):
        self.conn: Optional[sqlite3.Connection] = None
        self.settings = settings

    def close(self) -> None:
        conn, self.conn = self.conn, None
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:  # pragma: no cover
                pass


_holder_var: contextvars.ContextVar = contextvars.ContextVar("cc_db_holder", default=None)


def connect(settings: Optional[Settings] = None) -> sqlite3.Connection:
    """Open a new configured connection (caller owns it)."""
    settings = settings or get_settings()
    conn = sqlite3.connect(
        settings.database_path,
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=15,
        # A request's connection may be touched by more than one threadpool thread, one at a time.
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def get_db() -> sqlite3.Connection:
    """The current request's (or ``db_session``'s) connection, opened lazily."""
    holder = _holder_var.get()
    if holder is None:
        raise RuntimeError(
            "get_db() called outside a request or db_session(); wrap scripts in `with db_session():`."
        )
    if holder.conn is None:
        holder.conn = connect(holder.settings)
    return holder.conn


def has_db_context() -> bool:
    return _holder_var.get() is not None


def open_holder(settings: Optional[Settings] = None):
    """Install a fresh holder; returns ``(holder, token)``. Used by the request middleware."""
    holder = _Holder(settings or get_settings())
    return holder, _holder_var.set(holder)


def close_holder(holder: _Holder, token) -> None:
    holder.close()
    _holder_var.reset(token)


@contextlib.contextmanager
def db_session(settings: Optional[Settings] = None) -> Iterator[sqlite3.Connection]:
    """Scripts / scheduler / tests: ``with db_session() as db: queries.create_user(...)``.
    Also binds the settings for the block. The connection is closed on exit."""
    settings = settings or get_settings()
    holder = _Holder(settings)
    token = _holder_var.set(holder)
    try:
        with use_settings(settings):
            yield get_db()
    finally:
        holder.close()
        _holder_var.reset(token)


# ---------------------------------------------------------------------------------------
# schema / migrations / seed

def _columns(db: sqlite3.Connection, table: str) -> set:
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(db: sqlite3.Connection) -> None:
    """Additive, idempotent migrations for databases created before the academic hierarchy."""
    if "section_id" not in _columns(db, "students"):
        db.execute("ALTER TABLE students ADD COLUMN section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_students_section ON students(section_id)")
    if "last_login_at" not in _columns(db, "users"):
        db.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")


def init_db(settings: Optional[Settings] = None) -> None:
    """Create/upgrade the schema and seed the default academic structure. Idempotent; safe at every start."""
    settings = settings or get_settings()
    db_dir = os.path.dirname(os.path.abspath(settings.database_path))
    os.makedirs(db_dir, exist_ok=True)
    with db_session(settings) as db:
        if settings.database_path != ":memory:":
            try:
                db.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:  # pragma: no cover
                pass
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            db.executescript(f.read())
        _migrate(db)
        db.commit()
        from models import security_queries
        security_queries.ensure_schema()
        from services import academic_service
        academic_service.seed_default_structure()
        academic_service.backfill_legacy_data()
