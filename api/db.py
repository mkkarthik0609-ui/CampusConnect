"""PostgreSQL access (psycopg 3 + connection pool) behind a small sqlite3-style facade.

The query modules (``models/*_queries.py``) were written against ``sqlite3`` (``db.execute(sql, params)``,
``?`` placeholders, ``row["col"]``, ``cursor.lastrowid``). ``Connection`` keeps that calling convention and
translates the few SQLite-isms on the fly (see ``translate``), so SQL stays in one place and PostgreSQL does
the work.

Request model: ``DbMiddleware`` (api/security.py) puts an empty ``_Holder`` into a ContextVar for every
request. ``get_db()`` lazily checks a connection out of the pool on first use; the middleware returns it
(rolling back anything uncommitted) when the request ends. Outside a request (scripts, scheduler, tests,
startup) use ``with db_session() as db:``.

Connections: runtime traffic uses ``database_url`` (Neon's pooled PgBouncer endpoint, transaction mode, so
no server-side prepared statements); migrations use ``database_url_direct``.
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
import os
import re
import threading
import time
from typing import Iterator, Optional

import psycopg
from psycopg.types.numeric import FloatLoader, IntDumper
from psycopg_pool import ConnectionPool, PoolTimeout

from api.settings import Settings, get_settings, use_settings

log = logging.getLogger("campusconnect.db")

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")

# Re-exported so callers can catch constraint errors without importing psycopg.
IntegrityError = psycopg.errors.IntegrityError
UniqueViolation = psycopg.errors.UniqueViolation
DatabaseError = psycopg.Error

# Tables whose primary key is not an integer ``id`` column (INSERT must not get ``RETURNING id``).
_NO_ID_TABLES = frozenset({"schema_migrations", "file_blobs", "captcha_challenges", "presence"})


# ---------------------------------------------------------------------------------------
# SQL translation (SQLite dialect -> PostgreSQL)

_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


@functools.lru_cache(maxsize=2048)
def translate(sql: str) -> tuple[str, bool]:
    """Returns ``(postgres_sql, wants_lastrowid)``.

    * ``?`` -> ``%s`` (outside string literals); literal ``%`` -> ``%%``.
    * ``datetime('now')`` -> ``cc_now()`` (UTC ``YYYY-MM-DD HH:MM:SS`` text, same shape SQLite produced).
    * ``LIKE`` -> ``ILIKE`` (SQLite's LIKE is case-insensitive for ASCII).
    * ``COLLATE NOCASE`` is dropped: the case-insensitive columns are ``citext``.
    * ``INSERT`` without ``RETURNING`` gets ``RETURNING id`` so ``cursor.lastrowid`` keeps working.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(sql[i:j + 1].replace("%", "%%"))
            i = j + 1
            continue
        if ch == "?":
            out.append("%s")
        elif ch == ":" and i + 1 < n and (sql[i + 1].isalpha() or sql[i + 1] == "_") and (i == 0 or sql[i - 1] != ":"):
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            out.append("%(" + sql[i + 1:j] + ")s")  # sqlite named parameter  :name  ->  %(name)s
            i = j
            continue
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
        i += 1
    text = "".join(out)
    text = re.sub(r"datetime\(\s*'now'\s*\)", "cc_now()", text, flags=re.IGNORECASE)
    text = re.sub(r"datetime\(\s*'now'\s*,\s*('[^']*')\s*\)", r"cc_now(\1)", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+COLLATE\s+NOCASE\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![A-Za-z_])(NOT\s+)?LIKE\b", lambda m: (m.group(1) or "") + "ILIKE", text, flags=re.IGNORECASE)
    wants = False
    m = _INSERT_RE.match(text)
    if m and "RETURNING" not in text.upper() and m.group(1).lower() not in _NO_ID_TABLES:
        text = text.rstrip().rstrip(";") + " RETURNING id"
        wants = True
    return text, wants


# ---------------------------------------------------------------------------------------
# rows / cursors

class Row(tuple):
    """Tuple that also answers ``row["column"]`` and ``row.keys()`` (like ``sqlite3.Row``)."""

    def __new__(cls, index: dict, values):
        obj = super().__new__(cls, values)
        obj._index = index
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._index[key])
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._index)

    def get(self, key, default=None):
        return tuple.__getitem__(self, self._index[key]) if key in self._index else default


def _row_factory(cursor):
    desc = cursor.description
    if desc is None:
        return lambda values: values
    index: dict = {}
    for pos, col in enumerate(desc):
        index.setdefault(col.name, pos)
    return lambda values: Row(index, values)


