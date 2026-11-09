"""Admin passkeys (WebAuthn) - a thin wrapper around py_webauthn.

Credentials are DISCOVERABLE (resident) so sign-in needs no email lookup and cannot enumerate admins.
The challenge, RP id and origin used for it live in the signed session (5 minutes, single use).
The RP id is derived from the request ``Origin`` header, but only when that origin is in
``Settings.webauthn_allowed_origins`` (the browser origin differs from the backend host behind the
Vercel rewrites)."""
import json
import time
from urllib.parse import urlparse

from webauthn import (
    generate_authentication_options, generate_registration_options, options_to_json,
    verify_authentication_response, verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, ResidentKeyRequirement,
    UserVerificationRequirement,
)

from api.settings import get_settings
from models import queries
from models import security_queries as sq
from services import auth_service
from services.auth_service import GENERIC_LOGIN_ERROR, LOCKOUT_MESSAGE, LockoutError, ValidationError

SESSION_KEY = "webauthn"
CHALLENGE_TTL_SECONDS = 300
MAX_PASSKEYS_PER_ADMIN = 10
RP_NAME = "Campus Connect"
FAILED = "Passkey verification failed. Please try again."
_TRANSPORTS = {"usb", "nfc", "ble", "internal", "hybrid", "smart-card", "cable"}


def resolve_origin(origin_header):
    """-> (origin, rp_id) for an allow-listed browser origin, else ValidationError."""
    origin = (origin_header or "").strip().rstrip("/").lower()
    allowed = {o.strip().rstrip("/").lower() for o in get_settings().webauthn_allowed_origins}
    host = urlparse(origin).hostname if origin in allowed else None
    if not host:
        raise ValidationError("Passkeys are not available from this website address.")
    return origin, host


def _begin(session, purpose, origin, rp_id, options, user_id=None):
    session[SESSION_KEY] = {
        "purpose": purpose, "challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id,
        "origin": origin, "user_id": user_id, "exp": int(time.time()) + CHALLENGE_TTL_SECONDS,
    }
    return json.loads(options_to_json(options))


def _take(session, purpose, user_id=None):
    """Pop the pending challenge (single use, even when verification later fails)."""
    state = session.pop(SESSION_KEY, None)
    if (not isinstance(state, dict) or state.get("purpose") != purpose or state.get("user_id") != user_id
            or int(state.get("exp") or 0) < int(time.time())):
        raise ValidationError("This passkey request expired. Please try again.")
    return state


def _selection():
    return AuthenticatorSelectionCriteria(
        resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.PREFERRED)


# ---------------------------------------------------------------- registration (signed-in admin)

def registration_options(session, origin_header, user):
    origin, rp_id = resolve_origin(origin_header)
    if sq.count_passkeys(user["id"]) >= MAX_PASSKEYS_PER_ADMIN:
        raise ValidationError(f"You can register at most {MAX_PASSKEYS_PER_ADMIN} passkeys. Remove one first.")
    options = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME, user_id=str(user["id"]).encode(), user_name=user["email"],
        user_display_name=user["full_name"], authenticator_selection=_selection(),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["credential_id"]))
                             for p in sq.list_passkeys(user["id"])],
    )
    return _begin(session, "register", origin, rp_id, options, user["id"])


def register_passkey(session, user, credential, label=None):
    state = _take(session, "register", user["id"])
    try:
        verified = verify_registration_response(
            credential=credential, expected_challenge=base64url_to_bytes(state["challenge"]),
            expected_rp_id=state["rp_id"], expected_origin=state["origin"])
        transports = [t for t in (credential.get("response") or {}).get("transports") or [] if t in _TRANSPORTS]
    except (WebAuthnException, ValueError, KeyError, TypeError, AttributeError):
        raise ValidationError(FAILED)
    label = " ".join((label or "").split())[:60] or "Passkey"
    try:
        return sq.create_passkey(user["id"], bytes_to_base64url(verified.credential_id),
                                 verified.credential_public_key, verified.sign_count, ",".join(transports), label)
    except Exception as exc:  # noqa: BLE001 - sqlite3.IntegrityError: this authenticator is already registered
        if "UNIQUE" in str(exc):
            raise ValidationError("This passkey is already registered.") from exc
        raise


# ---------------------------------------------------------------- sign-in (anonymous)

def authentication_options(session, origin_header):
    origin, rp_id = resolve_origin(origin_header)
    options = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.PREFERRED)
    return _begin(session, "login", origin, rp_id, options)


def authenticate_admin_passkey(session, credential, identifier=None, ip=None):
    """Verify a discoverable-credential assertion and return the ADMIN user row. One generic error for
    every failure; failures are throttled per client address like password sign-ins."""
    throttle_key = f"\x01admin-passkey:{ip or ''}"
    if auth_service._is_locked_out(throttle_key, ip):
        raise LockoutError(LOCKOUT_MESSAGE)
    try:
        state = _take(session, "login")
        user = _verify_assertion(state, credential, identifier)
    except ValidationError:
        sq.record_login_attempt(throttle_key, ip, False)
        raise ValidationError(GENERIC_LOGIN_ERROR)
    sq.clear_failures_for_identifier(throttle_key)
    sq.record_login_attempt(throttle_key, ip, True)
    sq.touch_last_login(user["id"])
    return user


def _verify_assertion(state, credential, identifier):
    fail = ValidationError(GENERIC_LOGIN_ERROR)
    if not isinstance(credential, dict) or not isinstance(credential.get("id"), str):
        raise fail
    row = sq.get_passkey_by_credential_id(credential["id"])
    user = queries.get_user_by_id(row["user_id"]) if row else None
    if not user or user["role"] != "ADMIN" or not user["is_active"]:
        raise fail
    if identifier and auth_service.normalize_identifier(identifier) != user["email"].strip().lower():
        raise fail
    try:
        handle = (credential.get("response") or {}).get("userHandle")
        if handle and base64url_to_bytes(handle) != str(user["id"]).encode():
            raise fail
        verified = verify_authentication_response(  # also rejects a sign-count regression (cloned key)
            credential=credential, expected_challenge=base64url_to_bytes(state["challenge"]),
            expected_rp_id=state["rp_id"], expected_origin=state["origin"],
            credential_public_key=bytes(row["public_key"]), credential_current_sign_count=row["sign_count"])
    except (WebAuthnException, ValueError, KeyError, TypeError, AttributeError):
        raise fail
    sq.touch_passkey(row["id"], verified.new_sign_count)
    return user
