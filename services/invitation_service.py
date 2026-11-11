"""Admin registrations (primary admin only).

The primary admin adds an admin's e-mail (an ``admin_invitations`` row). Nothing is e-mailed: the person signs in at
Admin Login with that e-mail + the shared ADMIN_ACCESS_ID and the account is created on first sign-in
(``auth_service.authenticate_admin``). "Resend" renews the registration window; a pending row can be revoked."""
import hashlib
import secrets
from datetime import timedelta

from api.db import get_db
from api.settings import get_settings
from models import queries
from models import security_queries as sq
from services import audit_service
from services.auth_service import ConflictError, validate_email
from services.errors import ServiceError

RESEND_COOLDOWN_SECONDS = 60


class InvitationError(ServiceError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def _expiry():
    return sq.fmt(sq.utcnow() + timedelta(hours=get_settings().invite_ttl_hours))


def derived_status(row) -> str:
    if row["status"] == "PENDING" and row["expires_at"] <= sq.fmt(sq.utcnow()):
        return "EXPIRED"
    return row["status"]


def _public(row):
    return {
        "id": row["id"], "email": row["email"], "full_name": row["full_name"], "status": derived_status(row),
        "created_at": row["created_at"], "expires_at": row["expires_at"], "last_sent_at": row["last_sent_at"],
        "accepted_at": row["accepted_at"],
    }


def list_invitations():
    rows = get_db().execute("SELECT * FROM admin_invitations ORDER BY id DESC LIMIT 200").fetchall()
    return [_public(r) for r in rows]


def create_invitation(actor, email, full_name=None):
    email = validate_email(email, "Email", "email")
    if full_name is not None:
        full_name = (full_name or "").strip()[:120] or None
    if queries.get_user_by_email(email):
        raise ConflictError("An account with this email already exists.", "email")
    db = get_db()
    existing = db.execute("SELECT * FROM admin_invitations WHERE email = ? AND status = 'PENDING'", (email,)).fetchone()
    if existing and derived_status(existing) == "PENDING":
        raise ConflictError("An invitation for this email is already pending. Resend or revoke it instead.", "email")
    if existing:  # expired: retire it so a new one can be issued
        db.execute("UPDATE admin_invitations SET status = 'REVOKED' WHERE id = ?", (existing["id"],))
    token = _new_token()
    try:
        cur = db.execute(
            "INSERT INTO admin_invitations (email, full_name, token_hash, invited_by, expires_at) VALUES (?, ?, ?, ?, ?)",
            (email, full_name, _hash(token), actor["id"], _expiry()))
    except Exception as exc:  # noqa: BLE001 - lost a race with a concurrent invite for the same address
        db.rollback()
        if exc.__class__.__name__ == "UniqueViolation":
            raise ConflictError("An invitation for this email is already pending.", "email") from exc
        raise
    db.commit()
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (cur.lastrowid,)).fetchone()
    audit_service.record(actor, "admin_invite.create", email)
    # Demo flow: nothing is e-mailed. The primary admin tells the person their e-mail + the admin ID; the account
    # is created on that person's first sign-in (auth_service.authenticate_admin).
    return _public(row)


def resend_invitation(actor, invitation_id):
    db = get_db()
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (invitation_id,)).fetchone()
    if not row or row["status"] != "PENDING":
        raise InvitationError("Only a pending invitation can be resent.")
    if row["last_sent_at"] and row["last_sent_at"] > sq.fmt(sq.utcnow() - timedelta(seconds=RESEND_COOLDOWN_SECONDS)):
        raise InvitationError("Please wait a minute before resending.")
    # Nothing is sent any more: "resend" just renews the registration window (and retires any old link token).
    db.execute("UPDATE admin_invitations SET token_hash = ?, expires_at = ?, last_sent_at = datetime('now'), "
               "send_count = send_count + 1 WHERE id = ? AND status = 'PENDING'",
               (_hash(_new_token()), _expiry(), invitation_id))
    db.commit()
    audit_service.record(actor, "admin_invite.resend", row["email"])
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (invitation_id,)).fetchone()
    return _public(row)


def revoke_invitation(actor, invitation_id):
    db = get_db()
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (invitation_id,)).fetchone()
    if not row:
        raise InvitationError("Invitation not found.")
    if row["status"] != "PENDING":
        raise InvitationError("Only a pending invitation can be revoked.")
    db.execute("UPDATE admin_invitations SET status = 'REVOKED' WHERE id = ? AND status = 'PENDING'", (invitation_id,))
    db.commit()
    audit_service.record(actor, "admin_invite.revoke", row["email"])
