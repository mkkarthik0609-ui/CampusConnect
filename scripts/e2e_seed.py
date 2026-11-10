"""Seed a THROW-AWAY database for the Playwright end-to-end suite (frontend/e2e).

    DATABASE_URL=postgresql://postgres@127.0.0.1:54329/cc_e2e DATABASE_URL_POOLED= python scripts/e2e_seed.py

Creates (idempotently) one faculty member and two students, the faculty assigned to the first student's class.
Credentials are fixed TEST values (never real ones). Refuses to run against a non-local database.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import db as dbmod  # noqa: E402
from api.settings import Settings  # noqa: E402
from models import academic_queries as aq  # noqa: E402
from models import queries  # noqa: E402
from services import assignment_service, auth_service  # noqa: E402

PASSWORD = "E2e#Passw0rd1"


def main():
    settings = Settings.from_env(seed_extra_branches=False)
    host = settings.database_url_direct.split("@")[-1].split("/")[0]
    if not any(h in host for h in ("127.0.0.1", "localhost")):
        print("Refusing to seed a non-local database.")
        return 2
    dbmod.init_db(settings)
    with dbmod.db_session(settings):
        admin = queries.get_user_by_email(settings.primary_admin_email)
        if admin is None:
            print("Start the API once with BOOTSTRAP_ADMIN=1 first (or create the admin).")
            return 3
        combo = aq.find_combo_by_names("CSE", "AIML", "3rd Year", "A")
        if not queries.get_user_by_email("e2e.faculty@college.edu"):
            auth_service.register_faculty({
                "full_name": "E2E Faculty", "faculty_code": "E2EF1", "department": "AIML",
                "professional_email": "e2e.faculty@college.edu", "password": PASSWORD, "subjects": ["DSA"]})
            fac = queries.get_faculty_by_user_id(queries.get_user_by_email("e2e.faculty@college.edu")["id"])
            assignment_service.admin_assign(fac["id"], combo["section_id"], admin["id"])
        for n in (1, 2):
            email = f"e2e.student{n}@college.edu"
            if not queries.get_user_by_email(email):
                auth_service.register_student({
                    "full_name": f"E2E Student {n}", "usn": f"1AB21CS90{n}", "section_id": combo["section_id"],
                    "phone": "9876543210", "personal_email": f"e2e.p{n}@example.com", "college_email": email,
                    "password": PASSWORD})
    print("seeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
