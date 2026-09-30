"""Data access for security features: login throttling, OTP request throttling, last-login
tracking and upload authorisation lookups. All timestamps are UTC, formatted like SQLite's
``datetime('now')`` ("YYYY-MM-DD HH:MM:SS") so they compare correctly with default column values."""
from datetime import datetime, timedelta, timezone

from models.database import get_db

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def utcnow():
    return datetime.now(timezone.utc)


def fmt(dt):
    return dt.astimezone(timezone.utc).strftime(_TS_FORMAT)


def parse_ts(value):
    """Parse a stored UTC timestamp (SQLite format or ISO-8601, naive = UTC) into an aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_schema():
    """Idempotent: tables/indexes owned by the security layer (login_attempts lives in schema.sql)."""
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS otp_requests (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               email TEXT NOT NULL,
               ip TEXT,
               created_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_otp_requests_email ON otp_requests(email, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_otp_requests_ip ON otp_requests(ip, created_at)")
    db.execute(
        """CREATE TABLE IF NOT EXISTS login_attempts (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               identifier TEXT NOT NULL,
               ip TEXT,
               success INTEGER NOT NULL DEFAULT 0,
               created_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_created ON login_attempts(created_at)")
    db.commit()


# ---------- login throttling ----------

def count_recent_failures_for_identifier(identifier, window_minutes):
    since = fmt(utcnow() - timedelta(minutes=window_minutes))
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM login_attempts WHERE identifier = ? AND success = 0 AND created_at >= ?",
        (identifier, since),
    ).fetchone()
    return row["c"]


def count_recent_failures_for_ip(ip, window_minutes):
    if not ip:
        return 0
    since = fmt(utcnow() - timedelta(minutes=window_minutes))
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM login_attempts WHERE ip = ? AND success = 0 AND created_at >= ?",
        (ip, since),
    ).fetchone()
    return row["c"]


def record_login_attempt(identifier, ip, success):
    db = get_db()
    db.execute(
        "INSERT INTO login_attempts (identifier, ip, success, created_at) VALUES (?, ?, ?, ?)",
        (identifier, ip, 1 if success else 0, fmt(utcnow())),
    )
    # Keep the table small: nothing older than two days is ever consulted.
    db.execute("DELETE FROM login_attempts WHERE created_at < ?", (fmt(utcnow() - timedelta(days=2)),))
    db.commit()


def clear_failures_for_identifier(identifier):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE identifier = ? AND success = 0", (identifier,))
    db.commit()


# ---------- users ----------

def touch_last_login(user_id):
    db = get_db()
    db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (fmt(utcnow()), user_id))
    db.commit()


# ---------- OTP request throttling ----------

def count_recent_otp_requests_for_email(email, window_minutes=60):
    since = fmt(utcnow() - timedelta(minutes=window_minutes))
    return get_db().execute(
        "SELECT COUNT(*) AS c FROM otp_requests WHERE email = ? AND created_at >= ?", (email, since)
    ).fetchone()["c"]


def count_recent_otp_requests_for_ip(ip, window_minutes=60):
    if not ip:
        return 0
    since = fmt(utcnow() - timedelta(minutes=window_minutes))
    return get_db().execute(
        "SELECT COUNT(*) AS c FROM otp_requests WHERE ip = ? AND created_at >= ?", (ip, since)
    ).fetchone()["c"]


def record_otp_request(email, ip):
    db = get_db()
    db.execute(
        "INSERT INTO otp_requests (email, ip, created_at) VALUES (?, ?, ?)", (email, ip, fmt(utcnow()))
    )
    db.execute("DELETE FROM otp_requests WHERE created_at < ?", (fmt(utcnow() - timedelta(days=2)),))
    db.commit()


# ---------- upload authorisation ----------

def get_chat_for_attachment(attachment_path):
    """Return {chat_id, student_user_id, faculty_user_id, original_name} for the message that owns
    this stored attachment, or None if no message references it."""
    return get_db().execute(
        """SELECT m.chat_id AS chat_id, su.id AS student_user_id, fu.id AS faculty_user_id,
                  m.attachment_original_name AS original_name
           FROM messages m
           JOIN chats c ON c.id = m.chat_id
           JOIN students s ON s.id = c.student_id
           JOIN users su ON su.id = s.user_id
           JOIN faculty f ON f.id = c.faculty_id
           JOIN users fu ON fu.id = f.user_id
           WHERE m.attachment_path = ?
           LIMIT 1""",
        (attachment_path,),
    ).fetchone()
