"""Logical backup of the PostgreSQL database to one gzip-compressed JSON file (no pg_dump needed).

    python scripts/backup_db.py --out backups/                    # backups/campusconnect-YYYYmmddTHHMMSSZ.json.gz
    python scripts/backup_db.py --out backups/ --keep 14          # also prune all but the newest 14 backups

Uses DATABASE_URL (the DIRECT Neon connection) from the environment / .env, reads inside ONE repeatable-read
snapshot (so the file is consistent while the app keeps running) and never prints a connection string.
Includes uploaded files (table file_blobs, base64). Transient tables (login_attempts, captcha_challenges) are
skipped. Restore with scripts/restore_db.py. Neon's own point-in-time restore (7 days on Free) is the primary
safety net; this file is the portable second copy you can keep off-platform.
"""
import argparse
import base64
import datetime as dt
import glob
import gzip
import json
import os
import sys

import psycopg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.settings import Settings  # noqa: E402

SKIP = {"schema_migrations", "login_attempts", "captcha_challenges"}
# Foreign-key order (parents first); unknown extra tables are appended alphabetically.
ORDER = [
    "users", "branches", "departments", "academic_years", "sections", "faculty", "students", "faculty_subjects",
    "faculty_classes", "faculty_assignments", "faculty_assignment_requests", "supporting_relationships", "chats",
    "messages", "admin_messages", "meeting_requests", "permission_requests", "notifications", "admin_invitations",
    "file_blobs", "audit_log", "presence",
]


def ordered(tables):
    known = [t for t in ORDER if t in tables]
    return known + sorted(t for t in tables if t not in ORDER)


def encode(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(value)).decode("ascii")}
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="backups", help="output directory")
    ap.add_argument("--keep", type=int, default=0, help="keep only the newest N backups in --out (0 = keep all)")
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=False)
    except ImportError:
        pass
    url = Settings.from_env().database_url_direct
    if not url:
        print("DATABASE_URL is not set.")
        return 2
    os.makedirs(args.out, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = os.path.join(args.out, f"campusconnect-{stamp}.json.gz")
    tmp = target + ".partial"

    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        version = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        names = {r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")} - SKIP
        dump = {"format": 1, "created_at": stamp, "schema_version": version, "tables": {}}
        for table in ordered(names):
            cur = conn.execute(f"SELECT * FROM {table}")
            cols = [d.name for d in cur.description]
            dump["tables"][table] = {"columns": cols, "rows": [[encode(v) for v in row] for row in cur.fetchall()]}
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(dump, f)
    os.replace(tmp, target)  # never leaves a half-written backup under the final name
    total = sum(len(t["rows"]) for t in dump["tables"].values())
    print(f"Backup written: {target} ({os.path.getsize(target)} bytes, {len(dump['tables'])} tables, {total} rows, "
          f"schema v{version})")

    if args.keep > 0:
        files = sorted(glob.glob(os.path.join(args.out, "campusconnect-*.json.gz")))
        for old in files[:-args.keep]:
            os.remove(old)
            print(f"Pruned {old}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
