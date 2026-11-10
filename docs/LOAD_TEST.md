# Load test — measured on a development machine (not on Render/Neon)

`scripts/load_test.py` — closed-loop virtual users against a **local** stack (single `uvicorn` process, local
PostgreSQL 13, Windows 11 desktop CPU, pool of 10 connections). Each user signs in once (Argon2id), then loops:
session check, chat list, notifications, chat thread, and every 5th round a sent message (≈ what the SPA's
polling produces), with 0.1 s think time.

| Virtual users | Requests | Errors | Throughput | p50 | p95 | p99 | Login (Argon2id) median |
|---|---|---|---|---|---|---|---|
| 20 (think 0.2 s) | 6 548 | 0 | 198 req/s | 29–63 ms | 60–101 ms | 72–143 ms | 128 ms |
| 60 (think 0.1 s) | 6 256 | 0 | 202 req/s | ≈ 220 ms | ≈ 270 ms | ≈ 300 ms | 322 ms |
| 120 (think 0.1 s) | 4 970 | 0 | 123 req/s | ≈ 600 ms | ≈ 900 ms | ≈ 1.0 s | 599 ms |

## What it found (and what was fixed)

* **Deadlock under load (fixed).** The first run at 60 users collapsed to ~2 req/s with 60 s hangs. Cause: FastAPI
  runs sync dependencies and endpoints on 40 worker threads; requests that already held a pooled connection waited for
  a free worker to continue while the 40 workers were all blocked waiting for one of the few pooled connections.
  Fix: *admission control* in `DbMiddleware` — at most `DB_POOL_MAX` requests are in flight, the rest queue cheaply on
  the event loop and get `503 + Retry-After` after 15 s; plus a dedicated thread limiter for returning connections.
  Regression test: `tests/test_concurrency.py::test_many_more_requests_than_pooled_connections_never_deadlock`.
* **One process saturates around 200 req/s** locally (Python GIL + Argon2 on login). Latency then grows linearly with
  users instead of failing — requests queue rather than error.
* **Login is the expensive request** (≈ 130 ms CPU locally, Argon2id 19 MiB / t=2). On Render Free's 0.1 vCPU share
  expect it to be several times slower; it only happens once per session (12 h), so it matters for *login bursts*
  (e.g. a class signing in at the start of a period), not for steady state.

## What this does NOT tell you

* Render Free has a **shared 0.1 CPU and 512 MB RAM**; the numbers above are from a much faster machine. Divide
  throughput by roughly the CPU ratio rather than trusting them. They were **not** measured on Render or Neon.
* Neon adds network latency per query (typically 20–60 ms from Render Oregon) and its compute scales to zero after
  5 minutes idle (first query after idle +0.5–2 s). A typical request issues 2–6 queries, so budget ≈ 100–300 ms
  per request on the free stack, and ≈ 40–60 s for the very first request after Render has slept.
* Polling dominates traffic: the SPA polls chat/notifications every few seconds per open tab. 100 simultaneously
  open tabs ≈ 30–50 req/s before any user action. Hidden tabs stop polling and errors back off (frontend).

## Practical capacity guidance for the free tier (an estimate, to be confirmed on the deployed stack)

* Comfortable: tens of concurrently *active* users (a mentoring cohort / one department).
* Likely fine but sluggish at login bursts: ~100–150 concurrently open tabs.
* Beyond that: move the API off the 0.1 CPU free instance first (it is the bottleneck, not Neon).
* Neon Free limits that bite first: 0.5 GB storage (uploads live in the database — 8 MB per attachment) and
  100 compute-hours/month (keep `/healthz` database-free, which it is, and avoid external pingers that call
  `/healthz?deep=1`).

Reproduce: see `frontend/e2e/README.md` for the local stack, then
`python scripts/load_test.py --users 60 --seconds 30`.
