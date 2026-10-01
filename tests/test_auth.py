"""Auth API tests: session, login/logout, student captcha signup, faculty signup, service-level validation."""
import pytest

from models import queries
from services import auth_service
from tests.conftest import (
    PASSWORD, make_admin, register_faculty, register_student, find_section, login_client, api_login,
    api_post, http_faculty_signup, http_student_signup, db_one, db_count, db_all, db_exec, solve_captcha,
)


def err(resp):
    return resp.json()["error"]


# ---------------------------------------------------------------------------
# /api/auth/session
# ---------------------------------------------------------------------------

def test_session_anonymous_creates_csrf_token(client):
    resp = client.get("/api/auth/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is False and body["user"] is None
    assert body["unread_notifications"] == 0 and body["unread_messages"] == 0
    assert len(body["csrf_token"]) >= 32
    # stable for the same browser session
    assert client.get("/api/auth/session").json()["csrf_token"] == body["csrf_token"]


def test_session_cookie_flags(client):
    resp = client.get("/api/auth/session")
    cookie = resp.headers["set-cookie"].lower()
    assert cookie.startswith("cc_session=")
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie


def test_login_returns_user_and_session_reports_it(app, client):
    stu = register_student(app, "1AB21CS001")
    body = api_login(client, stu["email"], PASSWORD)
    assert body["ok"] is True and body["csrf_token"]
    user = body["user"]
    assert user["role"] == "STUDENT" and user["email"] == stu["email"]
    assert user["student_id"] == stu["student_id"] and user["faculty_id"] is None
    assert user["theme"] == "light" and user["profile_picture_url"] is None
    assert set(user) == {"id", "role", "full_name", "email", "theme", "profile_picture_url",
                         "student_id", "faculty_id"}

    sess = client.get("/api/auth/session").json()
    assert sess["authenticated"] is True and sess["user"] == user
    assert sess["csrf_token"] == body["csrf_token"]


def test_session_counts_unread(app, client):
    from services import notification_service as notif
    stu = register_student(app, "1AB21CS002")
    from api.db import db_session
    with db_session(app.state.settings):
        notif.notify(stu["user_id"], notif.NEW_MESSAGE, "t", "m")
        notif.notify(stu["user_id"], notif.NEW_MESSAGE, "t2", "m2")
    api_login(client, stu["email"])
    assert client.get("/api/auth/session").json()["unread_notifications"] == 2


# ---------------------------------------------------------------------------
# login / logout
# ---------------------------------------------------------------------------

def test_wrong_password_and_unknown_user_share_one_error(app, client):
    register_faculty(app, "FAC202")
    a = api_post(client, "/api/auth/login", json={"identifier": "fac202@college.edu", "password": "WrongPassw0rd!"})
    b = api_post(client, "/api/auth/login", json={"identifier": "nobody@college.edu", "password": PASSWORD})
    assert a.status_code == b.status_code == 401
    assert err(a) == err(b)
    assert err(a)["code"] == "invalid_credentials" and err(a)["message"] == "Invalid email or password."
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_login_with_faculty_code_and_usn_identifiers(app):
    register_faculty(app, "FAC203")
    register_student(app, "1AB21CS901")
    for ident in ("fac203", "FAC203", "1ab21cs901", "1AB21CS901"):
        c = login_client(app, ident)
        assert c.get("/api/auth/session").json()["authenticated"] is True


def test_login_validation_errors(client):
    r = api_post(client, "/api/auth/login", json={"identifier": "  ", "password": "x"})
    assert r.status_code == 400 and err(r)["code"] == "validation_error" and "identifier" in err(r)["fields"]
    r = api_post(client, "/api/auth/login", json={"identifier": "a@b.com"})
    assert r.status_code == 400 and "password" in err(r)["fields"]
    r = api_post(client, "/api/auth/login", json={"identifier": "a@b.com", "password": "x", "admin": True})
    assert r.status_code == 400  # unknown fields are rejected


def test_logout_clears_session_and_rotates_token(app):
    make_admin(app)
    c = login_client(app, "admin@college.edu")
    old = c.get("/api/auth/session").json()["csrf_token"]
    resp = api_post(c, "/api/auth/logout")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    new = resp.json()["csrf_token"]
    assert new != old
    sess = c.get("/api/auth/session").json()
    assert sess["authenticated"] is False and sess["csrf_token"] == new
    assert c.get("/api/notifications").status_code == 401


def test_logout_requires_post(client):
    assert client.get("/api/auth/logout").status_code == 405


def test_authenticate_rejects_inactive_user(app):
    stu = register_student(app, "1AB21CS905")
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (stu["user_id"],))
    from api.db import db_session
    with db_session(app.state.settings):
        with pytest.raises(auth_service.ValidationError):
            auth_service.authenticate(stu["email"], PASSWORD)


