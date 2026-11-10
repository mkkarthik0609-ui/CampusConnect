"""One-off, non-destructive copy of a legacy SQLite database (+ its uploads folder) into PostgreSQL.

    python scripts/migrate_sqlite_to_postgres.py --sqlite database.db --uploads uploads            # dry run
    python scripts/migrate_sqlite_to_postgres.py --sqlite database.db --uploads uploads --apply

* Target = DATABASE_URL (the DIRECT Neon connection) from the environment / .env. Schema migrations are applied
  first (idempotent). Nothing is printed that contains a connection string.
* SAFE BY DEFAULT: the SQLite file is opened read-only; the script REFUSES to run when any table it would fill
  already has rows (it never deletes or overwrites), and the whole copy is a single transaction.
* ADMIN accounts are NOT copied (use --include-admins to copy them): the primary admin is created from the
  protected ADMIN_* environment variables at first start, other admins are re-invited. Rows that belong to an
  un-copied admin are skipped (admin_messages) or have the admin reference cleared (assigned_by / reviewed_by).
* Rows keep their ids; identity sequences are advanced afterwards. Upload files referenced by messages and
  profile pictures are copied into table file_blobs (same relative key the app uses).
* Old password hashes (werkzeug scrypt/pbkdf2) keep working and are upgraded to Argon2id on each user's next login.
"""
import argparse
import mimetypes
import os
import sqlite3
import sys

import psycopg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import db as dbmod  # noqa: E402
from api.settings import Settings  # noqa: E402

# Tables in foreign-key order.
TABLES = [
    "users", "branches", "departments", "academic_years", "sections", "faculty", "students", "faculty_subjects",
    "faculty_classes", "faculty_assignments", "faculty_assignment_requests", "supporting_relationships", "chats",
    "messages", "admin_messages", "meeting_requests", "permission_requests", "notifications",
]
# nullable references to users that may point at an un-copied admin -> cleared instead of failing
CLEAR_IF_MISSING = {
    "faculty_assignments": ["assigned_by"],
    "faculty_assignment_requests": ["reviewed_by"],
}


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=False)
    except ImportError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", required=True, help="path to the legacy SQLite database file")
    ap.add_argument("--uploads", default=None, help="legacy uploads folder (contains chat/ and profile/)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run, rolled back)")
    ap.add_argument("--include-admins", action="store_true", help="also copy ADMIN accounts")
    args = ap.parse_args(argv)

    load_env()
    settings = Settings.from_env()
    url = settings.database_url_direct
    if not url:
        print("DATABASE_URL is not set.")
        return 2
    if not os.path.isfile(args.sqlite):
        print(f"SQLite file not found: {args.sqlite}")
        return 2

    if args.apply:
        dbmod.run_migrations(settings)
    else:
        print("(dry run: schema migrations are NOT applied; the target must already be migrated)")
    src = sqlite3.connect(f"file:{os.path.abspath(args.sqlite)}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    with psycopg.connect(url, connect_timeout=30) as dst:
        occupied = [t for t in TABLES if t in have and dst.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()]
        if occupied:
            print("Refusing to run: target tables already contain data:", ", ".join(occupied))
            return 3

        skipped_admin_ids = set()
        report = {}
        for table in TABLES:
            if table not in have:
                continue
            dst_cols = [r[0] for r in dst.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (table,))]
            src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            cols = [c for c in src_cols if c in dst_cols]
            rows = src.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id").fetchall()
            copied = skipped = 0
            for row in rows:
                values = dict(zip(cols, tuple(row)))
                if table == "users" and values["role"] == "ADMIN" and not args.include_admins:
                    skipped_admin_ids.add(values["id"])
                    skipped += 1
                    continue
                refs = [values.get(k) for k in ("sender_user_id", "recipient_user_id", "requester_user_id",
                                                "target_approver_user_id", "user_id")]
                if table in ("admin_messages", "messages", "permission_requests", "notifications") and any(
                        r in skipped_admin_ids for r in refs if r is not None):
                    skipped += 1
                    continue
                for col in CLEAR_IF_MISSING.get(table, []):
                    if values.get(col) in skipped_admin_ids:
                        values[col] = None
                dst.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                    tuple(values[c] for c in cols))
                copied += 1
            report[table] = (len(rows), copied, skipped)
            if "id" in dst_cols and copied:
                dst.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))")

        files = 0
        if args.uploads and os.path.isdir(args.uploads):
            paths = [r[0] for r in dst.execute(
                "SELECT attachment_path FROM messages WHERE attachment_path IS NOT NULL "
                "UNION SELECT profile_picture_path FROM users WHERE profile_picture_path IS NOT NULL")]
            for rel in paths:
                full = os.path.realpath(os.path.join(args.uploads, *rel.split("/")))
                if not full.startswith(os.path.realpath(args.uploads) + os.sep) or not os.path.isfile(full):
                    print(f"  upload missing on disk, skipped: {rel}")
                    continue
                with open(full, "rb") as f:
                    data = f.read()
                dst.execute(
                    "INSERT INTO file_blobs (path, content, content_type, size_bytes) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (path) DO NOTHING",
                    (rel, data, mimetypes.guess_type(full)[0] or "application/octet-stream", len(data)))
                files += 1

        print(f"{'table':32} {'in sqlite':>9} {'copied':>7} {'skipped':>8}")
        for table, (n, copied, skipped) in report.items():
            print(f"{table:32} {n:>9} {copied:>7} {skipped:>8}")
        print(f"upload files copied into file_blobs: {files}")
        if args.apply:
            dst.commit()
            print("COMMITTED.")
        else:
            dst.rollback()
            print("Dry run: rolled back. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
