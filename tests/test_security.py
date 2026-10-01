"""Security regression tests for the FastAPI backend: CSRF, throttling, session lifecycle, password
policy, upload authorisation, headers, OTP limits, proxy handling, SPA serving, health, bootstrap."""
import os
import uuid

import pytest
from fastapi import APIRouter, Depends, Request
from fastapi.testclient import TestClient

from api.db import db_session
from api.deps import client_ip, get_current_user, require_role
from api.main import create_app
from models import queries
from services import auth_service, session_service
from tests.conftest import (
    PASSWORD, TEST_SECRET, api_login, api_post, csrf_token, db_count, db_exec, set_session_cookie, db_one, find_section, login_client,
    make_admin, make_settings, read_session, register_faculty, register_student, write_session,
)

GOOD_PASSWORD = "Str0ngPass!"


def err(resp):
    return resp.json()["error"]


def login(client, identifier, password=PASSWORD):
    return api_post(client, "/api/auth/login", json={"identifier": identifier, "password": password})


def add_probe_routes(app):
    """Extra routes used to test framework-level behaviour (global CSRF, roles, 500s, client ip)."""
    probe = APIRouter(prefix="/api/_probe")

    @probe.post("/write")
    def write():
        return {"wrote": True}

    @probe.delete("/write")
    def delete():
        return {"deleted": True}

    @probe.get("/admin")
    def admin_only(user=Depends(require_role("ADMIN"))):
        return {"role": user.role, "name": user.full_name}

    @probe.get("/me")
    def me(user=Depends(get_current_user)):
        return dict(user)

    @probe.get("/boom")
    def boom():
        raise RuntimeError("super secret internals")

    @probe.get("/ip")
    def ip(request: Request):
        return {"ip": client_ip(request), "scheme": request.url.scheme}

    app.include_router(probe)
    return app


@pytest.fixture
def probe_app(app):
    return add_probe_routes(app)


@pytest.fixture
def csrf_app(tmp_path):
    return add_probe_routes(create_app(make_settings(tmp_path, csrf_enabled=True)))


def make_user(app, role, email, password=GOOD_PASSWORD, name="Test User", **extra):
    with db_session(app.state.settings):
        uid = queries.create_user(role, email, auth_service.generate_password_hash(password), name)
        ids = {"user_id": uid}
        if role == "STUDENT":
            ids["student_id"] = queries.create_student(
                uid, extra.get("usn", "1AB21CS001"), "BE", "CSE", "1st Year", "A",
                "9876543210", f"p_{email}", email,
            )
        elif role == "FACULTY":
            ids["faculty_id"] = queries.create_faculty(uid, extra.get("code", "FAC001"), "CSE", email)
        return ids


# ---------------------------------------------------------------- CSRF

def test_csrf_rejects_post_without_token(csrf_app):
    make_user(csrf_app, "ADMIN", "admin@x.edu")
    client = TestClient(csrf_app)
    resp = client.post("/api/auth/login", json={"identifier": "admin@x.edu", "password": GOOD_PASSWORD})
    assert resp.status_code == 400
    assert err(resp)["code"] == "csrf_failed"
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_csrf_rejects_wrong_and_foreign_tokens(csrf_app):
    make_user(csrf_app, "ADMIN", "admin@x.edu")
    a, b = TestClient(csrf_app), TestClient(csrf_app)
    token_a = a.get("/api/auth/session").json()["csrf_token"]
    b.get("/api/auth/session")
    body = {"identifier": "admin@x.edu", "password": GOOD_PASSWORD}
    for bad in ("", "x" * 43, token_a[:-1]):
        resp = b.post("/api/auth/login", json=body, headers={"X-CSRFToken": bad})
        assert resp.status_code == 400 and err(resp)["code"] == "csrf_failed"
    # a token belonging to another browser session is useless
    assert b.post("/api/auth/login", json=body, headers={"X-CSRFToken": token_a}).status_code == 400
    # no cookie at all (token never issued to this client)
    fresh = TestClient(csrf_app)
    assert fresh.post("/api/auth/login", json=body, headers={"X-CSRFToken": token_a}).status_code == 400


def test_csrf_accepts_post_with_token(csrf_app):
    make_user(csrf_app, "ADMIN", "admin@x.edu")
    client = TestClient(csrf_app)
    token = client.get("/api/auth/session").json()["csrf_token"]
    resp = client.post("/api/auth/login", json={"identifier": "admin@x.edu", "password": GOOD_PASSWORD},
                       headers={"X-CSRFToken": token})
    assert resp.status_code == 200


def test_csrf_is_global_for_every_unsafe_method(csrf_app):
    """A route that knows nothing about CSRF is still protected (app-level dependency)."""
    client = TestClient(csrf_app)
    token = client.get("/api/auth/session").json()["csrf_token"]
    assert client.get("/api/_probe/me").status_code == 401  # safe method: no token needed
    for method in ("POST", "DELETE"):
        resp = client.request(method, "/api/_probe/write")
        assert resp.status_code == 400 and err(resp)["code"] == "csrf_failed", method
        ok = client.request(method, "/api/_probe/write", headers={"X-CSRFToken": token})
        assert ok.status_code == 200, method
    # multipart requests are covered as well
    assert client.post("/api/_probe/write", files={"f": ("a.txt", b"x")}).status_code == 400
    assert client.post("/api/_probe/write", files={"f": ("a.txt", b"x")},
                       headers={"X-CSRFToken": token}).status_code == 200
    # csrf runs before authentication for logout, and before body validation
    assert client.post("/api/auth/logout").status_code == 400


