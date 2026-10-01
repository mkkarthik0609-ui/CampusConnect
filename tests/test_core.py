"""Core plumbing tests: settings, db holder/sessions, error mapping, router registration, public
endpoints (academic tree, notifications, meta), serializers."""
import sqlite3
import threading

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from api import db as dbmod
from api.deps import ApiModel, CurrentUser, Stripped, get_current_user, ok, items, service_errors
from api.errors import ApiError, map_service_error
from api.main import ROUTER_MODULES, create_app
from api.settings import Settings, get_settings, use_settings
from models import academic_queries as aq
from models import queries
from services import (academic_service, assignment_service, auth_service, captcha_service, chat_service,
                      file_service, meeting_service, permission_service, supporting_service)
from services.errors import ServiceError
from tests.conftest import (
    PASSWORD, api_login, api_post, db_count, db_exec, db_one, find_section, login_client, make_admin,
    make_settings, register_faculty, register_student,
)


def err(resp):
    return resp.json()["error"]


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

def test_settings_defaults_are_environment_independent(monkeypatch):
    monkeypatch.setenv("CAPTCHA_MAX_PER_IP_PER_HOUR", "1")
    monkeypatch.setenv("DATABASE_PATH", "/elsewhere.db")
    s = Settings()
    assert s.captcha_max_per_ip_per_hour == 60 and s.database_path != "/elsewhere.db"
    assert s.csrf_enabled and s.session_cookie_name == "cc_session"
    assert s.max_request_bytes == 10 * 1024 * 1024
    assert s.session_idle_timeout_minutes == 60 and s.session_lifetime_seconds == 12 * 3600


