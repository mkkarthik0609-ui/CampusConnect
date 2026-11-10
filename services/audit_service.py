"""Append-only audit trail for sensitive administrative actions (table ``audit_log``).

Never put secrets (passwords, tokens, invitation links) in ``detail``."""
import logging

from api.db import get_db

log = logging.getLogger("campusconnect.audit")


def record(actor, action, target=None, detail=None, ip=None, commit=True):
    """``actor`` is a CurrentUser/row (or None for system/anonymous actions)."""
    try:
        db = get_db()
        db.execute(
            "INSERT INTO audit_log (actor_user_id, actor_email, action, target, detail, ip) VALUES (?, ?, ?, ?, ?, ?)",
            (actor["id"] if actor else None, actor["email"] if actor else None, action,
             None if target is None else str(target)[:200], None if detail is None else str(detail)[:500], ip),
        )
        if commit:
            db.commit()
    except Exception:  # noqa: BLE001 - an audit write must never break the action it describes
        log.exception("audit write failed for action %s", action)


def recent(limit=100):
    limit = max(1, min(int(limit), 500))
    return get_db().execute(
        "SELECT id, actor_user_id, actor_email, action, target, detail, ip, created_at FROM audit_log "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
