"""Security regression tests: CSRF, throttling, session invalidation, password policy, uploads
authorisation, headers, OTP limits, redirects and health check. Self-contained (own helpers)."""
import os
import re
import sys
import tempfile
import uuid

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config, validate_config  # noqa: E402
from app import create_app  # noqa: E402
from models import queries  # noqa: E402
from models.database import get_db  # noqa: E402

GOOD_PASSWORD = "Str0ngPass!"
SECRET = "unit-test-secret-key-0123456789abcdef"


# ---------------------------------------------------------------- helpers

def _build_app(csrf=False, **overrides):
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    upload_root = tempfile.mkdtemp()
    attrs = dict(
        TESTING=True,
        WTF_CSRF_ENABLED=csrf,
        SECRET_KEY=SECRET,
        DATABASE_PATH=db_path,
        UPLOAD_ROOT=upload_root,
        PROFILE_STUDENT_DIR=os.path.join(upload_root, "profile", "students"),
        PROFILE_FACULTY_DIR=os.path.join(upload_root, "profile", "faculty"),
        CHAT_UPLOAD_DIR=os.path.join(upload_root, "chat"),
    )
    attrs.update(overrides)
    cfg = type("_SecCfg", (Config,), attrs)
    return create_app(cfg)


@pytest.fixture
def app():
    return _build_app()


@pytest.fixture
def csrf_app():
    return _build_app(csrf=True)


def _make_user(app, role, email, password=GOOD_PASSWORD, name="Test User", **extra):
    with app.app_context():
        uid = queries.create_user(role, email, generate_password_hash(password), name)
        ids = {"user_id": uid}
        if role == "STUDENT":
            ids["student_id"] = queries.create_student(
                uid, extra.get("usn", "1AB21CS001"), "BE", "CSE", "1st Year", "A",
                "9876543210", f"p_{email}", email,
            )
        elif role == "FACULTY":
            ids["faculty_id"] = queries.create_faculty(uid, extra.get("code", "FAC001"), "CSE", email)
        return ids


def _login(client, identifier, password=GOOD_PASSWORD):
    return client.post("/login", data={"email": identifier, "password": password})


def _csrf_token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "csrf meta tag missing"
    return match.group(1)


# ---------------------------------------------------------------- CSRF

def test_csrf_rejects_post_without_token(csrf_app):
    _make_user(csrf_app, "ADMIN", "admin@x.edu")
    client = csrf_app.test_client()
    resp = client.post("/login", data={"email": "admin@x.edu", "password": GOOD_PASSWORD})
    assert resp.status_code == 400
    assert b"expired" in resp.data.lower()  # friendly errors.html page, not a stack trace


def test_csrf_accepts_post_with_token(csrf_app):
    _make_user(csrf_app, "ADMIN", "admin@x.edu")
    client = csrf_app.test_client()
    token = _csrf_token(client)
    resp = client.post("/login", data={"email": "admin@x.edu", "password": GOOD_PASSWORD, "csrf_token": token})
    assert resp.status_code == 302


def test_logout_requires_post(app):
    assert app.test_client().get("/logout").status_code == 405


# ---------------------------------------------------------------- login throttling

def test_same_message_for_unknown_wrong_and_inactive(app):
    ids = _make_user(app, "STUDENT", "s@x.edu")
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (ids["user_id"],))
        get_db().commit()
    _make_user(app, "FACULTY", "f@x.edu")
    c = app.test_client()
    bodies = []
    for ident, pw in (("nobody@x.edu", "Whatever1"), ("f@x.edu", "WrongPass1"), ("s@x.edu", GOOD_PASSWORD)):
        resp = _login(c, ident, pw)
        assert resp.status_code == 200
        bodies.append(re.search(rb"Invalid email or password\.", resp.data) is not None)
    assert all(bodies)


def test_lockout_after_repeated_failures(app):
    _make_user(app, "FACULTY", "f@x.edu")
    c = app.test_client()
    for _ in range(5):
        assert _login(c, "f@x.edu", "WrongPass1").status_code == 200
    resp = _login(c, "f@x.edu", GOOD_PASSWORD)  # even the right password is refused while locked
    assert resp.status_code == 429
    assert b"Too many unsuccessful attempts" in resp.data
    with c.session_transaction() as sess:
        assert "user_id" not in sess
    # lockout applies to unknown identifiers as well (no account enumeration)
    for _ in range(5):
        _login(c, "ghost@x.edu", "WrongPass1")
    assert _login(c, "ghost@x.edu", "WrongPass1").status_code == 429


