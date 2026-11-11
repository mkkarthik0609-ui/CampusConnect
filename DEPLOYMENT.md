# Deploying Campus Connect (Vercel SPA + Render API + Neon PostgreSQL)

Campus Connect is a **FastAPI JSON API** (`api/`, entry point `api.main:app`) backed by **Neon PostgreSQL**, plus
a **React single-page app** (`frontend/`). All three run on free tiers:

```
 Browser ──HTTPS──▶ Vercel (your public domain, Root Directory = frontend)
                     ├─ /assets/*, /index.html, /favicon ...   static files from the Vite build (frontend/dist)
                     ├─ /api/*, /uploads/*, /healthz ────────▶ rewrite/proxy ──▶ Render Free web service (uvicorn + FastAPI)
                     │                                                            └─ psycopg pool (max 5) ──▶ Neon PostgreSQL (Free)
                     │                                                                 ├─ tables (users, chats, meetings, ...)
                     │                                                                 └─ file_blobs (uploads as bytea)
                     └─ every other path ──▶ /index.html (client-side routing)
```

The browser only ever talks to **one origin** (the Vercel domain). The session cookie is therefore first-party
and **no CORS configuration exists or is needed**. Render runs the API (no disk, no local state); Neon holds
every byte of data, uploads included; Vercel is the static host and a reverse proxy.

Files involved: `render.yaml`, `requirements.txt`, `.python-version`, `migrations/*.sql` (Render/Neon) and
`frontend/vercel.json`, `frontend/package.json` (Vercel).

> Nothing in this repository deploys anything by itself, and no credentials are stored in it. You enter secrets
> (database URLs, admin password, mail key) in the Render dashboard only. Never put them in git, `render.yaml`
> or Vercel.

## Free-tier limits (read before relying on this in production)

| Service | Limit | Consequence for Campus Connect |
|---|---|---|
| Render Free web service | 512 MB RAM, 0.1 CPU, 750 instance hours/month, **no persistent disk**, spins down after ~15 min without inbound traffic | Cold start of up to ~60 s on the first request after idle. The UI shows a "waking the server" banner and retries idempotent GETs. The in-process reminder job does not run while the service sleeps. Local files are wiped on every restart/deploy, which is why uploads live in PostgreSQL. |
| Neon Free | 0.5 GB storage per project, compute scales to zero after 5 min idle (first query then costs about +0.5-2 s), 100 CU-hours/month, point-in-time restore window of 7 days | The database holds uploads too (see "Upload storage capacity"). The app retries connections with backoff (connect timeout 15 s) so a waking compute does not fail the request. |
| Vercel Hobby | Non-commercial use; check current terms | Static hosting + rewrites only. |

Free-tier quotas change; verify the current numbers on each provider's pricing page before launch.

### Measured capacity

_Placeholder. This section is filled from `docs/LOAD_TEST.md` if that file exists. No load-test figures are
claimed here until a test has actually been run and written up._

---

## 0. Before you start

- The code is in a GitHub repository (Render and Vercel both deploy from Git).
- `.env`, `database.db` (the old SQLite file, if you still have one) and uploads are **not** committed (see
  `.gitignore`).
- Decide the primary admin's name / e-mail / a strong password (at least 8 characters with upper-case, lower-case
  and a digit). You will type them into the Render dashboard, never into a file.
