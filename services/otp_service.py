"""Email-verification OTPs for student signup.

Delivery: if RESEND_API_KEY (HTTPS API, works where outbound SMTP is blocked) or SMTP_HOST is configured
the code is emailed and never shown on screen. Otherwise the
code is returned to the caller (demo mode) only while settings.show_demo_otp is true.

The "verified in this browser session" helpers take the signed-cookie ``session`` dict explicitly."""
import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import urllib.error
import urllib.request
from datetime import timedelta
from email.message import EmailMessage

from api.settings import get_settings
from models import queries
from models import security_queries as sq
from services.auth_service import ValidationError

logger = logging.getLogger(__name__)

SESSION_EMAIL_KEY = "otp_verified_email"
SESSION_TIME_KEY = "otp_verified_at"


class OtpRateLimitError(ValidationError):
    """Too many codes requested for this email / IP -> HTTP 429."""


class DeliveryError(ValidationError):
    """The verification email could not be sent (SMTP failure) or no delivery channel exists -> HTTP 503."""


def normalize_email(email):
    return (email or "").strip().lower()


def delivery_mode():
    """'resend', 'smtp', 'demo' (on-screen) or 'none'."""
    cfg = get_settings()
    if cfg.resend_api_key:
        return "resend"
    if cfg.smtp_host:
        return "smtp"
    if cfg.show_demo_otp:
        return "demo"
    return "none"


def _hash_otp(email, otp):
    key = str(get_settings().secret_key).encode("utf-8")
    return hmac.new(key, f"otp:{email}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _check_rate_limit(email, ip):
    cfg = get_settings()
    if sq.count_recent_otp_requests_for_email(email) >= cfg.otp_max_per_email_per_hour or (
        ip and sq.count_recent_otp_requests_for_ip(ip) >= cfg.otp_max_per_ip_per_hour
    ):
        raise OtpRateLimitError("Too many verification codes requested. Please try again in an hour.")


def generate_and_store_otp(email, ip=None):
    """Create and store a new OTP for `email` and return the plaintext code (caller delivers it).
    Raises OtpRateLimitError beyond 5 codes per email / per IP per hour."""
    email = normalize_email(email)
    _check_rate_limit(email, ip)
    length = get_settings().otp_length
    otp = "".join(secrets.choice("0123456789") for _ in range(length))
    expires_at = (sq.utcnow() + timedelta(minutes=get_settings().otp_expiry_minutes)).isoformat()
    queries.create_otp_session(email, _hash_otp(email, otp), expires_at)
    sq.record_otp_request(email, ip)
    return otp


def _deliver_via_resend(cfg, email, otp):
    """Send the OTP through the Resend HTTPS API. Raises DeliveryError on any failure."""
    payload = {
        "from": cfg.resend_from or "Campus Connect <onboarding@resend.dev>",
        "to": [email],
        "subject": "Your Campus Connect verification code",
        "text": (
            f"Your Campus Connect verification code is {otp}.\n"
            f"It expires in {cfg.otp_expiry_minutes} minutes. If you did not request it, ignore this email."
        ),
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "campus-connect/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", "replace")  # Resend's error text; never contains the code
        logger.error("Resend rejected OTP email: HTTP %s %s", exc.code, detail)
        raise DeliveryError("We could not send the verification email right now. Please try again later.")
    except (urllib.error.URLError, OSError):
        logger.exception("Failed to send OTP email via Resend")
        raise DeliveryError("We could not send the verification email right now. Please try again later.")
    return True


def deliver_otp(email, otp):
    """Email the OTP when SMTP is configured. Returns True if emailed, False if the caller should
    fall back to the on-screen demo. Raises DeliveryError (a ValidationError) if sending fails."""
    cfg = get_settings()
    if cfg.resend_api_key:
        return _deliver_via_resend(cfg, email, otp)
    if not cfg.smtp_host:
        return False
    msg = EmailMessage()
    msg["Subject"] = "Your Campus Connect verification code"
    msg["From"] = cfg.smtp_from or cfg.smtp_user or "no-reply@localhost"
    msg["To"] = email
    msg.set_content(
        f"Your Campus Connect verification code is {otp}.\n"
        f"It expires in {cfg.otp_expiry_minutes} minutes. If you did not request it, ignore this email."
    )
    mode = (cfg.smtp_tls or "1").lower()
    try:
        if mode == "ssl":
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
        with server:
            if mode not in ("0", "false", "no", "off", "ssl"):
                server.starttls()
            if cfg.smtp_user:
                server.login(cfg.smtp_user, cfg.smtp_password or "")
            server.send_message(msg)
    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send OTP email")  # never log the code itself
        raise DeliveryError("We could not send the verification email right now. Please try again later.")
    return True


def verify_otp(email, submitted_otp):
    email = normalize_email(email)
    session_row = queries.get_latest_otp_session(email)
    if not session_row:
        return False, "No OTP was generated for this email. Please request a new one."
    if session_row["verified"]:
        return False, "This OTP has already been used. Please request a new one."
    if session_row["attempt_count"] >= get_settings().otp_max_attempts:
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
        max_age_minutes = get_settings().otp_verified_max_age_minutes
    created = sq.parse_ts(session_row["created_at"])
    return bool(created and sq.utcnow() - created <= timedelta(minutes=max_age_minutes))


# ---- binding the verified email to the browser session ----

def remember_verified_in_session(session, email):
    session[SESSION_EMAIL_KEY] = normalize_email(email)
    session[SESSION_TIME_KEY] = int(sq.utcnow().timestamp())


def is_verified_in_session(session, email):
    """The email was verified by *this* browser session within OTP_VERIFIED_MAX_AGE_MINUTES."""
    if session.get(SESSION_EMAIL_KEY) != normalize_email(email):
        return False
    verified_at = session.get(SESSION_TIME_KEY)
    if not isinstance(verified_at, int):
        return False
    age = sq.utcnow().timestamp() - verified_at
    return 0 <= age <= get_settings().otp_verified_max_age_minutes * 60


def clear_verified_in_session(session):
    session.pop(SESSION_EMAIL_KEY, None)
    session.pop(SESSION_TIME_KEY, None)
