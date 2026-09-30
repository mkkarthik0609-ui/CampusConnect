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

# The CLI must not start the reminder scheduler thread.
os.environ.setdefault("ENABLE_SCHEDULER", "0")

from models import queries  # noqa: E402
from services import auth_service  # noqa: E402
from services.auth_service import ValidationError  # noqa: E402


def bootstrap_from_env():
    """Create the admin described by ADMIN_NAME/ADMIN_EMAIL/ADMIN_PASSWORD if it does not exist yet.
    Must run inside an app context. Returns 'created', 'exists' or 'skipped' (variables missing).
    Raises ValidationError if the supplied values are invalid."""
    name = os.environ.get("ADMIN_NAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not (name and email and password):
        return "skipped"
    return "created" if auth_service.ensure_admin(name, email, password) else "exists"


def _run_from_env(app):
    with app.app_context():
        try:
            status = bootstrap_from_env()
        except ValidationError as e:
            print(f"Error: {e}")
            return 1
    if status == "skipped":
        print("ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD must all be set. Nothing was changed.")
        return 2
    if status == "exists":
        print("An account with that email already exists. Nothing was changed.")
    else:
        print("Admin account created. You can now log in at /login.")
    return 0


def _run_interactive(app):
    with app.app_context():
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
        print(f"Admin account created (id={user_id}). You can now log in at /login.")
        return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    from app import create_app  # imported lazily: app.py may itself import this module at startup
    app = create_app()
    if "--from-env" in argv:
        return _run_from_env(app)
    return _run_interactive(app)


if __name__ == "__main__":
    sys.exit(main())
