"""Restore a backup made by scripts/backup_db.py into an EMPTY PostgreSQL database.

    python scripts/restore_db.py backups/campusconnect-20261111T000000Z.json.gz            # dry run
    python scripts/restore_db.py backups/campusconnect-20261111T000000Z.json.gz --apply

Target = DATABASE_URL (DIRECT) from the environment / .env. Migrations are applied first, then every table is
filled inside ONE transaction. SAFE BY DEFAULT: dry run unless --apply; it REFUSES to write when any table in the
backup already contains rows (it never deletes or overwrites), and identity sequences are advanced afterwards.
To restore over live data: restore into a fresh Neon branch/database, verify, then repoint the app.
"""
import argparse
import base64
import gzip
import json
import os
import re
import sys

import psycopg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import db as dbmod  # noqa: E402
from api.settings import Settings  # noqa: E402


IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def decode(value):
    if isinstance(value, dict) and "__b64__" in value:
        return base64.b64decode(value["__b64__"])
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=False)
    except ImportError:
        pass
    settings = Settings.from_env()
    if not settings.database_url_direct:
        print("DATABASE_URL is not set.")
        return 2
    with gzip.open(args.backup, "rt", encoding="utf-8") as f:
        dump = json.load(f)
    for table, data in dump["tables"].items():  # the file is untrusted input: names go into SQL text
        if not IDENT.match(table) or not all(IDENT.match(c) for c in data["columns"]):
            print(f"Refusing to run: unsafe table/column name in backup ({table!r}).")
            return 4
    if args.apply:
        dbmod.run_migrations(settings)
    else:
        print("(dry run: schema migrations are NOT applied; the target must already be migrated)")

    with psycopg.connect(settings.database_url_direct, connect_timeout=30) as conn:
        occupied = [t for t in dump["tables"]
                    if dump["tables"][t]["rows"] and conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()]
        if occupied:
            print("Refusing to run: target tables already contain data:", ", ".join(occupied))
            return 3
        for table, data in dump["tables"].items():
            cols = data["columns"]
            if not data["rows"]:
                continue
            marks = ", ".join(["%s"] * len(cols))
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})",
                    [tuple(decode(v) for v in row) for row in data["rows"]])
            if "id" in cols:
                seq = conn.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,)).fetchone()[0]
                if seq:
                    conn.execute(f"SELECT setval('{seq}', (SELECT MAX(id) FROM {table}))")
            print(f"{table:32} {len(data['rows']):>7} rows")
        if args.apply:
            conn.commit()
            print("COMMITTED.")
        else:
            conn.rollback()
            print("Dry run: rolled back. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