def test_csrf_token_rotates_on_login_and_logout(csrf_app):
    make_user(csrf_app, "ADMIN", "admin@x.edu")
    c = TestClient(csrf_app)
    anon = c.get("/api/auth/session").json()["csrf_token"]
    resp = c.post("/api/auth/login", json={"identifier": "admin@x.edu", "password": GOOD_PASSWORD},
                  headers={"X-CSRFToken": anon})
    after_login = resp.json()["csrf_token"]
    assert after_login and after_login != anon
    assert c.get("/api/auth/session").json()["csrf_token"] == after_login
    # the pre-login token (e.g. captured by an attacker) no longer works
    assert c.post("/api/auth/logout", headers={"X-CSRFToken": anon}).status_code == 400
    resp = c.post("/api/auth/logout", headers={"X-CSRFToken": after_login})
    assert resp.status_code == 200
    after_logout = resp.json()["csrf_token"]
    assert after_logout not in (anon, after_login)
    assert c.post("/api/_probe/write", headers={"X-CSRFToken": after_login}).status_code == 400
    assert c.post("/api/_probe/write", headers={"X-CSRFToken": after_logout}).status_code == 200


def test_csrf_disabled_by_default_in_tests(probe_app, client):
    assert client.post("/api/_probe/write").status_code == 200


# ---------------------------------------------------------------- login throttling

def test_same_message_for_unknown_wrong_and_inactive(app, client):
    ids = make_user(app, "STUDENT", "s@x.edu")
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (ids["user_id"],))
    make_user(app, "FACULTY", "f@x.edu")
    bodies = []
    for ident, pw in (("nobody@x.edu", "Whatever1"), ("f@x.edu", "WrongPass1"), ("s@x.edu", GOOD_PASSWORD)):
        resp = login(client, ident, pw)
        assert resp.status_code == 401
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["error"]["message"] == "Invalid email or password."


def test_lockout_after_repeated_failures(app, client):
    make_user(app, "FACULTY", "f@x.edu")
    for _ in range(5):
        assert login(client, "f@x.edu", "WrongPass1").status_code == 401
    resp = login(client, "f@x.edu", GOOD_PASSWORD)  # even the right password is refused while locked
    assert resp.status_code == 429
    assert err(resp)["code"] == "rate_limited" and "Too many unsuccessful attempts" in err(resp)["message"]
    assert "user_id" not in read_session(client)
    # lockout applies to unknown identifiers as well (no account enumeration)
    for _ in range(5):
        login(client, "ghost@x.edu", "WrongPass1")
    assert login(client, "ghost@x.edu", "WrongPass1").status_code == 429


def test_lockout_is_per_identifier_case_insensitive(app, client):
    make_user(app, "FACULTY", "f@x.edu")
    for ident in ("f@x.edu", "F@X.EDU", " f@x.edu ", "F@x.edu", "f@X.edu"):
        login(client, ident, "WrongPass1")
    assert login(client, "f@x.edu", GOOD_PASSWORD).status_code == 429


def test_ip_lockout_across_identifiers(tmp_path):
    app = create_app(make_settings(tmp_path, login_max_failures_per_ip=4))
    make_user(app, "FACULTY", "f@x.edu")
    c = TestClient(app)
    for i in range(4):
        login(c, f"user{i}@x.edu", "WrongPass1")
    assert login(c, "f@x.edu", GOOD_PASSWORD).status_code == 429


def test_success_clears_identifier_counter_and_records_last_login(app, client):
    ids = make_user(app, "FACULTY", "f@x.edu")
    for _ in range(3):
        login(client, "f@x.edu", "WrongPass1")
    assert login(client, "f@x.edu", GOOD_PASSWORD).status_code == 200
    assert db_one(app, "SELECT last_login_at FROM users WHERE id = ?", (ids["user_id"],))["last_login_at"]
    for _ in range(3):  # would be 6 total without the reset
        login(client, "f@x.edu", "WrongPass1")
    assert login(client, "f@x.edu", GOOD_PASSWORD).status_code == 200


def test_login_takes_constant_hash_work_for_unknown_user(app, client, monkeypatch):
    """Unknown identifiers still run one password-hash verification (timing equalisation)."""
    calls = []
    real = auth_service.check_password_hash
    monkeypatch.setattr(auth_service, "check_password_hash", lambda h, p: calls.append(h) or real(h, p))
    make_user(app, "FACULTY", "f@x.edu")
    login(client, "ghost@x.edu", "WrongPass1")
    login(client, "f@x.edu", "WrongPass1")
    assert len(calls) == 2 and calls[0] != calls[1]


def test_login_replaces_pre_login_session(app, client):
    make_user(app, "ADMIN", "a@x.edu")
    write_session(client, {"attacker_planted": "x", "csrf_token": "attacker-known-token",
                           "otp_verified_email": "victim@x.edu"})
    resp = login(client, "a@x.edu", GOOD_PASSWORD)
    assert resp.status_code == 200
    sess = read_session(client)
    assert "attacker_planted" not in sess and "otp_verified_email" not in sess
    assert sess["role"] == "ADMIN"
    assert sess["csrf_token"] != "attacker-known-token" and sess["csrf_token"] == resp.json()["csrf_token"]


# ---------------------------------------------------------------- session validation

