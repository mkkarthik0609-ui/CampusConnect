"""Email-verification OTPs for student signup.

Delivery: if SMTP_HOST is configured the code is emailed and never shown on screen. Otherwise the
code is shown on screen (demo mode) only while config SHOW_DEMO_OTP is true."""
import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from flask import current_app, has_request_context, request, session

from models import queries
from models import security_queries as sq
from services.auth_service import ValidationError

logger = logging.getLogger(__name__)

SESSION_EMAIL_KEY = "otp_verified_email"
SESSION_TIME_KEY = "otp_verified_at"


class OtpRateLimitError(ValidationError):
    pass


def normalize_email(email):
    return (email or "").strip().lower()


def delivery_mode():
    """'smtp', 'demo' (on-screen) or 'none'."""
    if current_app.config.get("SMTP_HOST"):
        return "smtp"
    if current_app.config.get("SHOW_DEMO_OTP"):
        return "demo"
    return "none"


def _hash_otp(email, otp):
    key = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(key, f"otp:{email}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _check_rate_limit(email, ip):
    cfg = current_app.config
    if sq.count_recent_otp_requests_for_email(email) >= cfg["OTP_MAX_PER_EMAIL_PER_HOUR"] or (
        ip and sq.count_recent_otp_requests_for_ip(ip) >= cfg["OTP_MAX_PER_IP_PER_HOUR"]
    ):
        raise OtpRateLimitError("Too many verification codes requested. Please try again in an hour.")


def generate_and_store_otp(email, ip=None):
    """Create and store a new OTP for `email` and return the plaintext code (caller delivers it).
    Raises OtpRateLimitError beyond 5 codes per email / per IP per hour."""
    email = normalize_email(email)
    if ip is None and has_request_context():
        ip = request.remote_addr
    _check_rate_limit(email, ip)
    length = current_app.config["OTP_LENGTH"]
    otp = "".join(secrets.choice("0123456789") for _ in range(length))
    expires_at = (sq.utcnow() + timedelta(minutes=current_app.config["OTP_EXPIRY_MINUTES"])).isoformat()
    queries.create_otp_session(email, _hash_otp(email, otp), expires_at)
    sq.record_otp_request(email, ip)
    return otp


def deliver_otp(email, otp):
    """Email the OTP when SMTP is configured. Returns True if emailed, False if the caller should
    fall back to the on-screen demo. Raises ValidationError if sending fails."""
    cfg = current_app.config
    if not cfg.get("SMTP_HOST"):
        return False
    msg = EmailMessage()
    msg["Subject"] = "Your Campus Connect verification code"
    msg["From"] = cfg.get("SMTP_FROM") or cfg.get("SMTP_USER") or "no-reply@localhost"
    msg["To"] = email
    msg.set_content(
        f"Your Campus Connect verification code is {otp}.\n"
        f"It expires in {cfg['OTP_EXPIRY_MINUTES']} minutes. If you did not request it, ignore this email."
    )
    mode = (cfg.get("SMTP_TLS") or "1").lower()
    try:
        if mode == "ssl":
            server = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
        with server:
            if mode not in ("0", "false", "no", "off", "ssl"):
                server.starttls()
            if cfg.get("SMTP_USER"):
                server.login(cfg["SMTP_USER"], cfg.get("SMTP_PASSWORD", ""))
            server.send_message(msg)
    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send OTP email")  # never log the code itself
        raise ValidationError("We could not send the verification email right now. Please try again later.")
    return True


def verify_otp(email, submitted_otp):
    email = normalize_email(email)
    session_row = queries.get_latest_otp_session(email)
    if not session_row:
        return False, "No OTP was generated for this email. Please request a new one."
    if session_row["verified"]:
        return False, "This OTP has already been used. Please request a new one."
    if session_row["attempt_count"] >= current_app.config["OTP_MAX_ATTEMPTS"]:
        return False, "Too many incorrect attempts. Please request a new OTP."
    expires = sq.parse_ts(session_row["expires_at"])
    if expires is None or sq.utcnow() > expires:
        return False, "This OTP has expired. Please request a new one."

    expected = _hash_otp(email, (submitted_otp or "").strip())
    if not hmac.compare_digest(expected, session_row["otp_hash"]):
        queries.increment_otp_attempt(session_row["id"])
        return False, "Incorrect OTP."

    queries.mark_otp_verified(session_row["id"])
    return True, None


def is_email_otp_verified(email, max_age_minutes=None):
    """True if the latest OTP for `email` is verified and was issued within `max_age_minutes`
    (default: config OTP_VERIFIED_MAX_AGE_MINUTES)."""
    email = normalize_email(email)
    session_row = queries.get_latest_otp_session(email)
    if not (session_row and session_row["verified"]):
        return False
    if max_age_minutes is None:
        max_age_minutes = current_app.config["OTP_VERIFIED_MAX_AGE_MINUTES"]
    created = sq.parse_ts(session_row["created_at"])
    return bool(created and sq.utcnow() - created <= timedelta(minutes=max_age_minutes))


# ---- binding the verified email to the browser session ----

def remember_verified_in_session(email):
    session[SESSION_EMAIL_KEY] = normalize_email(email)
    session[SESSION_TIME_KEY] = int(sq.utcnow().timestamp())


def is_verified_in_session(email):
    """The email was verified by *this* browser session within OTP_VERIFIED_MAX_AGE_MINUTES."""
    if session.get(SESSION_EMAIL_KEY) != normalize_email(email):
        return False
    verified_at = session.get(SESSION_TIME_KEY)
    if not isinstance(verified_at, int):
        return False
    age = sq.utcnow().timestamp() - verified_at
    return 0 <= age <= current_app.config["OTP_VERIFIED_MAX_AGE_MINUTES"] * 60


def clear_verified_in_session():
    session.pop(SESSION_EMAIL_KEY, None)
    session.pop(SESSION_TIME_KEY, None)