# ---------------------------------------------------------------------------
# faculty signup
# ---------------------------------------------------------------------------

def test_faculty_signup_and_login(client, app):
    resp = http_faculty_signup(client, "FAC200")
    assert resp.status_code == 201 and resp.json()["ok"] is True
    row = db_one(app, "SELECT f.department, f.faculty_code FROM faculty f WHERE f.faculty_code = 'FAC200'")
    assert row == {"department": "AIML", "faculty_code": "FAC200"}
    assert len(db_all(app, "SELECT * FROM faculty_subjects")) == 2

    body = api_login(client, "fac200@college.edu", PASSWORD)
    assert body["user"]["role"] == "FACULTY" and body["user"]["faculty_id"]


def test_faculty_signup_accepts_subject_list(client, app):
    resp = http_faculty_signup(client, "FAC211", subjects=["DSA", "OS", "dsa"])
    assert resp.status_code == 201
    assert len(db_all(app, "SELECT * FROM faculty_subjects")) == 2


def test_faculty_signup_creates_no_class_assignments(client, app):
    """Classes are never chosen at faculty signup; forged class fields are rejected."""
    resp = http_faculty_signup(client, "FAC210", extra={"section_id": find_section(app=app), "classes": "1"})
    assert resp.status_code == 400
    assert db_count(app, "faculty") == 0
    assert http_faculty_signup(client, "FAC210").status_code == 201
    assert db_count(app, "faculty_assignments") == 0
    assert db_count(app, "faculty_assignment_requests") == 0