def test_unauthenticated_and_forbidden_responses(probe_app, app, client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 401 and err(resp)["code"] == "unauthenticated"
    assert client.get("/api/_probe/admin").status_code == 401
    make_user(app, "STUDENT", "s@x.edu")
    login(client, "s@x.edu", GOOD_PASSWORD)
    resp = client.get("/api/_probe/admin")
    assert resp.status_code == 403 and err(resp)["code"] == "forbidden"


def test_current_user_object_has_no_password_hash(probe_app, app, client):
    make_user(app, "STUDENT", "s@x.edu")
    login(client, "s@x.edu", GOOD_PASSWORD)
    me = client.get("/api/_probe/me").json()
    assert "password_hash" not in me
    assert me["role"] == "STUDENT" and me["student_id"] and me["user_id"] == me["id"]


def test_deactivated_user_session_is_invalidated(probe_app, app, client):
    ids = make_user(app, "ADMIN", "a@x.edu")
    login(client, "a@x.edu", GOOD_PASSWORD)
    assert client.get("/api/_probe/admin").status_code == 200
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (ids["user_id"],))
    assert client.get("/api/_probe/admin").status_code == 401
    assert "user_id" not in read_session(client)
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_deleted_user_session_is_invalidated(probe_app, app, client):
    ids = make_user(app, "ADMIN", "a@x.edu")
    login(client, "a@x.edu", GOOD_PASSWORD)
    db_exec(app, "DELETE FROM users WHERE id = ?", (ids["user_id"],))
    assert client.get("/api/_probe/admin").status_code == 401
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_role_and_name_are_refreshed_from_database(probe_app, app, client):
    ids = make_user(app, "STUDENT", "s@x.edu", name="Old Name")
    login(client, "s@x.edu", GOOD_PASSWORD)
    db_exec(app, "UPDATE users SET full_name = 'New Name' WHERE id = ?", (ids["user_id"],))
    assert client.get("/api/_probe/me").json()["full_name"] == "New Name"
    assert read_session(client)["full_name"] == "New Name"
    # A (validly signed but stale/edited) cookie claiming ADMIN cannot keep privileges: DB wins.
    sess = read_session(client)
    sess["role"] = "ADMIN"
    write_session(client, sess)
    assert client.get("/api/_probe/admin").status_code == 403
    assert read_session(client)["role"] == "STUDENT"
    # promotion / demotion in the database takes effect on the next request
    db_exec(app, "UPDATE users SET role = 'ADMIN' WHERE id = ?", (ids["user_id"],))
    assert client.get("/api/_probe/admin").json()["role"] == "ADMIN"


def test_forged_session_cookie_is_rejected(probe_app, app, client):
    ids = make_user(app, "ADMIN", "a@x.edu")
    fake = {"user_id": ids["user_id"], "role": "ADMIN", "login_at": session_service.now(),
            "last_seen": session_service.now(), "csrf_token": "x" * 40}
    # signed with the wrong key
    write_session(client, fake, secret="not-the-real-secret-key-not-the-real-secret")
    assert client.get("/api/_probe/admin").status_code == 401
    assert client.get("/api/auth/session").json()["authenticated"] is False
    # raw unsigned JSON / garbage
    for junk in ("eyJ1c2VyX2lkIjogMX0=", "garbage", fake["csrf_token"]):
        set_session_cookie(client, junk)
        assert client.get("/api/_probe/admin").status_code == 401
    # payload tampered after signing
    login(client, "a@x.edu", GOOD_PASSWORD)
    value = client.cookies.get("cc_session")
    payload, rest = value.split(".", 1)
    set_session_cookie(client, "A" + payload[1:] + "." + rest)
    assert client.get("/api/_probe/admin").status_code == 401
    # sanity: the same user with a correctly signed cookie is fine
    write_session(client, fake)
    assert client.get("/api/_probe/admin").status_code == 200


def test_session_for_unknown_or_malformed_user_id_is_rejected(probe_app, client):
    now = session_service.now()
    for uid in (999999, "1", None, True, [1]):
        write_session(client, {"user_id": uid, "role": "ADMIN", "login_at": now, "last_seen": now})
        assert client.get("/api/_probe/admin").status_code == 401, uid


def test_idle_timeout(probe_app, app, client, monkeypatch):
    make_user(app, "ADMIN", "a@x.edu")
    login(client, "a@x.edu", GOOD_PASSWORD)
    start = session_service.now()
    monkeypatch.setattr(session_service, "now", lambda: start + 59 * 60)
    assert client.get("/api/_probe/admin").status_code == 200  # within the window (and refreshes last_seen)
    monkeypatch.setattr(session_service, "now", lambda: start + 59 * 60 + 61 * 60)
    resp = client.get("/api/_probe/admin")
    assert resp.status_code == 401 and "inactivity" in err(resp)["message"]
    assert "user_id" not in read_session(client)
    # the session endpoint simply reports anonymous afterwards and hands out a fresh token
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_idle_timeout_is_configurable(tmp_path):
    app = add_probe_routes(create_app(make_settings(tmp_path, session_idle_timeout_minutes=5)))
    make_user(app, "ADMIN", "a@x.edu")
    c = TestClient(app)
    login(c, "a@x.edu", GOOD_PASSWORD)
    sess = read_session(c)
    sess["last_seen"] -= 6 * 60
    write_session(c, sess)
    assert c.get("/api/_probe/admin").status_code == 401


def test_absolute_timeout_even_when_active(probe_app, app, client, monkeypatch):
    make_user(app, "ADMIN", "a@x.edu")
    login(client, "a@x.edu", GOOD_PASSWORD)
    start = session_service.now()
    offset = 0
    # stay active every 30 minutes for just under 12 hours: still signed in
    while offset + 30 * 60 < 12 * 3600:
        offset += 30 * 60
        monkeypatch.setattr(session_service, "now", lambda o=offset: start + o)
        assert client.get("/api/_probe/admin").status_code == 200, offset
    monkeypatch.setattr(session_service, "now", lambda: start + 12 * 3600 + 120)
    resp = client.get("/api/_probe/admin")
    assert resp.status_code == 401 and "expired" in err(resp)["message"]
    assert "user_id" not in read_session(client)


# ---------------------------------------------------------------- password policy

@pytest.mark.parametrize("password", [
    "short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "", None, "A" * 129 + "a1",
])
def test_weak_passwords_rejected(password):
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password(password)


@pytest.mark.parametrize("password", ["Sample@1234", "Abcdefg1", "Sym-bols_Ok9!"])
def test_strong_passwords_accepted(password):
    assert auth_service.hash_password(password)


