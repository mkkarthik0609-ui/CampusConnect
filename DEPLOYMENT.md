# Deploying Campus Connect (Render API + Vercel SPA)

Campus Connect is a **FastAPI JSON API with SQLite** (`api/`, entry point `api.main:app`) and a
**React single-page app** (`frontend/`). They are deployed separately:

```
 Browser ──HTTPS──▶ Vercel (your public domain, Root Directory = frontend)
                     ├─ /assets/*, /index.html, /favicon ...   static files from the Vite build (frontend/dist)
                     ├─ /api/*, /uploads/*, /healthz ────────▶ rewrite/proxy ──▶ Render web service (uvicorn + FastAPI)
                     │                                                            └─ persistent disk /var/data
                     │                                                                ├─ campusconnect.db (SQLite)
                     │                                                                └─ uploads/
                     └─ every other path ──▶ /index.html (client-side routing)
```

The browser only ever talks to **one origin** (the Vercel domain). The session cookie is therefore
first-party and **no CORS configuration exists or is needed**. Render runs the API; Vercel is the static host
and a reverse proxy.

Files involved: `render.yaml`, `requirements.txt`, `.python-version` (Render) and `frontend/vercel.json`,
`frontend/package.json`, `frontend/scripts/set-backend-url.mjs` (Vercel).

> Nothing in this repository deploys anything by itself, and no credentials are stored in it. You enter
> secrets in the Render / Vercel dashboards.

---

## 0. Before you start

- The code is in a GitHub repository (Render and Vercel both deploy from Git).
- `database.db`, `.env` and uploaded files are **not** committed (see `.gitignore`).
- Decide your admin name / e-mail / a strong password (at least 8 characters with upper-case, lower-case and
  a digit). You will type them into the Render dashboard, never into a file.
- Tests pass locally: `venv\Scripts\python.exe -m pytest tests -q`, and `npm run lint && npm run build` in
  `frontend/`.

## 1. Backend on Render (do this first)

### Plan and storage: read this

**SQLite only, one process, a persistent disk is required.** SQLite lives in a single file, so the backend
needs storage that survives restarts and redeploys.

| Render plan | Filesystem | What happens to SQLite + uploads |
|---|---|---|
| **Free** | Ephemeral | **All data is lost on every deploy, restart and idle spin-down.** Free services cannot attach a disk and sleep when idle (the first request after a sleep takes about a minute, and the in-process reminder job does not run while asleep). Acceptable only for a throw-away demo. |
| **Starter or higher** (paid) | Persistent disk supported | Data under the mounted disk (`/var/data`) persists across deploys and restarts. **This is what `render.yaml` uses.** |

A persistent disk attaches to **one instance only**, so this service cannot be scaled out horizontally. That
matches the design.

### Why exactly one worker

The start command pins `--workers 1`:

- the meeting-reminder job is an in-process APScheduler thread; with N workers you would get N schedulers and
  N duplicate reminders;
- SQLite allows one writer at a time; a single process avoids cross-process lock contention (the app uses WAL
  mode and a 15 s busy timeout).

Do not raise `--workers` and do not add a second service that uses the same disk.

### Option A: Blueprint (recommended)

1. Render dashboard -> **New -> Blueprint** -> connect your GitHub repo -> pick the branch.
2. Render reads `render.yaml` and proposes one web service, `campus-connect`, with a 1 GB disk at `/var/data`.
3. When prompted, fill in the values marked `sync: false`: `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
4. **Apply**. The build runs `pip install -r requirements.txt`, then
   `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers`.
5. Note the service URL, e.g. `https://campus-connect-xxxx.onrender.com`.

### Option B: manual web service

New -> **Web Service** -> connect repo, then set:

| Field | Value |
|---|---|
| Runtime | Python 3 |
| Instance type | **Starter** (or higher) |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers` |
| Health check path | `/healthz` |
| Auto-deploy | Yes |
| Disk | name `campus-connect-data`, mount path `/var/data`, size 1 GB |

...and add the environment variables below.

### Why `--no-proxy-headers`

uvicorn can rewrite the client address from `X-Forwarded-For` on its own, but only for peers listed in
`--forwarded-allow-ips` (default: localhost), so on Render it would do nothing useful. The app handles
`X-Forwarded-*` itself and knows how many proxies to trust (`TRUST_PROXY=1`, `TRUST_PROXY_HOPS`), so uvicorn's
copy is switched off to avoid two layers disagreeing.

### Environment variables (Render)

Every variable the backend reads is documented in `.env.example`. The ones that matter in production:

| Variable | Value | Notes |
|---|---|---|
| `PYTHON_VERSION` | `3.12.7` | Render wants a full `x.y.z`; `.python-version` says the same. |
| `APP_ENV` | `production` | Secure session cookie, HSTS, strong-`SECRET_KEY` check, `/docs` disabled. The app refuses to start without a strong key. |
| `SECRET_KEY` | *(generated)* | `render.yaml` uses `generateValue: true` (at least 24 chars required). Changing it logs everyone out. |
| `DATABASE_PATH` | `/var/data/campusconnect.db` | Must be on the disk. |
| `UPLOAD_ROOT` | `/var/data/uploads` | Must be on the disk. |
| `TRUST_PROXY` | `1` | Honour `X-Forwarded-*` (real client IP for rate limiting, https scheme). |
| `TRUST_PROXY_HOPS` | `2` | Proxies appending to `X-Forwarded-For`: Vercel + Render's load balancer. Use `1` if a custom domain points straight at Render and Vercel is not in the path. |
| `BOOTSTRAP_ADMIN` | `1` | Creates the first admin at start-up from the three variables below (idempotent). |
| `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | *(typed in the dashboard)* | Never commit these. |
| `SHOW_DEMO_OTP` | `1` | Student signup OTP is returned to the browser and shown on screen (demo mode, used only when no SMTP is configured). Set `0` once SMTP works. |
| `REMINDER_INTERVAL_MINUTES` | `60` | Meeting-reminder job interval. |
| `RESEND_API_KEY`, `RESEND_FROM` | *(optional)* | OTP e-mail through Resend's HTTPS API (works on Render free, where SMTP is blocked). Takes priority over SMTP. `RESEND_FROM` e.g. `Campus Connect <no-reply@yourdomain.com>` (verified domain). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | *(optional)* | Real OTP e-mail. Add in the dashboard only when you have a provider. |
| `ENABLE_SCHEDULER` | `1` (default) | `0` turns the reminder job off. |
| `LOGIN_MAX_FAILURES_PER_IDENTIFIER`, `LOGIN_MAX_FAILURES_PER_IP`, `SESSION_IDLE_TIMEOUT_MINUTES`, `OTP_MAX_PER_EMAIL_PER_HOUR`, `OTP_MAX_PER_IP_PER_HOUR` | defaults 5 / 20 / 60 / 5 / 20 | Optional tuning. |
| `FRONTEND_DIST` | *(unset)* | Only if you want the API itself to serve a built SPA; not used with the Vercel setup. |

**No CORS, cookie-domain or allowed-origin variable exists**: because the Vercel rewrite makes the browser see a
single origin, none is needed. The session cookie (`cc_session`) is `HttpOnly`, `SameSite=Lax` and `Secure`
(automatically, because `APP_ENV=production`).

### Verify the backend

1. Wait for the deploy to go **Live**.
2. `https://<service>.onrender.com/healthz` returns HTTP 200 `{"status":"ok"}`.
3. `https://<service>.onrender.com/api/meta` returns `{"app":"Campus Connect","demo_otp_enabled":true,...}`.
   (The API alone has no UI, and `/docs` is intentionally disabled in production.)
4. Check the Render Logs: one process, a line `Admin bootstrap: created` (first deploy) or `exists`, no tracebacks.

### First admin

The first admin is created by `BOOTSTRAP_ADMIN=1` with the `ADMIN_*` variables. There is no public admin
signup. Further admins are added inside the app (Admin -> Admins). As a fallback run, in the Render **Shell**
tab of the service:

```bash
python create_admin.py --from-env      # reads ADMIN_NAME / ADMIN_EMAIL / ADMIN_PASSWORD
python create_admin.py                 # or interactive prompts
```

After the first successful bootstrap you may set `BOOTSTRAP_ADMIN` to `0`; leaving it on is harmless because it
only creates the admin when that e-mail does not exist, and never overwrites an existing password.

---

## 2. Frontend on Vercel (after Render is live)

### What the Vercel project does

`frontend/vercel.json` configures the project (it is read when **Root Directory = `frontend`**):

- Framework `vite`, install `npm ci`, build `npm run build`, output `dist`.
- Rewrites, in order (static files win over rewrites):
  `/api/:path*` and `/uploads/:path*` and `/healthz` -> `https://<your-render-service>.onrender.com/...`, then the
  SPA fallback `/(.*)` -> `/index.html`.
- Cache: `/assets/*` (content-hashed by Vite) `public, max-age=31536000, immutable`; everything else served by
  Vercel (including `index.html`) `no-cache`.
- Security headers on the static/SPA responses, matching the API's own policy: CSP (`script-src 'self'`,
  `frame-ancestors 'none'`, ...), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, HSTS. Proxied `/api` and `/uploads` responses carry the API's own headers
  (`/api/*` is `Cache-Control: no-store`).

The legacy root-level `vercel.json`, `package.json`, `.vercelignore` and `scripts/build-frontend.mjs` were
removed. With Root Directory = `frontend`, Vercel only sees the frontend folder, so no `.vercelignore` is needed.

### Pointing Vercel at Render

`frontend/vercel.json` ships with the placeholder host `YOUR-RENDER-SERVICE.onrender.com`. **The Vercel build
fails on purpose if the placeholder is still present** (`frontend/scripts/set-backend-url.mjs`, run as the
`prebuild` npm script and only strict when the `VERCEL` environment variable is set), so you cannot ship a proxy
that points nowhere. Two ways to set it:

1. **Recommended: commit it.** In `frontend/`:

   ```powershell
   npm run set-backend-url -- https://campus-connect-xxxx.onrender.com
   ```

   It edits only the rewrite destinations. Review the diff, commit and push.
2. **Convenience: `BACKEND_URL` in Vercel.** Add an environment variable `BACKEND_URL` =
   `https://campus-connect-xxxx.onrender.com` to the Vercel project. The `prebuild` script then rewrites
   `vercel.json` during the build. Vercel normally reads `vercel.json` before the build starts, so if you
   see after deployment that `/api` still hits the placeholder host, use option 1 instead.

### Steps

1. Do option 1 (or 2) above.
2. Vercel dashboard -> **Add New -> Project** -> import the same GitHub repo.
3. Project settings: **Root Directory `frontend`**, Framework Preset **Vite**, Build Command `npm run build`,
   Output Directory `dist`, Install Command `npm ci`, Node.js version 24.x (Settings -> General).
4. No other environment variables are needed (`BACKEND_URL` only for option 2).
5. **Deploy**. Open the `*.vercel.app` URL: the Campus Connect landing page loads.
6. (Optional) Settings -> Domains -> add your college domain. Point everyone at *this* domain.

> The Hobby plan is for non-commercial use; check Vercel's current terms for an institutional deployment.

### Cookies, CSRF and proxy headers (important)

- **Cookies.** The session cookie `cc_session` is `HttpOnly`, `SameSite=Lax`, `Secure` in production. Because the
  browser only sees the Vercel origin it is a first-party, host-only cookie: nothing needs `SameSite=None`.
- **Client IP.** Vercel appends the real client address to `X-Forwarded-For`; Render's load balancer appends
  Vercel's. With `TRUST_PROXY=1` and `TRUST_PROXY_HOPS=2` the app takes the second entry from the right as the
  client, so login throttling and OTP limits work per real user. With the wrong hop count every user would
  appear to share one proxy IP (and lock each other out), or a client could spoof its address.
- **CSRF.** Every `POST/PUT/PATCH/DELETE` must send `X-CSRFToken` equal to the token in the session. The SPA
  gets the token from `GET /api/auth/session` (and from login/logout responses) and sends it automatically.
  There is no `Referer`/host comparison, so the proxy chain cannot cause false CSRF failures. A missing or wrong
  token gives `400 csrf_failed`.