def test_ip_lockout_across_identifiers(app):
    app.config["LOGIN_MAX_FAILURES_PER_IP"] = 4
    _make_user(app, "FACULTY", "f@x.edu")
    c = app.test_client()
    for i in range(4):
        _login(c, f"user{i}@x.edu", "WrongPass1")
    assert _login(c, "f@x.edu", GOOD_PASSWORD).status_code == 429


def test_success_clears_identifier_counter_and_records_last_login(app):
    ids = _make_user(app, "FACULTY", "f@x.edu")
    c = app.test_client()
    for _ in range(3):
        _login(c, "f@x.edu", "WrongPass1")
    assert _login(c, "f@x.edu").status_code == 302
    with app.app_context():
        row = queries.get_user_by_id(ids["user_id"])
        assert row["last_login_at"]
    for _ in range(3):  # would be 6 total without the reset
        _login(c, "f@x.edu", "WrongPass1")
    assert _login(c, "f@x.edu").status_code == 302


def test_login_replaces_pre_login_session(app):
    _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["attacker_planted"] = "x"
    _login(c, "a@x.edu")
    with c.session_transaction() as sess:
        assert "attacker_planted" not in sess
        assert sess["role"] == "ADMIN"


# ---------------------------------------------------------------- session invalidation

def test_deactivated_user_session_is_invalidated(app):
    ids = _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    _login(c, "a@x.edu")
    assert c.get("/admin/dashboard").status_code == 200
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (ids["user_id"],))
        get_db().commit()
    resp = c.get("/admin/dashboard")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    with c.session_transaction() as sess:
        assert "user_id" not in sess


def test_deleted_user_session_is_invalidated(app):
    ids = _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    _login(c, "a@x.edu")
    with app.app_context():
        get_db().execute("DELETE FROM users WHERE id = ?", (ids["user_id"],))
        get_db().commit()
    assert c.get("/admin/dashboard").status_code == 302


def test_role_is_refreshed_from_database(app):
    ids = _make_user(app, "ADMIN", "a@x.edu", name="Old Name")
    c = app.test_client()
    _login(c, "a@x.edu")
    with app.app_context():
        get_db().execute("UPDATE users SET full_name = 'New Name' WHERE id = ?", (ids["user_id"],))
        get_db().commit()
    c.get("/admin/dashboard")
    with c.session_transaction() as sess:
        assert sess["full_name"] == "New Name"
    # A forged role in the cookie cannot survive the DB refresh.
    with c.session_transaction() as sess:
        sess["role"] = "STUDENT"
    c.get("/admin/dashboard")
    with c.session_transaction() as sess:
        assert sess["role"] == "ADMIN"


def test_idle_timeout_and_absolute_timeout(app):
    _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    _login(c, "a@x.edu")
    with c.session_transaction() as sess:
        sess["last_seen"] = sess["last_seen"] - 61 * 60
    resp = c.get("/admin/dashboard")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]

    _login(c, "a@x.edu")
    with c.session_transaction() as sess:
        sess["login_at"] = sess["login_at"] - 13 * 3600
    assert c.get("/admin/dashboard").status_code == 302


# ---------------------------------------------------------------- password policy

@pytest.mark.parametrize("password", [
    "short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "", None, "A" * 129 + "a1",
])
def test_weak_passwords_rejected(app, password):
    from services import auth_service
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password(password)


@pytest.mark.parametrize("password", ["Sample@1234", "Abcdefg1", "Sym-bols_Ok9!"])
def test_strong_passwords_accepted(app, password):
    from services import auth_service
    assert auth_service.hash_password(password)


def test_password_equal_to_email_or_username_rejected(app):
    from services import auth_service
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("Fac001@Uni1", disallow=("fac001@uni1",))
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("Fac001Uni1", disallow=("Fac001Uni1@college.edu",))


def test_signup_enforces_password_policy(app):
    from models import academic_queries as aq
    with app.app_context():
        department = aq.list_active_department_names()[0]
    c = app.test_client()
    resp = c.post("/signup/faculty", data={
        "full_name": "P", "faculty_code": "FAC9", "department": department,
        "professional_email": "p@x.edu", "subjects": "DSA",
        "password": "alllowercase1", "confirm_password": "alllowercase1",
    }, follow_redirects=True)
    assert b"uppercase" in resp.data


# ---------------------------------------------------------------- change password