class Cursor:
    """Thin wrapper adding ``lastrowid`` and sqlite-style ``fetch*``."""

    def __init__(self, cur: psycopg.Cursor, wants_lastrowid: bool):
        self._cur = cur
        self.lastrowid: Optional[int] = None
        if wants_lastrowid:
            row = cur.fetchone() if cur.description else None
            self.lastrowid = row[0] if row else None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    """sqlite3-like facade over a pooled psycopg connection."""

    def __init__(self, raw: psycopg.Connection):
        self._raw = raw
        self._depth = 0

    def execute(self, sql: str, params=()) -> Cursor:
        text, wants = translate(sql)
        # () (not None) so psycopg always processes the placeholders and un-doubles literal "%%"
        bound = params if isinstance(params, dict) else (tuple(params) if params else ())
        cur = self._raw.execute(text, bound)
        return Cursor(cur, wants)

    def executemany(self, sql: str, seq) -> None:
        text, _ = translate(sql)
        with self._raw.cursor() as cur:
            cur.executemany(text, [tuple(p) for p in seq])

    def commit(self) -> None:
        if self._depth == 0:  # inside ``transaction()`` the helpers' own commits are deferred to its exit
            self._raw.commit()

    @contextlib.contextmanager
    def transaction(self):
        """All-or-nothing block: commits made by the query helpers inside it are deferred and applied once, on
        a clean exit; any exception rolls the whole block back. Nestable (only the outermost block commits)."""
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._raw.rollback()
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                if self._raw.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
                    # A swallowed database error aborted the transaction; committing would silently roll it back
                    # while the caller believes it succeeded.
                    self._raw.rollback()
                    raise RuntimeError("transaction was aborted by an earlier database error")
                self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    @property
    def raw(self) -> psycopg.Connection:
        return self._raw


def _configure(conn: psycopg.Connection) -> None:
    conn.row_factory = _row_factory  # type: ignore[assignment]
    conn.prepare_threshold = None  # PgBouncer transaction pooling cannot keep prepared statements
    conn.adapters.register_loader("numeric", FloatLoader)  # SUM()/AVG() -> float, JSON friendly
    conn.adapters.register_dumper(bool, IntDumper)  # flags are INTEGER 0/1 columns


# ---------------------------------------------------------------------------------------
# pools

_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()


def _pool_for(settings: Settings) -> ConnectionPool:
    url = settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL_POOLED (or DATABASE_URL) is not configured.")
    pool = _pools.get(url)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(url)
        if pool is None:
            pool = ConnectionPool(
                url,
                min_size=settings.db_pool_min,
                max_size=settings.db_pool_max,
                timeout=settings.db_pool_timeout,
                max_lifetime=600,   # recycle: Neon/PgBouncer drop long-lived idle sessions
                max_idle=120,
                check=ConnectionPool.check_connection,  # drop connections the server closed while idle
                kwargs={"connect_timeout": settings.db_connect_timeout, "application_name": "campusconnect"},
                configure=_configure,
                open=False,
            )
            pool.open()
            _pools[url] = pool
    return pool


def dispose_pools(url: Optional[str] = None) -> None:
    """Close pools (tests drop their database afterwards; ``None`` closes all)."""
    with _pools_lock:
        for key in [url] if url else list(_pools):
            pool = _pools.pop(key, None)
            if pool is not None:
                pool.close()


def _checkout(settings: Settings):
    """Get a pooled connection, retrying transient connect failures (Neon cold start / network blips)."""
    pool = _pool_for(settings)
    last: Optional[Exception] = None
    for attempt in range(settings.db_connect_retries):
        try:
            return pool, pool.getconn()
        except (psycopg.OperationalError, PoolTimeout) as exc:
            last = exc
            log.warning("database checkout failed (attempt %d): %s", attempt + 1, type(exc).__name__)
            time.sleep(min(0.5 * 2 ** attempt, 4))
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------------------
# request / session holder

class _Holder:
    __slots__ = ("conn", "pool", "settings", "after_close")

    def __init__(self, settings: Optional[Settings] = None):
        self.after_close: list = []
        self.conn: Optional[Connection] = None
        self.pool: Optional[ConnectionPool] = None
        self.settings = settings

    def close(self) -> None:
        conn, pool = self.conn, self.pool
        self.conn = self.pool = None
        if conn is not None and pool is not None:
            raw = conn.raw
            try:
                if not raw.closed and raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                    raw.rollback()  # nothing uncommitted may leak into the next request that reuses the connection
                for sql, params in self.after_close:  # deferred autonomous writes (e.g. presence), own transaction
                    raw.execute(sql, params)
                    raw.commit()
            except Exception:  # noqa: BLE001
                log.warning("cleanup before returning a database connection failed", exc_info=True)
            finally:
                try:
                    pool.putconn(raw)  # ALWAYS give the slot back; the pool discards a broken connection itself
                except Exception:  # noqa: BLE001  pragma: no cover
                    log.exception("failed to return database connection to pool")


