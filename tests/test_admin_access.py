"""Admin authentication and administrator management.

* Password sign-in is always real (never an "any password" shortcut); no passkeys / passwordless flows exist.
* Only the primary administrator appoints admins, through single-use expiring invitations whose token is
  stored hashed; invitees choose their own password.
* The primary admin is protected from deactivation; sessions end on deactivation and password change.
"""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from api.db import init_db
from api.main import create_app
from api.settings import Settings
from tests.conftest import (
    ADMIN_EMAIL, PASSWORD, api_delete, api_post, create_faculty, create_student, db_all, db_count, db_exec, db_one,
    login_client, make_admin, make_settings,
)

ADMIN_URL = "/api/auth/admin-login"
NEW_PASSWORD = "Fresh#Passw0rd9"


@pytest.fixture
def owner(app):
    uid = make_admin(app)
    return {"id": uid, "client": login_client(app, ADMIN_EMAIL)}


def token_of(link):
    assert link and "#t=" in link
    return link.split("#t=", 1)[1]


def invite(client, email="second@college.edu", name="Second Admin"):
    resp = api_post(client, "/api/admin/admin-invitations", json={"email": email, "full_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def accept(app, token, password=NEW_PASSWORD, name="Second Admin", confirm=None):
    return api_post(TestClient(app), "/api/auth/admin-invite/accept", json={
        "token": token, "full_name": name, "password": password,
        "confirm_password": password if confirm is None else confirm})


def appoint(app, owner, email="second@college.edu", password=NEW_PASSWORD):
    """Full flow: invite -> accept. Returns (admin_id, password)."""
    body = invite(owner["client"], email)
    assert accept(app, token_of(body["invite_link"]), password).status_code == 201
    return db_one(app, "SELECT id FROM users WHERE email = ?", (email,))["id"], password


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


def test_no_passkey_or_passwordless_surface_remains(app, owner):
    for method, url in (("post", "/api/auth/admin-passkey/options"), ("post", "/api/auth/admin-passkey/verify"),
                        ("get", "/api/admin/passkeys"), ("post", "/api/admin/passkeys/options")):
        assert getattr(owner["client"], method)(url).status_code in (404, 405), url
    assert not hasattr(Settings(), "webauthn_allowed_origins")
    assert db_all(app, "SELECT 1 FROM pg_tables WHERE tablename = 'admin_passkeys'") == []


def test_admin_login_is_throttled(app):
    make_admin(app)
    c = TestClient(app)
    for _ in range(5):
        assert api_post(c, ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": "wrong"}).status_code == 401
    assert api_post(c, ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 429


def test_password_hashes_are_argon2id_and_legacy_hashes_upgrade_on_login(app):
    from werkzeug.security import generate_password_hash
    make_admin(app)
    assert db_one(app, "SELECT password_hash FROM users WHERE email = ?", (ADMIN_EMAIL,))["password_hash"].startswith("$argon2id$")
    db_exec(app, "UPDATE users SET password_hash = ? WHERE email = ?",
            (generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000"), ADMIN_EMAIL))
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    assert db_one(app, "SELECT password_hash FROM users WHERE email = ?", (ADMIN_EMAIL,))["password_hash"].startswith("$argon2id$")
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200


# ---------------------------------------------------------------- invitations

def test_primary_invites_and_invitee_creates_own_password(app, owner):
    body = invite(owner["client"])
    token = token_of(body["invite_link"])
    # No mail provider is configured in tests: the API must say so, never claim delivery.
    assert body["email_delivery"] == "NOT_CONFIGURED" and "not configured" in body["message"].lower()
    assert body["invitation"]["status"] == "PENDING" and body["invitation"]["delivery_status"] == "NOT_CONFIGURED"
    # Only the hash of the token is stored; the account does not exist until the password is set.
    row = db_one(app, "SELECT token_hash FROM admin_invitations")
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest() and token not in json.dumps(row)
    assert db_count(app, "users", "email = 'second@college.edu'") == 0
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": "x"}).status_code == 401

    c = TestClient(app)
    info = api_post(c, "/api/auth/admin-invite/inspect", json={"token": token})
    assert info.status_code == 200 and info.json()["email"] == "second@college.edu"
    assert info.headers["cache-control"] == "no-store"
    assert accept(app, token).status_code == 201
    user = db_one(app, "SELECT role, is_active, password_hash FROM users WHERE email = 'second@college.edu'")
    assert user["role"] == "ADMIN" and user["is_active"] == 1 and user["password_hash"].startswith("$argon2id$")
    # single use
    assert accept(app, token, "Another#Passw0rd1").status_code == 400
    assert api_post(c, "/api/auth/admin-invite/inspect", json={"token": token}).status_code == 400
    assert db_one(app, "SELECT status FROM admin_invitations")["status"] == "ACCEPTED"

    second = TestClient(app)
    assert api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": NEW_PASSWORD}).status_code == 200
    assert second.get("/api/admin/dashboard").status_code == 200
    assert second.get("/api/admin/admins").status_code == 200  # may read the list
    # ...but only the primary appoints / manages admins
    assert api_post(second, "/api/admin/admin-invitations", json={"email": "x@college.edu"}).status_code == 403
    assert second.get("/api/admin/admin-invitations").status_code == 403


def test_invitation_tokens_never_appear_in_logs_or_listings(app, owner, caplog):
    caplog.set_level("DEBUG")
    body = invite(owner["client"])
    token = token_of(body["invite_link"])
    listing = json.dumps(owner["client"].get("/api/admin/admin-invitations").json())
    assert token not in listing and "invite_link" not in listing and "token_hash" not in listing
    accept(app, token)
    assert token not in caplog.text


def test_duplicate_and_conflicting_invitations_are_refused(app, owner):
    c = owner["client"]
    invite(c)
    assert api_post(c, "/api/admin/admin-invitations", json={"email": "SECOND@college.edu"}).status_code == 409  # pending
    assert api_post(c, "/api/admin/admin-invitations", json={"email": ADMIN_EMAIL.upper()}).status_code == 409   # primary
    stu = create_student(app, "1AB21CS005")
    assert api_post(c, "/api/admin/admin-invitations", json={"email": stu["email"]}).status_code == 409         # existing user
    assert api_post(c, "/api/admin/admin-invitations", json={"email": "not-an-email"}).status_code == 400
    assert db_count(app, "admin_invitations", "email = 'second@college.edu'") == 1


def test_invitation_expires(app, owner):
    token = token_of(invite(owner["client"])["invite_link"])
    db_exec(app, "UPDATE admin_invitations SET expires_at = datetime('now', '-1 minute')")
    assert api_post(TestClient(app), "/api/auth/admin-invite/inspect", json={"token": token}).status_code == 400
    assert accept(app, token).status_code == 400
    assert db_count(app, "users", "email = 'second@college.edu'") == 0
    listed = owner["client"].get("/api/admin/admin-invitations").json()["items"]
    assert listed[0]["status"] == "EXPIRED"
    # an expired invitation does not block a fresh one for the same address
    assert api_post(owner["client"], "/api/admin/admin-invitations", json={"email": "second@college.edu"}).status_code == 201


def test_resend_rotates_the_token_and_revoke_kills_it(app, owner):
    c = owner["client"]
    first = invite(c)
    old = token_of(first["invite_link"])
    inv_id = first["invitation"]["id"]
    assert api_post(c, f"/api/admin/admin-invitations/{inv_id}/resend").status_code == 400  # 60 s cooldown
    db_exec(app, "UPDATE admin_invitations SET last_sent_at = datetime('now', '-5 minutes')")
    resent = api_post(c, f"/api/admin/admin-invitations/{inv_id}/resend")
    assert resent.status_code == 200 and resent.json()["invitation"]["send_count"] == 2
    new = token_of(resent.json()["invite_link"])
    assert new != old
    assert accept(app, old).status_code == 400          # the previously issued link is dead
    assert api_delete(c, f"/api/admin/admin-invitations/{inv_id}").status_code == 200
    assert accept(app, new).status_code == 400          # revoked
    assert api_post(c, f"/api/admin/admin-invitations/{inv_id}/resend").status_code == 400
    assert api_delete(c, f"/api/admin/admin-invitations/{inv_id}").status_code == 400
    assert db_count(app, "users", "email = 'second@college.edu'") == 0
    assert api_post(c, "/api/admin/admin-invitations", json={"email": "second@college.edu"}).status_code == 201


def test_accepting_validates_password_and_does_not_burn_the_token(app, owner):
    token = token_of(invite(owner["client"])["invite_link"])
    assert accept(app, token, "weak").status_code == 400
    assert accept(app, token, NEW_PASSWORD, confirm="Different#Passw0rd2").status_code == 400
    assert accept(app, token, "second@college.edu").status_code == 400  # may not equal the email
    assert db_one(app, "SELECT status FROM admin_invitations")["status"] == "PENDING"
    assert accept(app, token).status_code == 201


def test_two_simultaneous_acceptances_create_one_account(app, owner):
    import threading
    token = token_of(invite(owner["client"])["invite_link"])
    results = []

    def go(pw):
        results.append(accept(app, token, pw).status_code)

    threads = [threading.Thread(target=go, args=(p,)) for p in (NEW_PASSWORD, "Other#Passw0rd7", "Third#Passw0rd8")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [201, 400, 400]
    assert db_count(app, "users", "email = 'second@college.edu'") == 1


def test_garbage_tokens_are_rejected_and_throttled(app):
    c = TestClient(app)
    for bad in ("", "x", "a" * 43, "../../etc/passwd", "a" * 500):
        assert api_post(c, "/api/auth/admin-invite/inspect", json={"token": bad}).status_code in (400, 429)
    for _ in range(25):
        api_post(c, "/api/auth/admin-invite/inspect", json={"token": "z" * 43})
    assert api_post(c, "/api/auth/admin-invite/inspect", json={"token": "y" * 43}).status_code == 429


def test_public_signup_cannot_claim_an_admin_or_invited_address(app, owner):
    from tests.conftest import find_section, http_faculty_signup, http_student_signup
    sec = find_section(app=app)
    c = TestClient(app)
    assert http_student_signup(c, None, ADMIN_EMAIL, "1AB21CS100", sec).status_code == 409
    assert http_faculty_signup(c, "FACX1", extra={"professional_email": ADMIN_EMAIL}).status_code == 409
    invite(owner["client"], "pending@college.edu")
    assert http_student_signup(c, None, "pending@college.edu", "1AB21CS101", sec).status_code == 409
    assert db_count(app, "users", "role <> 'ADMIN'") == 0


# ---------------------------------------------------------------- management of existing admins

def test_primary_admin_is_protected(app, owner):
    admin_id, pw = appoint(app, owner)
    second = TestClient(app)
    api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": pw})
    for client, expected in ((owner["client"], 400), (second, 403)):  # 400 protected, 403 not the primary
        assert api_post(client, f"/api/admin/admins/{owner['id']}/active", json={"active": False}).status_code == expected
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1
    assert api_post(second, f"/api/admin/admins/{admin_id}/active", json={"active": False}).status_code == 403


def test_primary_admin_is_reactivated_at_startup(app, owner):
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (owner["id"],))
    init_db(app.state.settings)
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1


def test_deactivated_admin_cannot_sign_in_and_loses_the_session(app, owner):
    admin_id, pw = appoint(app, owner)
    second = TestClient(app)
    assert api_post(second, ADMIN_URL, json={"identifier": "second@college.edu", "password": pw}).status_code == 200
    resp = api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": False})
    assert resp.status_code == 200 and resp.json()["admin"]["is_active"] is False
    assert second.get("/api/admin/dashboard").status_code == 401  # existing session ended
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": pw}).status_code == 401
    assert api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": True}).status_code == 200
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": "second@college.edu", "password": pw}).status_code == 200
    audit = [r["action"] for r in db_all(app, "SELECT action FROM audit_log ORDER BY id")]
    assert "admin.deactivate" in audit and "admin.activate" in audit and "admin_invite.accept" in audit


def test_admin_cannot_be_deleted_or_have_role_changed_through_the_api(app, owner):
    admin_id, _ = appoint(app, owner)
    for method, url in (("delete", f"/api/admin/admins/{admin_id}"), ("patch", f"/api/admin/admins/{admin_id}"),
                        ("put", f"/api/admin/admins/{owner['id']}"), ("post", f"/api/admin/admins/{owner['id']}/role")):
        r = getattr(owner["client"], method)(url)
        assert r.status_code in (403, 404, 405), (method, url, r.status_code)
    assert db_one(app, "SELECT role FROM users WHERE id = ?", (owner["id"],))["role"] == "ADMIN"


def test_admin_management_requires_an_admin(app, owner):
    stu = create_student(app, "1AB21CS002")
    sc = login_client(app, stu["email"])
    assert api_post(sc, "/api/admin/admin-invitations", json={"email": "a@b.co"}).status_code == 403
    assert api_post(sc, f"/api/admin/admins/{owner['id']}/active", json={"active": True}).status_code == 403
    assert TestClient(app).get("/api/admin/admin-invitations").status_code == 401
    assert api_post(TestClient(app), "/api/admin/admin-invitations", json={"email": "a@b.co"}).status_code in (400, 401)


# ---------------------------------------------------------------- sessions and password change

def test_password_change_revokes_other_sessions_but_keeps_this_one(app):
    make_admin(app)
    a, b = login_client(app, ADMIN_EMAIL), login_client(app, ADMIN_EMAIL)
    r = api_post(a, "/api/account/password", json={
        "current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert r.status_code == 200
    assert a.get("/api/admin/dashboard").status_code == 200   # the device that changed it stays signed in
    assert b.get("/api/admin/dashboard").status_code == 401   # every other session is gone
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 401
    assert api_post(TestClient(app), ADMIN_URL, json={"identifier": ADMIN_EMAIL, "password": NEW_PASSWORD}).status_code == 200
    assert "account.password_change" in [r["action"] for r in db_all(app, "SELECT action FROM audit_log")]


# ---------------------------------------------------------------- settings / bootstrap

def test_settings_read_primary_admin_from_env(monkeypatch):
    monkeypatch.setenv("PRIMARY_ADMIN_EMAIL", " Boss@Example.com ")
    s = Settings.from_env()
    assert s.primary_admin_email == "boss@example.com" and s.is_primary_admin("BOSS@example.com")
    monkeypatch.delenv("PRIMARY_ADMIN_EMAIL")
    assert Settings.from_env().primary_admin_email == "mkkarthik0609@gmail.com"


def test_bootstrap_only_creates_the_primary_admin(app, monkeypatch):
    from api.db import db_session
    from services import auth_service
    monkeypatch.setenv("ADMIN_NAME", "Someone")
    monkeypatch.setenv("ADMIN_EMAIL", "someone.else@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    with db_session(app.state.settings):
        with pytest.raises(auth_service.ValidationError):
            auth_service.bootstrap_admin_from_env()
    assert db_count(app, "users") == 0


def test_bootstrap_never_overwrites_an_existing_primary_password(app, monkeypatch):
    from api.db import db_session
    from services import auth_service
    make_admin(app)
    before = db_one(app, "SELECT password_hash FROM users WHERE email = ?", (ADMIN_EMAIL,))["password_hash"]
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", "Different@1234")
    with db_session(app.state.settings):
        assert auth_service.bootstrap_admin_from_env() == "exists"
    assert db_one(app, "SELECT password_hash FROM users WHERE email = ?", (ADMIN_EMAIL,))["password_hash"] == before
