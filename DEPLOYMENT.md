# Deploying Campus Connect (Render backend + Vercel frontend)

Campus Connect is a **server-rendered Flask/Jinja app with SQLite**, not a single-page app.
There is no separate API to host, so the split works like this:

```
 Browser ──HTTPS──▶ Vercel (your public domain)
                     ├─ /static/*, /robots.txt   served from Vercel's CDN (files win over rewrites)
                     └─ everything else ────────▶ rewrite/proxy ──▶ Render web service (gunicorn + Flask)
                                                                      └─ persistent disk /var/data
                                                                          ├─ campusconnect.db (SQLite)
                                                                          └─ uploads/
```

The browser only ever talks to **one origin** (the Vercel domain). Session cookies are therefore
first-party and there is no CORS. Render runs the actual application; Vercel is a CDN + reverse proxy.

Files involved: `render.yaml`, `wsgi.py`, `gunicorn.conf.py`, `requirements.txt`, `.python-version`
(Render) and `vercel.json`, `package.json`, `scripts/build-frontend.mjs`,
`scripts/set-backend-url.mjs`, `.vercelignore` (Vercel).

> Nothing in this repository deploys anything by itself, and no credentials are stored in it. You
> enter secrets in the Render / Vercel dashboards.

---

## 0. Before you start

- The code is in a GitHub repository (Render and Vercel both deploy from Git).
- `database.db`, `.env`, and uploaded files are **not** committed (see `.gitignore`).
- Decide your admin name / e-mail / a strong password (at least 8 characters with upper-case,
  lower-case and a digit). You will type them into the Render dashboard, never into a file.
- Tests pass locally: `venv\Scripts\python.exe -m pytest -q`.

## 1. Backend on Render (do this first)

### Plan and storage — read this

SQLite lives in a single file, so the backend needs storage that survives restarts and redeploys.

| Render plan | Filesystem | What happens to SQLite + uploads |
|---|---|---|
| **Free** | Ephemeral | **All data is lost on every deploy, restart and idle spin-down.** Free services also cannot attach a disk and sleep when idle (the first request after a sleep takes about a minute, and the in-process reminder job does not run while asleep). Acceptable only for a throw-away demo. |
| **Starter or higher** (paid) | Persistent disk supported | Data under the mounted disk (`/var/data`) persists across deploys and restarts. **This is what `render.yaml` uses.** |

A persistent disk can be attached to **one instance only**, which also means this service cannot
be scaled out horizontally. That matches the design: one gunicorn worker, several threads.

### Why exactly one worker

`gunicorn.conf.py` and the start command pin `--workers 1 --threads 4`:

- the meeting-reminder job is an in-process APScheduler thread — with N workers you would get N
  schedulers and N duplicate reminders;
- SQLite allows one writer at a time — a single process with threads avoids cross-process
  lock contention (the app sets a 15 s busy timeout and WAL mode).

Do not raise `--workers`, and do not add `--preload`.

### Option A — Blueprint (recommended)

1. Render dashboard → **New → Blueprint** → connect your GitHub repo → pick the branch.
2. Render reads `render.yaml` and proposes one web service, `campus-connect`, with a 1 GB disk at
   `/var/data`.
3. When prompted, fill in the values marked "sync: false":
   `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
4. **Apply**. The first build runs `pip install -r requirements.txt`, then
   `gunicorn wsgi:app -c gunicorn.conf.py --workers 1 --threads 4`.
5. Note the service URL, e.g. `https://campus-connect-xxxx.onrender.com`.

### Option B — manual web service

New → **Web Service** → connect repo, then set:

