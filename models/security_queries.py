"""Data access for security features: login throttling, captcha challenges, last-login
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
    # E-mail OTP verification was removed (captcha replaced it); drop its leftovers on existing databases.
    db.execute("DROP TABLE IF EXISTS otp_requests")
    db.execute("DROP TABLE IF EXISTS otp_sessions")
    db.execute(
        """CREATE TABLE IF NOT EXISTS captcha_challenges (
               id TEXT PRIMARY KEY,
               answer_hash TEXT NOT NULL,
               expires_at TEXT NOT NULL,
               ip TEXT,
               created_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_captcha_ip ON captcha_challenges(ip, created_at)")
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


# ---------- captcha challenges ----------

def count_recent_captchas_for_ip(ip, window_minutes=60):
    if not ip:
        return 0
    since = fmt(utcnow() - timedelta(minutes=window_minutes))
    return get_db().execute(
        "SELECT COUNT(*) AS c FROM captcha_challenges WHERE ip = ? AND created_at >= ?", (ip, since)
    ).fetchone()["c"]


def create_captcha(challenge_id, answer_hash, expires_at, ip):
    db = get_db()
    db.execute(
        "INSERT INTO captcha_challenges (id, answer_hash, expires_at, ip, created_at) VALUES (?, ?, ?, ?, ?)",
        (challenge_id, answer_hash, expires_at, ip, fmt(utcnow())),
    )
    # Rows are only needed until they expire / are used; the per-IP count looks back one hour.
    db.execute("DELETE FROM captcha_challenges WHERE created_at < ?", (fmt(utcnow() - timedelta(hours=2)),))
    db.commit()


def consume_captcha(challenge_id):
    """Return the challenge row and delete it, atomically (None if unknown or already consumed)."""
    db = get_db()
    row = db.execute("SELECT * FROM captcha_challenges WHERE id = ?", (challenge_id,)).fetchone()
    if row is None:
        return None
    deleted = db.execute("DELETE FROM captcha_challenges WHERE id = ?", (challenge_id,)).rowcount
    db.commit()
    return row if deleted == 1 else None


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
