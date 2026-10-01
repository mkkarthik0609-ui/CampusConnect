# System endpoints

## `GET /healthz`
Public liveness/readiness probe (Render health check). Runs `SELECT 1`.
200 `{"status": "ok"}`; 503 `{"status": "error"}` when the database is unavailable (details are only logged).

## `GET /api/meta`
Public, non-sensitive.
```json
{ "app": "Campus Connect" }
```

## `GET /uploads/{path}`
Authorised file serving (requires a session; 401 otherwise).
* `profile/students/<file>` and `profile/faculty/<file>`: any signed-in user; images are shown inline
  (`Cache-Control: private, max-age=300`).
* `chat/<file>`: only the two chat participants (while the chat is still permitted) or an ADMIN (403 otherwise); sent
  as `Content-Disposition: attachment` with the original file name, `Cache-Control: private, no-store`.
* Everything else, unknown files and path traversal attempts: 404. Always `X-Content-Type-Options: nosniff`;
  anything that is not png/jpg/jpeg is an attachment.
Reference files in JSON as `/uploads/<relative path>`.

## Cross-cutting behaviour
* Security headers on every response: CSP (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'
  https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:;
  connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`),
  `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS in production/https.
* Every `/api/*` response is `Cache-Control: no-store`.
* Requests larger than 10 MB -> 413 `payload_too_large`.
* Unknown `/api/*` -> 404 `not_found` JSON; wrong method -> 405 `method_not_allowed`.
* If `frontend/dist` exists the app serves it: `/assets/*` (immutable) and `index.html` for any other GET that is not
  `/api`, `/uploads`, `/healthz`.