- Tests pass locally (see [Tests](#8-running-the-tests)) and `npm run lint && npm run build` in `frontend/`.

## 1. Database on Neon (do this first)

1. Create a Neon project (https://neon.tech). Pick the region **closest to Render's Oregon region** (AWS
   `us-west-2` / Oregon) to keep query latency low.
2. Open **Connect** and copy **two** connection strings for the same database:
   * **Direct** (host without `-pooler`): used for migrations (advisory lock, DDL).
   * **Pooled** (host contains `-pooler`, PgBouncer transaction mode): used by the running app.
   Both must include `sslmode=require`.
3. Keep them for step 2.3 below. **Never** paste them into git, `render.yaml`, an issue or a chat.

The schema is created by the app itself on first start (see [Migrations](#migrations-run-automatically)); there
is nothing to run in Neon's SQL editor.

## 2. Backend on Render

### Plan and storage: read this

`render.yaml` uses `plan: free` and has **no `disk:` block**. The service holds no state: sessions are signed
cookies, data and uploads are in Neon. A restart, redeploy or idle spin-down loses nothing.

Trade-offs of the Free plan:

* **Cold start up to ~60 s** after ~15 min idle. The first visitor sees the "waking the server" banner; the SPA
  retries idempotent GETs. Mutating requests are never retried automatically.
* **Reminders pause while asleep.** The meeting-reminder job runs inside the process (`ENABLE_SCHEDULER`).
 * To avoid sleeping you may ping the service; see [`docs/KEEP_ALIVE.md`](docs/KEEP_ALIVE.md). A ping does not
  guarantee uptime and uses up the 750 h/month allowance.

### Why exactly one worker

The start command pins `--workers 1`: the meeting-reminder job is an in-process APScheduler thread, so N workers
would run N schedulers. (Reminders are claimed atomically in the database, so a stray second instance cannot send
duplicates, but keep one process anyway: Render Free has 512 MB RAM.) Database access is pooled
(`DB_POOL_MAX`, default 5) so one process is plenty for a campus pilot.

### Option A: Blueprint (recommended)

1. Render dashboard -> **New -> Blueprint** -> connect your GitHub repo -> pick the branch.
2. Render reads `render.yaml` and proposes one free web service, `campus-connect`.
3. Fill in the values marked `sync: false` (see the table below): at least `DATABASE_URL`, `DATABASE_URL_POOLED`,
   `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
4. **Apply**. The build runs `pip install -r requirements.txt`, then
   `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers`.
5. The **first deploy runs the migrations** automatically (see below) and seeds the default academic structure.
6. Note the service URL, e.g. `https://campus-connect-xxxx.onrender.com`.

### Option B: manual web service

New -> **Web Service** -> connect repo, then set:

| Field | Value |
|---|---|
| Runtime | Python 3 |
| Instance type | **Free** |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers` |
| Health check path | `/healthz` |
| Auto-deploy | Yes |
| Disk | none |

...and add the environment variables below.

### Why `--no-proxy-headers`

uvicorn can rewrite the client address from `X-Forwarded-For` on its own, but only for peers listed in
`--forwarded-allow-ips` (default: localhost), so on Render it would do nothing useful. The app handles
`X-Forwarded-*` itself and knows how many proxies to trust (`TRUST_PROXY=1`, `TRUST_PROXY_HOPS`), so uvicorn's
copy is switched off to avoid two layers disagreeing.

### Environment variables (Render)

Names only; set the values in the Render dashboard. Every variable the backend reads is documented in
`.env.example`.

| Variable | Value | Notes |
|---|---|---|
| `PYTHON_VERSION` | `3.12.7` | Render wants a full `x.y.z`; `.python-version` says the same. |
| `APP_ENV` | `production` | Secure session cookie, HSTS, strong-`SECRET_KEY` check, `/docs` disabled. The app refuses to start without a strong key. |
| `SECRET_KEY` | *(generated by Render)* | `render.yaml` uses `generateValue: true` (at least 24 chars required). Changing it logs everyone out (see "Rotating SECRET_KEY"). |
| `DATABASE_URL` | *(Neon **direct** URL, dashboard only)* | Used for migrations and maintenance. |
| `DATABASE_URL_POOLED` | *(Neon **pooled** URL, dashboard only)* | Used for all runtime traffic (PgBouncer transaction mode; prepared statements are disabled in the client). If only one of the two is set, it is used for both. |
| `DB_POOL_MAX` | `5` (default) | Connections per process. Keep it small on a 512 MB instance. |
| `TRUST_PROXY` | `1` | Honour `X-Forwarded-*` (real client IP for rate limiting, https scheme). |
| `TRUST_PROXY_HOPS` | `2` | Proxies appending to `X-Forwarded-For`: Vercel + Render's load balancer. Use `1` if a custom domain points straight at Render and Vercel is not in the path. |
| `BOOTSTRAP_ADMIN` | `1` for the first start, then `0` | Creates the primary admin from the three variables below. |
| `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | *(typed in the dashboard)* | Never commit these. `ADMIN_EMAIL` must equal `PRIMARY_ADMIN_EMAIL`. |
| `PRIMARY_ADMIN_EMAIL` | `mkkarthik0609@gmail.com` (default) | The owner admin. Cannot be deactivated or deleted; only this admin adds further admins. |
| `INVITE_TTL_HOURS` | `720` (default, 30 days) | How long an added admin e-mail stays registered. |
| `ADMIN_ACCESS_ID` | `campus-connect-123` (default) | Shared admin ID used with an admin e-mail at Admin Login. Demo-grade by design. |
| `REMINDER_INTERVAL_MINUTES` | `60` | Meeting-reminder job interval. |
| `ENABLE_SCHEDULER` | `1` (default) | `0` turns the reminder job off. |
| `SEED_EXTRA_BRANCHES` | `1` (default) | `0` skips seeding the extra branches (ECE, ISE, Mechanical, ...) next to CSE. |
| `LOGIN_MAX_FAILURES_PER_IDENTIFIER`, `LOGIN_MAX_FAILURES_PER_IP`, `SESSION_IDLE_TIMEOUT_MINUTES`, `CAPTCHA_MAX_PER_IP_PER_HOUR`, `LOGIN_CAPTCHA_AFTER_FAILURES` | defaults 5 / 150 / 60 / 60 / 3 | Optional tuning. |

**Vercel needs no environment variables**: only the rewrites in `frontend/vercel.json`.

**Removed and no longer read:** `DATABASE_PATH`, `UPLOAD_ROOT`, `WEBAUTHN_ALLOWED_ORIGINS`. Delete them from the
Render dashboard if they are still set.

**No CORS, cookie-domain or allowed-origin variable exists**: because the Vercel rewrite makes the browser see a
single origin, none is needed. The session cookie (`cc_session`) is `HttpOnly`, `SameSite=Lax` and `Secure`
(automatically, because `APP_ENV=production`).

### Migrations run automatically

At every start the app applies any `migrations/NNNN_name.sql` that has not been applied yet, in order, using the
**direct** URL and a PostgreSQL advisory lock (so two instances starting together cannot collide). Applied
versions are recorded in the table `schema_migrations`.

| Migration | What it adds |
|---|---|
| `0001_baseline.sql` | The full schema of the former SQLite app (users, students, faculty, hierarchy, chats, messages, meetings, notifications, ...), `citext`, the `cc_now()` helper |
| `0002_invitations_storage_audit.sql` | `admin_invitations`, `file_blobs`, `audit_log`, `presence`, `users.session_version` |
| `0003_unverified_classes.sql` | `is_verified` on branches / departments / academic_years / sections |

Migrations are idempotent (`IF NOT EXISTS`). To add one, create the next numbered file; never edit an applied one.

### Verify the backend

1. Wait for the deploy to go **Live**.
2. `https://<service>.onrender.com/healthz` returns HTTP 200 `{"status":"ok"}`. The health check does not touch the
   database, so Render's periodic probes never wake the Neon compute.
3. `https://<service>.onrender.com/api/meta` returns `{"app":"Campus Connect"}`.
   (The API alone has no UI, and `/docs` is intentionally disabled in production.)
4. Check the Render Logs: one process, `applied migration 0001_baseline` (first deploy only), a line
   `Admin bootstrap: created` (first deploy) or `exists`, no tracebacks.
5. Sign in as the primary admin through the Vercel site (after section 3).

### First admin (bootstrap)

There is no public admin signup.

1. In the Render dashboard set `BOOTSTRAP_ADMIN=1`, `ADMIN_NAME`, `ADMIN_EMAIL` (= `PRIMARY_ADMIN_EMAIL`) and
   `ADMIN_PASSWORD`. These live in the dashboard only.
2. On start-up the app creates the primary admin **only if that account does not exist**. It never overwrites an
   existing password, and afterwards it drops `ADMIN_PASSWORD` from the running process' environment.
3. After the first successful start and a successful admin login, **remove `ADMIN_PASSWORD` and set
   `BOOTSTRAP_ADMIN=0`** in Render. Leaving them is not harmful to existing data but keeps a secret around for no
   reason.
4. Further admins are **added** by the primary admin inside the app (Admin -> Admins). Nothing is e-mailed: the person signs in at Admin Login with their e-mail and the shared admin ID (`ADMIN_ACCESS_ID`, default `campus-connect-123`) and the account is created on first sign-in. There are no admin passwords.
5. Fallback from the Render Shell tab: `python create_admin.py --from-env`.

### Upload storage capacity

Chat attachments and profile pictures are stored in the table `file_blobs` (bytea), not on disk. Limits: 8 MB per
chat attachment (png, jpg, jpeg, pdf, docx), 3 MB per profile picture. Uploads are validated by extension, size,
magic bytes **and** structure (Pillow decode for images, `%%EOF` for PDF, a zip containing `word/` for docx).
Access control is unchanged: profile pictures are visible to any signed-in user; chat files only to the two chat
participants or an admin.

Neon Free is **0.5 GB for everything**. Rough rule of thumb: a few hundred 1 MB attachments already use a
noticeable part of it. Watch the storage figure on the Neon dashboard. When it approaches the quota, move
`put/get/delete` in `services/storage.py` (three functions) to Cloudflare R2 or S3 and keep only the key in the
database; no other code needs to change. Deleting old chat attachments or upgrading the Neon plan are the other
options.

---

## 3. Frontend on Vercel (after Render is live)

### What the Vercel project does

`frontend/vercel.json` configures the project (it is read when **Root Directory = `frontend`**):

- Framework `vite`, install `npm ci`, build `npm run build`, output `dist`.
- Rewrites, in order (static files win over rewrites):
  `/api/:path*`, `/uploads/:path*` and `/healthz` -> `https://<your-render-service>.onrender.com/...`, then the SPA
  fallback `/(.*)` -> `/index.html`. **The rewrite destination must be your Render URL.**
- Cache: `/assets/*` (content-hashed by Vite) `public, max-age=31536000, immutable`; everything else served by
  Vercel (including `index.html`) `no-cache`.
- Security headers on the static/SPA responses, matching the API's own policy: CSP (`script-src 'self'`,
  `frame-ancestors 'none'`, ...), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, HSTS. Proxied `/api` and `/uploads` responses carry the API's own headers
  (`/api/*` is `Cache-Control: no-store`).

### Pointing Vercel at Render

Check `frontend/vercel.json`: all three rewrite destinations must contain your Render host. To change it, run in
`frontend/`:

```powershell
npm run set-backend-url -- https://campus-connect-xxxx.onrender.com
```

It edits only the rewrite destinations. Review the diff, commit and push. (Alternatively set `BACKEND_URL` in the
Vercel project; the `prebuild` script then rewrites `vercel.json` during the build. Vercel normally reads
`vercel.json` before the build starts, so if `/api` still hits the old host after deployment, commit the change
instead.)

### Steps

1. Make sure the rewrites point at your Render URL (above).
2. Vercel dashboard -> **Add New -> Project** -> import the same GitHub repo.
3. Project settings: **Root Directory `frontend`**, Framework Preset **Vite**, Build Command `npm run build`,
   Output Directory `dist`, Install Command `npm ci`, Node.js version 24.x (Settings -> General).
4. No environment variables are needed.
5. **Deploy**. Open the `*.vercel.app` URL: the Campus Connect landing page loads.
6. (Optional) Settings -> Domains -> add your college domain, and set `PUBLIC_APP_URL` on Render to it.

> The Hobby plan is for non-commercial use; check Vercel's current terms for an institutional deployment.

### Cookies, CSRF and proxy headers (important)

- **Cookies.** The session cookie `cc_session` is `HttpOnly`, `SameSite=Lax`, `Secure` in production. Because the
  browser only sees the Vercel origin it is a first-party, host-only cookie: nothing needs `SameSite=None`.
- **Client IP.** Vercel appends the real client address to `X-Forwarded-For`; Render's load balancer appends
  Vercel's. With `TRUST_PROXY=1` and `TRUST_PROXY_HOPS=2` the app takes the second entry from the right as the
  client, so login throttling and captcha limits work per real user. With the wrong hop count every user would
  appear to share one proxy IP (and lock each other out), or a client could spoof its address.
- **CSRF.** Every `POST/PUT/PATCH/DELETE` must send `X-CSRFToken` equal to the token in the session. The SPA
  gets the token from `GET /api/auth/session` (and from login/logout responses) and sends it automatically.
  A missing or wrong token gives `400 csrf_failed`.
- **The `*.onrender.com` URL still works** and has its own, separate session cookie. It is a second door to the
  same API; do not advertise it.
- **Uploads** are served by the API at `/uploads/<path>` only to authorised signed-in users, so they also pass
  through the Vercel proxy. Request bodies up to 10 MB (the app's limit) are accepted.

---

## 4. Smoke-test checklist (on the Vercel URL)

Allow up to a minute for the first request if the service was asleep.

- [ ] `/healthz` returns 200 `{"status":"ok"}` through Vercel (proves the rewrite works).
- [ ] The landing page renders styled; in the Network tab `/assets/*.js` come with
      `cache-control: public, max-age=31536000, immutable` and `index.html` with `no-cache`.
- [ ] Deep link `/login` and a hard refresh on `/admin/dashboard` load the SPA (SPA fallback works).
- [ ] Primary admin sign-in works. In DevTools -> Application -> Cookies: `cc_session` is `Secure` + `HttpOnly`,
      host = the Vercel domain.
- [ ] CSRF: a `POST` without the header is rejected, e.g. in the browser console
      `fetch('/api/auth/logout', {method:'POST', credentials:'include'}).then(r => r.status)` returns `400`;
      the normal UI sign-out (which sends the header) works.
- [ ] `/api/*` responses are `Cache-Control: no-store` (also check `x-vercel-cache` is not `HIT`).
- [ ] Admin -> Academics shows CSE with AIML, AIDE, GenAI, Cybersecurity, Blockchain, IoT.
- [ ] Admin -> Admins: add a second admin e-mail; that person signs in at Admin Login with the e-mail and the admin ID.
- [ ] Register a faculty account; Admin assigns it a class (e.g. CSE -> AIML -> 3rd Year -> A).
- [ ] Register a student in that class; the signup form (with its captcha) works.
- [ ] Student sees the assigned faculty; chat and a meeting request between them work.
- [ ] A second faculty member *not* assigned to that class cannot open that class or message the student (403).
- [ ] Upload a profile picture and a chat attachment; both display after a page reload.
- [ ] Redeploy on Render (Manual Deploy) and confirm data **and uploads** are still there.
- [ ] Throttling is per user: 6 wrong passwords for one account lock that account, not other users.
- [ ] Render logs show a single process and no scheduler errors.

## 5. Backups and restore

Your data is in Neon. Use both layers:

1. **Neon built-in point-in-time restore / branching** (7-day history window on Free). In the Neon console you
   can restore the database to an earlier moment or create a branch from one. This is the fastest recovery from
   a bad migration or accidental delete. Take a branch before risky changes.
2. **Logical JSON backup/restore via psycopg** (no `pg_dump` needed on Render). Run from the Render Shell tab or
   locally with `DATABASE_URL` pointing at the **direct** URL:

   ```bash
   python scripts/backup_db.py --out backups/
   python scripts/restore_db.py backups/<file>.json.gz --apply
   ```

   The restore refuses to write into a non-empty target database. Render's filesystem is ephemeral, so copy each
   backup file off Render (download it, or run the script from your own machine) and keep at least one copy
   outside Render and Neon. Uploads are in the database (`file_blobs`), so they are part of the backup.

   _These scripts are being written separately; confirm they exist in `scripts/` before relying on them._

**Restore procedure (summary):** for a point-in-time problem use Neon's restore. For a total loss: create a new
Neon project/branch, put its URLs into Render, let the first start run the migrations, then
`python scripts/restore_db.py <file> --apply` into the empty database.

### Importing the old SQLite data (one-off)

`scripts/migrate_sqlite_to_postgres.py` copies an existing SQLite database and its `uploads/` folder into an empty
PostgreSQL database:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite database.db --uploads uploads            # dry run
python scripts/migrate_sqlite_to_postgres.py --sqlite database.db --uploads uploads --apply     # write
```

It is a dry run unless `--apply` is given, refuses to write into non-empty tables, never deletes anything, and does
**not** copy admin accounts unless `--include-admins` is passed (admins are bootstrapped / added by the primary admin instead).
Run it with `DATABASE_URL` set to the Neon **direct** URL, after the app has applied its migrations.

## 6. Rotating `SECRET_KEY`

`SECRET_KEY` signs the session cookie and keys the captcha answer hash. To rotate it:

1. Render -> service -> Environment -> change `SECRET_KEY` (a new random value of at least 24 characters, for
   example `python -c "import secrets; print(secrets.token_urlsafe(48))"`), save. Render redeploys.
2. Everyone is signed out and must log in again (passwords are not affected: they are hashed independently of the
   key). Outstanding captchas become invalid. Admin invitation links keep working (only the token hash is stored).
3. Do not regenerate it casually; every change signs all users out.

To sign out one user (or after a suspected password leak) change/reset their password or deactivate the account:
that bumps their `session_version` and ends all their other sessions without touching anyone else.

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| First page load takes 30-60 s, "waking the server" banner | Normal on Render Free after ~15 min idle. Wait; the SPA retries. |
| First request after a quiet period is 1-2 s slower than usual | Neon compute woke from scale-to-zero. Normal on the Free plan. |
| API answers 503 with `Retry-After` | The database is unreachable (Neon waking up, quota exhausted, bad URL). Check the Neon dashboard and the `DATABASE_URL*` values; the app recovers by itself when the database is back. |
| Service fails to start, logs show a connection/auth error | `DATABASE_URL` / `DATABASE_URL_POOLED` wrong or missing `sslmode=require`; copy them again from Neon. |
| Vercel build fails: "vercel.json still points at the placeholder" | Run `npm run set-backend-url -- https://<service>.onrender.com` in `frontend/`, commit, push (or set `BACKEND_URL` in Vercel). |
| `/api/...` returns an HTML 404/502 from Vercel, or hits the wrong host | Rewrites still point at an old URL; check `frontend/vercel.json` in the deployed source. |
| Blank page / 404 on deep links | Root Directory is not `frontend`, or the output directory is not `dist`. |
| Every unsafe request returns `400 csrf_failed` | The session cookie is missing (cookies blocked, or the app was opened on a different host than the one that set it) or the SPA is not sending `X-CSRFToken`. Reload the page so `/api/auth/session` runs again. |
| Users are logged out after each deploy | `SECRET_KEY` changed. `generateValue` generates once; do not regenerate. |
| Render health check failing | Check Logs; a missing or short `SECRET_KEY` makes production start-up fail by design. |
| Login throttling locks everybody out | `TRUST_PROXY` / `TRUST_PROXY_HOPS` are wrong so all users share one IP (a proxy address). Check the hop count (2 with Vercel, 1 without). |
| Uploads fail or the database is full | Neon Free storage (0.5 GB) is used up; see "Upload storage capacity". |

## 8. Running the tests

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -n 4
```

The tests need a **throw-away PostgreSQL server**. Set `TEST_DATABASE_ADMIN_URL` to a superuser connection
(default `postgresql://postgres@127.0.0.1:54329/postgres`); the suite creates and drops its own `cc_test_*`
databases there. **Never point it at Neon production.** `tests/conftest.py` blanks `DATABASE_URL`,
and `DATABASE_URL_POOLED` as a safety net.

## 9. Owner action list

**Neon**
1. Create the project near Oregon; copy the direct and pooled URLs.

**Render**
1. Push the repo to GitHub.
2. New -> Blueprint -> select the repo -> set `DATABASE_URL`, `DATABASE_URL_POOLED`, `ADMIN_NAME`,
   `ADMIN_EMAIL`, `ADMIN_PASSWORD` -> Apply.
3. Wait for Live; check `/healthz`; copy the service URL.
4. After the first successful admin login: remove `ADMIN_PASSWORD`, set `BOOTSTRAP_ADMIN=0`.

**Vercel**
1. In `frontend/`: `npm run set-backend-url -- https://<service>.onrender.com`; commit and push.
2. New Project -> import the repo -> **Root Directory `frontend`** -> confirm Build `npm run build`,
   Output `dist` -> Deploy.
3. Run the smoke-test checklist above on the Vercel URL; add your custom domain if you have one.

**Afterwards**
- Schedule logical backups (section 5), keep one off-site copy, and watch Neon's storage figure.