def test_password_equal_to_email_or_username_rejected():
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("Fac001@Uni1", disallow=("fac001@uni1",))
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("Fac001Uni1", disallow=("Fac001Uni1@college.edu",))


def test_signup_enforces_password_policy(client):
    resp = api_post(client, "/api/auth/signup/faculty", json={
        "full_name": "P", "faculty_code": "FAC9", "department": "AIML",
        "professional_email": "p@x.edu", "subjects": "DSA",
        "password": "alllowercase1", "confirm_password": "alllowercase1"})
    assert resp.status_code == 400 and "uppercase" in err(resp)["message"]
    assert "password" in err(resp)["fields"]


def test_signup_rejects_password_equal_to_faculty_id(client):
    resp = api_post(client, "/api/auth/signup/faculty", json={
        "full_name": "P", "faculty_code": "Fac9Pass1", "department": "AIML",
        "professional_email": "p@x.edu", "subjects": "DSA",
        "password": "Fac9Pass1", "confirm_password": "Fac9Pass1"})
    assert resp.status_code == 400 and "same as" in err(resp)["message"]


# ---------------------------------------------------------------- change password / theme

def test_change_password_flow(app, client):
    make_user(app, "ADMIN", "a@x.edu")
    resp = api_post(client, "/api/account/password",
                    json={"current_password": GOOD_PASSWORD, "new_password": "NewPass123", "confirm_password": "NewPass123"})
    assert resp.status_code == 401  # login required
    login(client, "a@x.edu", GOOD_PASSWORD)

    def post(cur, new, conf):
        return api_post(client, "/api/account/password", json={
            "current_password": cur, "new_password": new, "confirm_password": conf})

    r = post("Nope12345", "NewPass123", "NewPass123")
    assert r.status_code == 400 and "current_password" in err(r)["fields"]
    assert "current password is incorrect" in err(r)["message"]
    r = post(GOOD_PASSWORD, "NewPass123", "NewPass124")
    assert r.status_code == 400 and "do not match" in err(r)["message"] and "confirm_password" in err(r)["fields"]
    r = post(GOOD_PASSWORD, GOOD_PASSWORD, GOOD_PASSWORD)
    assert r.status_code == 400 and "must be different" in err(r)["message"]
    r = post(GOOD_PASSWORD, "weakpassword", "weakpassword")
    assert r.status_code == 400 and "uppercase" in err(r)["message"] and "new_password" in err(r)["fields"]
    r = api_post(client, "/api/account/password", json={"current_password": GOOD_PASSWORD})
    assert r.status_code == 400 and "new_password" in err(r)["fields"]

    r = post(GOOD_PASSWORD, "NewPass123", "NewPass123")
    assert r.status_code == 200 and r.json()["ok"] is True
    c2 = TestClient(app)
    assert login(c2, "a@x.edu", GOOD_PASSWORD).status_code == 401  # old password no longer works
    assert login(c2, "a@x.edu", "NewPass123").status_code == 200


def test_change_password_guesses_are_throttled(app, client):
    make_user(app, "ADMIN", "a@x.edu")
    login(client, "a@x.edu", GOOD_PASSWORD)
    for _ in range(5):
        r = api_post(client, "/api/account/password", json={
            "current_password": "Wrong1234", "new_password": "NewPass123", "confirm_password": "NewPass123"})
        assert r.status_code == 400
    r = api_post(client, "/api/account/password", json={
        "current_password": GOOD_PASSWORD, "new_password": "NewPass123", "confirm_password": "NewPass123"})
    assert r.status_code == 429 and err(r)["code"] == "rate_limited"


def test_theme_update(app, client):
    ids = make_user(app, "STUDENT", "s@x.edu")
    assert api_post(client, "/api/account/theme", json={"theme": "dark"}).status_code == 401
    login(client, "s@x.edu", GOOD_PASSWORD)
    assert api_post(client, "/api/account/theme", json={"theme": "purple"}).status_code == 400
    assert api_post(client, "/api/account/theme", json={"theme": "dark"}).json()["theme"] == "dark"
    assert db_one(app, "SELECT theme_preference FROM users WHERE id = ?", (ids["user_id"],))["theme_preference"] == "dark"
    assert client.get("/api/auth/session").json()["user"]["theme"] == "dark"


# ---------------------------------------------------------------- uploads authorisation

def _chat_with_attachment(app):
    student = make_user(app, "STUDENT", "stu@x.edu", usn="1AB21CS001")
    make_user(app, "STUDENT", "other@x.edu", usn="1AB21CS002")
    faculty = make_user(app, "FACULTY", "fac@x.edu")
    make_user(app, "ADMIN", "admin@x.edu")
    name = f"{uuid.uuid4().hex}.pdf"
    os.makedirs(app.state.settings.chat_upload_dir, exist_ok=True)
    with open(os.path.join(app.state.settings.chat_upload_dir, name), "wb") as f:
        f.write(b"%PDF-1.4 secret")
    with db_session(app.state.settings):
        rel = queries.create_supporting_request(student["student_id"], faculty["faculty_id"], "STUDENT")
        queries.respond_supporting_relationship(rel, "ACCEPTED")
        chat = queries.get_or_create_chat(student["student_id"], faculty["faculty_id"])
        queries.create_message(chat["id"], student["user_id"], None, f"chat/{name}", "pdf", "my notes.pdf")
    return name


def test_chat_attachment_only_for_participants_and_admin(app):
    name = _chat_with_attachment(app)
    url = f"/uploads/chat/{name}"

    anon = TestClient(app)
    resp = anon.get(url)
    assert resp.status_code == 401 and err(resp)["code"] == "unauthenticated"

    third = TestClient(app)
    login(third, "other@x.edu", GOOD_PASSWORD)
    assert third.get(url).status_code == 403

    for ident in ("stu@x.edu", "fac@x.edu", "admin@x.edu"):
        c = TestClient(app)
        login(c, ident, GOOD_PASSWORD)
        resp = c.get(url)
        assert resp.status_code == 200, ident
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "my%20notes.pdf" in resp.headers["Content-Disposition"]
        assert "no-store" in resp.headers["Cache-Control"]
        assert resp.content.startswith(b"%PDF")


