import pytest

from models import queries
from services import auth_service
from tests.conftest import (
    PASSWORD, create_admin, create_faculty, create_student, section_id_for, login_client,
    http_faculty_signup, http_student_signup, flash_text, db_one, db_count, db_all,
)


# ---------------------------------------------------------------------------
# faculty signup / login
# ---------------------------------------------------------------------------

def test_faculty_signup_and_login(client, app):
    resp = http_faculty_signup(client, "FAC200")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert "Registration successful" in flash_text(client)

    row = db_one(app, "SELECT f.department, f.faculty_code FROM faculty f WHERE f.faculty_code = 'FAC200'")
    assert row == {"department": "AIML", "faculty_code": "FAC200"}

    resp = client.post("/login", data={"email": "fac200@college.edu", "password": PASSWORD})
    assert resp.status_code == 302
    resp = client.get("/faculty/dashboard")
    assert resp.status_code == 200


def test_faculty_signup_creates_no_class_assignments(client, app):
    """Classes are never chosen at faculty signup, even if a client forges class fields."""
    http_faculty_signup(client, "FAC210", extra={
        "classes": "1", "section_id": str(section_id_for(app)), "branch": "CSE", "year": "3rd Year",
        "section": "A",
    })
    assert db_count(app, "faculty") == 1
    assert db_count(app, "faculty_assignments") == 0
    assert db_count(app, "faculty_assignment_requests") == 0


@pytest.mark.parametrize("dept", ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"])
def test_faculty_signup_accepts_every_seeded_department(client, app, dept):
    http_faculty_signup(client, "FAC300", department=dept)
    assert db_one(app, "SELECT department FROM faculty WHERE faculty_code = 'FAC300'")["department"] == dept


def test_faculty_department_is_case_insensitive_and_canonicalised(client, app):
    http_faculty_signup(client, "FAC301", department="aiml")
    assert db_one(app, "SELECT department FROM faculty WHERE faculty_code = 'FAC301'")["department"] == "AIML"


@pytest.mark.parametrize("dept", ["CSE", "Physics", "", "AIML; DROP TABLE faculty", "   "])
def test_faculty_signup_rejects_non_admin_departments(client, app, dept):
    resp = http_faculty_signup(client, "FAC302", department=dept)
    assert resp.status_code == 200  # form re-rendered
    assert db_count(app, "faculty") == 0


def test_faculty_signup_rejects_deactivated_department(client, app):
    from services import academic_service
    with app.app_context():
        from models import academic_queries as aq
        dept = aq.list_departments()[0]  # AIDE (alphabetical)
        academic_service.set_active("department", dept["id"], False)
        name = dept["name"]
    http_faculty_signup(client, "FAC303", department=name)
    assert db_count(app, "faculty") == 0


def test_duplicate_faculty_code_rejected(client, app):
    http_faculty_signup(client, "FAC201")
    resp = http_faculty_signup(client, "FAC201", extra={"professional_email": "other@college.edu"})
    assert resp.status_code == 200
    assert b"already registered" in resp.data
    assert db_count(app, "faculty") == 1


def test_duplicate_faculty_code_is_case_insensitive(client, app):
    http_faculty_signup(client, "FAC204")
    http_faculty_signup(client, "fac204", extra={"professional_email": "x@college.edu"})
    assert db_count(app, "faculty") == 1


def test_duplicate_faculty_email_rejected(client, app):
    http_faculty_signup(client, "FAC205")
    resp = http_faculty_signup(client, "FAC206", extra={"professional_email": "fac205@college.edu"})
    assert b"already exists" in resp.data
    assert db_count(app, "faculty") == 1


def test_faculty_signup_requires_subjects(client, app):
    resp = http_faculty_signup(client, "FAC207", subjects=" , ")
    assert b"subject" in resp.data.lower()
    assert db_count(app, "faculty") == 0


def test_faculty_signup_password_mismatch(client, app):
    resp = client.post("/signup/faculty", data={
        "full_name": "P", "faculty_code": "FAC208", "department": "AIML",
        "professional_email": "fac208@college.edu", "subjects": "DSA",
        "password": PASSWORD, "confirm_password": "Different1!",
    })
    assert b"do not match" in resp.data
    assert db_count(app, "faculty") == 0


def test_faculty_signup_short_password_rejected(client, app):
    http_faculty_signup(client, "FAC209", password="Ab1")
    assert db_count(app, "faculty") == 0


def test_wrong_password_rejected(client, app):
    http_faculty_signup(client, "FAC202")
    resp = client.post("/login", data={"email": "fac202@college.edu", "password": "WrongPassw0rd!"},
                       follow_redirects=True)
    assert b"Invalid email or password" in resp.data
    assert client.get("/faculty/dashboard").status_code == 302


def test_unknown_user_login_rejected(client):
    resp = client.post("/login", data={"email": "nobody@college.edu", "password": PASSWORD},
                       follow_redirects=True)
    assert b"Invalid email or password" in resp.data


def test_login_with_faculty_code_identifier(client, app):
    http_faculty_signup(client, "FAC203")
    resp = client.post("/login", data={"email": "fac203", "password": PASSWORD})
    assert resp.status_code == 302
    assert client.get("/faculty/dashboard").status_code == 200


# ---------------------------------------------------------------------------
# student OTP signup flow
# ---------------------------------------------------------------------------

def test_student_otp_flow_wrong_otp_rejected(client, app):
    client.post("/signup/student", data={"college_email": "otpstudent@college.edu"})
    row = db_one(app, "SELECT * FROM otp_sessions WHERE email = ? ORDER BY id DESC LIMIT 1",
                 ("otpstudent@college.edu",))
    assert row is not None
    resp = client.post("/signup/student/verify-otp", data={
        "email": "otpstudent@college.edu", "otp": "000000x",
    }, follow_redirects=True)
    assert b"Incorrect OTP" in resp.data
    assert db_one(app, "SELECT attempt_count FROM otp_sessions WHERE id = ?", (row["id"],))["attempt_count"] == 1


def test_student_details_page_requires_verified_otp(client, app):
    sid = section_id_for(app)
    resp = client.post("/signup/student/details?email=nope@college.edu", data={
        "college_email": "nope@college.edu", "full_name": "X", "usn": "1AB21CS900", "section_id": str(sid),
        "phone": "9999999999", "personal_email": "x@example.com", "password": PASSWORD,
        "confirm_password": PASSWORD,
    })
    assert resp.status_code == 302 and "/signup/student" in resp.headers["Location"]
    assert db_count(app, "students") == 0


def test_student_full_signup_then_login(client, app, captured_otps):
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    resp = http_student_signup(client, captured_otps, "s900@college.edu", "1AB21CS900", sid)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")

    resp = client.post("/login", data={"email": "s900@college.edu", "password": PASSWORD})
    assert resp.status_code == 302
    assert client.get("/student/dashboard").status_code == 200


def test_student_login_with_usn_identifier(client, app):
    create_student(app, "1AB21CS901")
    resp = client.post("/login", data={"email": "1ab21cs901", "password": PASSWORD})
    assert resp.status_code == 302
    assert client.get("/student/dashboard").status_code == 200


def test_no_otp_issued_for_existing_account(client, app, captured_otps):
    create_student(app, "1AB21CS902", email="dupe@college.edu")
    client.post("/signup/student", data={"college_email": "dupe@college.edu"})
    assert "dupe@college.edu" not in captured_otps  # no OTP issued for an existing account


def test_student_signup_password_mismatch(client, app, captured_otps):
    sid = section_id_for(app)
    resp = http_student_signup(client, captured_otps, "s903@college.edu", "1AB21CS903", sid, confirm="Other1234!")
    assert b"do not match" in resp.data
    assert db_count(app, "students") == 0


def test_logout_is_post_and_clears_session(app):
    create_admin(app)
    c = login_client(app, "admin@college.edu")
    assert c.get("/admin/dashboard").status_code == 200
    resp = c.post("/logout")
    assert resp.status_code == 302
    assert c.get("/admin/dashboard").status_code == 302


def test_index_redirects_by_role(app):
    create_admin(app)
    fac = create_faculty(app)
    stu = create_student(app, "1AB21CS904")
    anon = app.test_client()
    assert anon.get("/").headers["Location"].endswith("/login")
    for email, target in (("admin@college.edu", "/admin/dashboard"), (fac["email"], "/faculty/dashboard"),
                          (stu["email"], "/student/dashboard")):
        c = login_client(app, email)
        assert c.get("/").headers["Location"].endswith(target)


# ---------------------------------------------------------------------------
# service-level validation
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


def test_authenticate_rejects_inactive_user(app):
    stu = create_student(app, "1AB21CS905")
    with app.app_context():
        from models.database import get_db
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (stu["user_id"],))
        get_db().commit()
        with pytest.raises(auth_service.ValidationError):
            auth_service.authenticate(stu["email"], PASSWORD)