| Field | Value |
|---|---|
| Runtime | Python 3 |
| Instance type | **Starter** (or higher) |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn wsgi:app -c gunicorn.conf.py --workers 1 --threads 4` |
| Health check path | `/healthz` |
| Auto-deploy | Yes |
| Disk | name `campus-connect-data`, mount path `/var/data`, size 1 GB |

…and add the environment variables below.

### Environment variables (Render)

| Variable | Value | Notes |
|---|---|---|
| `PYTHON_VERSION` | `3.12.7` | Render wants a full `x.y.z`; `.python-version` in the repo says the same. |
| `APP_ENV` | `production` | Enables Secure cookies, HSTS and the strong-`SECRET_KEY` check. The app refuses to start in production without a strong key. |
| `SECRET_KEY` | *(generated)* | `render.yaml` uses `generateValue: true`. Changing it logs everyone out. |
| `DATABASE_PATH` | `/var/data/campusconnect.db` | Must be on the disk. |
| `UPLOAD_ROOT` | `/var/data/uploads` | Must be on the disk. |
| `TRUST_PROXY` | `1` | Honour `X-Forwarded-*` from Vercel / Render. |
| `TRUST_PROXY_HOPS` | `2` | Proxies in front of the app: Vercel + Render's load balancer. Use `1` if you skip Vercel. |
| `BOOTSTRAP_ADMIN` | `1` | Creates the first admin at start-up from the three variables below (idempotent). |
| `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | *(you type them in the dashboard)* | Never commit these. |
| `SHOW_DEMO_OTP` | `1` | Student signup OTP is shown on screen (demo mode). Set `0` once SMTP works. |
| `REMINDER_INTERVAL_MINUTES` | `60` | |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | *(optional)* | Real OTP e-mail. Add in the dashboard only when you have a provider. |
| `ENABLE_SCHEDULER` | `1` (default) | `0` turns the reminder job off. |
| `CSRF_SSL_STRICT` | *(unset)* | See "Cookies, CSRF and proxy headers" below. |

The full list with placeholder values is in `.env.example`.

### Verify the backend

1. Wait for the deploy to go **Live**.
2. Open `https://<service>.onrender.com/healthz` — expect HTTP 200 (a small JSON/OK body).
3. Open `https://<service>.onrender.com/login` — the login page renders (without styling is fine:
   `/static` is also served by Flask, so it should be styled too).
4. Log in with the admin you supplied. Afterwards you may remove `BOOTSTRAP_ADMIN` or set it to `0`;
   leaving it on is harmless because it only creates the admin when that e-mail does not exist.

> `/healthz` is the endpoint `render.yaml` points the health check at. If the health check fails
> on first deploy, check the service's Logs tab and confirm the app exposes `/healthz`.

### First admin

The first admin is created by `BOOTSTRAP_ADMIN=1` with the `ADMIN_*` variables. There is no public
admin signup. Further admins are added inside the app (Admin → Admins). As a fallback you can run,
in the Render **Shell** tab of the service:

```bash
python create_admin.py --from-env      # reads ADMIN_NAME / ADMIN_EMAIL / ADMIN_PASSWORD
python create_admin.py                 # or interactive prompts
```

---

## 2. Frontend on Vercel (after Render is live)

### What the Vercel project does

- `npm run build` → `scripts/build-frontend.mjs` copies `static/` to `public/static/` and writes
  `public/robots.txt` (`Disallow: /`, the app is login-only).
- `vercel.json` serves `public/` as the output directory and adds one **rewrite**:
  `/:path*` → `https://<your-service>.onrender.com/:path*`. Vercel checks the filesystem first, so
  `/static/...` and `/robots.txt` come from the CDN; every other path is proxied to Flask
  (query strings, methods, cookies and bodies are forwarded).
- Cache headers: `/static/**/*.css|js` → `public, max-age=3600, stale-while-revalidate=86400`
  (CSS/JS change on deploys and are not content-hashed, so they are deliberately *not*
  `immutable`); images/fonts → `public, max-age=604800, stale-while-revalidate=86400`.
  Dynamic (proxied) responses get `x-vercel-enable-rewrite-caching: 0` so a logged-in page is
  never cached at the CDN.
- `.vercelignore` keeps every Python file out of the Vercel upload, so Vercel sees a plain
  static/Node project and does not try to auto-detect and run the Flask app as a Python function.

### Why a committed `vercel.json` (and not build-time generation)

Vercel reads `vercel.json` *before* the build starts, so a `vercel.json` generated during the build
would be ignored. The approach that really works is a committed file plus a helper. The committed
file contains the placeholder host `YOUR-RENDER-SERVICE.onrender.com`, and **the Vercel build
fails on purpose if the placeholder is still there** (only when building on Vercel, so you cannot
ship a proxy that points nowhere).

### Steps

1. Put your Render URL into `vercel.json`:

   ```powershell
   node scripts\set-backend-url.mjs https://campus-connect-xxxx.onrender.com
   # or:  $env:BACKEND_URL="https://campus-connect-xxxx.onrender.com"; node scripts\set-backend-url.mjs
   ```

   It edits only the rewrite destination. Review the diff, commit and push. (You can also edit
   `vercel.json` by hand — replace `YOUR-RENDER-SERVICE.onrender.com`.)
2. Vercel dashboard → **Add New → Project** → import the same GitHub repo.
3. Project settings (Vercel should pick these up from `vercel.json`, but verify):
   Framework Preset **Other**, Build Command `npm run build`, Output Directory `public`,
   Install Command: any (there are no dependencies), Root Directory: repository root.
