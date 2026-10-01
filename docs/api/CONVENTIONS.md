# Campus Connect JSON API — conventions

The FastAPI app (`api/main.py`) is a pure JSON API under `/api/*` plus file serving under `/uploads/*`.
The React SPA (in `frontend/`) is the only UI. The API may also serve the built SPA
(`frontend/dist`) for single-origin local runs; every non-`/api`, non-`/uploads`, non-`/healthz`
GET falls back to `index.html`.

## Transport
- JSON request/response (`Content-Type: application/json`), except file uploads (`multipart/form-data`).
- Session auth: HttpOnly cookie `cc_session` (signed session cookie). No tokens in localStorage.
- **CSRF**: `GET /api/auth/session` returns `{"authenticated": bool, "user": {...}|null, "csrf_token": "..."}`.
  Every POST/PUT/PATCH/DELETE must send header `X-CSRFToken: <csrf_token>` (multipart too). The global `csrf_protect` dependency enforces it. A missing/invalid token → 400
  `{"error": {"code": "csrf_failed", ...}}`. The token rotates on login/logout — the client must refetch
  `/api/auth/session` after those calls (login/logout responses also include a fresh `csrf_token`).
- Same-origin in production: Vercel serves the SPA and rewrites `/api/*` and `/uploads/*` to the Render
  backend, so cookies stay first-party. In dev, Vite proxies `/api` and `/uploads` to `http://127.0.0.1:5000`.

## Responses
- Success: HTTP 200/201 and a JSON object. Mutations return `{"ok": true, "message": "<human text>", ...extra}`.
- Lists: `{"items": [...]}` (plus extras such as `"total"`). Single resources: a named object, e.g. `{"student": {...}}`.
- Errors: `{"error": {"code": "<snake_case>", "message": "<human text>", "fields": {"<field>": "<msg>"}?}}` with
  the correct status: 400 validation, 401 not signed in (`unauthenticated`), 403 forbidden (`forbidden`),
  404 `not_found`, 405, 409 conflict, 413 too large, 429 throttled (`rate_limited`), 500 `server_error`.
  Business-rule failures from services (ValidationError, ChatAccessError, MeetingError, …) → 400 (or 403 when
  it is an authorization failure) with their message. Never return HTML from `/api/*`.
- Dates are the SQLite strings already stored (`YYYY-MM-DD HH:MM:SS`, UTC); the SPA formats them.
- IDs are integers. Use snake_case keys everywhere.

## Auth / user object
`user` (from `/api/auth/session` and login):
```json
{ "id": 1, "role": "STUDENT|FACULTY|ADMIN", "full_name": "...", "email": "...", "theme": "light|dark",
  "profile_picture_url": "/uploads/profile/students/x.png" | null,
  "student_id": 3 | null, "faculty_id": null }
```
Plus counters on the session endpoint: `"unread_notifications": n, "unread_messages": n`.

## Academic hierarchy
A "class" = one `section` row with its chain. Class object:
`{ "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
   "label": "CSE → AIML → 3rd Year → A" }`.
Public `GET /api/academic/tree` (no auth, active rows only) returns the nested tree
`{"branches":[{"id","name","departments":[{"id","name","years":[{"id","name","sections":[{"id","name"}]}]}]}]}`.

## Files
Uploads are referenced by `/uploads/<relative path>` (auth-checked by the API). Upload endpoints take multipart fields.

## Docs
Each backend area documents its endpoints (method, path, auth/role, request body, response example, error cases)
in `docs/api/<area>.md`. The frontend agents build against these files, so keep them exact.
