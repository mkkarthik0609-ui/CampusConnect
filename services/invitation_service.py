"""Administrator invitations (primary admin only).

Flow: invite (token generated, only its SHA-256 stored) -> e-mail with a link whose token sits in the URL
*fragment* (``/admin-invite#t=...``, so it is never sent to any server log) -> invitee opens it, chooses a
password -> the account is created ACTIVE in one transaction that also consumes the invitation. Tokens are
single-use (atomic ``UPDATE ... WHERE status='PENDING'``), expire, and can be resent (rotates the token) or
revoked. The raw token / link is never logged or stored."""
import hashlib
import secrets
from datetime import timedelta

from api.db import get_db
from api.settings import get_settings
from models import queries
from models import security_queries as sq
from services import audit_service, auth_service, mail_service
from services.auth_service import ConflictError, ValidationError, hash_password, validate_email
from services.errors import ServiceError

RESEND_COOLDOWN_SECONDS = 60
INVALID_LINK = "This invitation link is invalid or has expired. Ask the primary administrator to send a new one."


class InvitationError(ServiceError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def _expiry():
    return sq.fmt(sq.utcnow() + timedelta(hours=get_settings().invite_ttl_hours))


def invite_link(token: str) -> str:
    return f"{get_settings().public_app_url}/admin-invite#t={token}"


def derived_status(row) -> str:
    if row["status"] == "PENDING" and row["expires_at"] <= sq.fmt(sq.utcnow()):
        return "EXPIRED"
    return row["status"]


def _public(row):
    return {
        "id": row["id"], "email": row["email"], "full_name": row["full_name"], "status": derived_status(row),
        "created_at": row["created_at"], "expires_at": row["expires_at"], "last_sent_at": row["last_sent_at"],
        "send_count": row["send_count"], "delivery_status": row["delivery_status"],
        "accepted_at": row["accepted_at"],
    }


def list_invitations():
    rows = get_db().execute("SELECT * FROM admin_invitations ORDER BY id DESC LIMIT 200").fetchall()
    return [_public(r) for r in rows]


def _deliver(row, token, inviter_name):
    """E-mail the link. Returns (delivery_status, link_for_manual_sharing_or_None). The link is returned to the
    (authenticated, primary) caller only when e-mail could not be delivered, so the invite is never stranded."""
    link = invite_link(token)
    hours = get_settings().invite_ttl_hours
    status = mail_service.send(
        row["email"], "You are invited to administer Campus Connect",
        f"{inviter_name} invited you to be an administrator of Campus Connect.\n\n"
        f"Open this link to choose your password (valid for {hours} hours, single use):\n{link}\n\n"
        "If you did not expect this invitation, ignore this e-mail.")
    db = get_db()
    db.execute(
        "UPDATE admin_invitations SET delivery_status = ?, last_sent_at = datetime('now'), send_count = send_count + 1 "
        "WHERE id = ?", (status, row["id"]))
    db.commit()
    return status, (link if status != mail_service.SENT else None)


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
    status, link = _deliver(row, token, actor["full_name"])
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _public(row), status, link


def resend_invitation(actor, invitation_id):
    db = get_db()
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (invitation_id,)).fetchone()
    if not row or row["status"] != "PENDING":
        raise InvitationError("Only a pending invitation can be resent.")
    if row["last_sent_at"] and row["last_sent_at"] > sq.fmt(sq.utcnow() - timedelta(seconds=RESEND_COOLDOWN_SECONDS)):
        raise InvitationError("Please wait a minute before resending.")
    token = _new_token()  # rotating invalidates the previously e-mailed link
    db.execute("UPDATE admin_invitations SET token_hash = ?, expires_at = ? WHERE id = ? AND status = 'PENDING'",
               (_hash(token), _expiry(), invitation_id))
    db.commit()
    audit_service.record(actor, "admin_invite.resend", row["email"])
    status, link = _deliver(row, token, actor["full_name"])
    row = db.execute("SELECT * FROM admin_invitations WHERE id = ?", (invitation_id,)).fetchone()
    return _public(row), status, link


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


_THROTTLE_KEY = "\x01admin-invite"


def _find_valid(token, ip):
    cfg = get_settings()
    if ip and sq.count_recent_failures_for_identifier(_THROTTLE_KEY + ip, cfg.login_window_minutes) >= 20:
        raise auth_service.LockoutError(auth_service.LOCKOUT_MESSAGE)
    row = None
    if isinstance(token, str) and 20 <= len(token) <= 200:
        row = get_db().execute(
            "SELECT * FROM admin_invitations WHERE token_hash = ? AND status = 'PENDING' AND expires_at > ?",
            (_hash(token), sq.fmt(sq.utcnow()))).fetchone()
    if row is None:
        sq.record_login_attempt(_THROTTLE_KEY + (ip or ""), None, False)  # not in the login IP counter
        raise InvitationError(INVALID_LINK)
    return row


def inspect_invitation(token, ip=None):
    """Public: who the link is for (no secrets), so the page can greet them."""
    row = _find_valid(token, ip)
    return {"email": row["email"], "full_name": row["full_name"], "expires_at": row["expires_at"]}


def accept_invitation(token, full_name, password, confirm_password, ip=None):
    """Create the ADMIN account and consume the invitation atomically. Returns the new user id."""
    row = _find_valid(token, ip)
    if password != confirm_password:
        raise ValidationError("Passwords do not match.", "confirm_password")
    full_name = auth_service.validate_required(full_name or row["full_name"], "Full name", "full_name")
    password_hash = hash_password(password, disallow=(row["email"],))  # validates strength before consuming
    db = get_db()
    claimed = db.execute(
        "UPDATE admin_invitations SET status = 'ACCEPTED', accepted_at = datetime('now') "
        "WHERE id = ? AND status = 'PENDING' AND token_hash = ?", (row["id"], _hash(token))).rowcount
    if claimed != 1:  # someone else consumed it first
        db.rollback()
        raise InvitationError(INVALID_LINK)
    if queries.get_user_by_email(row["email"]):
        db.rollback()
        raise InvitationError(INVALID_LINK)
    try:
        cur = db.execute(
            "INSERT INTO users (role, email, password_hash, full_name) VALUES ('ADMIN', ?, ?, ?)",
            (row["email"], password_hash, full_name))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if exc.__class__.__name__ == "UniqueViolation":
            raise InvitationError(INVALID_LINK) from exc
        raise
    db.execute("UPDATE admin_invitations SET accepted_user_id = ? WHERE id = ?", (cur.lastrowid, row["id"]))
    db.commit()
    audit_service.record(None, "admin_invite.accept", row["email"], ip=ip)
    return cur.lastrowid