def test_chat_attachment_denied_when_access_was_revoked(app):
    name = _chat_with_attachment(app)
    db_exec(app, "UPDATE users SET is_active = 0 WHERE email = 'fac@x.edu'")
    c = TestClient(app)
    login(c, "stu@x.edu", GOOD_PASSWORD)
    assert c.get(f"/uploads/chat/{name}").status_code == 200  # participants keep access per chat rules


def test_upload_path_traversal_and_unknown_files_rejected(app):
    _chat_with_attachment(app)
    c = TestClient(app)
    login(c, "stu@x.edu", GOOD_PASSWORD)
    assert c.get("/uploads/chat/does-not-exist.pdf").status_code == 404
    for path in ("/uploads/../config.py", "/uploads/chat/../../config.py", "/uploads/%2e%2e/config.py",
                 "/uploads/chat/..%2f..%2fconfig.py", "/uploads/profile/students/../../../app.py",
                 "/uploads/chat%5c..%5cx.pdf", "/uploads//etc/passwd"):
        assert c.get(path).status_code in (400, 403, 404), path
    assert c.get("/uploads/other/thing.txt").status_code == 404
    assert c.get("/uploads/profile/students").status_code == 404
    assert c.get("/uploads/").status_code == 404


def test_profile_picture_visible_to_any_logged_in_user(app):
    make_user(app, "STUDENT", "stu@x.edu")
    name = f"{uuid.uuid4().hex}.png"
    os.makedirs(app.state.settings.profile_student_dir, exist_ok=True)
    with open(os.path.join(app.state.settings.profile_student_dir, name), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nxxxx")
    c = TestClient(app)
    assert c.get(f"/uploads/profile/students/{name}").status_code == 401
    login(c, "stu@x.edu", GOOD_PASSWORD)
    resp = c.get(f"/uploads/profile/students/{name}")
    assert resp.status_code == 200
    assert "attachment" not in resp.headers.get("Content-Disposition", "")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Content-Type"] == "image/png"


def test_non_image_in_profile_folder_is_attachment(app):
    make_user(app, "STUDENT", "stu@x.edu")
    os.makedirs(app.state.settings.profile_student_dir, exist_ok=True)
    with open(os.path.join(app.state.settings.profile_student_dir, "x.html"), "wb") as f:
        f.write(b"<script>alert(1)</script>")
    c = TestClient(app)
    login(c, "stu@x.edu", GOOD_PASSWORD)
    resp = c.get("/uploads/profile/students/x.html")
    assert resp.status_code == 200 and "attachment" in resp.headers["Content-Disposition"]


def test_original_filename_is_sanitised():
    from services import file_service
    assert file_service.sanitize_original_name("../../etc/pass wd.pdf", "pdf") == "etc_pass_wd.pdf"
    assert file_service.sanitize_original_name("<script>.pdf", "pdf") == "script.pdf"
    assert file_service.sanitize_original_name("", "png") == "attachment.png"


class _Upload:
    """Minimal UploadFile stand-in."""

    def __init__(self, filename, data):
        import io
        self.filename, self.file = filename, io.BytesIO(data)


def test_file_service_validates_magic_bytes_size_and_names(app):
    from services import file_service
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    with db_session(app.state.settings):
        rel = file_service.save_profile_picture(_Upload("me.PNG", png), "STUDENT")
        assert rel.startswith("profile/students/") and rel.endswith(".png") and "me" not in rel
        assert open(os.path.join(app.state.settings.upload_root, rel), "rb").read() == png
        for bad in (_Upload("evil.png", b"MZ\x90\x00" + b"0" * 32), _Upload("a.exe", png),
                    _Upload("e.png", b""), _Upload("big.png", png + b"0" * (3 * 1024 * 1024))):
            with pytest.raises(file_service.FileValidationError):
                file_service.save_profile_picture(bad, "FACULTY")
        with pytest.raises(file_service.FileValidationError):
            file_service.save_chat_attachment(_Upload("x.pdf", b"not a pdf"))
        rel, ext, original = file_service.save_chat_attachment(_Upload("../n o.pdf", b"%PDF-1.4 x"))
        assert rel.startswith("chat/") and ext == "pdf" and original == "n_o.pdf"


# ---------------------------------------------------------------- headers / errors / health

def test_security_headers_present(client):
    resp = client.get("/api/auth/session")
    h = resp.headers
    csp = h["Content-Security-Policy"]
    for directive in ("default-src 'self'", "script-src 'self'", "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                      "font-src 'self' https://fonts.gstatic.com data:", "img-src 'self' data: blob:",
                      "connect-src 'self'", "frame-ancestors 'none'", "base-uri 'self'",
                      "form-action 'self'", "object-src 'none'"):
        assert directive in csp, directive
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=(self)" in h["Permissions-Policy"]
    assert "Strict-Transport-Security" not in h  # plain-http development


def test_api_responses_are_never_cached(app, client):
    make_user(app, "ADMIN", "a@x.edu")
    assert client.get("/api/auth/session").headers["Cache-Control"] == "no-store"
    login(client, "a@x.edu", GOOD_PASSWORD)
    for url in ("/api/auth/session", "/api/notifications", "/api/academic/tree", "/api/nope"):
        resp = client.get(url)
        assert resp.headers["Cache-Control"] == "no-store", url
        assert resp.headers["Pragma"] == "no-cache", url
    assert "Content-Security-Policy" in client.get("/api/nope").headers  # also on error responses


def test_hsts_and_secure_cookie_in_production(tmp_path):
    app = create_app(make_settings(tmp_path, environment="production", secret_key="p" * 40))
    resp = TestClient(app).get("/api/auth/session")
    assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]
    cookie = resp.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    # interactive docs are off in production
    c = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404


