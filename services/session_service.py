"""Server-side session hygiene: identity refresh, idle/absolute timeouts and deactivation checks."""
import time

from flask import current_app, flash, g, redirect, request, session, url_for

from models import queries

# Endpoints that must never be blocked or touched by session enforcement.
_SKIP_ENDPOINTS = {"static", "healthz"}
_TOUCH_INTERVAL_SECONDS = 60


def apply_identity(user_row):
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


def stamp_login():
    now = int(time.time())
    session["login_at"] = now
    session["last_seen"] = now


def _expire(message):
    session.clear()
    flash(message, "error")
    return redirect(url_for("auth.login"))


def enforce_session():
    """before_request hook. For logged-in sessions: enforce absolute + idle timeouts, re-load the user
    (missing or deactivated -> session destroyed) and refresh role/name from the database so a
    stale cookie can never keep old privileges."""
    if "user_id" not in session or request.endpoint in _SKIP_ENDPOINTS:
        return None
    cfg = current_app.config
    now = int(time.time())

    login_at = session.get("login_at")
    last_seen = session.get("last_seen")
    if not isinstance(login_at, int):
        login_at = now
        session["login_at"] = now
    if not isinstance(last_seen, int):
        last_seen = now

    if now - login_at > cfg["PERMANENT_SESSION_LIFETIME"].total_seconds():
        return _expire("Your session has expired. Please sign in again.")
    idle_limit = int(cfg.get("SESSION_IDLE_TIMEOUT_MINUTES") or 0) * 60
    if idle_limit and now - last_seen > idle_limit:
        return _expire("You were signed out after a period of inactivity. Please sign in again.")

    user = queries.get_user_by_id(session["user_id"])
    if not user or not user["is_active"]:
        return _expire("Your session has ended. Please sign in again.")

    needs_ids = (user["role"] == "STUDENT" and "student_id" not in session) or (
        user["role"] == "FACULTY" and "faculty_id" not in session
    )
    if session.get("role") != user["role"] or session.get("full_name") != user["full_name"] or needs_ids:
        apply_identity(user)

    if now - last_seen >= _TOUCH_INTERVAL_SECONDS or "last_seen" not in session:
        session["last_seen"] = now
    g.current_user = user
    return None
