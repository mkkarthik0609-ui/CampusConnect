import os
import sqlite3
from flask import current_app, g


def _schema_path():
    return os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=15,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 15000")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _columns(db, table):
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(db):
    """Additive, idempotent migrations for databases created before the academic hierarchy."""
    if "section_id" not in _columns(db, "students"):
        db.execute("ALTER TABLE students ADD COLUMN section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_students_section ON students(section_id)")
    if "last_login_at" not in _columns(db, "users"):
        db.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")


def init_db(app):
    with app.app_context():
        db = get_db()
        if app.config.get("DATABASE_PATH") != ":memory:":
            try:
                db.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:
                pass
        with open(_schema_path(), "r", encoding="utf-8") as f:
            db.executescript(f.read())
        _migrate(db)
        db.commit()
        from services import academic_service
        academic_service.seed_default_structure()
        academic_service.backfill_legacy_data()


def register_db(app):
    app.teardown_appcontext(close_db)
