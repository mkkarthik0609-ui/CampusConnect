"""Shared test fixtures and helpers (see docs/api/ARCHITECTURE.md, section "Tests").

Every test gets its own FastAPI app on a throw-away PostgreSQL database (cloned from a migrated template
database; TEST_DATABASE_ADMIN_URL points at a scratch server, default postgresql://postgres@127.0.0.1:54329),
CSRF disabled. Service-level
helpers (`make_admin`, `register_faculty`, `register_student`, ...) take the `app` as first argument
and create rows directly through the services; HTTP helpers take a `TestClient`.
"""
import base64
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Safety net: anything that (accidentally) falls back to env-based settings must never reach a real database
# (the repo-root .env holds the Neon URLs; python-dotenv never overrides variables that are already set).
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_URL_POOLED"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import psycopg  # noqa: E402
from psycopg import sql as pgsql  # noqa: E402

from api import db as dbmod  # noqa: E402
from api.db import db_session  # noqa: E402
from api.main import create_app  # noqa: E402
from api.settings import Settings  # noqa: E402
from models import queries  # noqa: E402
from models import academic_queries as aq  # noqa: E402
from api.settings import use_settings  # noqa: E402
from services import auth_service, assignment_service, captcha_service  # noqa: E402

def _make_png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def _make_docx():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w/>")
    return buf.getvalue()


REAL_PNG = _make_png()
REAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
REAL_DOCX = _make_docx()

PASSWORD = "Passw0rd!x"
ADMIN_EMAIL = "mkkarthik0609@gmail.com"
TEST_SECRET = "test-secret-key-test-secret-key-0123456789"


def make_settings(tmp_path, **overrides):
    """Settings for a throw-away app. Pass overrides such as csrf_enabled=True."""
    url = overrides.pop("database_url", None) or new_test_db_url()
    values = dict(
        database_url=url,
        database_url_direct=url,
        testing=True,
        csrf_enabled=False,
        enable_scheduler=False,
        seed_extra_branches=False,  # tests assume the CSE-only default tree
        secret_key=TEST_SECRET,
        frontend_dist=str(tmp_path / "no-frontend-dist"),
    )
    values.update(overrides)
    return Settings(**values)


ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "postgresql://postgres@127.0.0.1:54329/postgres")
_DBNAME = "cc_test_" + os.environ.get("PYTEST_XDIST_WORKER", "main")
_TABLES: list = []


def _admin_conn():
    return psycopg.connect(ADMIN_URL, autocommit=True)


def _db_url():
    return ADMIN_URL.rsplit("/", 1)[0] + "/" + _DBNAME


@pytest.fixture(scope="session", autouse=True)
def _worker_database():
    """One migrated database per pytest process; every test starts from emptied tables (TRUNCATE is far
    cheaper than cloning a database per test)."""
    with _admin_conn() as admin:
        admin.execute(pgsql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(pgsql.Identifier(_DBNAME)))
        admin.execute(pgsql.SQL("CREATE DATABASE {}").format(pgsql.Identifier(_DBNAME)))
    dbmod.run_migrations(Settings(testing=True, database_url=_db_url(), database_url_direct=_db_url()))
    with psycopg.connect(_db_url(), autocommit=True) as c:
        _TABLES.extend(r[0] for r in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'schema_migrations'"))
    yield
    dbmod.dispose_pools()
    with _admin_conn() as admin:
        admin.execute(pgsql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(pgsql.Identifier(_DBNAME)))


def new_test_db_url():
    return _db_url()


@pytest.fixture(autouse=True)
def _empty_tables():
    yield
    with psycopg.connect(_db_url(), autocommit=True) as c:
        c.execute("TRUNCATE " + ", ".join(_TABLES) + " RESTART IDENTITY CASCADE")


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch):
    """Argon2id is deliberately slow; tests use the cheapest legal parameters (verification is parameter-agnostic)."""
    from argon2 import PasswordHasher

    monkeypatch.setattr(auth_service, "_hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
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


def put_blob(app, path, data):
    """Store a file the way uploads are stored (table file_blobs)."""
    from services import storage
    with _session(app) as db:
        storage.put(path, data)
        db.commit()


def blob_paths(app, prefix=""):
    return [r["path"] for r in db_all(app, "SELECT path FROM file_blobs WHERE path LIKE ? ORDER BY path", (prefix + "%",))]


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
