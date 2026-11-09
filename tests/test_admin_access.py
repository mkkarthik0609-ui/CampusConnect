"""Admin authentication: real password sign-in (never an "any password" shortcut), several equal admins
with a protected primary admin, and passkey (WebAuthn) registration + sign-in using a software authenticator."""
import base64
import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api.db import init_db
from api.main import create_app
from api.settings import Settings
from tests.conftest import (
    ADMIN_EMAIL, PASSWORD, api_delete, api_post, create_faculty, create_student, db_all, db_count, db_exec, db_one,
    login_client, make_admin, make_settings, read_session,
)

ORIGIN = "http://localhost:5173"
RP_ID = "localhost"
ADMIN_URL = "/api/auth/admin-login"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftAuthenticator:
    """A tiny ES256 platform authenticator: builds the registration / assertion objects a browser returns."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(32)
        self.counter = 0

    def _client_data(self, kind, options, origin=ORIGIN):
        return json.dumps({"type": kind, "challenge": options["challenge"], "origin": origin}).encode()

    def create(self, options, origin=ORIGIN):
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth_data = (hashlib.sha256(RP_ID.encode()).digest() + bytes([0x45]) + struct.pack(">I", 0) + bytes(16)
                     + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose)
        return {
            "id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
            "response": {
                "clientDataJSON": b64(self._client_data("webauthn.create", options, origin)),
                "attestationObject": b64(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options, user_handle=None, origin=ORIGIN, counter=None):
        self.counter = self.counter + 1 if counter is None else counter
        client_data = self._client_data("webauthn.get", options, origin)
        auth_data = hashlib.sha256(RP_ID.encode()).digest() + bytes([0x05]) + struct.pack(">I", self.counter)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        response = {"clientDataJSON": b64(client_data), "authenticatorData": b64(auth_data), "signature": b64(signature)}
        if user_handle is not None:
            response["userHandle"] = b64(str(user_handle).encode())
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key", "response": response,
                "clientExtensionResults": {}}


def hdr(origin=ORIGIN):
    return {"headers": {"Origin": origin}}


def add_passkey(client, auth=None, label="Laptop"):
    auth = auth or SoftAuthenticator()
    options = api_post(client, "/api/admin/passkeys/options", **hdr()).json()["options"]
    resp = api_post(client, "/api/admin/passkeys/verify", json={"credential": auth.create(options), "label": label})
    assert resp.status_code == 201, resp.text
    return auth, resp.json()["id"]


def passkey_login(client, auth, user_id, identifier=None, **get_kw):
    options = api_post(client, "/api/auth/admin-passkey/options", **hdr()).json()["options"]
    body = {"credential": auth.get(options, user_handle=user_id, **get_kw)}
    if identifier:
        body["identifier"] = identifier
    return api_post(client, "/api/auth/admin-passkey/verify", json=body)


@pytest.fixture
def owner(app):
    uid = make_admin(app)
    return {"id": uid, "client": login_client(app, ADMIN_EMAIL)}


def appoint(client, email="second@college.edu", name="Second Admin"):
    resp = api_post(client, "/api/admin/admins", json={"full_name": name, "email": email})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------- password sign-in is always real

def test_admin_login_rejects_wrong_password_and_non_admins(app):
    make_admin(app)
    stu = create_student(app, "1AB21CS001")
    fac = create_faculty(app, "FAC001")
    for who, password in ((ADMIN_EMAIL, "not-the-stored-password"), (ADMIN_EMAIL, PASSWORD + "x"),
                          (stu["email"], PASSWORD), (fac["email"], PASSWORD), ("nobody@example.com", PASSWORD)):
        resp = api_post(TestClient(app), ADMIN_URL, json={"identifier": who, "password": password})
        assert resp.status_code == 401, (who, resp.text)
        assert resp.json()["error"]["code"] == "invalid_credentials"
    ok = api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL.upper(), "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "ADMIN"


@pytest.mark.parametrize("environment,testing", [("development", True), ("test", True), ("development", False),
                                                 ("production", True)])
def test_arbitrary_password_is_never_accepted(tmp_path, environment, testing):
    kw = {"environment": environment, "testing": testing, "enable_scheduler": False}
    if environment == "production":
        kw["secret_key"] = "production-secret-key-long-enough-123"
    app = create_app(make_settings(tmp_path, **kw))
    make_admin(app)
    for password in ("anything", "x", PASSWORD.lower(), " "):
        resp = api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": password})
        assert resp.status_code == 401, (environment, password)


def test_the_any_password_shortcut_no_longer_exists():
    settings = Settings()
    assert not hasattr(settings, "admin_any_password_enabled")
    assert not hasattr(settings, "sole_admin_email")


def test_admin_login_is_throttled(app):
    make_admin(app)
    c = TestClient(app)
    for _ in range(5):
        assert api_post(c, ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": "wrong"}).status_code == 401
    assert api_post(c, ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 429


# ---------------------------------------------------------------- several equal admins

def test_primary_appoints_an_admin_and_only_the_primary_can(app, owner):
    body = appoint(owner["client"])
    temp = body["temporary_password"]
    assert len(temp) >= 12 and body["admin"]["email"] == "second@college.edu" and body["admin"]["is_primary"] is False
    row = db_one(app, "SELECT password_hash FROM users WHERE email = 'second@college.edu'")
    assert temp not in row["password_hash"]
    assert "temporary_password" not in json.dumps(owner["client"].get("/api/admin/admins").json())

    second = TestClient(app)  # signs in through the very same two-field endpoint
    assert api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": temp}).status_code == 200
    assert second.get("/api/admin/dashboard").status_code == 200  # full admin access for everything else
    assert second.get("/api/admin/admins").status_code == 200      # may read the list

    # ...but cannot appoint or manage admins: that stays with the primary administrator.
    admin_id = body["admin"]["id"]
    assert api_post(second, "/api/admin/admins", json={"full_name": "X", "email": "x@college.edu"}).status_code == 403
    assert api_post(second, f"/api/admin/admins/{admin_id}/reset-password").status_code == 403
    assert api_post(second, f"/api/admin/admins/{admin_id}/active", json={"active": False}).status_code == 403
    assert api_delete(second, f"/api/admin/admins/{admin_id}/passkeys").status_code == 403
    assert owner["client"].get("/api/admin/admins").json()["total"] == 2


def test_appointing_admins_is_validated(app, owner):
    c = owner["client"]
    assert api_post(c, "/api/admin/admins", json={"full_name": "A", "email": ADMIN_EMAIL.upper()}).status_code == 409
    assert api_post(c, "/api/admin/admins", json={"full_name": "A", "email": "not-an-email"}).status_code == 400
    assert api_post(c, "/api/admin/admins", json={"full_name": " ", "email": "a@b.co"}).status_code == 400
    assert api_post(c, "/api/admin/admins", json={"full_name": "A", "email": "a@b.co", "password": "x"}).status_code == 400
    assert db_count(app, "users", "role = 'ADMIN'") == 1


def test_primary_admin_is_protected(app, owner):
    second = TestClient(app)
    body = appoint(owner["client"])
    api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": body["temporary_password"]})
    for client, expected in ((owner["client"], 400), (second, 403)):  # 400 protected, 403 not the primary
        assert api_post(client, f"/api/admin/admins/{owner['id']}/active", json={"active": False}).status_code == expected
        assert api_post(client, f"/api/admin/admins/{owner['id']}/reset-password").status_code == expected
        assert api_delete(client, f"/api/admin/admins/{owner['id']}/passkeys").status_code == expected
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1
    # the primary cannot deactivate itself either
    assert api_post(owner["client"], f"/api/admin/admins/{owner['id']}/active", json={"active": False}).status_code == 400


def test_primary_admin_is_reactivated_at_startup(app, owner):
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (owner["id"],))
    init_db(app.state.settings)
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1


def test_deactivated_admin_cannot_sign_in_and_loses_the_session(app, owner):
    body = appoint(owner["client"])
    temp, admin_id = body["temporary_password"], body["admin"]["id"]
    second = TestClient(app)
    assert api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": temp}).status_code == 200

    resp = api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": False})
    assert resp.status_code == 200 and resp.json()["admin"]["is_active"] is False
    assert second.get("/api/admin/dashboard").status_code == 401  # existing session ended
    assert api_post(TestClient(app), ADMIN_URL, json={
        "identifier": "second@college.edu", "password": temp}).status_code == 401

    assert api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": True}).status_code == 200
    assert api_post(TestClient(app), ADMIN_URL, json={
        "identifier": "second@college.edu", "password": temp}).status_code == 200


def test_reset_password_issues_a_new_one_time_password_and_lifts_lockout(app, owner):
    body = appoint(owner["client"])
    admin_id, old = body["admin"]["id"], body["temporary_password"]
    for _ in range(5):
        api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": "bad"})
    resp = api_post(owner["client"], f"/api/admin/admins/{admin_id}/reset-password")
    assert resp.status_code == 200
    new = resp.json()["temporary_password"]
    assert new != old
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": old}).status_code == 401
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": new}).status_code == 200
    assert api_post(owner["client"], "/api/admin/admins/99999/reset-password").status_code == 400


def test_admin_management_requires_an_admin(app, owner):
    stu = create_student(app, "1AB21CS002")
    sc = login_client(app, stu["email"])
    assert api_post(sc, "/api/admin/admins", json={"full_name": "A", "email": "a@b.co"}).status_code == 403
    assert api_post(sc, f"/api/admin/admins/{owner['id']}/active", json={"active": True}).status_code == 403
    assert api_post(TestClient(app), "/api/admin/passkeys/options", **hdr()).status_code in (401, 403)
    assert TestClient(app).get("/api/admin/passkeys").status_code == 401


# ---------------------------------------------------------------- passkeys

def test_passkey_registration_and_sign_in_end_to_end(app, owner):
    c = owner["client"]
    auth, passkey_id = add_passkey(c)
    listing = c.get("/api/admin/passkeys").json()
    assert listing["total"] == 1 and listing["items"][0]["label"] == "Laptop"
    assert listing["items"][0]["transports"] == ["internal"] and "public_key" not in listing["items"][0]
    assert c.get("/api/admin/admins").json()["items"][0]["passkey_count"] == 1

    anon = TestClient(app)  # discoverable credential: no email typed
    resp = passkey_login(anon, auth, owner["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["role"] == "ADMIN" and resp.json()["csrf_token"]
    assert read_session(anon)["user_id"] == owner["id"]
    assert anon.get("/api/admin/dashboard").status_code == 200
    assert db_one(app, "SELECT sign_count FROM admin_passkeys WHERE id = ?", (passkey_id,))["sign_count"] == 1

    again = passkey_login(TestClient(app), auth, owner["id"], identifier=ADMIN_EMAIL.upper())  # typed email must match
    assert again.status_code == 200, again.text


def test_passkey_sign_in_rejections(app, owner):
    c = owner["client"]
    auth, _ = add_passkey(c)
    bad = TestClient(app)

    assert passkey_login(bad, auth, owner["id"], identifier="someone@else.com").status_code == 401  # email mismatch
    assert passkey_login(bad, SoftAuthenticator(), owner["id"]).status_code == 401                  # unknown credential
    assert passkey_login(bad, auth, owner["id"], origin="https://evil.example").status_code == 401  # wrong origin
    assert passkey_login(bad, auth, owner["id"] + 1).status_code == 401                              # wrong user handle

    imposter = SoftAuthenticator()
    imposter.cred_id = auth.cred_id  # same credential id, different key -> bad signature
    assert passkey_login(bad, imposter, owner["id"]).status_code == 401
    db_exec(app, "DELETE FROM login_attempts")  # five failures would otherwise lock this client out

    options = api_post(bad, "/api/auth/admin-passkey/options", **hdr()).json()["options"]
    assertion = auth.get(options, owner["id"], counter=5)
    body = {"credential": assertion}
    assert api_post(bad, "/api/auth/admin-passkey/verify", json=body).status_code == 200
    assert api_post(bad, "/api/auth/admin-passkey/verify", json=body).status_code == 401  # challenge is single use
    assert passkey_login(TestClient(app), auth, owner["id"], counter=3).status_code == 401  # counter regression
    assert passkey_login(TestClient(app), auth, owner["id"], counter=6).status_code == 200

    assert api_post(bad, "/api/auth/admin-passkey/verify", json={"credential": {"id": "x"}}).status_code == 401
    assert api_post(TestClient(app), "/api/auth/admin-passkey/verify", json={"credential": assertion}).status_code == 401


def test_passkey_options_only_for_allowed_origins(app, owner):
    for origin in ("https://evil.example", "http://localhost:9999", ""):
        assert api_post(TestClient(app), "/api/auth/admin-passkey/options", **hdr(origin)).status_code == 400
        assert api_post(owner["client"], "/api/admin/passkeys/options", **hdr(origin)).status_code == 400
    ok = api_post(TestClient(app), "/api/auth/admin-passkey/options", **hdr("https://campus-connect-network.vercel.app"))
    options = ok.json()["options"]
    assert ok.status_code == 200 and options["rpId"] == "campus-connect-network.vercel.app"
    assert options.get("allowCredentials") in (None, [])


def test_registration_options_require_discoverable_credentials(app, owner):
    options = api_post(owner["client"], "/api/admin/passkeys/options", **hdr()).json()["options"]
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "preferred"
    assert options["rp"]["id"] == RP_ID and options["user"]["name"] == ADMIN_EMAIL


def test_passkey_registration_rejections(app, owner):
    c = owner["client"]
    auth = SoftAuthenticator()
    options = api_post(c, "/api/admin/passkeys/options", **hdr()).json()["options"]
    wrong_origin = auth.create(options, origin="https://evil.example")
    assert api_post(c, "/api/admin/passkeys/verify", json={"credential": wrong_origin}).status_code == 400
    # the challenge is consumed by the failed attempt
    assert api_post(c, "/api/admin/passkeys/verify", json={"credential": auth.create(options)}).status_code == 400
    assert api_post(c, "/api/admin/passkeys/verify", json={"credential": {"junk": 1}}).status_code == 400
    assert db_count(app, "admin_passkeys") == 0

    add_passkey(c, auth)
    options = api_post(c, "/api/admin/passkeys/options", **hdr()).json()["options"]
    assert unb64(options["excludeCredentials"][0]["id"]) == auth.cred_id
    assert api_post(c, "/api/admin/passkeys/verify", json={"credential": auth.create(options)}).status_code == 400


def test_passkeys_are_per_admin_and_can_be_removed_or_revoked(app, owner):
    body = appoint(owner["client"])
    second = TestClient(app)
    api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": body["temporary_password"]})
    _, mine = add_passkey(owner["client"])
    auth2, theirs = add_passkey(second, label="Phone")

    assert second.get("/api/admin/passkeys").json()["total"] == 1
    assert api_delete(second, f"/api/admin/passkeys/{mine}").status_code == 404   # not theirs
    assert db_count(app, "admin_passkeys") == 2

    # any admin may revoke another admin's passkeys (not the primary's)
    resp = api_delete(owner["client"], f"/api/admin/admins/{body['admin']['id']}/passkeys")
    assert resp.status_code == 200 and resp.json()["removed"] == 1
    assert passkey_login(TestClient(app), auth2, body["admin"]["id"]).status_code == 401
    assert api_delete(owner["client"], f"/api/admin/passkeys/{mine}").status_code == 200
    assert api_delete(owner["client"], f"/api/admin/passkeys/{mine}").status_code == 404
    assert db_count(app, "admin_passkeys") == 0
    assert theirs


def test_passkey_sign_in_requires_an_active_admin(app, owner):
    body = appoint(owner["client"])
    admin_id = body["admin"]["id"]
    second = TestClient(app)
    api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": body["temporary_password"]})
    auth, _ = add_passkey(second)
    assert passkey_login(TestClient(app), auth, admin_id).status_code == 200

    api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": False})
    assert passkey_login(TestClient(app), auth, admin_id).status_code == 401
    api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": True})
    db_exec(app, "UPDATE users SET role = 'STUDENT' WHERE id = ?", (admin_id,))  # no longer an admin
    assert passkey_login(TestClient(app), auth, admin_id).status_code == 401


def test_passkey_failures_are_throttled(app, owner):
    auth, _ = add_passkey(owner["client"])
    c = TestClient(app)
    for _ in range(5):
        assert passkey_login(c, SoftAuthenticator(), owner["id"]).status_code == 401
    assert passkey_login(c, auth, owner["id"]).status_code == 429


def test_at_most_ten_passkeys_per_admin(app, owner):
    for _ in range(10):
        add_passkey(owner["client"])
    resp = api_post(owner["client"], "/api/admin/passkeys/options", **hdr())
    assert resp.status_code == 400


def test_passkey_table_is_cascaded_with_the_user(app, owner):
    add_passkey(owner["client"])
    db_exec(app, "DELETE FROM users WHERE id = ?", (owner["id"],))
    assert db_all(app, "SELECT id FROM admin_passkeys") == []


# ---------------------------------------------------------------- settings / bootstrap

def test_settings_read_primary_admin_and_allowed_origins_from_env(monkeypatch):
    monkeypatch.setenv("PRIMARY_ADMIN_EMAIL", " Boss@Example.com ")
    monkeypatch.setenv("WEBAUTHN_ALLOWED_ORIGINS", "https://a.example/, https://b.example")
    s = Settings.from_env()
    assert s.primary_admin_email == "boss@example.com" and s.is_primary_admin("BOSS@example.com")
    assert s.webauthn_allowed_origins == ("https://a.example", "https://b.example")
    monkeypatch.delenv("PRIMARY_ADMIN_EMAIL")
    monkeypatch.delenv("WEBAUTHN_ALLOWED_ORIGINS")
    s = Settings.from_env()
    assert s.primary_admin_email == "mkkarthik0609@gmail.com"
    assert "https://campus-connect-network.vercel.app" in s.webauthn_allowed_origins


def test_bootstrap_only_creates_the_primary_admin(app, monkeypatch):
    from api.db import db_session
    from services import auth_service
    monkeypatch.setenv("ADMIN_NAME", "Someone")
    monkeypatch.setenv("ADMIN_EMAIL", "someone.else@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    with db_session(app.state.settings):
        with pytest.raises(auth_service.ValidationError):
            auth_service.bootstrap_admin_from_env()