- **The `*.onrender.com` URL still works** and has its own, separate session cookie. It is a second door to the
  same API; do not advertise it.
- **Uploads** are served by the API at `/uploads/<path>` only to authorised signed-in users, so they also pass
  through the Vercel proxy. Request bodies up to 10 MB (the app's limit) are accepted.

---

## 3. Smoke-test checklist (on the Vercel URL)

- [ ] `/healthz` returns 200 `{"status":"ok"}` through Vercel (proves the rewrite works).
- [ ] The landing page renders styled; in the Network tab `/assets/*.js` come with
      `cache-control: public, max-age=31536000, immutable` and `index.html` with `no-cache`.
- [ ] Deep link `/login` and a hard refresh on `/admin/dashboard` load the SPA (SPA fallback works).
- [ ] Admin sign-in works. In DevTools -> Application -> Cookies: `cc_session` is `Secure` + `HttpOnly`,
      host = the Vercel domain.
- [ ] CSRF: a `POST` without the header is rejected, e.g. in the browser console
      `fetch('/api/auth/logout', {method:'POST', credentials:'include'}).then(r => r.status)` returns `400`;
      the normal UI sign-out (which sends the header) works.
- [ ] `/api/*` responses are `Cache-Control: no-store` (also check `x-vercel-cache` is not `HIT`).
- [ ] Admin -> Academics shows CSE with AIML, AIDE, GenAI, Cybersecurity, Blockchain, IoT.
- [ ] Register a faculty account; Admin assigns it a class (e.g. CSE -> AIML -> 3rd Year -> A).
- [ ] Register a student in that class; the OTP step works (on-screen OTP in demo mode).
- [ ] Student sees the assigned faculty; chat and a meeting request between them work.
- [ ] A second faculty member *not* assigned to that class cannot open that class or message the student (403).
- [ ] Upload a profile picture and a chat attachment; both display after a page reload (proves `/uploads`
      through the proxy and the persistent disk).
- [ ] Throttling is per user: 6 wrong passwords for one account lock that account, not other users.
- [ ] Redeploy on Render (Manual Deploy) and confirm data and uploads are still there.
- [ ] Render logs show a single process and no scheduler errors.

## 4. Backups and restore

The SQLite file and uploads live on the persistent disk. Render also offers disk snapshots on paid disks (see
the disk's settings in the dashboard for current retention); treat them as a safety net, not your only copy.

**Online backup** uses SQLite's backup API and is safe while the app is running (do not `cp` a live WAL
database):

```bash
# In the Render Shell tab (service -> Shell):
python scripts/backup_db.py --dest /var/data/backups --keep 14
# equivalent with the sqlite3 CLI, if it is installed:
sqlite3 /var/data/campusconnect.db ".backup '/var/data/backups/campusconnect-$(date +%F).db'"
```

`scripts/backup_db.py` verifies `PRAGMA integrity_check` and prunes all but the newest `--keep` copies.

**Nightly:** a Render web service has no built-in cron that can see its own disk (a Render Cron Job is a
separate service and cannot mount this disk). Practical options, in order of simplicity:

1. Run the command above by hand (or over Render SSH) on a schedule you will actually keep, and copy the newest
   file off Render.
2. Add an APScheduler job in `api/main.py` that calls the same `sqlite3` backup code (a small code change, not
   included).
3. Rely on Render disk snapshots plus a weekly off-site copy.

Keep at least one copy **outside** Render.

**Restore:** stop writes (Render -> Suspend the service), then

```bash
cp /var/data/backups/campusconnect-YYYYMMDDTHHMMSSZ.db /var/data/campusconnect.db
rm -f /var/data/campusconnect.db-wal /var/data/campusconnect.db-shm
```

and resume the service. Uploaded files are not inside the database; back up `/var/data/uploads` separately
(for example `tar czf uploads-$(date +%F).tgz -C /var/data uploads`).

## 5. SQLite or a bigger database?

**Recommendation:** SQLite on a persistent disk is fine for a **single-college pilot**: up to a few thousand
registered users with modest write volume (chat messages, meeting requests, logins). WAL mode gives
concurrent readers with one writer, and this app's writes are small and short. It is also the simplest thing to
operate and back up. The constraints, restated:

- **SQLite only** (the code calls `sqlite3` directly);
- **single worker / single instance** (in-process scheduler, one writer, a disk attaches to one instance);
- **a persistent disk is mandatory** in production; the free plan loses all data.

Move to PostgreSQL when you need more than one web instance (horizontal scale, zero-downtime rolling deploys),
sustained write-heavy use (hundreds of concurrent chatting users), managed point-in-time recovery, or reporting
tools that need a network database.

**Honest cost of the upgrade:** the code uses `sqlite3` directly (`api/db.py`, `models/queries.py`,
`models/academic_queries.py` and the other `models/*_queries.py`), `sqlite3.Row`, SQLite-specific SQL
(`datetime('now')`, `AUTOINCREMENT`, `PRAGMA ...`, `lastrowid`) and `models/schema.sql` written for SQLite.
Moving to Postgres needs a DB-layer port, not just a connection string: a driver (for example `psycopg`) behind
`get_db()` with dict rows and `%s` parameters; a translated schema (`SERIAL`/`IDENTITY`, `TIMESTAMPTZ`,
`COLLATE NOCASE` -> `citext`); `RETURNING id` instead of `lastrowid`; a one-off data copy script; and a full test
rerun. Budget it as a small project of its own. Until then keep one worker and the persistent disk.

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Vercel build fails: "vercel.json still points at the placeholder" | Run `npm run set-backend-url -- https://<service>.onrender.com` in `frontend/`, commit, push (or set `BACKEND_URL` in Vercel). |
| `/api/...` returns an HTML 404/502 from Vercel, or hits the wrong host | Rewrites still point at the placeholder or an old URL; check `frontend/vercel.json` in the deployed source. |
| Blank page / 404 on deep links | Root Directory is not `frontend`, or the output directory is not `dist`. |
| Every unsafe request returns `400 csrf_failed` | The session cookie is missing (cookies blocked, or the app was opened on a different host than the one that set it) or the SPA is not sending `X-CSRFToken`. Reload the page so `/api/auth/session` runs again. |
| Users are logged out after each deploy | `SECRET_KEY` changed. `generateValue` generates once; do not regenerate. |
| Data disappeared after a deploy | The service is on the free plan (ephemeral disk), or `DATABASE_PATH` / `UPLOAD_ROOT` do not point under `/var/data`. |
| "database is locked" | More than one process is writing. Confirm `--workers 1` and that only one service uses the disk. |
| Render health check failing | Check Logs; a missing or short `SECRET_KEY` makes production start-up fail by design. |
| Duplicate meeting reminders | More than one process is running: restore `--workers 1`. |
| Login throttling locks everybody out | `TRUST_PROXY` / `TRUST_PROXY_HOPS` are wrong so all users share one IP (a proxy address). Check the hop count (2 with Vercel, 1 without). |
| Signup says delivery unavailable | `SHOW_DEMO_OTP=0` with no SMTP configured, so no OTP channel exists. |

## 7. Owner action list

**Render**
1. Push the repo to GitHub.
2. New -> Blueprint -> select the repo -> set `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` -> Apply
   (keep the **Starter** plan so the disk is allowed).
3. Wait for Live; check `/healthz`.
4. Copy the service URL.

**Vercel**
1. In `frontend/`: `npm run set-backend-url -- https://<service>.onrender.com`; commit and push
   (or set `BACKEND_URL` in the Vercel project).
2. New Project -> import the repo -> **Root Directory `frontend`** -> confirm Build `npm run build`,
   Output `dist` -> Deploy.
3. Run the smoke-test checklist above on the Vercel URL; add your custom domain if you have one.

**Afterwards**
- Schedule backups (section 4) and keep one off-site copy.
- Once SMTP is configured, set `SHOW_DEMO_OTP=0`.
