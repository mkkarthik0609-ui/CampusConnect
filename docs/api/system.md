# System endpoints

## `GET /healthz`
Public liveness probe (Render health check, also reachable through the Vercel rewrite). By design it **does not
touch the database**, so Render's periodic probes never wake the Neon compute. 200 `{"status":"ok"}`.
`GET /healthz?deep=1` additionally runs `SELECT 1` against the database and answers 503 `{"status":"error"}` when
it is unreachable (details are only logged); use it by hand for diagnostics, not as the Render health check.

## `GET /health` (also `HEAD`)
Keep-alive ping target (see [../KEEP_ALIVE.md](../KEEP_ALIVE.md)): `200 {"status":"ok"}`, touches nothing.

## `GET /api/meta`
Public, non-sensitive.
```json
{ "app": "Campus Connect" }
```

## `GET /uploads/{path}`
Authorised file serving (requires a session; 401 otherwise). Files are read from the PostgreSQL table `file_blobs`
(there is no upload directory on disk; Render Free's filesystem is ephemeral).
* `profile/students/<file>` and `profile/faculty/<file>`: any signed-in user; images are shown inline
  (`Cache-Control: private, max-age=300`).
* `chat/<file>`: only the two chat participants (while the chat is still permitted) or an ADMIN (403 otherwise); sent
  as `Content-Disposition: attachment` with the original file name, `Cache-Control: private, no-store`.
* Everything else, unknown files and path traversal attempts: 404. Always `X-Content-Type-Options: nosniff`;
  anything that is not png/jpg/jpeg is an attachment.
Reference files in JSON as `/uploads/<relative path>`. Uploads are validated on write (extension, size - 8 MB attachment / 3 MB picture - magic bytes and structure) and stored as `bytea`.

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