4. No environment variables are needed on Vercel.
5. **Deploy**. Open the `*.vercel.app` URL — you should see the Campus Connect login page, styled.
6. (Optional) Settings → Domains → add your college domain. Point everyone at *this* domain.

> The Hobby plan is for non-commercial use; check Vercel's current terms for an institutional
> deployment.

### Cookies, CSRF and proxy headers (important)

- **Cookies.** The session cookie (`cc_session`) is `HttpOnly`, `SameSite=Lax`, and `Secure`
  in production. Because the browser only sees the Vercel origin, it is a first-party, host-only
  cookie: nothing needs `SameSite=None`, and no CORS headers are required.
- **Public host = the Vercel domain.** Vercel forwards the original client information as
  `X-Forwarded-*`; Render's load balancer adds its own. With `TRUST_PROXY=1` the app applies
  Werkzeug's `ProxyFix` so it sees `https` and the real client IP (login throttling is per IP, so
  this matters). `TRUST_PROXY_HOPS=2` tells it that two proxies append to `X-Forwarded-For`.
- **CSRF.** Every POST form carries a Flask-WTF CSRF token bound to the session; that protection is
  unchanged. Flask-WTF additionally compares the `Referer` header with `request.host` for HTTPS
  requests. Behind a rewrite chain `request.host` can be the Render host while the `Referer` is the
  Vercel domain, which would reject every POST. For that reason the app **disables that extra
  referrer check by default when `TRUST_PROXY=1`** (`WTF_CSRF_SSL_STRICT` defaults to off; set
  `CSRF_SSL_STRICT=1` only after confirming in production that the host header arrives correctly).
  The token check, `SameSite=Lax` cookies and same-origin forms still apply.
- **The `*.onrender.com` URL still works** and has its own, separate session cookie. It is a second
  door to the same app; it is not a security problem, but do not advertise it.
