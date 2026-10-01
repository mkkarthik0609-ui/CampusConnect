# Backend architecture (FastAPI + raw sqlite3)

Campus Connect is a pure JSON API (`/api/*`), file serving (`/uploads/*`) and `/healthz`; the React SPA in
`frontend/` is the only UI. The contract is `docs/api/CONVENTIONS.md`; this file explains how the code is wired
and how to add a router.

```
api/main.py        create_app(settings=None) -> FastAPI ; lazy module attribute `app` (uvicorn api.main:app)
api/settings.py    Settings dataclass (+ from_env), get_settings(), use_settings()
api/db.py          get_db(), db_session(), init_db(), connect()        (models/database.py is a shim to this)
api/security.py    ASGI middlewares (proxy, headers/size cap/500 net, db holder), CSP, CSRF compare
api/errors.py      ApiError + handlers, map_service_error(), SPA index fallback
api/deps.py        get_current_user, current_user_optional, require_role, csrf_protect, client_ip,
                   service_errors, ok/items, ApiModel/Stripped/Page, CurrentUser
api/schemas.py     user_payload(), class_object(), class_object_for_section(), faculty_brief(),
                   profile_picture_url() (+ UserOut/ClassOut pydantic models)
api/routers/*.py   one module per area, each exports `router`
services/*.py      business logic (framework-agnostic; raise *Error exceptions)
models/*queries.py SQL (framework-agnostic; call get_db())
```

## Run

```
venv\Scripts\python.exe -m uvicorn api.main:app --port 5000          # API (+ SPA if frontend/dist exists)
venv\Scripts\python.exe app.py                                        # same, via the tiny runner (DEBUG=1 -> reload)
venv\Scripts\python.exe -m pytest -q                                  # tests
venv\Scripts\python.exe create_admin.py [--from-env]                  # first admin
```
Production (Render, **one process**): `uvicorn api.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers`
(`TRUST_PROXY=1` makes the app itself read `X-Forwarded-*`, see below). Do not use several workers: the
APScheduler reminder job lives in the process and SQLite has a single writer.

## Settings / environment variables

`Settings.from_env()` reads the environment (and `.env`, real env wins). Every field has a safe default; tests pass
an explicit `Settings(...)`.

| env var | Settings field | default / meaning |
|---|---|---|
| `APP_ENV` | `environment` | `development`; `production` (or `RENDER` set) enables Secure cookie, HSTS, SECRET_KEY check, disables docs |
| `SECRET_KEY` | `secret_key` | **required in production** (>= 24 chars); dev: random key persisted in `.dev_secret_key` |
| `DEBUG` | `debug` | enables `/docs`, `/redoc`, `/openapi.json` and reload in `app.py` (never in production) |
| `DATABASE_PATH` | `database_path` | `database.db` in repo root |
| `UPLOAD_ROOT` | `upload_root` | `uploads/` (derived: `profile_student_dir`, `profile_faculty_dir`, `chat_upload_dir`) |
| `FRONTEND_DIST` | `frontend_dist` | `frontend/dist` |
| `TRUST_PROXY`, `TRUST_PROXY_HOPS` | `trust_proxy`, `trust_proxy_hops` | client IP = `hops`-th from the right of `X-Forwarded-For` (Vercel + Render = 2) |
| `CAPTCHA_MAX_PER_IP_PER_HOUR`, `LOGIN_CAPTCHA_AFTER_FAILURES` | `captcha_max_per_ip_per_hour`, `login_captcha_after_failures` | 60 / 3 |
| `LOGIN_MAX_FAILURES_PER_IDENTIFIER`, `LOGIN_MAX_FAILURES_PER_IP` | `login_max_failures_*` | 5 / 20 per 15 min |
| `SESSION_IDLE_TIMEOUT_MINUTES` | `session_idle_timeout_minutes` | 60 (absolute lifetime 12 h = `session_lifetime_seconds`) |
| `ENABLE_SCHEDULER` | `enable_scheduler` | `1`; reminder job interval `REMINDER_INTERVAL_MINUTES` (60) |
| `BOOTSTRAP_ADMIN` + `ADMIN_NAME/EMAIL/PASSWORD` | `bootstrap_admin` | idempotent first admin at start; never overwrites an existing password |
| - | `csrf_enabled` | `True`; only tests set `False` |
| - | `testing` | `True` in tests: no scheduler, no admin bootstrap, random secret if none |

