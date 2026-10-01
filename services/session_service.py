"""Server-side session hygiene (framework-agnostic): identity refresh, idle/absolute timeouts and
deactivation checks. ``session`` is the plain dict-like signed-cookie session (request.session)."""
import secrets
import time

from models import queries

TOUCH_INTERVAL_SECONDS = 60

# Reasons returned by ``resolve_session_user`` when a session was ended.
EXPIRED_ABSOLUTE = "absolute"
EXPIRED_IDLE = "idle"
EXPIRED_INACTIVE = "inactive"

MESSAGES = {
    EXPIRED_ABSOLUTE: "Your session has expired. Please sign in again.",
    EXPIRED_IDLE: "You were signed out after a period of inactivity. Please sign in again.",
    EXPIRED_INACTIVE: "Your session has ended. Please sign in again.",
}


def now():
    """Current epoch seconds (module-level so tests can monkeypatch the clock)."""
    return int(time.time())


def new_csrf_token():
    return secrets.token_urlsafe(32)


def ensure_csrf_token(session):
    token = session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = new_csrf_token()
        session["csrf_token"] = token
    return token


def apply_identity(session, user_row):
    """Copy the authoritative identity (role, name, student/faculty ids) from the DB row into the session."""
    session["user_id"] = user_row["id"]
    session["role"] = user_row["role"]
    session["full_name"] = user_row["full_name"]
    session.pop("student_id", None)
    session.pop("faculty_id", None)
    if user_row["role"] == "STUDENT":
        student = queries.get_student_by_user_id(user_row["id"])
        if student:
            session["student_id"] = student["id"]
    elif user_row["role"] == "FACULTY":
        faculty = queries.get_faculty_by_user_id(user_row["id"])
        if faculty:
            session["faculty_id"] = faculty["id"]


def stamp_login(session):
    stamp = now()
    session["login_at"] = stamp
    session["last_seen"] = stamp


def start_session(session, user_row):
    """Begin a fresh authenticated session (fixation-safe): everything from the anonymous session is
    discarded and a NEW csrf token is issued. Returns the new token."""
    session.clear()
    session["theme"] = user_row["theme_preference"]
    apply_identity(session, user_row)
    stamp_login(session)
    return ensure_csrf_token(session)


def end_session(session):
    """Sign out: drop everything and issue a fresh anonymous csrf token. Returns it."""
    session.clear()
    return ensure_csrf_token(session)


def resolve_session_user(session, absolute_seconds, idle_minutes):
    """For a session carrying ``user_id``: enforce the absolute + idle timeouts, re-load the user
    (missing or deactivated -> session destroyed) and refresh role/name/ids from the database so a
    stale cookie can never keep old privileges.

    Returns ``(user_row, None)`` when valid or ``(None, reason)`` after the session was destroyed
    (reason is one of EXPIRED_*). Returns ``(None, None)`` when there is no signed-in user."""
    user_id = session.get("user_id")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        if "user_id" in session:  # malformed
            session.clear()
        return None, None
    stamp = now()
    login_at = session.get("login_at")
    last_seen = session.get("last_seen")
    if not isinstance(login_at, int):
        login_at = stamp
        session["login_at"] = stamp
    if not isinstance(last_seen, int):
        last_seen = stamp

    if stamp - login_at > absolute_seconds:
        session.clear()
        return None, EXPIRED_ABSOLUTE
    idle_limit = int(idle_minutes or 0) * 60
    if idle_limit and stamp - last_seen > idle_limit:
        session.clear()
        return None, EXPIRED_IDLE

    user = queries.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        session.clear()
        return None, EXPIRED_INACTIVE

    needs_ids = (user["role"] == "STUDENT" and "student_id" not in session) or (
        user["role"] == "FACULTY" and "faculty_id" not in session
    )
    if session.get("role") != user["role"] or session.get("full_name") != user["full_name"] or needs_ids:
        apply_identity(session, user)

    if stamp - last_seen >= TOUCH_INTERVAL_SECONDS or "last_seen" not in session:
        session["last_seen"] = stamp
    return user, None