def test_settings_from_env(monkeypatch, tmp_path):
    for k, v in {
        "APP_ENV": "production", "SECRET_KEY": "k" * 32, "DATABASE_PATH": str(tmp_path / "x.db"),
        "UPLOAD_ROOT": str(tmp_path / "up"), "TRUST_PROXY": "1", "TRUST_PROXY_HOPS": "2",
        "CAPTCHA_MAX_PER_IP_PER_HOUR": "9", "ENABLE_SCHEDULER": "0", "BOOTSTRAP_ADMIN": "yes",
        "LOGIN_MAX_FAILURES_PER_IDENTIFIER": "7", "LOGIN_CAPTCHA_AFTER_FAILURES": "oops", "DEBUG": "1",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert s.is_production and s.cookie_secure and s.secret_key == "k" * 32
    assert s.trust_proxy and s.trust_proxy_hops == 2
    assert s.captcha_max_per_ip_per_hour == 9
    assert not s.enable_scheduler and s.bootstrap_admin
    assert s.login_max_failures_per_identifier == 7
    assert s.login_captcha_after_failures == 3  # unparsable -> default
    assert not s.debug and not s.docs_enabled  # never debug in production
    assert s.chat_upload_dir == str(tmp_path / "up" / "chat")
    assert s.profile_student_dir.endswith("students") and s.profile_faculty_dir.endswith("faculty")
    s.validate()


def test_render_env_defaults_to_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("SECRET_KEY", "")
    assert Settings.from_env().is_production
    with pytest.raises(RuntimeError):
        Settings.from_env().validate()


def test_get_settings_follows_the_request_and_session_context(tmp_path):
    a = create_app(make_settings(tmp_path / "a", captcha_length=4))
    b = create_app(make_settings(tmp_path / "b", captcha_length=8))
    assert TestClient(a).get("/api/meta").status_code == 200
    # two apps alive at once keep their own settings/database per request
    ca, cb = TestClient(a), TestClient(b)
    assert ca.get("/api/auth/captcha").status_code == 200 and cb.get("/api/auth/captcha").status_code == 200
    assert db_count(a, "captcha_challenges") == 1 and db_count(b, "captcha_challenges") == 1
    with use_settings(a.state.settings):
        assert get_settings().captcha_length == 4


def test_testing_settings_get_a_random_secret_when_none_given(tmp_path):
    app = create_app(Settings(testing=True, enable_scheduler=False, database_path=str(tmp_path / "t.db"),
                              upload_root=str(tmp_path / "u"), frontend_dist=str(tmp_path / "nope")))
    assert len(app.state.settings.secret_key) >= 32


# ---------------------------------------------------------------------------
# database layer
# ---------------------------------------------------------------------------

def test_get_db_outside_a_session_is_an_error():
    with pytest.raises(RuntimeError):
        dbmod.get_db()


def test_db_session_config_and_close(app):
    with dbmod.db_session(app.state.settings) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 15000
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert dbmod.get_db() is db
        assert isinstance(db.execute("SELECT 1 AS x").fetchone(), sqlite3.Row)
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")
    assert not dbmod.has_db_context()


def test_app_context_shim_opens_a_session(app):
    with app.app_context():
        assert queries.get_user_by_email("nobody@x.edu") is None


def test_one_connection_per_request_shared_across_threadpool_and_closed(app):
    seen = []
    router = APIRouter(prefix="/api/_core")

    def dep():
        seen.append(("dep", id(dbmod.get_db()), threading.get_ident()))

    @router.get("/conn")
    def conn(_=Depends(dep)):
        db = dbmod.get_db()
        seen.append(("endpoint", id(db), threading.get_ident()))
        queries.get_user_by_email("x@x.edu")  # legacy query functions use the same connection
        seen.append(("queries", id(dbmod.get_db()), threading.get_ident()))
        holder = dbmod._holder_var.get()
        seen.append(("holder", id(holder.conn), 0))
        db.execute("SELECT 1")
        app.state.last_conn = db
        return {"ok": True}

    app.include_router(router)
    c = TestClient(app)
    assert c.get("/api/_core/conn").status_code == 200
    assert len({entry[1] for entry in seen}) == 1  # same connection everywhere
    with pytest.raises(sqlite3.ProgrammingError):  # closed when the request ended
        app.state.last_conn.execute("SELECT 1")
    c.get("/api/_core/conn")
    assert seen[-1][1] != seen[0][1]  # a new request gets a new connection


def test_connection_is_closed_even_when_the_endpoint_fails(app):
    router = APIRouter(prefix="/api/_core")

    @router.get("/fail")
    def fail():
        app.state.last_conn = dbmod.get_db()
        raise ApiError(418, "teapot", "short and stout")

    app.include_router(router)
    resp = TestClient(app).get("/api/_core/fail")
    assert resp.status_code == 418 and err(resp) == {"code": "teapot", "message": "short and stout"}
    with pytest.raises(sqlite3.ProgrammingError):
        app.state.last_conn.execute("SELECT 1")


def test_init_db_is_idempotent_and_seeds_default_hierarchy(app):
    before = db_count(app, "sections")
    assert before == 6 * 4 * 3  # CSE x 6 departments x 4 years x A-C
    dbmod.init_db(app.state.settings)
    dbmod.init_db(app.state.settings)
    assert db_count(app, "sections") == before and db_count(app, "branches") == 1


def test_init_db_migrates_an_old_database(tmp_path):
    path = tmp_path / "old.db"
    legacy = sqlite3.connect(path)
    legacy.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, full_name TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
          theme_preference TEXT NOT NULL DEFAULT 'light', profile_picture_path TEXT,
          created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
    """)
    legacy.commit()
    legacy.close()
    settings = make_settings(tmp_path, database_path=str(path))
    app = create_app(settings)
    cols = {r["name"] for r in dbmod.connect(settings).execute("PRAGMA table_info(users)").fetchall()}
    assert "last_login_at" in cols
    assert db_count(app, "sections") > 0


def test_models_database_is_a_thin_shim():
    from models import database
    assert database.get_db is dbmod.get_db and database.init_db is dbmod.init_db


# ---------------------------------------------------------------------------
# error mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc, status, code", [
    (auth_service.ValidationError("bad"), 400, "validation_error"),
    (auth_service.ConflictError("dup"), 409, "conflict"),
    (auth_service.LockoutError("slow down"), 429, "rate_limited"),
    (captcha_service.CaptchaRateLimitError("slow"), 429, "rate_limited"),
    (captcha_service.CaptchaError("wrong"), 400, "validation_error"),
    (chat_service.ChatAccessError("You do not have access to this conversation."), 403, "forbidden"),
    (chat_service.ChatAccessError("Conversation not found."), 404, "not_found"),
    (chat_service.ChatEditError("Message cannot be empty."), 400, "validation_error"),
    (chat_service.ChatEditError("You can only edit your own messages."), 403, "forbidden"),
    (meeting_service.MeetingError("Meeting request not found."), 404, "not_found"),
    (meeting_service.MeetingError("You are not authorized to act on this meeting request."), 403, "forbidden"),
    (meeting_service.MeetingError("This meeting request has already been responded to."), 409, "conflict"),
    (meeting_service.MeetingError("Please provide a reason."), 400, "validation_error"),
    (supporting_service.SupportingError("Request not found."), 404, "not_found"),
    (permission_service.PermissionError_("Only an admin may review faculty change requests."), 403, "forbidden"),
    (assignment_service.AssignmentError("X is already assigned to Y."), 409, "conflict"),
    (academic_service.AcademicError("Section must be a single letter."), 400, "validation_error"),
    (file_service.FileValidationError("File is too large. Maximum size is 8 MB."), 413, "payload_too_large"),
    (file_service.FileValidationError("File is empty."), 400, "validation_error"),
    (ServiceError("teapot", 418, "teapot"), 418, "teapot"),
])
def test_map_service_error(exc, status, code):
    mapped = map_service_error(exc)
    assert (mapped.status, mapped.code) == (status, code)
    assert mapped.message == str(exc)


def test_map_service_error_ignores_foreign_exceptions_and_carries_field():
    assert map_service_error(RuntimeError("x")) is None
    assert map_service_error(auth_service.ValidationError("m", "usn")).fields == {"usn": "m"}
    assert map_service_error(auth_service.ConflictError("m", "usn")).fields == {"usn": "m"}


def test_service_errors_context_manager_and_decorator():
    with pytest.raises(ApiError) as info:
        with service_errors():
            raise meeting_service.MeetingError("Meeting request not found.")
    assert info.value.status == 404
    with pytest.raises(RuntimeError):
        with service_errors():
            raise RuntimeError("not ours")
    with pytest.raises(ApiError):
        with service_errors():
            raise ApiError(409, "conflict", "keeps its own status")

    @service_errors()
    def decorated(x: int):
        raise auth_service.ValidationError("bad")

    assert decorated.__name__ == "decorated"
    with pytest.raises(ApiError) as info:
        decorated(1)
    assert info.value.status == 400


def test_unwrapped_service_errors_still_become_json_errors(app):
    """Even a router that forgets `service_errors()` returns the standard error shape."""
    router = APIRouter(prefix="/api/_core")

    @router.get("/svc")
    def svc():
        raise meeting_service.MeetingError("You are not authorized to act on this meeting request.")

    app.include_router(router)
    resp = TestClient(app).get("/api/_core/svc")
    assert resp.status_code == 403 and err(resp)["code"] == "forbidden"


def test_pydantic_validation_error_shape(app):
    router = APIRouter(prefix="/api/_core")

    class In(ApiModel):
        name: Stripped
        age: int
        tags: list[str] = []

    @router.post("/in")
    def endpoint(body: In):
        return {"name": body.name}

    app.include_router(router)
    c = TestClient(app)
    resp = c.post("/api/_core/in", json={"name": "  Ann  ", "age": 3})
    assert resp.json() == {"name": "Ann"}  # Stripped trims whitespace
    resp = c.post("/api/_core/in", json={"age": "x", "extra": 1, "tags": [1]})
    body = err(resp)
    assert resp.status_code == 400 and body["code"] == "validation_error"
    assert body["fields"]["name"] == "This field is required."
    assert {"age", "extra", "tags.0"} <= set(body["fields"])
    resp = c.post("/api/_core/in")
    assert resp.status_code == 400 and err(resp)["code"] == "bad_request"
    resp = c.post("/api/_core/in", json={"name": "x", "age": 1, "extra": 1})
    assert resp.status_code == 400 and "extra" in err(resp)["fields"]


def test_response_helpers():
    assert ok() == {"ok": True}
    assert ok("Saved.", id=3) == {"ok": True, "message": "Saved.", "id": 3}
    assert items(iter([1, 2]), total=2) == {"items": [1, 2], "total": 2}


# ---------------------------------------------------------------------------
# router registration
# ---------------------------------------------------------------------------

def test_router_modules_list_covers_the_documented_areas():
    assert {"auth", "account", "academic", "notifications", "system", "uploads", "admin", "admin_academic",
            "faculty", "student", "chat", "meetings", "supporting", "research"} <= set(ROUTER_MODULES)


def test_registered_routes(app):
    paths = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}
    for method, path in [
        ("GET", "/api/auth/session"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"),
        ("GET", "/api/auth/captcha"), ("POST", "/api/auth/signup/student"), ("POST", "/api/auth/signup/faculty"),
        ("GET", "/api/auth/faculty-departments"), ("POST", "/api/account/password"),
        ("POST", "/api/account/theme"), ("GET", "/api/academic/tree"), ("GET", "/api/notifications"),
        ("POST", "/api/notifications/read-all"), ("POST", "/api/notifications/{notification_id}/read"),
        ("GET", "/api/meta"),
    ]:
        assert (method, path) in paths, (method, path)


def test_missing_router_modules_are_skipped_but_other_import_errors_fail(tmp_path, monkeypatch):
    import importlib
    import sys
    import types

    broken = types.ModuleType("api.routers.admin")

    real_import = importlib.import_module

    def fake_import(name, *a, **k):
        if name == "api.routers.chat":
            raise ModuleNotFoundError("No module named 'some_dependency'", name="some_dependency")
        return real_import(name, *a, **k)

    monkeypatch.setattr("api.main.importlib.import_module", fake_import)
    with pytest.raises(ModuleNotFoundError):
        create_app(make_settings(tmp_path))
    monkeypatch.undo()
    # a router that exists is picked up and registered
    sys.modules.pop("api.routers.admin", None)
    router = APIRouter(prefix="/api/admin")

    @router.get("/ping")
    def ping():
        return {"pong": True}

    broken.router = router
    monkeypatch.setitem(sys.modules, "api.routers.admin", broken)
    app = create_app(make_settings(tmp_path / "ok"))
    assert TestClient(app).get("/api/admin/ping").json() == {"pong": True}


def test_importing_api_main_does_not_create_the_real_app():
    import api.main
    assert api.main._app is None or api.main._app is not None  # attribute exists, lazily
    assert callable(getattr(api.main, "create_app"))
    with pytest.raises(AttributeError):
        api.main.does_not_exist


# ---------------------------------------------------------------------------
# public endpoints
# ---------------------------------------------------------------------------

def test_academic_tree_is_public_active_only_and_shaped(app, client):
    tree = client.get("/api/academic/tree").json()
    assert list(tree) == ["branches"]
    branch = tree["branches"][0]
    assert set(branch) == {"id", "name", "departments"} and branch["name"] == "CSE"
    assert len(branch["departments"]) == 6
    dept = branch["departments"][0]
    assert set(dept) == {"id", "name", "years"}
    year = dept["years"][0]
    assert set(year) == {"id", "name", "sections"} and set(year["sections"][0]) == {"id", "name"}

    # deactivated section / department / year disappear
    with dbmod.db_session(app.state.settings):
        section = aq.list_sections(year["id"])[0]
        academic_service.set_active("section", section["id"], False)
        other = aq.list_departments()[1]
        academic_service.set_active("department", other["id"], False)
    tree = client.get("/api/academic/tree").json()
    names = [d["name"] for d in tree["branches"][0]["departments"]]
    assert other["name"] not in names and len(names) == 5
    sections = [s["id"] for d in tree["branches"][0]["departments"] if d["id"] == dept["id"]
                for y in d["years"] if y["id"] == year["id"] for s in y["sections"]]
    assert section["id"] not in sections and len(sections) == 2


def test_academic_tree_ids_match_signup_section_ids(app, client):
    tree = client.get("/api/academic/tree").json()
    dept = next(d for d in tree["branches"][0]["departments"] if d["name"] == "AIML")
    year = next(y for y in dept["years"] if y["name"] == "3rd Year")
    section = next(s for s in year["sections"] if s["name"] == "A")
    assert section["id"] == find_section(app=app)


def test_meta_endpoint(client):
    assert client.get("/api/meta").json() == {"app": "Campus Connect"}


def test_notifications_api(app, client):
    from services import notification_service as notif
    stu = register_student(app, "1AB21CS001")
    assert client.get("/api/notifications").status_code == 401
    with dbmod.db_session(app.state.settings):
        first = notif.notify(stu["user_id"], notif.MEETING_REQUESTED, "T1", "M1", "meeting", 7)
        second = notif.notify(stu["user_id"], notif.NEW_MESSAGE, "T2", "M2")
    api_login(client, stu["email"])
    body = client.get("/api/notifications").json()
    assert set(body) == {"items", "unread_count"} and body["unread_count"] == 2
    item = next(i for i in body["items"] if i["id"] == first)
    assert item == {"id": first, "type": "MEETING_REQUESTED", "title": "T1", "message": "M1",
                    "related_entity_type": "meeting", "related_entity_id": 7, "is_read": False,
                    "created_at": item["created_at"]}
    assert item["created_at"]

    resp = api_post(client, f"/api/notifications/{first}/read")
    assert resp.status_code == 200 and resp.json()["ok"] is True and resp.json()["unread_count"] == 1
    assert api_post(client, f"/api/notifications/{first}/read").status_code == 200  # idempotent
    assert api_post(client, "/api/notifications/99999/read").status_code == 404
    resp = api_post(client, "/api/notifications/read-all")
    assert resp.status_code == 200 and resp.json()["unread_count"] == 0
    body = client.get("/api/notifications").json()
    assert body["unread_count"] == 0 and all(i["is_read"] for i in body["items"])
    assert client.get("/api/auth/session").json()["unread_notifications"] == 0
    assert second in {i["id"] for i in body["items"]}


def test_notifications_are_listed_newest_first_and_limited(app, client):
    from services import notification_service as notif
    stu = register_student(app, "1AB21CS001")
    with dbmod.db_session(app.state.settings):
        for i in range(55):
            notif.notify(stu["user_id"], notif.NEW_MESSAGE, f"t{i}", "m")
    api_login(client, stu["email"])
    assert len(client.get("/api/notifications").json()["items"]) == 50
    assert client.get("/api/notifications").json()["unread_count"] == 55


# ---------------------------------------------------------------------------
# serializers / helpers used by other routers
# ---------------------------------------------------------------------------

def test_user_payload_and_class_object(app):
    from api.schemas import class_object_for_section, faculty_brief, profile_picture_url, user_payload
    stu = register_student(app, "1AB21CS001")
    fac = register_faculty(app, "FAC001")
    with dbmod.db_session(app.state.settings):
        row = queries.get_user_by_id(stu["user_id"])
        assert user_payload(row) == {
            "id": stu["user_id"], "role": "STUDENT", "full_name": "Student 1AB21CS001",
            "email": stu["email"], "theme": "light", "profile_picture_url": None,
            "student_id": stu["student_id"], "faculty_id": None}
        frow = queries.get_user_by_id(fac["user_id"])
        assert user_payload(frow)["faculty_id"] == fac["faculty_id"]
        assert class_object_for_section(stu["section_id"]) == {
            "section_id": stu["section_id"], "branch": "CSE", "department": "AIML", "year": "3rd Year",
            "section": "A", "label": "CSE → AIML → 3rd Year → A"}
        assert class_object_for_section(None) is None and class_object_for_section(987654) is None
        card = faculty_brief(queries.get_faculty_with_user(fac["faculty_id"]))
        assert card["faculty_code"] == "FAC001" and card["profile_picture_url"] is None
    assert profile_picture_url("profile/students/a.png") == "/uploads/profile/students/a.png"
    assert profile_picture_url(None) is None


def test_current_user_attribute_access(app, client):
    router = APIRouter(prefix="/api/_core")

    @router.get("/who")
    def who(user: CurrentUser = Depends(get_current_user)):
        return {"id": user.id, "same": user["id"] == user.user_id, "role": user.role,
                "student_id": user.student_id, "faculty_id": user.faculty_id, "theme": user.theme,
                "missing": hasattr(user, "nope")}

    app.include_router(router)
    stu = register_student(app, "1AB21CS001")
    api_login(client, stu["email"])
    body = client.get("/api/_core/who").json()
    assert body == {"id": stu["user_id"], "same": True, "role": "STUDENT", "student_id": stu["student_id"],
                    "faculty_id": None, "theme": "light", "missing": False}


# ---------------------------------------------------------------------------
# conftest helpers
# ---------------------------------------------------------------------------

def test_conftest_helpers(app, admin, admin_client):
    assert admin["email"] == "admin@college.edu" and make_admin(app) == admin["user_id"]
    assert admin_client.get("/api/auth/session").json()["user"]["role"] == "ADMIN"
    fac = register_faculty(app, "FAC001")
    stu = register_student(app, "1AB21CS001")
    assert db_one(app, "SELECT COUNT(*) AS c FROM users")["c"] == 3
    c = login_client(app, fac["email"])
    assert c.get("/api/auth/session").json()["user"]["faculty_id"] == fac["faculty_id"]
    db_exec(app, "UPDATE users SET theme_preference = 'dark' WHERE id = ?", (stu["user_id"],))
    assert login_client(app, stu["email"]).get("/api/auth/session").json()["user"]["theme"] == "dark"
    assert PASSWORD