Services read configuration with `from api.settings import get_settings; get_settings().captcha_length`.

## Request lifecycle

1. `ProxyHeadersMiddleware` (only if `trust_proxy`): client ip / scheme / host from `X-Forwarded-*`.
2. `SecurityMiddleware`: 10 MB cap (413), security headers + CSP, `Cache-Control: no-store` on every `/api/*`
   response, last-resort JSON 500.
3. `DbMiddleware`: binds the app's settings and installs an empty *holder* in a ContextVar. `get_db()` opens the
   sqlite3 connection lazily into the holder (foreign_keys ON, busy_timeout, WAL). The holder is a mutable object,
   so sync `def` endpoints and sync dependencies (run in the threadpool with a *copy* of the context) share one
   connection per request; the middleware closes it when the request ends. `models/*queries.py` simply call
   `get_db()`. Queries commit themselves (`db.commit()`); there is no implicit transaction per request.
4. `SessionMiddleware` (Starlette): HttpOnly, SameSite=Lax (Secure in production) signed cookie `cc_session`
   -> `request.session` (a dict). Forged/unsigned cookies give an empty session. Keys: `user_id, role, full_name,
   student_id, faculty_id, theme, login_at, last_seen, csrf_token`.
5. App-level dependency `csrf_protect` (runs for every route): POST/PUT/PATCH/DELETE must carry header
   `X-CSRFToken` equal (constant-time) to `session["csrf_token"]`, else 400 `csrf_failed`. Safe methods are exempt.
6. Route dependencies: `get_current_user` validates the session (absolute + idle timeouts, user exists and
   `is_active`, role/name/ids refreshed from the DB) or raises 401 `unauthenticated`; `require_role(...)` adds 403.
7. The sync endpoint runs, returns a dict (JSON) or raises `ApiError` / a service exception; handlers in
   `api/errors.py` turn everything into `{"error": {"code", "message", "fields"?}}`.

Outside a request (scripts, scheduler, tests, startup) wrap DB use in `with db_session() as db:`.

## Adding a router

Create `api/routers/<name>.py` (names already reserved in `api/main.py:ROUTER_MODULES`: admin, admin_academic,
faculty, student, chat, meetings, supporting, research). It is auto-registered; a module that does not exist is
skipped, any other import error fails the boot.

```python
from fastapi import APIRouter, Depends, Request
from api.deps import ApiModel, Stripped, CurrentUser, require_role, service_errors, ok, items, client_ip
from api.errors import ApiError
from api.schemas import user_payload, class_object, class_object_for_section, faculty_brief
from services import meeting_service

router = APIRouter(prefix="/api/meetings")            # full path incl. /api/<area>

class RequestMeetingIn(ApiModel):                      # extra="forbid": unknown keys -> 400 with the key name
    faculty_id: int
    reason: Stripped                                   # Stripped = str with whitespace stripped (not for passwords)
    message: Stripped = ""

@router.post("", status_code=201)                      # plain `def`, never `async def` (sqlite3 is sync)
def request_meeting(body: RequestMeetingIn,
                    user: CurrentUser = Depends(require_role("STUDENT"))):
    with service_errors():                             # ValidationError/MeetingError/... -> ApiError 400/403/404/409
        meeting_id = meeting_service.request_meeting(user.student_id, body.faculty_id, body.reason, body.message)
    return ok("Meeting requested.", id=meeting_id)     # {"ok": true, "message": ..., "id": ...}
```

