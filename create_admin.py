"""CLI to create an admin account. There is no public admin signup route
(PRD section 4.3 / ESD section 4) - this script (or BOOTSTRAP_ADMIN=1 at app start) is the way
to create the first admin.

Usage:
    venv\\Scripts\\python.exe create_admin.py               # interactive
    venv\\Scripts\\python.exe create_admin.py --from-env    # non-interactive, idempotent

--from-env reads ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD from the environment (or .env). It
creates the admin if no user with that email exists; otherwise it exits 0 and changes nothing (an
existing account's password is never overwritten). Passwords are never printed.
"""
import getpass
import os
import sys

from api.db import db_session, init_db
from api.settings import Settings, set_settings
from models import queries
from services import auth_service
from services.auth_service import ValidationError


def bootstrap_from_env():
    """Kept for backwards compatibility: see ``auth_service.bootstrap_admin_from_env``.
    Must run inside ``db_session()``. Returns 'created', 'exists' or 'skipped'."""
    return auth_service.bootstrap_admin_from_env()


def _run_from_env(settings):
    with db_session(settings):
        try:
            status = auth_service.bootstrap_admin_from_env()
        except ValidationError as e:
            print(f"Error: {e}")
            return 1
    if status == "skipped":
        print("ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD must all be set. Nothing was changed.")
        return 2
    if status == "exists":
        print("An account with that email already exists. Nothing was changed.")
    else:
        print("Admin account created. You can now sign in.")
    return 0


def _run_interactive(settings):
    with db_session(settings):
        existing_admins = queries.count_admins()
        if existing_admins > 0:
            print(f"{existing_admins} admin account(s) already exist.")
            proceed = input("Create another admin anyway? [y/N]: ").strip().lower()
            if proceed != "y":
                print("Cancelled.")
                return 0

        full_name = input("Admin full name: ").strip()
        email = input("Admin email: ").strip().lower()
        password = getpass.getpass("Admin password (min 8 chars, upper + lower + digit): ")
        confirm = getpass.getpass("Confirm password: ")

        try:
            if password != confirm:
                raise ValidationError("Passwords do not match.")
            email = auth_service.validate_email(email, "Email")
            full_name = auth_service.validate_required(full_name, "Full name")
            if queries.get_user_by_email(email):
                raise ValidationError("An account with this email already exists.")
            password_hash = auth_service.hash_password(password, disallow=(email,))
        except ValidationError as e:
            print(f"Error: {e}")
            return 1

        user_id = queries.create_user("ADMIN", email, password_hash, full_name)
        print(f"Admin account created (id={user_id}). You can now sign in.")
        return 0


def main(argv=None, settings=None):
    argv = sys.argv[1:] if argv is None else argv
    settings = settings or Settings.from_env(enable_scheduler=False)
    set_settings(settings)
    os.makedirs(os.path.dirname(os.path.abspath(settings.database_path)), exist_ok=True)
    init_db(settings)  # make sure the schema exists (idempotent)
    if "--from-env" in argv:
        return _run_from_env(settings)
    return _run_interactive(settings)


if __name__ == "__main__":
    sys.exit(main())
