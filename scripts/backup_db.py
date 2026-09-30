"""Consistent online backup of the SQLite database (safe while the app is running).

Uses sqlite3's backup API, the same mechanism as the CLI's `.backup` command, so it needs no
`sqlite3` binary and produces a single self-contained file (WAL contents included).

    python scripts/backup_db.py                       # uses DATABASE_PATH, writes to BACKUP_DIR
    python scripts/backup_db.py --keep 14 --dest /var/data/backups

On Render (Shell tab of the web service):
    python scripts/backup_db.py --dest /var/data/backups --keep 14

Environment: DATABASE_PATH (default ./database.db), BACKUP_DIR (default ./backups).
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "database.db")))
    parser.add_argument("--dest", default=os.environ.get("BACKUP_DIR", os.path.join(BASE_DIR, "backups")))
    parser.add_argument("--keep", type=int, default=14, help="number of newest backups to keep (0 = keep all)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.db):
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    os.makedirs(args.dest, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = os.path.join(args.dest, f"campusconnect-{stamp}.db")

    src = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if check != "ok":
        print(f"Backup written to {target} but integrity_check reported: {check}", file=sys.stderr)
        return 2
    print(f"Backup OK: {target} ({os.path.getsize(target)} bytes)")

    if args.keep > 0:
        old = sorted(f for f in os.listdir(args.dest) if f.startswith("campusconnect-") and f.endswith(".db"))
        for name in old[:-args.keep]:
            os.remove(os.path.join(args.dest, name))
            print(f"Pruned old backup: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