def test_register_student_requires_name_and_valid_contacts(app):
    sid = section_id_for(app)
    base = {"full_name": "A", "usn": "1AB21CS906", "section_id": sid, "phone": "9999999999",
            "personal_email": "a@b.com", "college_email": "a906@college.edu", "password": PASSWORD}
    with app.app_context():
        for key, bad in (("full_name", " "), ("phone", "1"), ("personal_email", "x"), ("college_email", "x")):
            data = dict(base, **{key: bad})
            with pytest.raises(auth_service.ValidationError):
                auth_service.register_student(data)
        assert queries.get_user_by_email("a906@college.edu") is None


def test_register_student_duplicate_usn_and_email(app):
    create_student(app, "1AB21CS907", email="a907@college.edu")
    sid = section_id_for(app)
    with app.app_context():
        with pytest.raises(auth_service.ValidationError):
            auth_service.register_student({
                "full_name": "A", "usn": "1ab21cs907", "section_id": sid, "phone": "9999999999",
                "personal_email": "a@b.com", "college_email": "another@college.edu", "password": PASSWORD})
        with pytest.raises(auth_service.ValidationError):
            auth_service.register_student({
                "full_name": "A", "usn": "1AB21CS908", "section_id": sid, "phone": "9999999999",
                "personal_email": "a@b.com", "college_email": "a907@college.edu", "password": PASSWORD})


def test_register_faculty_service_validation(app):
    with app.app_context():
        base = {"full_name": "P", "faculty_code": "F9", "department": "AIML",
                "professional_email": "f9@college.edu", "password": PASSWORD, "subjects": ["DSA"]}
        for key, bad in (("full_name", ""), ("faculty_code", ""), ("department", "Nope"),
                         ("professional_email", "bad"), ("subjects", []), ("subjects", [" "])):
            with pytest.raises(auth_service.ValidationError):
                auth_service.register_faculty(dict(base, **{key: bad}))
        assert db_all(app, "SELECT * FROM faculty") == []