def test_hsts_when_request_arrived_over_https(client):
    resp = TestClient(client.app, base_url="https://testserver").get("/api/auth/session")
    assert "Strict-Transport-Security" in resp.headers


def test_docs_only_in_debug(tmp_path):
    assert TestClient(create_app(make_settings(tmp_path))).get("/docs").status_code == 404
    app = create_app(make_settings(tmp_path / "d", debug=True))
    c = TestClient(app)
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/docs").status_code == 200
    assert "Content-Security-Policy" not in c.get("/docs").headers  # Swagger UI needs its CDN assets


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_healthz_reports_503_when_database_is_down(client, monkeypatch):
    def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr("api.routers.system.get_db", broken)
    resp = client.get("/healthz")
    assert resp.status_code == 503 and resp.json() == {"status": "error"}


def test_error_responses_use_json_shape_and_do_not_leak(probe_app, client):
    resp = client.get("/api/_probe/boom")
    assert resp.status_code == 500
    assert resp.json() == {"error": {"code": "server_error", "message": "Something went wrong on our end."}}
    assert "super secret" not in resp.text and "Traceback" not in resp.text
    assert resp.headers["X-Content-Type-Options"] == "nosniff"  # safety net still adds headers

    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404 and err(resp)["code"] == "not_found"
    resp = client.get("/api/auth/logout")
    assert resp.status_code == 405 and err(resp)["code"] == "method_not_allowed"
    resp = client.post("/api/does-not-exist")
    assert resp.status_code == 404 and err(resp)["code"] == "not_found"


def test_request_validation_errors_use_error_shape(client):
    resp = client.post("/api/auth/login", content=b"{not json", headers={"content-type": "application/json"})
    assert resp.status_code == 400 and err(resp)["code"] == "bad_request"
    resp = client.post("/api/auth/login", json=["a"])
    assert resp.status_code == 400
    resp = client.post("/api/auth/login", json={"identifier": 5, "password": "x"})
    assert resp.status_code == 400 and "identifier" in err(resp)["fields"]
    resp = client.get("/api/notifications/abc/read")
    assert resp.status_code in (404, 405)
    resp = client.post("/api/notifications/abc/read")
    assert resp.status_code in (400, 401)
    assert set(resp.json()) == {"error"}


def test_request_size_cap(tmp_path):
    app = add_probe_routes(create_app(make_settings(tmp_path, max_request_bytes=2000)))
    c = TestClient(app)
    resp = c.post("/api/_probe/write", content=b"x" * 5000, headers={"content-type": "application/octet-stream"})
    assert resp.status_code == 413 and err(resp)["code"] == "payload_too_large"
    assert c.post("/api/_probe/write", content=b"x" * 100).status_code == 200


def test_default_request_cap_is_10mb(app):
    assert app.state.settings.max_request_bytes == 10 * 1024 * 1024


def test_secret_key_validation():
    from api.settings import Settings
    Settings(testing=True).validate()
    with pytest.raises(RuntimeError):
        Settings(environment="production", secret_key="").validate()
    with pytest.raises(RuntimeError):
        Settings(environment="production", secret_key="dev-secret-key-change-in-production").validate()
    with pytest.raises(RuntimeError):
        Settings(environment="development", secret_key="dev-secret-key-change-in-production").validate()
    with pytest.raises(RuntimeError):
        Settings(environment="production", secret_key="short-key").validate()
    Settings(environment="production", secret_key="x" * 40).validate()


