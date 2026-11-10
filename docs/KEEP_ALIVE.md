# Keep-alive health check (Render + cron-job.org)

## What was added
`GET /health` (and `HEAD`) in `api/routers/system.py` returns `200 {"status":"ok"}`.
It touches nothing: no database, no disk, no session cookie, no network, no auth, so it costs almost no CPU,
RAM or bandwidth. `/healthz` (the Render health check) is also database-free; `/healthz?deep=1` is the variant that checks the database.
No scheduler, worker or dependency was added; cron-job.org is the only thing that sends the periodic request.

> Reality check. A ping every 10 minutes keeps a free Render web service from idling out (the free tier
> spins down after ~15 minutes without inbound traffic), but it does NOT guarantee 100% uptime. Render can
> still restart, suspend or redeploy the service (maintenance, resource limits, monthly instance-hour
> limits, failed deploys) and a missed or failed cron run lets it spin down. Cold start after a spin-down
> takes tens of seconds. `render.yaml` declares `plan: free`:
> the service has no disk and no local state (data and uploads are in Neon PostgreSQL), so a restart or spin-down
> loses nothing; the ping only avoids the cold start. Because `/health` does not touch the database it also does not
> wake the Neon compute (which scales to zero after 5 min idle regardless).

## Configure cron-job.org (manual, ~2 minutes)
cron-job.org's free plan allows intervals down to 1 minute ([FAQ](https://cron-job.org/faq/)), so
every 10 minutes is supported. Nobody but you can reach your account, so do this yourself:

1. Sign up / log in at https://console.cron-job.org/ .
2. **Create cronjob**.
   - **Title**: `CampusConnect keep-alive`
   - **URL**: `https://campusconnect-kpa6.onrender.com/health` (your Render service URL: Render dashboard >
     the service > the `.onrender.com` link; do NOT use the Vercel URL, `/health` is not rewritten there).
     Never put credentials or tokens in the URL.
   - **Execution schedule**: *Every 10 minutes* (equivalent cron: `*/10 * * * *`).
3. **Advanced** tab:
   - **Request method**: `GET`
   - **Follow redirects** (HTTP 3xx): enabled.
   - **Expected status**: leave the default (2xx counts as success; `200` is what the endpoint returns).
   - **Timeout**: 30 s (the maximum on the free plan; a cold start can be slow).
4. **Notifications**: enable *Notify me when the execution of the cronjob fails* (and, optionally, when it
   succeeds again after failures). Add your e-mail in Settings if it is not set.
5. Save, then press **Test run** and confirm `200 OK`.

## Verify
```bash
curl -i https://campusconnect-kpa6.onrender.com/health
```
Expect `HTTP/2 200` and `{"status":"ok"}`. In cron-job.org open the job > **History**: each row should show
`200` roughly every 10 minutes. In Render: **Events** shows no "Service suspended / spun down" entries
while the pings run.

## Monitor
- **Render instance hours / bandwidth**: Dashboard > Account/Workspace > *Billing / Usage*. A free web service
  that never idles uses ~730 h/month; the free allowance is 750 h/month per workspace, so with several free
  services the pings can exhaust it. Watch this page.
- **Restarts / deploys**: service > *Events* and *Logs*.
- **HTTP failures**: service > *Metrics* (HTTP 5xx / latency) and cron-job.org History (non-2xx, timeouts).
- **Cron execution history**: cron-job.org job > History (only the most recent runs are kept).
- **Notifications**: Render > Account Settings > Notifications; cron-job.org failure e-mails.

## Rollback
The change is additive. To remove it: delete `health()` in `api/routers/system.py`, the `"/health"` entry in
`RESERVED_PREFIXES` (`api/errors.py`), `tests/test_health.py`, and delete/disable the cron-job.org job.
Nothing else (start command, env vars, instance type, `render.yaml`) was modified.