def test_change_password_flow(app):
    _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    assert c.get("/account/password").status_code == 302  # login required
    _login(c, "a@x.edu")
    assert c.get("/account/password").status_code == 200

    def post(cur, new, conf):
        return c.post("/account/password", data={
            "current_password": cur, "new_password": new, "confirm_password": conf,
        }, follow_redirects=False)

    assert b"current password is incorrect" in post("Nope12345", "NewPass123", "NewPass123").data
    assert b"do not match" in post(GOOD_PASSWORD, "NewPass123", "NewPass124").data
    assert b"must be different" in post(GOOD_PASSWORD, GOOD_PASSWORD, GOOD_PASSWORD).data
    assert b"uppercase" in post(GOOD_PASSWORD, "weakpassword", "weakpassword").data

    resp = post(GOOD_PASSWORD, "NewPass123", "NewPass123")
    assert resp.status_code == 302
    c2 = app.test_client()
    assert _login(c2, "a@x.edu", GOOD_PASSWORD).status_code == 200  # old password no longer works
    assert _login(c2, "a@x.edu", "NewPass123").status_code == 302


# ---------------------------------------------------------------- uploads authorisation

def _chat_with_attachment(app):
    student = _make_user(app, "STUDENT", "stu@x.edu", usn="1AB21CS001")
    other = _make_user(app, "STUDENT", "other@x.edu", usn="1AB21CS002")
    faculty = _make_user(app, "FACULTY", "fac@x.edu")
    _make_user(app, "ADMIN", "admin@x.edu")
    name = f"{uuid.uuid4().hex}.pdf"
    with open(os.path.join(app.config["CHAT_UPLOAD_DIR"], name), "wb") as f:
        f.write(b"%PDF-1.4 secret")
    with app.app_context():
        rel = queries.create_supporting_request(student["student_id"], faculty["faculty_id"], "STUDENT")
        queries.respond_supporting_relationship(rel, "ACCEPTED")
        chat = queries.get_or_create_chat(student["student_id"], faculty["faculty_id"])
        queries.create_message(
            chat["id"], student["user_id"], None, f"chat/{name}", "pdf", "my notes.pdf"
        )
    return name


def test_chat_attachment_only_for_participants_and_admin(app):
    name = _chat_with_attachment(app)
    url = f"/uploads/chat/{name}"

    anon = app.test_client()
    assert anon.get(url).status_code == 403

    third = app.test_client()
    _login(third, "other@x.edu")
    assert third.get(url).status_code == 403

    for ident in ("stu@x.edu", "fac@x.edu", "admin@x.edu"):
        c = app.test_client()
        _login(c, ident)
        resp = c.get(url)
        assert resp.status_code == 200, ident
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert resp.data.startswith(b"%PDF")


def test_upload_path_traversal_and_unknown_files_rejected(app):
    _chat_with_attachment(app)
    c = app.test_client()
    _login(c, "stu@x.edu")
    assert c.get("/uploads/chat/does-not-exist.pdf").status_code == 404
    assert c.get("/uploads/../config.py").status_code in (403, 404)
    assert c.get("/uploads/chat/../../config.py").status_code in (403, 404)
    assert c.get("/uploads/other/thing.txt").status_code == 404


