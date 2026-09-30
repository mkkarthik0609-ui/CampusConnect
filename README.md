# Campus Connect

A college web application connecting students and faculty for academic communication
(**Mentor-Connect**), faculty meeting requests, supporting-faculty relationships,
notifications, and administration — plus a separate scheduling-research component.

Built with **Python 3.12 + Flask + SQLite** (server-rendered Jinja templates). See `PRD.md` for
product requirements and `ESD.md` for the engineering/system design this implementation follows.

Key documents:

| Document | What it covers |
|---|---|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Render (backend) + Vercel (frontend) deployment, env vars, smoke tests, backups, SQLite vs PostgreSQL |
| [`DATABASE.md`](DATABASE.md) | All tables, ER + hierarchy diagrams, idempotent migration / backfill |
| [`docs/ACADEMIC_HIERARCHY.md`](docs/ACADEMIC_HIERARCHY.md) | Branch → Department → Year → Section model, Admin authority, access rules |
| `.env.example` | Every environment variable the app reads (placeholders only) |

## 1. Project Structure

```
CampusConnect/
├── app.py                  # Flask app factory (+ module-level `app`), security headers, /healthz, scheduler
├── wsgi.py                 # production entrypoint: gunicorn wsgi:app
├── gunicorn.conf.py        # 1 worker + threads (in-process scheduler, SQLite single writer)
├── config.py               # all configuration, read from environment / .env
├── create_admin.py         # CLI: create an admin (interactive, or --from-env)
├── requirements.txt        # runtime dependencies (pinned)
├── requirements-dev.txt    # + pytest, pytest-cov
├── requirements-research.txt  # optional: matplotlib for the research charts
├── .env.example            # documented environment variables (copy to .env)
├── render.yaml             # Render Blueprint (backend web service + persistent disk)
├── vercel.json             # Vercel: serve /static from CDN, proxy everything else to Render
├── package.json            # "build": node scripts/build-frontend.mjs
├── .vercelignore           # keeps Python files out of the Vercel upload
├── .github/workflows/ci.yml   # pytest on push / PR + frontend bundle build
│
├── scripts/
│   ├── build-frontend.mjs  # copies static/ -> public/static, writes public/robots.txt
│   ├── set-backend-url.mjs # writes your Render URL into vercel.json
│   └── backup_db.py        # online SQLite backup (+ integrity check, pruning)
│
├── models/
│   ├── database.py         # sqlite3 connection, WAL, additive idempotent migrations
│   ├── schema.sql          # full relational schema (see DATABASE.md)
│   ├── queries.py          # parameterized SQL for users, chats, meetings, ...
│   └── academic_queries.py # hierarchy, faculty assignments, class-scope checks
│
├── services/               # business logic, independent of Flask request objects
│   ├── auth_service.py     # validation, registration, password hashing, login throttling
│   ├── otp_service.py      # signup OTP (on-screen demo or SMTP e-mail)
│   ├── academic_service.py # Branch/Department/Year/Section rules, seeding, legacy backfill
│   ├── assignment_service.py  # faculty <-> class assignments, requests, access helpers
│   ├── permission_service.py  # profile-change approvals (student→faculty, faculty→admin)
│   ├── chat_service.py     # Mentor-Connect access rules, send/edit rules
│   ├── meeting_service.py  # meeting state machine, reminders
│   ├── supporting_service.py  # supporting-faculty relationship requests
│   ├── notification_service.py
│   ├── file_service.py     # upload validation (extension + magic bytes + size)
│   └── scheduling/         # RESEARCH ONLY — see section 9
│
├── routes/                 # Flask blueprints (thin; delegate to services)
│   ├── auth.py, student.py, faculty.py, admin.py, admin_academic.py,
│   ├── chat.py, meetings.py, supporting.py, notifications.py, helpers.py
│
├── templates/              # Jinja2, organised by auth / student / faculty / admin
├── static/                 # css, js, images (served by Vercel's CDN in production)
├── uploads/                # profile/{students,faculty}, chat  (contents git-ignored)
├── docs/ACADEMIC_HIERARCHY.md
├── research/               # scheduling experiment entry point + generated results
└── tests/                  # pytest suite
```