- **Uploads** are served by Flask at `/uploads/<path>` only to logged-in users, so they also pass
  through the Vercel proxy (they are intentionally not static files). Request bodies up to 10 MB
  (the app's limit) go through the proxy on uploads.

---

## 3. Smoke-test checklist (on the Vercel URL)

- [ ] `/healthz` returns 200 through Vercel.
- [ ] `/login` renders **with** styling (check the browser network tab: `/static/css/style.css` comes
      from Vercel with `cache-control: public, max-age=3600, ...`).
- [ ] Admin login works; the session cookie is `Secure` + `HttpOnly` and set for the Vercel host.
- [ ] Logged-in pages are not cached (`x-vercel-cache` is not `HIT` on HTML).
- [ ] Admin → Academics shows CSE with AIML, AIDE, GenAI, Cybersecurity, Blockchain, IoT.
- [ ] Register a faculty account; Admin assigns it a class (e.g. CSE → AIML → 3rd Year → A).
- [ ] Register a student in that class; OTP flow works (on-screen OTP in demo mode).
- [ ] Student sees the assigned faculty; chat and meeting request between them work.
- [ ] A second faculty *not* assigned to that class cannot open `/faculty/classes/<section_id>` (403)
      and cannot search/message the student.
- [ ] Upload a profile picture and a chat attachment; both display after a page reload.
- [ ] Redeploy on Render (Manual Deploy) and confirm the data and uploads are still there.
- [ ] Check the Render logs: one gunicorn worker, no scheduler errors.

## 4. Backups and restore

The SQLite file and uploads live on the persistent disk. Render also offers disk snapshots on paid
disks (see the disk's settings in the dashboard for current retention); treat them as a safety net,
not your only copy.

**Online backup** — uses SQLite's backup API, safe while the app is running (do not `cp` a live WAL
database):

```bash
# In the Render Shell tab (service → Shell):
python scripts/backup_db.py --dest /var/data/backups --keep 14
# equivalent with the sqlite3 CLI, if it is installed:
sqlite3 /var/data/campusconnect.db ".backup '/var/data/backups/campusconnect-$(date +%F).db'"
```

`scripts/backup_db.py` verifies `PRAGMA integrity_check` and prunes all but the newest `--keep`
copies.

**Nightly:** a Render web service has no built-in cron that can see its own disk (a Render Cron
Job is a separate service and cannot mount this disk). Practical options, in order of simplicity:

1. Run the command above by hand (or from your own machine over Render SSH) on a schedule you will
   actually keep, and copy the newest file off Render (`scp`/`rsync` via SSH, or download from the
   Shell).
2. Add an APScheduler job that calls the same `sqlite3.backup` code inside the app (a small code
   change; not included here because it touches `app.py`).
3. Rely on Render disk snapshots plus a weekly off-site copy.

Keep at least one copy **outside** Render.

**Restore:** stop writes (Render → Suspend the service, or Shell in and stop traffic), then

```bash
cp /var/data/backups/campusconnect-YYYYMMDDTHHMMSSZ.db /var/data/campusconnect.db
rm -f /var/data/campusconnect.db-wal /var/data/campusconnect.db-shm
```

and resume/redeploy the service. Uploaded files are not inside the database; back up
`/var/data/uploads` separately (for example `tar czf uploads-$(date +%F).tgz -C /var/data uploads`).

## 5. SQLite or PostgreSQL?

**Recommendation:** SQLite on a persistent disk is fine for a **single-college pilot** — up to a few
thousand registered users with modest write volume (chat messages, meeting requests, logins). WAL
mode gives concurrent readers with one writer, and this app's writes are small and short. It is
also the simplest thing to operate and back up.

Move to PostgreSQL when any of these become true: you need more than one web instance (horizontal
scale or zero-downtime rolling deploys — a disk attaches to one instance), sustained write-heavy
use (hundreds of concurrent chatting users), managed point-in-time recovery, or reporting tools
that need a network database.

**Honest cost of the upgrade:** the code calls `sqlite3` directly (`models/database.py`,
`models/queries.py`, `models/academic_queries.py`), uses `sqlite3.Row`, SQLite-specific SQL
(`datetime('now')`, `AUTOINCREMENT`, `PRAGMA ...`, `INSERT` id via `lastrowid`) and `schema.sql`
written for SQLite. Moving to Postgres therefore needs a DB-layer port, not just a connection
string:

1. Introduce a driver (for example `psycopg`) behind `get_db()` with dict-style rows and `%s`/named
   parameters instead of `?`.
2. Translate the schema (`SERIAL`/`IDENTITY`, `TIMESTAMPTZ`, boolean columns, `COLLATE NOCASE` →
   `citext` or lower-case indexes) and replace `datetime('now')`/`PRAGMA` usage.
3. Replace `cursor.lastrowid` with `RETURNING id`.
4. Write a one-off data copy script (SQLite → Postgres) and re-run the test suite against Postgres.
5. Then the single-worker restriction could be relaxed (run the scheduler in one dedicated worker).

Budget this as a small project of its own (days, not hours). Until then, keep one worker and the
persistent disk.

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Vercel build fails: "vercel.json still points at the placeholder" | Run `node scripts/set-backend-url.mjs https://<service>.onrender.com`, commit, push. |
| Vercel shows a 404 from Vercel itself / unstyled pages | Output directory not `public`, or the build did not run; check the build log for "Frontend build complete". |
| Every form POST returns 400 "CSRF ..." | The session cookie is missing (cookies blocked, or the page was opened via a different host than the one that set it), or `CSRF_SSL_STRICT=1` while the forwarded host does not match. Unset `CSRF_SSL_STRICT`. |
| Users are logged out after each deploy | `SECRET_KEY` changed. `generateValue` only generates once; do not regenerate. |
| Data disappeared after a deploy | The service is on the free plan (ephemeral disk), or `DATABASE_PATH` / `UPLOAD_ROOT` do not point under `/var/data`. |
| "database is locked" | More than one process is writing. Confirm a single gunicorn worker and only one service using the disk. |
| Render health check failing | Check Logs; confirm `/healthz` exists and the app starts (a missing/short `SECRET_KEY` makes production start-up fail by design). |
| Duplicate meeting reminders | More than one worker is running — restore `--workers 1`. |
| Login throttling locks everybody out | `TRUST_PROXY`/`TRUST_PROXY_HOPS` are wrong so all users appear to share one IP (a proxy address). Check the hop count. |

## 7. Owner action list

**Render**
1. Push the repo to GitHub.
2. New → Blueprint → select the repo → set `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` → Apply
   (choose/keep the **Starter** plan so the disk is allowed).
3. Wait for Live; check `/healthz` and log in as admin.
4. Copy the service URL.

**Vercel**
1. `node scripts\set-backend-url.mjs https://<service>.onrender.com`; commit and push.
2. New Project → import the repo → confirm Build `npm run build`, Output `public` → Deploy.
3. Run the smoke-test checklist above on the Vercel URL; add your custom domain if you have one.

**Afterwards**
- Schedule backups (section 4) and keep one off-site copy.
- Once SMTP is configured, set `SHOW_DEMO_OTP=0`.