@pytest.mark.parametrize("dept", ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"])
def test_faculty_signup_accepts_every_seeded_department(client, app, dept):
    assert http_faculty_signup(client, "FAC300", department=dept).status_code == 201
    assert db_one(app, "SELECT department FROM faculty WHERE faculty_code = 'FAC300'")["department"] == dept


def test_faculty_department_is_case_insensitive_and_canonicalised(client, app):
    http_faculty_signup(client, "FAC301", department="aiml")
    assert db_one(app, "SELECT department FROM faculty WHERE faculty_code = 'FAC301'")["department"] == "AIML"


@pytest.mark.parametrize("dept", ["CSE", "Physics", "", "AIML; DROP TABLE faculty", "   "])
def test_faculty_signup_rejects_non_admin_departments(client, app, dept):
    resp = http_faculty_signup(client, "FAC302", department=dept)
    assert resp.status_code == 400 and "department" in err(resp)["fields"]
    assert db_count(app, "faculty") == 0


def test_faculty_departments_endpoint_lists_active_only(client, app):
    from api.db import db_session
    from models import academic_queries as aq
    from services import academic_service
    body = client.get("/api/auth/faculty-departments").json()
    assert set(body["items"]) == {"AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"}
    with db_session(app.state.settings):
        dept = aq.list_departments()[0]
        academic_service.set_active("department", dept["id"], False)
        name = dept["name"]
    assert name not in client.get("/api/auth/faculty-departments").json()["items"]
    assert http_faculty_signup(client, "FAC303", department=name).status_code == 400
    assert db_count(app, "faculty") == 0


def test_duplicate_faculty_code_rejected(client, app):
    http_faculty_signup(client, "FAC201")
    resp = http_faculty_signup(client, "FAC201", extra={"professional_email": "other@college.edu"})
    assert resp.status_code == 409 and err(resp)["code"] == "conflict"
    assert "already registered" in err(resp)["message"] and "faculty_code" in err(resp)["fields"]
    assert db_count(app, "faculty") == 1


def test_duplicate_faculty_code_is_case_insensitive(client, app):
    http_faculty_signup(client, "FAC204")
    assert http_faculty_signup(client, "fac204", extra={"professional_email": "x@college.edu"}).status_code == 409
    assert db_count(app, "faculty") == 1


def test_duplicate_faculty_email_rejected(client, app):
    http_faculty_signup(client, "FAC205")
    resp = http_faculty_signup(client, "FAC206", extra={"professional_email": "fac205@college.edu"})
    assert resp.status_code == 409 and "already exists" in err(resp)["message"]
    assert db_count(app, "faculty") == 1


def test_faculty_signup_requires_subjects(client, app):
    resp = http_faculty_signup(client, "FAC207", subjects=" , ")
    assert resp.status_code == 400 and "subjects" in err(resp)["fields"]
    assert http_faculty_signup(client, "FAC207", subjects=[]).status_code == 400
    assert db_count(app, "faculty") == 0


def test_faculty_signup_password_mismatch(client, app):
    resp = http_faculty_signup(client, "FAC208", extra={"confirm_password": "Different1!"})
    assert resp.status_code == 400 and "do not match" in err(resp)["message"]
    assert "confirm_password" in err(resp)["fields"]
    assert db_count(app, "faculty") == 0


def test_faculty_signup_short_password_rejected(client, app):
    resp = http_faculty_signup(client, "FAC209", password="Ab1")
    assert resp.status_code == 400 and "password" in err(resp)["fields"]
    assert db_count(app, "faculty") == 0


# ---------------------------------------------------------------------------
# student signup (captcha, no OTP)
# ---------------------------------------------------------------------------

def test_old_otp_endpoints_are_gone(client):
    for path in ("start", "verify", "register"):
        assert api_post(client, f"/api/auth/signup/student/{path}", json={}).status_code in (404, 405)
    assert client.get("/api/meta").json() == {"app": "Campus Connect"}


def test_student_signup_requires_captcha(client, app):
    sid = find_section(app=app)
    resp = api_post(client, "/api/auth/signup/student", json={
        "college_email": "nocap@college.edu", "full_name": "X", "usn": "1AB21CS900", "section_id": sid,
        "phone": "9999999999", "personal_email": "x@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD})
    assert resp.status_code == 400 and "captcha" in err(resp)["fields"]
    assert db_count(app, "students") == 0


def test_student_full_signup_then_login(client, app):
    sid = find_section(app=app, department="AIML", year="3rd Year", section="A")
    resp = http_student_signup(client, None, "s900@college.edu", "1AB21CS900", sid)
    assert resp.status_code == 201 and resp.json()["ok"] is True
    row = db_one(app, "SELECT usn, section_id, section FROM students WHERE usn = '1AB21CS900'")
    assert row["section_id"] == sid and row["section"] == "A"

    # a captcha is single use: replaying the same solved one is refused
    solved = solve_captcha(client)
    payload = {"college_email": "s905@college.edu", "full_name": "X", "usn": "1AB21CS905", "section_id": sid,
               "phone": "9999999999", "personal_email": "x@example.com", "password": PASSWORD,
               "confirm_password": PASSWORD, **solved}
    assert api_post(client, "/api/auth/signup/student", json=payload).status_code == 201
    payload.update(college_email="s906@college.edu", usn="1AB21CS906")
    replay = api_post(client, "/api/auth/signup/student", json=payload)
    assert replay.status_code == 400 and "captcha" in err(replay)["fields"]

    body = api_login(client, "s900@college.edu", PASSWORD)
    assert body["user"]["role"] == "STUDENT" and body["user"]["student_id"]


def test_student_login_with_usn_identifier(app, client):
    register_student(app, "1AB21CS901")
    body = api_login(client, "1ab21cs901", PASSWORD)
    assert body["user"]["role"] == "STUDENT"


def test_student_signup_existing_email_is_a_conflict(client, app):
    register_student(app, "1AB21CS902", email="dupe@college.edu")
    resp = http_student_signup(client, None, "dupe@college.edu", "1AB21CS907", find_section(app=app))
    assert resp.status_code == 409 and "college_email" in err(resp)["fields"]


def test_student_signup_password_mismatch(client, app):
    sid = find_section(app=app)
    resp = http_student_signup(client, None, "s903@college.edu", "1AB21CS903", sid, confirm="Other1234!")
    assert resp.status_code == 400 and "do not match" in err(resp)["message"]
    assert db_count(app, "students") == 0


def test_student_signup_invalid_fields(client, app):
    sid = find_section(app=app)
    resp = http_student_signup(client, None, "s904@college.edu", "x", sid)
    assert resp.status_code == 400 and "usn" in err(resp)["fields"]
    resp = http_student_signup(client, None, "s904@college.edu", "1AB21CS904", 999999)
    assert resp.status_code == 400 and "section_id" in err(resp)["fields"]
    resp = http_student_signup(client, None, "s904@college.edu", "1AB21CS904", sid, extra={"section_id": "abc"})
    assert resp.status_code == 400 and "section_id" in err(resp)["fields"]
    assert db_count(app, "students") == 0


# ---------------------------------------------------------------------------
# service-level validation (framework-agnostic)
# ---------------------------------------------------------------------------

def test_hash_and_verify_password():
    h = auth_service.hash_password(PASSWORD)
    assert auth_service.verify_password(h, PASSWORD)
    assert not auth_service.verify_password(h, "nope")
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("short")
    with pytest.raises(auth_service.ValidationError):
        auth_service.hash_password("")


@pytest.mark.parametrize("email", ["", "plain", "a@b", "a b@c.com", None])
def test_validate_email_rejects_bad(email):
    with pytest.raises(auth_service.ValidationError):
        auth_service.validate_email(email)


def test_validate_email_normalises():
    assert auth_service.validate_email("A@B.com") == "a@b.com"


@pytest.mark.parametrize("phone", ["", "12345", "abcdefghij", "1" * 16])
def test_validate_phone_rejects_bad(phone):
    with pytest.raises(auth_service.ValidationError):
        auth_service.validate_phone(phone)


def test_validate_usn(app):
    with app.app_context():
        assert auth_service.validate_usn(" 1ab21cs001 ") == "1AB21CS001"
        for bad in ("", "AB", "1AB 21CS", "x" * 16):
            with pytest.raises(auth_service.ValidationError):
                auth_service.validate_usn(bad)


def test_register_student_requires_name_and_valid_contacts(app):
    sid = find_section(app=app)
    base = {"full_name": "A", "usn": "1AB21CS906", "section_id": sid, "phone": "9999999999",
            "personal_email": "a@b.com", "college_email": "a906@college.edu", "password": PASSWORD}
    with app.app_context():
        for key, bad in (("full_name", " "), ("phone", "1"), ("personal_email", "x"), ("college_email", "x")):
            with pytest.raises(auth_service.ValidationError):
                auth_service.register_student(dict(base, **{key: bad}))
        assert queries.get_user_by_email("a906@college.edu") is None


def test_register_student_duplicate_usn_and_email(app):
    register_student(app, "1AB21CS907", email="a907@college.edu")
    sid = find_section(app=app)
    with app.app_context():
        with pytest.raises(auth_service.ConflictError):
            auth_service.register_student({
                "full_name": "A", "usn": "1ab21cs907", "section_id": sid, "phone": "9999999999",
                "personal_email": "a@b.com", "college_email": "another@college.edu", "password": PASSWORD})
        with pytest.raises(auth_service.ConflictError):
            auth_service.register_student({
                "full_name": "A", "usn": "1AB21CS908", "section_id": sid, "phone": "9999999999",
                "personal_email": "a@b.com", "college_email": "a907@college.edu", "password": PASSWORD})


def test_register_faculty_service_validation(app):
    base = {"full_name": "P", "faculty_code": "F9", "department": "AIML",
            "professional_email": "f9@college.edu", "password": PASSWORD, "subjects": ["DSA"]}
    with app.app_context():
        for key, bad in (("full_name", ""), ("faculty_code", ""), ("department", "Nope"),
                         ("professional_email", "bad"), ("subjects", []), ("subjects", [" "])):
            with pytest.raises(auth_service.ValidationError):
                auth_service.register_faculty(dict(base, **{key: bad}))
    assert db_all(app, "SELECT * FROM faculty") == []