## 2. Local Setup (Windows)

Requires Python 3.12.

```powershell
cd C:\dev\CampusConnect
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # runtime + test tools
copy .env.example .env                                           # then edit .env (git-ignored)
```

macOS/Linux: `python3 -m venv venv && venv/bin/pip install -r requirements-dev.txt`.

For a runtime-only install use `requirements.txt` (this is what Render installs).

### Configuration

Settings come from environment variables; a local `.env` file is loaded automatically
(real environment variables win). The defaults work for development. In development with no
`SECRET_KEY`, the app generates a random one and stores it in `.dev_secret_key` (git-ignored) so
sessions survive restarts. In production (`APP_ENV=production`) a strong `SECRET_KEY` is
mandatory and the app refuses to start without one. See `.env.example` for every variable.

## 3. Database

The schema is created — and older databases are upgraded — automatically on start
(`models/database.init_db()`): tables are created with `IF NOT EXISTS`, missing columns are
added with `ALTER TABLE`, the default academic structure is seeded once, and legacy free-text
classes are linked to it. It is additive and idempotent; details in `DATABASE.md`.

The database file is `database.db` next to `app.py` (override with `DATABASE_PATH`). It is
git-ignored and must never be committed. To start fresh locally, stop the app and delete
`database.db` (and any `database.db-wal` / `-shm`).

## 4. Creating the First Admin

There is **no public admin signup**. Choose one:

```powershell
# interactive (prompts for name, email, password)
venv\Scripts\python.exe create_admin.py

# non-interactive: reads ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD from the environment / .env
venv\Scripts\python.exe create_admin.py --from-env
```

or set `BOOTSTRAP_ADMIN=1` together with `ADMIN_NAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` and the
app creates the admin on start-up when that account does not exist yet (this is how the Render
deployment does it). Passwords need at least 8 characters with upper-case, lower-case and a digit.
Put real values only in your private `.env` or the hosting dashboard — never in tracked files.
Admins can create further admins in the UI (**Admin → Admins**).

## 5. Running the Application