def test_profile_picture_visible_to_any_logged_in_user(app):
    _make_user(app, "STUDENT", "stu@x.edu")
    name = f"{uuid.uuid4().hex}.png"
    with open(os.path.join(app.config["PROFILE_STUDENT_DIR"], name), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nxxxx")
    c = app.test_client()
    assert c.get(f"/uploads/profile/students/{name}").status_code == 403
    _login(c, "stu@x.edu")
    resp = c.get(f"/uploads/profile/students/{name}")
    assert resp.status_code == 200
    assert "attachment" not in resp.headers.get("Content-Disposition", "")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_original_filename_is_sanitised(app):
    from services import file_service
    assert file_service.sanitize_original_name("../../etc/pass wd.pdf", "pdf") == "etc_pass_wd.pdf"
    assert file_service.sanitize_original_name("<script>.pdf", "pdf") == "script.pdf"
    assert file_service.sanitize_original_name("", "png") == "attachment.png"


# ---------------------------------------------------------------- headers / errors / health

def test_security_headers_present(app):
    resp = app.test_client().get("/login")
    h = resp.headers
    assert "default-src 'self'" in h["Content-Security-Policy"]
    assert "script-src 'self'" in h["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=(self)" in h["Permissions-Policy"]


def test_authenticated_html_is_not_cached(app):
    _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    _login(c, "a@x.edu")
    assert c.get("/admin/dashboard").headers["Cache-Control"] == "no-store"


def test_hsts_and_secure_cookie_in_production():
    app = _build_app(IS_PRODUCTION=True, SESSION_COOKIE_SECURE=True)
    resp = app.test_client().get("/login")
    assert "max-age=" in resp.headers["Strict-Transport-Security"]
    assert app.config["SESSION_COOKIE_NAME"] == "cc_session"
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_healthz(app):
    resp = app.test_client().get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_error_pages_do_not_leak_tracebacks(app):
    @app.route("/_boom")
    def boom():
        raise RuntimeError("super secret internals")

    c = app.test_client()
    resp = c.get("/_boom")
    assert resp.status_code == 500
    assert b"super secret internals" not in resp.data and b"Traceback" not in resp.data
    assert c.get("/logout").status_code == 405
    assert b"not allowed" in c.get("/logout").data
    assert c.get("/nope").status_code == 404


def test_secret_key_validation():
    validate_config({"TESTING": True})
    with pytest.raises(RuntimeError):
        validate_config({"IS_PRODUCTION": True, "SECRET_KEY": ""})
    with pytest.raises(RuntimeError):
        validate_config({"IS_PRODUCTION": True, "SECRET_KEY": "dev-secret-key-change-in-production"})
    with pytest.raises(RuntimeError):
        validate_config({"IS_PRODUCTION": False, "SECRET_KEY": "dev-secret-key-change-in-production"})
    validate_config({"IS_PRODUCTION": True, "SECRET_KEY": "x" * 40})


# ---------------------------------------------------------------- open redirect helper

def test_safe_redirect_back(app):
    from routes.helpers import safe_redirect_back
    with app.test_request_context("/x", base_url="http://campus.test", headers={"Referer": "http://campus.test/a/b?c=1"}):
        assert safe_redirect_back("index").headers["Location"] == "/a/b?c=1"
    for bad in ("http://evil.test/a", "https://campus.test.evil.test/", "//evil.test/x", "javascript:alert(1)", ""):
        with app.test_request_context("/x", base_url="http://campus.test", headers={"Referer": bad}):
            assert safe_redirect_back("auth.login").headers["Location"] == "/login", bad
    with app.test_request_context("/x", base_url="http://campus.test"):
        assert safe_redirect_back("auth.login").headers["Location"] == "/login"


def test_notification_redirect_ignores_foreign_referrer(app):
    _make_user(app, "ADMIN", "a@x.edu")
    c = app.test_client()
    _login(c, "a@x.edu")
    resp = c.post("/notifications/read-all", headers={"Referer": "http://evil.test/phish"})
    assert resp.status_code == 302
    assert "evil.test" not in resp.headers["Location"]


# ---------------------------------------------------------------- OTP

def _start_signup(client, email):
    return client.post("/signup/student", data={"college_email": email}, follow_redirects=True)


def _otp_from(resp):
    match = re.search(r"Demo OTP for [^:]+: (\d{6})", resp.get_data(as_text=True))
    assert match, "demo OTP not shown"
    return match.group(1)


def test_otp_rate_limit_per_email(app):
    c = app.test_client()
    for _ in range(5):
        assert b"Demo OTP" in _start_signup(c, "new@x.edu").data
    resp = _start_signup(c, "new@x.edu")
    assert b"Too many verification codes" in resp.data
    assert b"Demo OTP" not in resp.data
    # another email is unaffected
    assert b"Demo OTP" in _start_signup(c, "else@x.edu").data


def test_otp_rate_limit_per_ip(app):
    app.config["OTP_MAX_PER_IP_PER_HOUR"] = 3
    c = app.test_client()
    for i in range(3):
        assert b"Demo OTP" in _start_signup(c, f"u{i}@x.edu").data
    assert b"Too many verification codes" in _start_signup(c, "u99@x.edu").data


def test_otp_flow_binds_verification_to_browser_session(app):
    c = app.test_client()
    otp = _otp_from(_start_signup(c, "new@x.edu"))
    bad = c.post("/signup/student/verify-otp", data={"email": "new@x.edu", "otp": "000000" if otp != "000000" else "111111"})
    assert b"Incorrect OTP" in bad.data
    ok = c.post("/signup/student/verify-otp", data={"email": "new@x.edu", "otp": otp})
    assert ok.status_code == 302 and "/signup/student/details" in ok.headers["Location"]
    assert c.get("/signup/student/details?email=new@x.edu").status_code == 200
    # a different browser cannot reuse someone else's verified email
    other = app.test_client()
    resp = other.get("/signup/student/details?email=new@x.edu")
    assert resp.status_code == 302 and "/signup/student" in resp.headers["Location"]


def test_otp_verified_state_expires(app):
    c = app.test_client()
    otp = _otp_from(_start_signup(c, "new@x.edu"))
    c.post("/signup/student/verify-otp", data={"email": "new@x.edu", "otp": otp})
    with c.session_transaction() as sess:
        sess["otp_verified_at"] = sess["otp_verified_at"] - 31 * 60
    assert c.get("/signup/student/details?email=new@x.edu").status_code == 302


def test_otp_attempt_cap(app):
    c = app.test_client()
    otp = _otp_from(_start_signup(c, "new@x.edu"))
    wrong = "000000" if otp != "000000" else "111111"
    for _ in range(5):
        c.post("/signup/student/verify-otp", data={"email": "new@x.edu", "otp": wrong})
    resp = c.post("/signup/student/verify-otp", data={"email": "new@x.edu", "otp": otp})
    assert b"Too many incorrect attempts" in resp.data


def test_otp_is_emailed_not_shown_when_smtp_configured(monkeypatch):
    app = _build_app(SMTP_HOST="smtp.test", SMTP_PORT=587, SMTP_USER="u", SMTP_PASSWORD="p", SMTP_FROM="cc@test", SHOW_DEMO_OTP=True)
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
    resp = _start_signup(app.test_client(), "new@x.edu")
    assert len(sent) == 1 and sent[0]["To"] == "new@x.edu"
    code = re.search(r"code is (\d{6})", sent[0].get_content()).group(1)
    assert code.encode() not in resp.data
    assert b"Demo OTP" not in resp.data


def test_no_delivery_channel_refuses_to_issue_otp():
    app = _build_app(SHOW_DEMO_OTP=False, SMTP_HOST="")
    resp = _start_signup(app.test_client(), "new@x.edu")
    assert b"not available" in resp.data
    with app.app_context():
        assert queries.get_latest_otp_session("new@x.edu") is None


# ---------------------------------------------------------------- admin bootstrap

def test_admin_bootstrap_is_idempotent_and_never_overwrites(app, monkeypatch):
    import create_admin
    monkeypatch.setenv("ADMIN_NAME", "Owner")
    monkeypatch.setenv("ADMIN_EMAIL", "Owner@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sample@1234")
    with app.app_context():
        assert create_admin.bootstrap_from_env() == "created"
        first = queries.get_user_by_email("owner@example.com")
        assert first["role"] == "ADMIN"
        monkeypatch.setenv("ADMIN_PASSWORD", "Different@1234")
        assert create_admin.bootstrap_from_env() == "exists"
        assert queries.get_user_by_email("owner@example.com")["password_hash"] == first["password_hash"]
    monkeypatch.delenv("ADMIN_PASSWORD")
    with app.app_context():
        assert create_admin.bootstrap_from_env() == "skipped"


# ---------------------------------------------------------------- authorisation (IDOR) spot checks

def test_notification_mark_read_only_affects_own(app):
    a = _make_user(app, "ADMIN", "a@x.edu")
    b = _make_user(app, "ADMIN", "b@x.edu")
    with app.app_context():
        from services import notification_service as notif
        nid = notif.notify(b["user_id"], notif.NEW_MESSAGE, "t", "m")
    c = app.test_client()
    _login(c, "a@x.edu")
    c.post(f"/notifications/{nid}/read")
    with app.app_context():
        row = get_db().execute("SELECT is_read FROM notifications WHERE id = ?", (nid,)).fetchone()
        assert row["is_read"] == 0
    assert a["user_id"] != b["user_id"]


def test_student_cannot_open_other_students_chat(app):
    s1 = _make_user(app, "STUDENT", "s1@x.edu", usn="1AB21CS011")
    _make_user(app, "STUDENT", "s2@x.edu", usn="1AB21CS012")
    f = _make_user(app, "FACULTY", "f@x.edu")
    with app.app_context():
        chat = queries.get_or_create_chat(s1["student_id"], f["faculty_id"])
        chat_id = chat["id"]
    c = app.test_client()
    _login(c, "s2@x.edu")
    resp = c.get(f"/chat/{chat_id}")
    assert resp.status_code == 302 and "/chat" in resp.headers["Location"]
    resp = c.post(f"/chat/{chat_id}/message", data={"message_text": "hi"})
    with app.app_context():
        assert queries.list_messages_for_chat(chat_id) == []