Rules:
* **Sync `def` endpoints only**; they run in FastAPI's threadpool. Call `models.*queries` / services directly.
* **Auth**: `Depends(get_current_user)` (any role), `Depends(require_role("ADMIN", ...))`, or
  `Depends(current_user_optional)` (None when anonymous). The value is a `CurrentUser` (a dict that also
  allows attributes): `id`, `user_id`, `role`, `full_name`, `email`, `theme`, `is_active`, `profile_picture_path`,
  `student_id`, `faculty_id` (no `password_hash`). Use `request.session` only for session-bound state.
* **CSRF** is global; do nothing. Do not add per-router exemptions.
* **Requests**: pydantic models derived from `ApiModel` (`extra="forbid"`). Validation errors become
  `400 {"error": {"code": "validation_error", "message", "fields": {"name": "..."}}}`. Path/query ints are validated too.
  Numbers for text fields are rejected (pydantic lax mode accepts `"7"` for an `int`).
  Multipart: `file: UploadFile = File(...)`, `form fields: x: str = Form(...)` (python-multipart is installed);
  pass the `UploadFile` straight to `file_service.save_chat_attachment / save_profile_picture`.
* **Responses**: return dicts. Mutations `ok("text", **extra)`; lists `items(rows, total=n)`; single resources
  `{"student": {...}}`. Use `api.schemas` helpers for the shared user / class / faculty shapes.
* **Errors**: `raise ApiError(404, "not_found", "No such meeting.")` (optionally `fields={...}`), or let service
  exceptions bubble out of `with service_errors():`. Mapping (also installed as global handlers):
  `ServiceError` -> its `http_status/code`; `LockoutError`/`CaptchaRateLimitError` -> 429 `rate_limited`;
  `ConflictError` -> 409; other `ValidationError` -> 400 (+`fields` when it has `.field`); `DeliveryError` -> 503;
  `ChatAccessError` -> 403; `MeetingError`, `SupportingError`, `PermissionError_`, `AssignmentError`,
  `AcademicError`, `ChatEditError` -> 400 unless the message says *not found* (404), *not authorized / do not have
  permission* (403) or *already ...* (409); `FileValidationError` -> 400 (413 for "too large"). Raise `ApiError`
  yourself when a precise status matters.
* **Uploads**: never build file paths from user input. Store via `file_service`, reference files as
  `/uploads/<relative path>` (`file_service.upload_url`); the uploads router authorises reads.
* **Configuration**: `get_settings()`; never read `os.environ` in routers/services.

## Tests

`tests/conftest.py` builds the app on a temp database/upload dir with `csrf_enabled=False`:

```python
from tests.conftest import (PASSWORD, make_admin, register_faculty, register_student, find_section,
                            api_login, api_post, api_put, api_patch, api_delete, login_client, assign,
                            db_one, db_all, db_exec, db_count)

def test_thing(app, client):                           # fixtures: app (FastAPI), client (TestClient, cookies on)
    admin = make_admin(app)                            # -> user id (service level, idempotent)
    fac = register_faculty(app, code="FAC001")         # -> {"user_id","faculty_id","email","code","password"}
    stu = register_student(app, usn="1AB21CS001", section_id=find_section("CSE", "AIML", "3rd Year", "A", app=app))
    api_login(client, stu["email"], stu["password"])   # POST /api/auth/login, asserts 200, returns JSON
    r = api_post(client, "/api/meetings", json={...})  # adds X-CSRFToken from the cookie automatically
    assert r.status_code == 201
    other = login_client(app, fac["email"])            # separate TestClient (own cookie jar), already logged in
```
Fixtures `admin` (dict with `user_id`, `email`, `password`) and `admin_client` (logged-in TestClient) exist too.
Database assertions: `db_one(app, "SELECT ...", params)`, `db_all`, `db_exec`, `db_count(app, table, where, params)`
(each opens `db_session(app.state.settings)`). For custom code use `with db_session(app.state.settings):`.
CSRF is off by default; to test it build a second app with `Settings(..., csrf_enabled=True)` (see
`tests/test_security.py`). Passwords in tests are hashed with a cheap pbkdf2 (autouse fixture).
