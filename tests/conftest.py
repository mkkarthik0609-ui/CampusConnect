"""Shared test fixtures and helpers (see docs/api/ARCHITECTURE.md, section "Tests").

Every test gets its own FastAPI app on a temp SQLite file + upload dir, CSRF disabled. Service-level
helpers (`make_admin`, `register_faculty`, `register_student`, ...) take the `app` as first argument
and create rows directly through the services; HTTP helpers take a `TestClient`.
"""
import base64
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Safety net: anything that (accidentally) falls back to env-based settings must not touch the real DB.
_IMPORT_DB_FD, _IMPORT_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_IMPORT_DB_FD)
os.environ["DATABASE_PATH"] = _IMPORT_DB_PATH

from fastapi.testclient import TestClient  # noqa: E402

from api.db import db_session  # noqa: E402
from api.main import create_app  # noqa: E402
from api.settings import Settings  # noqa: E402
from models import queries  # noqa: E402
from models import academic_queries as aq  # noqa: E402
from api.settings import use_settings  # noqa: E402
from services import auth_service, assignment_service, captcha_service  # noqa: E402

PASSWORD = "Passw0rd!x"
ADMIN_EMAIL = "admin@college.edu"
TEST_SECRET = "test-secret-key-test-secret-key-0123456789"


def make_settings(tmp_path, **overrides):
    """Settings for a throw-away app. Pass overrides such as csrf_enabled=True."""
    values = dict(
        testing=True,
        csrf_enabled=False,
        enable_scheduler=False,
        secret_key=TEST_SECRET,
        database_path=str(tmp_path / "test.db"),
        upload_root=str(tmp_path / "uploads"),
        frontend_dist=str(tmp_path / "no-frontend-dist"),
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch):
    """scrypt is deliberately slow; use a cheap PBKDF2 for test speed (verification is method-agnostic)."""
    from werkzeug.security import generate_password_hash as real

    def cheap(password, method="pbkdf2:sha256:1000", salt_length=8):
        return real(password, method=method, salt_length=salt_length)

    monkeypatch.setattr(auth_service, "generate_password_hash", cheap)
    monkeypatch.setattr(auth_service, "_DUMMY_HASH", None)


@pytest.fixture
def app(tmp_path):
    return create_app(make_settings(tmp_path))


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def csrf_token(client):
    """The client's current CSRF token (read from its signed cookie, else from /api/auth/session)."""
    raw = client.cookies.get("cc_session")
    if raw:
        try:
            payload = raw.split(".")[0]
            data = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
            if data.get("csrf_token"):
                return data["csrf_token"]
        except (ValueError, IndexError):
            pass
    return client.get("/api/auth/session").json()["csrf_token"]


def read_session(client):
    """Decode the client's signed ``cc_session`` cookie into a dict ({} when absent)."""
    raw = client.cookies.get("cc_session")
    if not raw:
        return {}
    payload = raw.split(".")[0]
    return json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))


def set_session_cookie(client, raw_value):
    """Replace the session cookie with an arbitrary raw value (same domain the app's cookie uses)."""
    client.cookies.clear()
    client.cookies.set("cc_session", raw_value, domain="testserver.local", path="/")


def write_session(client, data, secret=None):
    """Replace the client's session cookie with a *validly signed* one holding `data` (simulates a
    client holding stale/edited server state; pass a different `secret` to simulate a forgery)."""
    import itsdangerous
    secret = secret or client.app.state.settings.secret_key
    value = itsdangerous.TimestampSigner(secret).sign(base64.b64encode(json.dumps(data).encode("utf-8")))
    set_session_cookie(client, value.decode("utf-8"))


def _send(client, method, url, **kw):
    headers = dict(kw.pop("headers", None) or {})
    headers.setdefault("X-CSRFToken", csrf_token(client))
    return client.request(method, url, headers=headers, **kw)


def api_post(client, url, json=None, **kw):
    return _send(client, "POST", url, json=json, **kw)


def api_put(client, url, json=None, **kw):
    return _send(client, "PUT", url, json=json, **kw)


def api_patch(client, url, json=None, **kw):
    return _send(client, "PATCH", url, json=json, **kw)


def api_delete(client, url, **kw):
    return _send(client, "DELETE", url, **kw)