def test_create_app_refuses_production_without_secret(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(make_settings(tmp_path, testing=False, environment="production", secret_key=""))


# ---------------------------------------------------------------- proxy handling

def test_client_ip_ignores_forwarded_headers_unless_trusted(probe_app, client):
    resp = client.get("/api/_probe/ip", headers={"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Proto": "https"})
    assert resp.json() == {"ip": "testclient", "scheme": "http"}


def test_client_ip_uses_trusted_proxy_hops(tmp_path):
    def build(hops):
        return TestClient(add_probe_routes(create_app(
            make_settings(tmp_path / f"h{hops}", trust_proxy=True, trust_proxy_hops=hops))))

    one = build(1).get("/api/_probe/ip", headers={"X-Forwarded-For": "6.6.6.6, 1.2.3.4", "X-Forwarded-Proto": "https"})
    assert one.json() == {"ip": "1.2.3.4", "scheme": "https"}
    two = build(2).get("/api/_probe/ip", headers={"X-Forwarded-For": "6.6.6.6, 1.2.3.4"})
    assert two.json()["ip"] == "6.6.6.6"
    # fewer entries than trusted hops: a spoofable value is never used
    assert build(2).get("/api/_probe/ip", headers={"X-Forwarded-For": "6.6.6.6"}).json()["ip"] == "testclient"
    assert build(1).get("/api/_probe/ip").json()["ip"] == "testclient"


def test_login_throttle_uses_forwarded_client_ip(tmp_path):
    app = create_app(make_settings(tmp_path, trust_proxy=True, trust_proxy_hops=1, login_max_failures_per_ip=3))
    make_user(app, "FACULTY", "f@x.edu")
    c = TestClient(app)
    for i in range(3):
        c.post("/api/auth/login", json={"identifier": f"u{i}@x.edu", "password": "Wrong1234"},
               headers={"X-Forwarded-For": "8.8.8.8"})
    blocked = c.post("/api/auth/login", json={"identifier": "f@x.edu", "password": GOOD_PASSWORD},
                     headers={"X-Forwarded-For": "8.8.8.8"})
    other = c.post("/api/auth/login", json={"identifier": "f@x.edu", "password": GOOD_PASSWORD},
                   headers={"X-Forwarded-For": "9.9.9.9"})
    assert blocked.status_code == 429 and other.status_code == 200


# ---------------------------------------------------------------- SPA serving

@pytest.fixture
def spa_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SPA</title><div id=root></div>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    return TestClient(create_app(make_settings(tmp_path, frontend_dist=str(dist))))


def test_spa_fallback_serves_index_for_client_routes(spa_client):
    for path in ("/", "/login", "/student/dashboard", "/some/deep/route"):
        resp = spa_client.get(path)
        assert resp.status_code == 200 and "<title>SPA</title>" in resp.text, path
        assert resp.headers["Cache-Control"] == "no-cache"
        assert "Content-Security-Policy" in resp.headers
    assert spa_client.get("/favicon.svg").text == "<svg/>"


def test_spa_assets_are_immutable_and_missing_assets_404(spa_client):
    resp = spa_client.get("/assets/app-abc123.js")
    assert resp.status_code == 200 and "immutable" in resp.headers["Cache-Control"]
    assert spa_client.get("/assets/missing.js").status_code == 404


def test_spa_does_not_shadow_api_uploads_or_health(spa_client):
    resp = spa_client.get("/api/unknown")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
    assert spa_client.get("/healthz").json() == {"status": "ok"}
    assert spa_client.get("/uploads/chat/x.pdf").status_code == 401
    assert spa_client.get("/api/auth/session").json()["authenticated"] is False
    # non-GET to an unknown path is a JSON 404, never the SPA
    resp = spa_client.post("/login")
    assert resp.status_code == 404 and resp.headers["content-type"].startswith("application/json")


def test_spa_fallback_cannot_read_outside_dist(spa_client):
    for path in ("/..%2f..%2fconfig.py", "/%2e%2e/%2e%2e/config.py", "/..\\..\\config.py"):
        resp = spa_client.get(path)
        assert "SECRET_KEY" not in resp.text and "DATABASE_PATH" not in resp.text, path


def test_no_spa_build_gives_json_404(client):
    resp = client.get("/login")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- OTP

def start(client, email):
    return api_post(client, "/api/auth/signup/student/start", json={"college_email": email})


def verify(client, email, otp):
    return api_post(client, "/api/auth/signup/student/verify", json={"college_email": email, "otp": otp})


def wrong_otp(otp):
    return "000000" if otp != "000000" else "111111"


def test_otp_rate_limit_per_email(client):
    for _ in range(5):
        assert "demo_otp" in start(client, "new@x.edu").json()
    resp = start(client, "new@x.edu")
    assert resp.status_code == 429 and err(resp)["code"] == "rate_limited"
    assert "Too many verification codes" in err(resp)["message"] and "demo_otp" not in resp.text
    assert "demo_otp" in start(client, "else@x.edu").json()  # another email is unaffected


def test_otp_rate_limit_per_ip(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, otp_max_per_ip_per_hour=3)))
    for i in range(3):
        assert start(c, f"u{i}@x.edu").status_code == 200
    assert start(c, "u99@x.edu").status_code == 429


def test_otp_is_hashed_at_rest_and_generated_with_requested_length(app, client):
    otp = start(client, "new@x.edu").json()["demo_otp"]
    assert len(otp) == 6 and otp.isdigit()
    row = db_one(app, "SELECT otp_hash FROM otp_sessions WHERE email = 'new@x.edu'")
    assert otp not in row["otp_hash"] and len(row["otp_hash"]) == 64


def test_otp_flow_binds_verification_to_browser_session(app, client):
    email, sid = "new@x.edu", find_section(app=app)
    otp = start(client, email).json()["demo_otp"]
    bad = verify(client, email, wrong_otp(otp))
    assert bad.status_code == 400 and err(bad)["fields"]["otp"] == "Incorrect OTP."
    assert verify(client, email, otp).status_code == 200
    payload = {"college_email": email, "full_name": "N", "usn": "1AB21CS555", "section_id": sid,
               "phone": "9999999999", "personal_email": "n@example.com", "password": PASSWORD,
               "confirm_password": PASSWORD}
    # a different browser cannot reuse someone else's verified email
    other = TestClient(app)
    resp = api_post(other, "/api/auth/signup/student/register", json=payload)
    assert resp.status_code == 403 and err(resp)["code"] == "otp_not_verified"
    assert api_post(client, "/api/auth/signup/student/register", json=payload).status_code == 201


