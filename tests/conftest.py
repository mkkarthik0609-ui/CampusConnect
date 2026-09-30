import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# `app.py` builds a module-level app at import time. Point it at a throw-away database
# *before* anything imports config/app so the real database.db is never touched by tests.
_IMPORT_DB_FD, _IMPORT_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_IMPORT_DB_FD)
os.environ["DATABASE_PATH"] = _IMPORT_DB_PATH

from config import Config  # noqa: E402
from app import create_app  # noqa: E402
from models import queries  # noqa: E402
from models import academic_queries as aq  # noqa: E402
from models.database import get_db  # noqa: E402
from services import auth_service, assignment_service, otp_service  # noqa: E402

PASSWORD = "Passw0rd!x"
ADMIN_EMAIL = "admin@college.edu"


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False


def make_config(db_path, upload_root):
    class _Cfg(TestConfig):
        DATABASE_PATH = str(db_path)
        UPLOAD_ROOT = str(upload_root)
        PROFILE_STUDENT_DIR = os.path.join(str(upload_root), "profile", "students")
        PROFILE_FACULTY_DIR = os.path.join(str(upload_root), "profile", "faculty")
        CHAT_UPLOAD_DIR = os.path.join(str(upload_root), "chat")

    return _Cfg


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch):
    """scrypt is deliberately slow; use a cheap PBKDF2 for test speed (verification is method-agnostic)."""
    from werkzeug.security import generate_password_hash as real

    def cheap(password, method="pbkdf2:sha256:1000", salt_length=8):
        return real(password, method=method, salt_length=salt_length)

    for mod in (auth_service, otp_service):
        if hasattr(mod, "generate_password_hash"):
            monkeypatch.setattr(mod, "generate_password_hash", cheap)


@pytest.fixture
def app(tmp_path):
    application = create_app(make_config(tmp_path / "test.db", tmp_path / "uploads"))
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# data helpers (all take the Flask app and open their own app context)
# ---------------------------------------------------------------------------

def section_id_for(app, department="AIML", year="3rd Year", section="A", branch="CSE"):
    with app.app_context():
        combo = aq.find_combo_by_names(branch, department, year, section)
        assert combo is not None, f"no such class: {branch}/{department}/{year}/{section}"
        return combo["section_id"]


def create_admin(app, email=ADMIN_EMAIL, password=PASSWORD, name="Admin One"):
    with app.app_context():
        existing = queries.get_user_by_email(email)
        if existing:  # idempotent: tests and fixtures may both ask for "the" admin
            return existing["id"]
        return queries.create_user("ADMIN", email, auth_service.hash_password(password), name)


def create_faculty(app, code="FAC001", department="AIML", password=PASSWORD, name=None, subjects=("DSA",)):
    """Register a faculty member through the real service. Returns dict of ids + credentials."""
    email = f"{code.lower()}@college.edu"
    with app.app_context():
        user_id = auth_service.register_faculty({
            "full_name": name or f"Prof {code}", "faculty_code": code, "department": department,
            "professional_email": email, "password": password, "subjects": list(subjects),
        })
        faculty = queries.get_faculty_by_user_id(user_id)
        return {"user_id": user_id, "faculty_id": faculty["id"], "email": email,
                "code": code, "password": password}


def create_student(app, usn="1AB21CS001", section_id=None, password=PASSWORD, name=None, email=None,
                   phone="9999999999"):
    """Register a student through the real service. Returns dict of ids + credentials."""
    if section_id is None:
        section_id = section_id_for(app)
    email = email or f"{usn.lower()}@college.edu"
    with app.app_context():
        user_id = auth_service.register_student({
            "full_name": name or f"Student {usn}", "usn": usn, "section_id": section_id, "phone": phone,
            "personal_email": f"{usn.lower()}@example.com", "college_email": email, "password": password,
        })
        student = queries.get_student_by_user_id(user_id)
        return {"user_id": user_id, "student_id": student["id"], "email": email,
                "usn": usn.upper(), "password": password, "section_id": section_id}


def assign(app, faculty, section_id, admin_user_id):
    """Admin-assign a faculty dict (from create_faculty) to a section id."""
    with app.app_context():
        return assignment_service.admin_assign(faculty["faculty_id"], section_id, admin_user_id)


def unassign(app, faculty, section_id, admin_user_id):
    with app.app_context():
        a = aq.get_assignment_for(faculty["faculty_id"], section_id)
        return assignment_service.admin_remove(a["id"], admin_user_id)


def login_client(app, email, password=PASSWORD):
    """A fresh test client (own cookie jar) that is logged in."""
    c = app.test_client()
    resp = c.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 302, f"login failed for {email}: {resp.status_code}"
    flashes(c)  # drop the "Welcome back" flash so tests only see their own messages
    return c


def flashes(client):
    """Return and clear the pending flash messages of a client's session as [(category, message)]."""
    with client.session_transaction() as sess:
        return [tuple(f) for f in sess.pop("_flashes", [])]


def flash_text(client):
    return " | ".join(m for _, m in flashes(client))


def db_one(app, sql, params=()):
    with app.app_context():
        row = get_db().execute(sql, params).fetchone()
        return dict(row) if row else None


def db_all(app, sql, params=()):
    with app.app_context():
        return [dict(r) for r in get_db().execute(sql, params).fetchall()]


def db_exec(app, sql, params=()):
    with app.app_context():
        db = get_db()
        db.execute(sql, params)
        db.commit()


def db_count(app, table, where="1=1", params=()):
    return db_one(app, f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params)["c"]


@pytest.fixture
def captured_otps(monkeypatch):
    """Capture the plaintext OTP the signup route generates (it is otherwise only hashed)."""
    box = {}
    original = otp_service.generate_and_store_otp

    def _wrapper(email):
        otp = original(email)
        box[email] = otp
        return otp

    monkeypatch.setattr(otp_service, "generate_and_store_otp", _wrapper)
    return box


def http_student_signup(client, captured, email, usn, section_id, password=PASSWORD, extra=None,
                        full_name="New Student", phone="9876543210", confirm=None):
    """Drive the real 3-step student signup. Returns the response of the final details POST."""
    resp = client.post("/signup/student", data={"college_email": email})
    assert resp.status_code == 302, "OTP step should redirect to verify page"
    resp = client.post("/signup/student/verify-otp", data={"email": email, "otp": captured[email]})
    assert resp.status_code == 302, "OTP verification should redirect to details page"
    data = {
        "college_email": email, "full_name": full_name, "usn": usn, "section_id": str(section_id),
        "phone": phone, "personal_email": f"p-{usn.lower()}@example.com",
        "password": password, "confirm_password": password if confirm is None else confirm,
    }
    data.update(extra or {})
    return client.post(f"/signup/student/details?email={email}", data=data)


def http_faculty_signup(client, code, department="AIML", password=PASSWORD, extra=None, subjects="DSA, OS"):
    data = {
        "full_name": f"Prof {code}", "faculty_code": code, "department": department,
        "professional_email": f"{code.lower()}@college.edu", "subjects": subjects,
        "password": password, "confirm_password": password,
    }
    data.update(extra or {})
    return client.post("/signup/faculty", data=data)


# ---------------------------------------------------------------------------
# ready-made world fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin(app):
    uid = create_admin(app)
    return {"user_id": uid, "email": ADMIN_EMAIL, "password": PASSWORD}


@pytest.fixture
def admin_client(app, admin):
    return login_client(app, admin["email"])
