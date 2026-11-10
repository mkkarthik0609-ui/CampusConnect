"""Typed ("Other") classes at signup / faculty requests, and the extra seeded branches."""
from api.db import db_session, init_db
from models import academic_queries as aq
from tests.conftest import (
    api_post, create_faculty, db_all, db_count, db_exec, db_one, http_student_signup, login_client, make_settings,
)

CUSTOM = {"branch": "Mechanical", "department": "Robotics", "year": "3", "section": "b"}


def test_extra_branches_are_seeded_when_enabled(tmp_path):
    cfg = make_settings(tmp_path, seed_extra_branches=True)
    init_db(cfg)
    init_db(cfg)  # idempotent
    with db_session(cfg):
        names = [b["name"] for b in aq.list_branches()]
    assert {"CSE", "ECE", "ISE", "EEE", "Mechanical", "Civil"} <= set(names)
    assert len(names) == len(set(names))


def test_student_can_type_a_class_that_is_not_listed(app, client):
    resp = http_student_signup(client, None, "c1@college.edu", "1AB21CS201", None, extra={"custom_class": CUSTOM})
    assert resp.status_code == 201, resp.text
    st = db_one(app, "SELECT * FROM students WHERE usn = '1AB21CS201'")
    assert (st["branch"], st["department"], st["year"], st["section"]) == ("Mechanical", "Robotics", "3rd Year", "B")
    assert st["section_id"] is not None
    # Typed-in classes work for the student but are NOT offered in the public pickers until an admin verifies them.
    tree = client.get("/api/academic/tree").json()["branches"]
    assert "Mechanical" not in [b["name"] for b in tree]
    assert db_one(app, "SELECT is_verified FROM branches WHERE name = 'Mechanical'")["is_verified"] == 0
    assert db_one(app, "SELECT is_verified FROM sections WHERE id = ?", (st["section_id"],))["is_verified"] == 0
    from tests.conftest import make_admin, ADMIN_EMAIL
    make_admin(app)
    ac = login_client(app, ADMIN_EMAIL)
    admin_tree = ac.get("/api/admin/academics").json()["branches"]
    mech = next(b for b in admin_tree if b["name"] == "Mechanical")
    assert mech["is_verified"] is False
    for level, row_id in (("branch", mech["id"]),):
        assert api_post(ac, f"/api/admin/academics/{level}/{row_id}/verify").status_code == 200
    dept = mech["departments"][0]
    year = dept["years"][0]
    for level, row_id in (("department", dept["id"]), ("year", year["id"]), ("section", year["sections"][0]["id"])):
        assert api_post(ac, f"/api/admin/academics/{level}/{row_id}/verify").status_code == 200
    assert "Mechanical" in [b["name"] for b in client.get("/api/academic/tree").json()["branches"]]
    assert api_post(ac, "/api/admin/academics/branch/999999/verify").status_code == 404
    assert api_post(login_client(app, "c1@college.edu"), f"/api/admin/academics/branch/{mech['id']}/verify").status_code == 403


def test_typed_class_reuses_existing_rows_case_insensitively(app, client):
    a = http_student_signup(client, None, "c2@college.edu", "1AB21CS202", None, extra={"custom_class": CUSTOM})
    b = http_student_signup(client, None, "c3@college.edu", "1AB21CS203", None,
                            extra={"custom_class": {**CUSTOM, "branch": "mechanical", "department": "ROBOTICS"}})
    assert a.status_code == b.status_code == 201
    assert db_count(app, "branches", "name = 'Mechanical'") == 1
    rows = db_all(app, "SELECT DISTINCT section_id FROM students WHERE usn IN ('1AB21CS202','1AB21CS203')")
    assert len(rows) == 1


def test_typed_class_is_validated_and_creates_nothing_on_failure(app, client):
    before = db_count(app, "branches")
    for bad in ({**CUSTOM, "section": "3A"}, {**CUSTOM, "year": "tenth"}, {**CUSTOM, "branch": "<script>"}):
        resp = http_student_signup(client, None, "c4@college.edu", "1AB21CS204", None, extra={"custom_class": bad})
        assert resp.status_code == 400, resp.text
    assert db_count(app, "branches") == before and db_count(app, "users") == 0


def test_a_class_admin_switched_off_cannot_be_typed_back_in(app, client):
    http_student_signup(client, None, "c5@college.edu", "1AB21CS205", None, extra={"custom_class": CUSTOM})
    db_exec(app, "UPDATE branches SET is_active = 0 WHERE name = 'Mechanical'")
    resp = http_student_signup(client, None, "c6@college.edu", "1AB21CS206", None, extra={"custom_class": CUSTOM})
    assert resp.status_code == 400
    assert db_one(app, "SELECT is_active FROM branches WHERE name = 'Mechanical'")["is_active"] == 0


def test_public_signup_cannot_take_the_primary_admin_email(app, client):
    resp = http_student_signup(client, None, "MKKarthik0609@gmail.com", "1AB21CS299", None,
                               extra={"custom_class": CUSTOM})
    assert resp.status_code == 409, resp.text
    assert db_count(app, "users") == 0


def test_faculty_can_request_a_typed_class(app):
    fac = create_faculty(app, "FAC900")
    c = login_client(app, fac["email"])
    resp = api_post(c, "/api/faculty/classes/request", json={"custom_class": CUSTOM})
    assert resp.status_code == 201, resp.text
    assert db_count(app, "faculty_assignment_requests") == 1
    assert api_post(c, "/api/faculty/classes/request", json={}).status_code == 400