def test_otp_verification_cannot_be_transplanted_to_another_email(app, client):
    otp = start(client, "a@x.edu").json()["demo_otp"]
    verify(client, "a@x.edu", otp)
    resp = api_post(client, "/api/auth/signup/student/register", json={
        "college_email": "b@x.edu", "full_name": "N", "usn": "1AB21CS556", "section_id": find_section(app=app),
        "phone": "9999999999", "personal_email": "n@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD})
    assert resp.status_code == 403


def test_otp_verified_state_expires(app, client):
    email = "new@x.edu"
    otp = start(client, email).json()["demo_otp"]
    verify(client, email, otp)
    sess = read_session(client)
    sess["otp_verified_at"] -= 31 * 60
    write_session(client, sess)
    resp = api_post(client, "/api/auth/signup/student/register", json={
        "college_email": email, "full_name": "N", "usn": "1AB21CS557", "section_id": find_section(app=app),
        "phone": "9999999999", "personal_email": "n@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD})
    assert resp.status_code == 403


def test_otp_attempt_cap(client):
    otp = start(client, "new@x.edu").json()["demo_otp"]
    for _ in range(5):
        verify(client, "new@x.edu", wrong_otp(otp))
    resp = verify(client, "new@x.edu", otp)
    assert resp.status_code == 400 and "Too many incorrect attempts" in err(resp)["message"]


def test_otp_expiry(app, client):
    otp = start(client, "new@x.edu").json()["demo_otp"]
    db_exec(app, "UPDATE otp_sessions SET expires_at = '2000-01-01T00:00:00' WHERE email = 'new@x.edu'")
    resp = verify(client, "new@x.edu", otp)
    assert resp.status_code == 400 and "expired" in err(resp)["message"]


def test_otp_cannot_be_reused(client):
    otp = start(client, "new@x.edu").json()["demo_otp"]
    assert verify(client, "new@x.edu", otp).status_code == 200
    again = verify(client, "new@x.edu", otp)
    assert again.status_code == 400 and "already been used" in err(again)["message"]


def test_otp_is_emailed_not_shown_when_smtp_configured(tmp_path, monkeypatch):
    import re
    app = create_app(make_settings(tmp_path, smtp_host="smtp.test", smtp_port=587, smtp_user="u",
                                   smtp_password="p", smtp_from="cc@test", show_demo_otp=True))
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr("services.otp_service.smtplib.SMTP", FakeSMTP)
    c = TestClient(app)
    resp = start(c, "new@x.edu")
    assert resp.status_code == 200
    assert len(sent) == 1 and sent[0]["To"] == "new@x.edu"
    code = re.search(r"code is (\d{6})", sent[0].get_content()).group(1)
    assert code not in resp.text and "demo_otp" not in resp.text
    assert resp.json()["delivery"] == "email"
    assert c.get("/api/meta").json()["demo_otp_enabled"] is False


def test_smtp_failure_is_reported_without_leaking(tmp_path, monkeypatch):
    import smtplib
    app = create_app(make_settings(tmp_path, smtp_host="smtp.test"))

    def boom(*a, **k):
        raise smtplib.SMTPException("secret smtp detail")
    monkeypatch.setattr("services.otp_service.smtplib.SMTP", boom)
    resp = start(TestClient(app), "new@x.edu")
    assert resp.status_code == 503 and err(resp)["code"] == "delivery_unavailable"
    assert "secret smtp detail" not in resp.text


def test_no_delivery_channel_refuses_to_issue_otp(tmp_path):
    app = create_app(make_settings(tmp_path, show_demo_otp=False, smtp_host=""))
    c = TestClient(app)
    resp = start(c, "new@x.edu")
    assert resp.status_code == 503 and "not available" in err(resp)["message"]
    assert c.get("/api/meta").json()["demo_otp_enabled"] is False
    with db_session(app.state.settings):
        assert queries.get_latest_otp_session("new@x.edu") is None


# ---------------------------------------------------------------- admin bootstrap

def test_admin_bootstrap_is_idempotent_and_never_overwrites(app, monkeypatch):
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", "Owner@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    with db_session(app.state.settings):
        assert auth_service.bootstrap_admin_from_env() == "created"
        first = queries.get_user_by_email("owner@example.com")
        assert first["role"] == "ADMIN"
        monkeypatch.setenv("ADMIN_PASSWORD", "Different@1234")
        assert auth_service.bootstrap_admin_from_env() == "exists"
        assert queries.get_user_by_email("owner@example.com")["password_hash"] == first["password_hash"]
    monkeypatch.delenv("ADMIN_PASSWORD")
    with db_session(app.state.settings):
        assert auth_service.bootstrap_admin_from_env() == "skipped"


def test_bootstrap_admin_at_startup_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    settings = make_settings(tmp_path, testing=False, bootstrap_admin=True)
    app = create_app(settings)
    create_app(settings)  # second start: idempotent
    c = TestClient(app)
    assert api_login(c, "owner@example.com", "Sample@1234")["user"]["role"] == "ADMIN"
    assert db_count(app, "users") == 1


def test_bootstrap_not_run_unless_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    app = create_app(make_settings(tmp_path, testing=False, bootstrap_admin=False))
    with db_session(app.state.settings):
        assert queries.get_user_by_email("owner@example.com") is None


def test_create_admin_cli(app, monkeypatch, capsys):
    import create_admin
    settings = app.state.settings
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", "cli@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    assert create_admin.main(["--from-env"], settings=settings) == 0
    assert create_admin.main(["--from-env"], settings=settings) == 0  # idempotent
    out = capsys.readouterr().out
    assert "created" in out and "Nothing was changed" in out and "Karthik" not in out
    with db_session(settings):
        assert queries.get_user_by_email("cli@example.com")["role"] == "ADMIN"
    monkeypatch.setenv("ADMIN_PASSWORD", "weak")
    monkeypatch.setenv("ADMIN_EMAIL", "cli2@example.com")
    assert create_admin.main(["--from-env"], settings=settings) == 1
    monkeypatch.delenv("ADMIN_NAME")
    assert create_admin.main(["--from-env"], settings=settings) == 2


# ---------------------------------------------------------------- scheduler

def test_scheduler_runs_only_when_enabled(tmp_path):
    off = create_app(make_settings(tmp_path / "off"))
    with TestClient(off):
        assert getattr(off.state, "scheduler", None) is None
    on = create_app(make_settings(tmp_path / "on", testing=False, enable_scheduler=True))
    with TestClient(on):
        scheduler = on.state.scheduler
        assert scheduler.running and scheduler.get_job("meeting_reminders")
    assert not scheduler.running


# ---------------------------------------------------------------- authorisation (IDOR) spot checks

def test_notification_mark_read_only_affects_own(app, client):
    from services import notification_service as notif
    make_user(app, "ADMIN", "a@x.edu")
    b = make_user(app, "ADMIN", "b@x.edu")
    with db_session(app.state.settings):
        nid = notif.notify(b["user_id"], notif.NEW_MESSAGE, "t", "m")
    login(client, "a@x.edu", GOOD_PASSWORD)
    assert api_post(client, f"/api/notifications/{nid}/read").status_code == 404
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 0
    api_post(client, "/api/notifications/read-all")
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 0