def api_login(client, identifier, password=PASSWORD):
    """POST /api/auth/login; asserts success and returns the JSON body."""
    resp = api_post(client, "/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, f"login failed for {identifier}: {resp.status_code} {resp.text}"
    return resp.json()


def login_client(app, email, password=PASSWORD):
    """A fresh TestClient (own cookie jar) that is logged in."""
    c = TestClient(app)
    api_login(c, email, password)
    return c


# ---------------------------------------------------------------------------
# data helpers (service level; each opens a db_session bound to the app's settings)
# ---------------------------------------------------------------------------

def _session(app):
    return db_session(app.state.settings if app is not None else None)


def find_section(branch="CSE", department="AIML", year="3rd Year", section="A", app=None):
    """Section id of a class in the seeded hierarchy (defaults: CSE / AIML / 3rd Year / A)."""
    with _session(app):
        combo = aq.find_combo_by_names(branch, department, year, section)
        assert combo is not None, f"no such class: {branch}/{department}/{year}/{section}"
        return combo["section_id"]


def section_id_for(app, department="AIML", year="3rd Year", section="A", branch="CSE"):
    return find_section(branch, department, year, section, app=app)


def make_admin(app, email=ADMIN_EMAIL, password=PASSWORD, name="Admin One"):
    """Create an ADMIN directly (idempotent). Returns the user id."""
    with _session(app):
        existing = queries.get_user_by_email(email)
        if existing:
            return existing["id"]
        return queries.create_user("ADMIN", email, auth_service.hash_password(password), name)


create_admin = make_admin


def register_faculty(app, code="FAC001", department="AIML", password=PASSWORD, name=None, subjects=("DSA",)):
    """Register a faculty member through the real service. Returns ids + credentials."""
    email = f"{code.lower()}@college.edu"
    with _session(app):
        user_id = auth_service.register_faculty({
            "full_name": name or f"Prof {code}", "faculty_code": code, "department": department,
            "professional_email": email, "password": password, "subjects": list(subjects),
        })
        faculty = queries.get_faculty_by_user_id(user_id)
        return {"user_id": user_id, "faculty_id": faculty["id"], "email": email,
                "code": code, "password": password}


create_faculty = register_faculty


def register_student(app, usn="1AB21CS001", section_id=None, password=PASSWORD, name=None, email=None,
                     phone="9999999999"):
    """Register a student through the real service. Returns ids + credentials."""
    if section_id is None:
        section_id = find_section(app=app)
    email = email or f"{usn.lower()}@college.edu"
    with _session(app):
        user_id = auth_service.register_student({
            "full_name": name or f"Student {usn}", "usn": usn, "section_id": section_id, "phone": phone,
            "personal_email": f"{usn.lower()}@example.com", "college_email": email, "password": password,
        })
        student = queries.get_student_by_user_id(user_id)
        return {"user_id": user_id, "student_id": student["id"], "email": email,
                "usn": usn.upper(), "password": password, "section_id": section_id}


create_student = register_student


def assign(app, faculty, section_id, admin_user_id):
    """Admin-assign a faculty dict (from register_faculty) to a section id."""
    with _session(app):
        return assignment_service.admin_assign(faculty["faculty_id"], section_id, admin_user_id)


def unassign(app, faculty, section_id, admin_user_id):
    with _session(app):
        a = aq.get_assignment_for(faculty["faculty_id"], section_id)
        return assignment_service.admin_remove(a["id"], admin_user_id)


def db_one(app, sql, params=()):
    with _session(app) as db:
        row = db.execute(sql, params).fetchone()
        return dict(row) if row else None


def db_all(app, sql, params=()):
    with _session(app) as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]


def db_exec(app, sql, params=()):
    with _session(app) as db:
        db.execute(sql, params)
        db.commit()


def db_count(app, table, where="1=1", params=()):
    return db_one(app, f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params)["c"]


# ---------------------------------------------------------------------------
# signup over HTTP
# ---------------------------------------------------------------------------

def solve_captcha(client, answer="TEST42", ip_header=None):
    """GET a real captcha challenge, then store the HMAC of a known `answer` for it (the real answer is
    only known to the server). Returns the {captcha_id, captcha_answer} fields to put in a request."""
    resp = client.get("/api/auth/captcha")
    assert resp.status_code == 200, resp.text
    challenge_id = resp.json()["captcha_id"]
    app = client.app
    with use_settings(app.state.settings):
        digest = captcha_service._hash_answer(challenge_id, captcha_service.normalize_answer(answer))
    db_exec(app, "UPDATE captcha_challenges SET answer_hash = ? WHERE id = ?", (digest, challenge_id))
    return {"captcha_id": challenge_id, "captcha_answer": answer}


def http_student_signup(client, captured, email, usn, section_id, password=PASSWORD, extra=None,
                        full_name="New Student", phone="9876543210", confirm=None):
    """Drive the real captcha-protected student signup. Returns the response.
    `captured` is unused (kept for old call sites)."""
    data = {
        "college_email": email, "full_name": full_name, "usn": usn, "section_id": section_id,
        "phone": phone, "personal_email": f"p-{usn.lower()}@example.com",
        "password": password, "confirm_password": password if confirm is None else confirm,
    }
    data.update(solve_captcha(client))
    data.update(extra or {})
    return api_post(client, "/api/auth/signup/student", json=data)


def http_faculty_signup(client, code, department="AIML", password=PASSWORD, extra=None, subjects="DSA, OS"):
    data = {
        "full_name": f"Prof {code}", "faculty_code": code, "department": department,
        "professional_email": f"{code.lower()}@college.edu", "subjects": subjects,
        "password": password, "confirm_password": password,
    }
    data.update(solve_captcha(client))
    data.update(extra or {})
    return api_post(client, "/api/auth/signup/faculty", json=data)


# ---------------------------------------------------------------------------
# ready-made world fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin(app):
    uid = make_admin(app)
    return {"user_id": uid, "email": ADMIN_EMAIL, "password": PASSWORD}


@pytest.fixture
def admin_client(app, admin):
    return login_client(app, admin["email"])