_holder_var: contextvars.ContextVar = contextvars.ContextVar("cc_db_holder", default=None)


def get_db() -> Connection:
    """The current request's (or ``db_session``'s) connection, checked out lazily."""
    holder = _holder_var.get()
    if holder is None:
        raise RuntimeError(
            "get_db() called outside a request or db_session(); wrap scripts in `with db_session():`."
        )
    if holder.conn is None:
        holder.pool, raw = _checkout(holder.settings or get_settings())
        holder.conn = Connection(raw)
    return holder.conn


def defer_write(sql: str, params: tuple = ()) -> bool:
    """Queue a small, independent write (already PostgreSQL SQL, ``%s`` placeholders) to run in its OWN
    transaction right after this request's work is rolled back/finished. False when there is no db context."""
    holder = _holder_var.get()
    if holder is None:
        return False
    holder.after_close.append((sql, params))
    return True


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
def db_session(settings: Optional[Settings] = None) -> Iterator[Connection]:
    """Scripts / scheduler / tests: ``with db_session() as db: queries.create_user(...)``.
    Also binds the settings for the block. The connection goes back to the pool on exit."""
    settings = settings or get_settings()
    holder = _Holder(settings)
    token = _holder_var.set(holder)
    try:
        with use_settings(settings):
            yield get_db()
    finally:
        holder.close()
        _holder_var.reset(token)


def check_connection(settings: Optional[Settings] = None) -> bool:
    """Cheap liveness probe for /healthz?deep=1 (never raises)."""
    try:
        with db_session(settings) as db:
            db.execute("SELECT 1").fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------------------
# migrations (direct connection) + seed

def _migration_files() -> list[tuple[int, str, str]]:
    files = []
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        m = re.match(r"^(\d{4})_([a-z0-9_]+)\.sql$", name)
        if m:
            files.append((int(m.group(1)), m.group(2), os.path.join(MIGRATIONS_DIR, name)))
    return files


def run_migrations(settings: Optional[Settings] = None) -> list[int]:
    """Apply pending ``migrations/NNNN_name.sql`` files in order, each in its own transaction, over the
    DIRECT connection (DDL + locks are not safe through a transaction-mode pooler). Safe to call from
    several instances at once: a transaction-level advisory lock serialises them. Returns the versions
    applied by this call."""
    settings = settings or get_settings()
    url = settings.database_url_direct or settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    applied: list[int] = []
    last: Optional[Exception] = None
    conn = None
    for attempt in range(settings.db_connect_retries):
        try:
            conn = psycopg.connect(url, autocommit=True, connect_timeout=settings.db_connect_timeout)
            break
        except psycopg.OperationalError as exc:
            last = exc
            time.sleep(min(0.5 * 2 ** attempt, 4))
    if conn is None:
        raise last  # type: ignore[misc]
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " applied_at TEXT NOT NULL DEFAULT to_char(timezone('utc', clock_timestamp()), 'YYYY-MM-DD HH24:MI:SS'))"
        )
        for version, name, path in _migration_files():
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(727274)")
                if conn.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,)).fetchone():
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    conn.execute(f.read())  # type: ignore[arg-type]
                conn.execute("INSERT INTO schema_migrations (version, name) VALUES (%s, %s)", (version, name))
                applied.append(version)
                log.info("applied migration %04d_%s", version, name)
    return applied


def schema_version(settings: Optional[Settings] = None) -> int:
    with db_session(settings) as db:
        row = db.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
        return int(row["v"])


def init_db(settings: Optional[Settings] = None) -> None:
    """Migrate the schema and seed the default academic structure. Idempotent; safe at every start."""
    settings = settings or get_settings()
    run_migrations(settings)
    with db_session(settings) as db:
        # The primary admin can never stay deactivated (an existing admin row is re-activated at start).
        db.execute("UPDATE users SET is_active = 1, updated_at = datetime('now') "
                   "WHERE role = 'ADMIN' AND is_active = 0 AND email = ?", (settings.primary_admin_email,))
        db.commit()
        from services import academic_service
        academic_service.seed_default_structure()
        if settings.seed_extra_branches:
            academic_service.seed_extra_structure()
        academic_service.backfill_legacy_data()