```powershell
venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:5000>. Debug mode is opt-in (`FLASK_DEBUG=1`) and ignored in production.
The meeting-reminder job (APScheduler, every `REMINDER_INTERVAL_MINUTES`, default 60) starts with
the app; disable it with `ENABLE_SCHEDULER=0`.

Production-style run (what Render executes), on Linux/macOS:

```bash
gunicorn wsgi:app -c gunicorn.conf.py --workers 1 --threads 4
```

(gunicorn does not run on native Windows; use WSL or just `python app.py` for local work.)

## 6. Academic Hierarchy (summary)

Admin owns the structure **Branch → Department → Year → Section**. The default seed is branch
`CSE` with departments `AIML`, `AIDE`, `GenAI`, `Cybersecurity`, `Blockchain`, `IoT`, years
`1st`–`4th`, and sections `A`–`C`.

- Students pick their class once at registration and cannot change it; Admin can **remove the
  registration** so the student can register again in the right class.
- Faculty have no classes at signup. Admin assigns them (many sections per faculty, several faculty
  per section) or approves their **class requests**.
- Faculty reach students, and students reach faculty, only through an active class assignment or an
  accepted supporting-faculty relationship — enforced server-side for chat, meetings, search,
  supporting requests and profile approvals.

Full rules and the file that implements each check: `docs/ACADEMIC_HIERARCHY.md`.

## 7. Demo Usage

1. **Admin** logs in (account from section 4), reviews **Academics**, and later **Assignments**.
2. **Faculty** registers at `/signup/faculty` (name, Faculty ID, department, subjects,
   professional email, password), then asks for classes under **My classes**, or Admin assigns
   them directly.
3. **Student** registers at `/signup/student`: college email → OTP (shown on screen in demo mode,
   e-mailed if SMTP is configured) → details including the Branch/Department/Year/Section.
4. Users log in at `/login` with email (students/faculty can also use Faculty ID / USN).
5. The student opens **Mentor-Connect** to message the faculty assigned to their class, or finds
   other faculty and sends a **supporting-faculty request** (faculty must accept before chat or
   meetings are permitted).
6. The student sends a **meeting request**. Faculty accepts or rejects it and, on accept, types
   the time as free text (e.g. "Tomorrow after 3:30 PM") — no calendar, fixed duration, or
   automatic slot assignment.
7. Either party can mark a meeting **Completed** or **Cancel** it (students must give a reason).
   Open meetings keep receiving reminders; there is no automatic expiry.
8. Phone / personal-email changes need approval (student → an in-scope class faculty; faculty
   changes → Admin). Nothing is applied until approved.

## 8. Testing

```powershell
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m pytest --cov=. -q      # with coverage
```

CI (`.github/workflows/ci.yml`) runs the same on every push and pull request with Python 3.12,
and also builds the Vercel static bundle.

## 9. Scheduling Research Component

Kept entirely separate from the live application (PRD section 13 / ESD section 22) — it never
touches real student/faculty accounts. Needs `pip install -r requirements-research.txt`
(matplotlib).

```powershell
venv\Scripts\python.exe research\run_experiment.py
```

It generates a synthetic dataset (`research/data/requests.csv`) and runs the same data through:

1. **FCFS** (`services/scheduling/fcfs.py`) — arrival order only.
2. **Rule-Based** (`services/scheduling/rule_based.py`) — priority ordering, conflict buffer,
   availability/overlap checks.
3. **Intelligent** (`services/scheduling/intelligent.py`) — transparent weighted scoring (no deep
   learning; weights are named constants in `WEIGHTS`).

Output lands in `research/results/` (`comparison.md` / `.json`, PNG charts, per-method CSVs).

## 10. Security Features

- Passwords hashed with Werkzeug; password policy enforced; college-email passwords never requested.
- Login throttling and temporary lockout per account and per IP (`login_attempts` table), one
  generic error for unknown user / wrong password / inactive account.
- CSRF protection on all state-changing requests (Flask-WTF); session cookie is `HttpOnly`,
  `SameSite=Lax`, `Secure` in production, with an absolute and an idle timeout.
- Security headers on every response (CSP, `X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, HSTS in production); logged-in HTML is `no-store`.
- Production refuses to start with a missing/weak `SECRET_KEY`; no default admin credentials;
  secrets come only from the environment.
- Role and ownership checks are server-side (`routes/helpers.py` `role_required`, plus per-record
  checks in services); class-scope access rules are described in `docs/ACADEMIC_HIERARCHY.md`.
- Uploads validated by extension, size and magic bytes, stored under generated names, and served
  only to logged-in users (non-images as downloads).
- All SQL is parameterized.
- Signup OTP rate-limited; OTP hashed at rest.

## 11. Deployment Summary

Backend on **Render** (gunicorn, one worker + threads, persistent disk at `/var/data` holding the
SQLite database and uploads, health check `/healthz`); frontend on **Vercel**, which serves
`/static` from its CDN and proxies every other route to Render so the browser sees a single origin.

1. Render: *New → Blueprint*, select the repo, enter `ADMIN_NAME` / `ADMIN_EMAIL` /
   `ADMIN_PASSWORD`, apply (paid **Starter** plan needed for the disk).
2. `node scripts/set-backend-url.mjs https://<service>.onrender.com`, commit, push.
3. Vercel: *New Project*, import the repo, deploy.

Step-by-step instructions, the free-plan data-loss warning, backups, and the PostgreSQL upgrade path
are in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## 12. Design Constraints Honored

No booking calendar, no fixed meeting duration, no automatic faculty availability, no automatic
no-show/expiry, no message deletion, no public admin signup, no college-email password storage,
no paid OTP service, no purple/violet theme — see `PRD.md` section 17 and `ESD.md` section 39 for
the full list this implementation was built against.
