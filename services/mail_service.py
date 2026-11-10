"""Outbound e-mail through the Resend HTTP API (free tier: 100 mails/day, 3000/month).

Configure RESEND_API_KEY and MAIL_FROM (a sender on a domain verified in Resend; Resend's shared
onboarding@resend.dev sender can only deliver to the account owner's own address). Without them nothing is
sent and callers receive ``NOT_CONFIGURED``: delivery is never claimed. Message bodies are not logged."""
import json
import logging
import urllib.error
import urllib.request

from api.settings import get_settings

log = logging.getLogger("campusconnect.mail")

SENT = "SENT"
FAILED = "FAILED"
NOT_CONFIGURED = "NOT_CONFIGURED"


def is_configured() -> bool:
    cfg = get_settings()
    return bool(cfg.resend_api_key and cfg.mail_from)


def send(to: str, subject: str, text: str, html: str = "") -> str:
    """Returns SENT / FAILED / NOT_CONFIGURED. Never raises."""
    cfg = get_settings()
    if not (cfg.resend_api_key and cfg.mail_from):
        return NOT_CONFIGURED
    payload = {"from": cfg.mail_from, "to": [to], "subject": subject, "text": text}
    if html:
        payload["html"] = html
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {cfg.resend_api_key}", "Content-Type": "application/json",
                 "User-Agent": "campusconnect/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 - fixed https URL
            return SENT if 200 <= resp.status < 300 else FAILED
    except urllib.error.HTTPError as exc:
        log.warning("mail provider rejected a message (HTTP %s)", exc.code)
    except Exception as exc:  # noqa: BLE001
        log.warning("mail delivery failed: %s", type(exc).__name__)
    return FAILED
