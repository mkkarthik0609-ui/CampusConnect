"""Small closed-loop load test for a LOCAL stack (never point it at production).

    # API running with a throw-away database (see frontend/e2e/README.md), then:
    DATABASE_URL=postgresql://postgres@127.0.0.1:54329/cc_e2e DATABASE_URL_POOLED= \
      python scripts/load_test.py --base http://127.0.0.1:8765 --users 20 --seconds 30

Seeds N students (+ one faculty assigned to them) directly in the database, then runs N virtual users in
parallel threads. Each user signs in once and loops: session check, chat list, notifications, send a chat
message, read the thread (the same mix the SPA's polling produces). Prints throughput, latency percentiles and
errors. The numbers describe THIS machine; scale for Render Free's 0.1 CPU / Neon's cold compute yourself.
"""
import argparse
import os
import statistics
import sys
import threading
import time

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import db as dbmod  # noqa: E402
from api.settings import Settings  # noqa: E402
from models import academic_queries as aq  # noqa: E402
from models import queries  # noqa: E402
from services import assignment_service, auth_service  # noqa: E402

PASSWORD = "Load#Passw0rd1"


def seed(n):
    settings = Settings.from_env(seed_extra_branches=False)
    host = settings.database_url_direct.split("@")[-1].split("/")[0]
    if not any(h in host for h in ("127.0.0.1", "localhost")):
        raise SystemExit("Refusing to seed a non-local database.")
    dbmod.init_db(settings)
    with dbmod.db_session(settings):
        admin = queries.get_user_by_email(settings.primary_admin_email)
        combo = aq.find_combo_by_names("CSE", "AIML", "3rd Year", "A")
        if not queries.get_user_by_email("load.faculty@college.edu"):
            auth_service.register_faculty({
                "full_name": "Load Faculty", "faculty_code": "LOADF1", "department": "AIML",
                "professional_email": "load.faculty@college.edu", "password": PASSWORD, "subjects": ["DSA"]})
            fac = queries.get_faculty_by_user_id(queries.get_user_by_email("load.faculty@college.edu")["id"])
            assignment_service.admin_assign(fac["id"], combo["section_id"], admin["id"])
        faculty_id = queries.get_faculty_by_user_id(queries.get_user_by_email("load.faculty@college.edu")["id"])["id"]
        for i in range(n):
            email = f"load.student{i}@college.edu"
            if not queries.get_user_by_email(email):
                auth_service.register_student({
                    "full_name": f"Load Student {i}", "usn": f"1LD21CS{i:03d}", "section_id": combo["section_id"],
                    "phone": "9876543210", "personal_email": f"load.p{i}@example.com",
                    "college_email": email, "password": PASSWORD})
    return faculty_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--think", type=float, default=0.2, help="pause between iterations (seconds)")
    args = ap.parse_args()
    faculty_id = seed(args.users)

    lat, errors, lock = [], [], threading.Lock()
    login_lat = []

    def record(name, started, ok):
        with lock:
            lat.append((name, time.perf_counter() - started))
            if not ok:
                errors.append(name)

    def user(i):
        c = httpx.Client(base_url=args.base, timeout=60)
        s = c.get("/api/auth/session").json()
        t = time.perf_counter()
        r = c.post("/api/auth/login", headers={"X-CSRFToken": s["csrf_token"]},
                   json={"identifier": f"load.student{i}@college.edu", "password": PASSWORD})
        login_lat.append(time.perf_counter() - t)
        if r.status_code != 200:
            with lock:
                errors.append(f"login {r.status_code}")
            return
        csrf = r.json()["csrf_token"]
        chat_id = c.post("/api/chat/open", headers={"X-CSRFToken": csrf}, json={"faculty_id": faculty_id}).json()["chat_id"]
        end = time.time() + args.seconds
        n = 0
        while time.time() < end:
            for name, method, url, kw in (
                ("session", "get", "/api/auth/session", {}),
                ("chat list", "get", "/api/chat", {}),
                ("notifications", "get", "/api/notifications", {}),
                ("thread", "get", f"/api/chat/{chat_id}", {}),
                ("send message", "post", f"/api/chat/{chat_id}/messages",
                 {"headers": {"X-CSRFToken": csrf}, "json": {"message_text": f"hello {i}-{n}"}}),
            ):
                if name == "send message" and n % 5:
                    continue
                t = time.perf_counter()
                try:
                    resp = getattr(c, method)(url, **kw)
                    record(name, t, resp.status_code < 400)
                except Exception:  # noqa: BLE001
                    record(name, t, False)
            n += 1
            time.sleep(args.think)
        c.close()

    started = time.time()
    threads = [threading.Thread(target=user, args=(i,)) for i in range(args.users)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    wall = time.time() - started

    def pct(values, p):
        values = sorted(values)
        return values[min(len(values) - 1, int(len(values) * p))] * 1000

    print(f"users={args.users} duration={wall:.1f}s requests={len(lat)} errors={len(errors)} "
          f"throughput={len(lat) / wall:.1f} req/s")
    if login_lat:
        print(f"login (Argon2id): median {statistics.median(login_lat) * 1000:.0f} ms, max {max(login_lat) * 1000:.0f} ms")
    for name in sorted({n for n, _ in lat}):
        v = [x for n, x in lat if n == name]
        print(f"  {name:14} n={len(v):5} p50={pct(v, .5):6.0f} ms  p95={pct(v, .95):6.0f} ms  p99={pct(v, .99):6.0f} ms")
    if errors:
        print("errors:", {e: errors.count(e) for e in set(errors)})
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
