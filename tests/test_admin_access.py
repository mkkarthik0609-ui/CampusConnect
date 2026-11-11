"""Admin authentication and administrator management (demo model).

* Admins sign in at /api/auth/admin-login with their e-mail + the shared admin ID (ADMIN_ACCESS_ID); no password,
  no e-mailed invitation links. The primary admin is always allowed; every other admin is an e-mail the primary
  admin added, and the account is created on that person's first sign-in.
* Only the primary administrator adds / deactivates / reactivates admins; the primary account is protected.
* Password sign-in (/api/auth/login) still works for accounts that have a real password.
"""
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
ADMIN_ID = "campus-connect-123"
NEW_PASSWORD = "Fresh#Passw0rd9"
SECOND = "second@college.edu"


def admin_login(client, email, admin_id=ADMIN_ID):
    return api_post(client, ADMIN_URL, json={"identifier": email, "admin_id": admin_id})


@pytest.fixture
def owner(app):
    uid = make_admin(app)
    return {"id": uid, "client": login_client(app, ADMIN_EMAIL)}


def add_admin(client, email=SECOND, name="Second Admin"):
    resp = api_post(client, "/api/admin/admin-invitations", json={"email": email, "full_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def appoint(app, owner, email=SECOND):
    """Add an e-mail and sign that admin in once (creates the account). Returns (admin_id, client)."""
    add_admin(owner["client"], email)
    c = TestClient(app)
    assert admin_login(c, email).status_code == 200
    return db_one(app, "SELECT id FROM users WHERE email = ?", (email,))["id"], c


# ---------------------------------------------------------------- admin ID sign-in

def test_primary_admin_signs_in_with_email_and_admin_id_even_without_an_existing_row(app):
    assert db_count(app, "users") == 0  # fresh database: the primary account is created on first sign-in
    resp = admin_login(TestClient(app), ADMIN_EMAIL.upper())
    assert resp.status_code == 200 and resp.json()["user"]["role"] == "ADMIN"
    assert db_one(app, "SELECT role, is_active FROM users WHERE email = ?", (ADMIN_EMAIL,))["is_active"] == 1


def test_existing_admin_signs_in_with_the_id_regardless_of_password(app):
    make_admin(app)
    assert admin_login(TestClient(app), ADMIN_EMAIL).status_code == 200


def test_wrong_id_unknown_email_and_non_admins_are_rejected_generically(app):
    make_admin(app)
    stu = create_student(app, "1AB21CS001")
    fac = create_faculty(app, "FAC001")
    cases = ((ADMIN_EMAIL, "wrong-id"), (ADMIN_EMAIL, PASSWORD), (ADMIN_EMAIL, " "),
             (stu["email"], ADMIN_ID), (fac["email"], ADMIN_ID), ("nobody@example.com", ADMIN_ID))
    for who, admin_id in cases:
        resp = admin_login(TestClient(app), who, admin_id)
        assert resp.status_code == 401, (who, admin_id, resp.text)
        assert resp.json()["error"]["code"] == "invalid_credentials"
    assert db_count(app, "users", "email = 'nobody@example.com'") == 0


def test_admin_id_is_configurable(tmp_path):
    app = create_app(make_settings(tmp_path, admin_access_id="another-id-7"))
    make_admin(app)
    assert admin_login(TestClient(app), ADMIN_EMAIL, ADMIN_ID).status_code == 401
    assert admin_login(TestClient(app), ADMIN_EMAIL, "another-id-7").status_code == 200


def test_the_default_admin_id_and_env_override(monkeypatch):
    assert Settings().admin_access_id == ADMIN_ID
    monkeypatch.setenv("ADMIN_ACCESS_ID", "  from-env-1 ")
    assert Settings.from_env().admin_access_id == "from-env-1"


def test_admin_login_is_throttled(app):
    make_admin(app)
    c = TestClient(app)
    for _ in range(5):
        assert admin_login(c, ADMIN_EMAIL, "wrong").status_code == 401
    assert admin_login(c, ADMIN_EMAIL).status_code == 429


def test_a_stranger_cannot_lock_the_owner_out_from_another_address(tmp_path):
    app = create_app(make_settings(tmp_path, trust_proxy=True, trust_proxy_hops=1))
    make_admin(app)
    attacker = TestClient(app, headers={"X-Forwarded-For": "203.0.113.9"})
    for _ in range(6):
        admin_login(attacker, ADMIN_EMAIL, "guess")
    assert admin_login(attacker, ADMIN_EMAIL).status_code == 429
    owner = TestClient(app, headers={"X-Forwarded-For": "198.51.100.7"})
    assert admin_login(owner, ADMIN_EMAIL).status_code == 200


def test_password_login_still_works_for_accounts_with_a_password(app):
    make_admin(app)
    assert api_post(TestClient(app), "/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200


def test_no_passkey_surface_remains(app, owner):
    for method, url in (("post", "/api/auth/admin-passkey/options"), ("post", "/api/auth/admin-passkey/verify"),
                        ("get", "/api/admin/passkeys"), ("post", "/api/admin/passkeys/options")):
        assert getattr(owner["client"], method)(url).status_code in (404, 405), url
    assert db_all(app, "SELECT 1 FROM pg_tables WHERE tablename = 'admin_passkeys'") == []


# ---------------------------------------------------------------- adding admins (no invitation mail)

def test_primary_adds_an_email_and_that_admin_signs_in_with_the_id(app, owner):
    body = add_admin(owner["client"])
    assert "email_delivery" not in body and "invite_link" not in body
    assert body["invitation"]["status"] == "PENDING"
    assert db_count(app, "users", "email = 'second@college.edu'") == 0  # no account until first sign-in
    # an unregistered e-mail with the right ID is still refused
    assert admin_login(TestClient(app), "stranger@college.edu").status_code == 401
    assert db_count(app, "users", "email = 'stranger@college.edu'") == 0

    second = TestClient(app)
    assert admin_login(second, SECOND).status_code == 200
    admin_id = db_one(app, "SELECT id FROM users WHERE email = ?", (SECOND,))["id"]
    user = db_one(app, "SELECT role, is_active, full_name FROM users WHERE id = ?", (admin_id,))
    assert user["role"] == "ADMIN" and user["is_active"] == 1 and user["full_name"] == "Second Admin"
    assert db_one(app, "SELECT status FROM admin_invitations")["status"] == "ACCEPTED"
    assert second.get("/api/admin/dashboard").status_code == 200
    assert second.get("/api/admin/admins").status_code == 200
    # ...but only the primary adds / manages admins
    assert api_post(second, "/api/admin/admin-invitations", json={"email": "x@college.edu"}).status_code == 403
    assert second.get("/api/admin/admin-invitations").status_code == 403
    # the admin can sign in again
    assert admin_login(TestClient(app), SECOND).status_code == 200


def test_duplicate_and_conflicting_additions_are_refused(app, owner):
    c = owner["client"]
    add_admin(c)
    assert api_post(c, "/api/admin/admin-invitations", json={"email": "SECOND@college.edu"}).status_code == 409  # pending
    assert api_post(c, "/api/admin/admin-invitations", json={"email": ADMIN_EMAIL.upper()}).status_code == 409   # primary
    stu = create_student(app, "1AB21CS005")
    assert api_post(c, "/api/admin/admin-invitations", json={"email": stu["email"]}).status_code == 409         # existing user
    assert api_post(c, "/api/admin/admin-invitations", json={"email": "not-an-email"}).status_code == 400
    assert db_count(app, "admin_invitations", "email = 'second@college.edu'") == 1


def test_expired_registration_cannot_sign_in_until_renewed(app, owner):
    inv_id = add_admin(owner["client"])["invitation"]["id"]
    db_exec(app, "UPDATE admin_invitations SET expires_at = datetime('now', '-1 minute'), "
                 "last_sent_at = datetime('now', '-5 minutes')")
    assert admin_login(TestClient(app), SECOND).status_code == 401
    assert db_count(app, "users", "email = 'second@college.edu'") == 0
    assert owner["client"].get("/api/admin/admin-invitations").json()["items"][0]["status"] == "EXPIRED"
    renewed = api_post(owner["client"], f"/api/admin/admin-invitations/{inv_id}/resend")  # "Resend" now renews
    assert renewed.status_code == 200 and "invite_link" not in renewed.json()
    assert admin_login(TestClient(app), SECOND).status_code == 200


def test_revoked_registration_cannot_sign_in(app, owner):
    inv_id = add_admin(owner["client"])["invitation"]["id"]
    assert api_delete(owner["client"], f"/api/admin/admin-invitations/{inv_id}").status_code == 200
    assert admin_login(TestClient(app), SECOND).status_code == 401
    assert db_count(app, "users", "email = 'second@college.edu'") == 0


def test_public_signup_cannot_claim_an_admin_or_added_address(app, owner):
    from tests.conftest import find_section, http_faculty_signup, http_student_signup
    sec = find_section(app=app)
    c = TestClient(app)
    assert http_student_signup(c, None, ADMIN_EMAIL, "1AB21CS100", sec).status_code == 409
    assert http_faculty_signup(c, "FACX1", extra={"professional_email": ADMIN_EMAIL}).status_code == 409
    add_admin(owner["client"], "pending@college.edu")
    assert http_student_signup(c, None, "pending@college.edu", "1AB21CS101", sec).status_code == 409
    assert db_count(app, "users", "role <> 'ADMIN'") == 0


def test_a_student_who_took_an_expired_address_cannot_become_admin(app, owner):
    from tests.conftest import find_section, http_student_signup
    add_admin(owner["client"], "later@college.edu")
    db_exec(app, "UPDATE admin_invitations SET expires_at = datetime('now', '-1 minute')")
    sec = find_section(app=app)
    assert http_student_signup(TestClient(app), None, "later@college.edu", "1AB21CS151", sec).status_code == 201
    assert admin_login(TestClient(app), "later@college.edu").status_code == 401
    assert db_one(app, "SELECT role FROM users WHERE email = 'later@college.edu'")["role"] != "ADMIN"


# ---------------------------------------------------------------- management of existing admins

def test_primary_admin_is_protected(app, owner):
    admin_id, second = appoint(app, owner)
    for client, expected in ((owner["client"], 400), (second, 403)):  # 400 protected, 403 not the primary
        assert api_post(client, f"/api/admin/admins/{owner['id']}/active", json={"active": False}).status_code == expected
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1
    assert api_post(second, f"/api/admin/admins/{admin_id}/active", json={"active": False}).status_code == 403


def test_primary_admin_is_reactivated_at_startup(app, owner):
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (owner["id"],))
    init_db(app.state.settings)
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (owner["id"],))["is_active"] == 1


def test_deactivated_admin_cannot_sign_in_and_loses_the_session(app, owner):
    admin_id, second = appoint(app, owner)
    resp = api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": False})
    assert resp.status_code == 200 and resp.json()["admin"]["is_active"] is False
    assert second.get("/api/admin/dashboard").status_code == 401  # existing session ended
    assert admin_login(TestClient(app), SECOND).status_code == 401
    assert api_post(owner["client"], f"/api/admin/admins/{admin_id}/active", json={"active": True}).status_code == 200
    assert admin_login(TestClient(app), SECOND).status_code == 200
    audit = [r["action"] for r in db_all(app, "SELECT action FROM audit_log ORDER BY id")]
    assert "admin.deactivate" in audit and "admin.activate" in audit and "admin_invite.create" in audit


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
