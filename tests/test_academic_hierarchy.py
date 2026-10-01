"""Admin-controlled academic hierarchy: seed, validation, the /api/admin academics + class-directory + student
endpoints, student registration, 'students cannot change class', admin remove-registration and legacy-data
migration."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from models import academic_queries as aq
from models import queries
from services import academic_service as svc
from services.academic_service import AcademicError
from tests.conftest import (
    PASSWORD, make_settings, create_admin, create_faculty, create_student, section_id_for, assign,
    login_client, api_post, api_delete, db_one, db_all, db_count, db_exec, http_student_signup, solve_captcha,
)

DEPARTMENTS = ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"]
YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]


def public_tree(client):
    resp = client.get("/api/academic/tree")
    assert resp.status_code == 200
    return resp.json()["branches"]


def err(resp, status, code=None):
    """Assert the conventions error shape and return the error object."""
    assert resp.status_code == status, resp.text
    body = resp.json()["error"]
    if code:
        assert body["code"] == code, body
    assert body["message"]
    return body


# ---------------------------------------------------------------------------
# seed content
# ---------------------------------------------------------------------------

def test_seed_creates_exactly_the_specified_structure(app):
    with app.app_context():
        branches = aq.list_branches()
        assert [b["name"] for b in branches] == ["CSE"]
        depts = aq.list_departments(branches[0]["id"])
        assert sorted(d["name"] for d in depts) == sorted(DEPARTMENTS)
        for d in depts:
            years = aq.list_years(d["id"])
            assert [y["name"] for y in years] == YEARS
            assert [y["sort_order"] for y in years] == [1, 2, 3, 4]
            for y in years:
                assert [s["name"] for s in aq.list_sections(y["id"])] == ["A", "B", "C"]
        assert len(aq.list_combos()) == 6 * 4 * 3
        assert all(c["chain_active"] for c in aq.list_combos())


def test_seed_is_idempotent_and_skipped_when_any_branch_exists(app):
    with app.app_context():
        before = len(aq.list_combos())
        svc.seed_default_structure()
        svc.seed_default_structure()
        assert len(aq.list_combos()) == before
        assert len(aq.list_branches()) == 1


def test_seed_not_rerun_after_admin_deactivates_everything(tmp_path):
    """Once a branch exists the admin owns the structure; a restart must not resurrect defaults."""
    cfg = make_settings(tmp_path, database_path=str(tmp_path / "x.db"), upload_root=str(tmp_path / "up"))
    app1 = create_app(cfg)
    with app1.app_context():
        svc.set_active("branch", aq.get_branch_by_name("CSE")["id"], False)
    app2 = create_app(cfg)  # simulated restart
    with app2.app_context():
        assert [b["name"] for b in aq.list_branches()] == ["CSE"]
        assert aq.get_branch_by_name("CSE")["is_active"] == 0


def test_public_tree_endpoint_matches_seed_and_is_anonymous(client):
    resp = client.get("/api/academic/tree")  # no login
    assert resp.status_code == 200
    tree = resp.json()["branches"]
    assert [b["name"] for b in tree] == ["CSE"]
    depts = tree[0]["departments"]
    assert sorted(d["name"] for d in depts) == sorted(DEPARTMENTS)
    aiml = next(d for d in depts if d["name"] == "AIML")
    assert [y["name"] for y in aiml["years"]] == YEARS
    assert [s["name"] for s in aiml["years"][2]["sections"]] == ["A", "B", "C"]
    assert set(tree[0]) == {"id", "name", "departments"}  # public: ids + names only


# ---------------------------------------------------------------------------
# normalisation / validation (service level)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,label,number", [
    ("1", "1st Year", 1), ("2", "2nd Year", 2), ("3", "3rd Year", 3), ("4", "4th Year", 4),
    ("3rd", "3rd Year", 3), ("3rd year", "3rd Year", 3), ("3RD YEAR", "3rd Year", 3),
    ("  2nd Year ", "2nd Year", 2), ("1st", "1st Year", 1), ("4th Year", "4th Year", 4),
    ("9", "9th Year", 9),
])
def test_normalize_year_accepts(raw, label, number):
    assert svc.normalize_year(raw) == (label, number)


@pytest.mark.parametrize("raw", ["", "  ", None, "0", "10", "abc", "3A", "third", "year 3", "-1", "3.5", "3rd yr"])
def test_normalize_year_rejects(raw):
    with pytest.raises(AcademicError):
        svc.normalize_year(raw)


@pytest.mark.parametrize("raw,expected", [("A", "A"), ("b", "B"), (" c ", "C"), ("z", "Z")])
def test_normalize_section_accepts_single_letters(raw, expected):
    assert svc.normalize_section(raw) == expected


@pytest.mark.parametrize("raw", ["3A", "AB", "", " ", None, "1", "A1", "A-", "é", "A B"])
def test_normalize_section_rejects_everything_but_a_single_letter(raw):
    with pytest.raises(AcademicError):
        svc.normalize_section(raw)


def test_year_label_ordinals():
    assert [svc.year_label(n) for n in (1, 2, 3, 4, 5)] == ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"]


@pytest.mark.parametrize("bad", ["", "  ", None, "-x", "a" * 41, "Bad;Name", "<script>", "x\ny;"])
def test_add_branch_rejects_bad_names(app, bad):
    with app.app_context():
        with pytest.raises(AcademicError):
            svc.add_branch(bad)
        assert len(aq.list_branches()) == 1


def test_add_branch_duplicate_rejected_case_insensitively_with_whitespace_collapsed(app):
    with app.app_context():
        svc.add_branch("Mechanical  Engineering")
        for dup in ("Mechanical Engineering", "mechanical engineering", "  MECHANICAL   ENGINEERING "):
            with pytest.raises(AcademicError, match="already exists"):
                svc.add_branch(dup)
        with pytest.raises(AcademicError):
            svc.add_branch("cse")
        assert aq.get_branch_by_name("Mechanical Engineering") is not None


def test_add_department_rules(app):
    with app.app_context():
        cse = aq.get_branch_by_name("CSE")
        other = svc.add_branch("ECE")
        with pytest.raises(AcademicError, match="already exists"):
            svc.add_department(cse["id"], "aiml")
        # the same department name is fine in a different branch
        new_id = svc.add_department(other, "AIML")
        assert aq.get_department(new_id)["branch_id"] == other
        with pytest.raises(AcademicError, match="Branch not found"):
            svc.add_department(99999, "Robotics")
        with pytest.raises(AcademicError, match="Branch not found"):
            svc.add_department(None, "Robotics")
        with pytest.raises(AcademicError):
            svc.add_department(cse["id"], "")
        assert svc.add_department(cse["id"], "Data Science")


def test_add_year_normalises_and_rejects_duplicates(app):
    with app.app_context():
        cse = aq.get_branch_by_name("CSE")
        dept = svc.add_department(cse["id"], "Robotics")
        assert aq.get_year(svc.add_year(dept, "3"))["name"] == "3rd Year"
        for dup in ("3", "3rd", "3rd Year", "3RD YEAR"):
            with pytest.raises(AcademicError, match="already exists"):
                svc.add_year(dept, dup)
        year = aq.get_year(svc.add_year(dept, "2nd year"))
        assert (year["name"], year["sort_order"]) == ("2nd Year", 2)
        assert [y["name"] for y in aq.list_years(dept)] == ["2nd Year", "3rd Year"]  # ordered by sort_order
        with pytest.raises(AcademicError):
            svc.add_year(dept, "Final")
        with pytest.raises(AcademicError, match="Department not found"):
            svc.add_year(99999, "1")


def test_add_sections_parsing_and_duplicates(app):
    with app.app_context():
        dept = svc.add_department(aq.get_branch_by_name("CSE")["id"], "Robotics")
        year = svc.add_year(dept, "1")
        assert svc.add_sections(year, "a") == ["A"]
        assert svc.add_sections(year, "B, C;D e") == ["B", "C", "D", "E"]
        assert svc.add_sections(year, "F F f") == ["F"]  # de-duplicated within the input
        assert svc.add_sections(year, "A, G") == ["G"]  # existing ones skipped silently if something is new
        with pytest.raises(AcademicError, match="already exist"):
            svc.add_sections(year, "A B")
        assert [s["name"] for s in aq.list_sections(year)] == list("ABCDEFG")


@pytest.mark.parametrize("bad", ["3A", "AB", "1", "A,3B", "", "   ", None, ",,"])
def test_add_sections_rejects_invalid_labels_atomically(app, bad):
    with app.app_context():
        dept = svc.add_department(aq.get_branch_by_name("CSE")["id"], "Robotics")
        year = svc.add_year(dept, "1")
        with pytest.raises(AcademicError):
            svc.add_sections(year, bad)
        assert aq.list_sections(year) == []


def test_add_sections_partial_invalid_creates_nothing(app):
    with app.app_context():
        dept = svc.add_department(aq.get_branch_by_name("CSE")["id"], "Robotics")
        year = svc.add_year(dept, "1")
        with pytest.raises(AcademicError):
            svc.add_sections(year, "A, B, 3C")
        assert aq.list_sections(year) == []  # validation happens before any insert


def test_add_sections_unknown_year(app):
    with app.app_context():
        with pytest.raises(AcademicError, match="Year not found"):
            svc.add_sections(99999, "A")


# ---------------------------------------------------------------------------
# activation / deletion (service level)
# ---------------------------------------------------------------------------

def _tree_names(app):
    tree = svc.get_tree()
    return {
        (b["name"], d["name"], y["name"], s["name"])
        for b in tree for d in b["departments"] for y in d["years"] for s in y["sections"]
    }


def test_deactivate_section_hides_it_from_tree_and_public_json(app, client):
    sid = section_id_for(app, "AIML", "3rd Year", "B")
    with app.app_context():
        svc.set_active("section", sid, False)
        assert ("CSE", "AIML", "3rd Year", "B") not in _tree_names(app)
        assert ("CSE", "AIML", "3rd Year", "A") in _tree_names(app)
        with pytest.raises(AcademicError):
            svc.resolve_section(sid)
    data = public_tree(client)
    aiml = next(d for d in data[0]["departments"] if d["name"] == "AIML")
    assert [s["name"] for s in aiml["years"][2]["sections"]] == ["A", "C"]
    with app.app_context():
        svc.set_active("section", sid, True)
        assert svc.resolve_section(sid)["section_name"] == "B"


@pytest.mark.parametrize("level,pick", [
    ("year", lambda a: aq.find_combo_by_names("CSE", "AIML", "3rd Year", "A")["year_id"]),
    ("department", lambda a: aq.find_combo_by_names("CSE", "AIML", "3rd Year", "A")["department_id"]),
    ("branch", lambda a: aq.find_combo_by_names("CSE", "AIML", "3rd Year", "A")["branch_id"]),
])
def test_deactivating_a_parent_hides_and_invalidates_all_children(app, level, pick):
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    with app.app_context():
        svc.set_active(level, pick(app), False)
        assert svc.get_tree() == [] or ("CSE", "AIML", "3rd Year", "A") not in _tree_names(app)
        # the child section row is itself still "active", but the chain is not
        assert aq.get_section(sid)["is_active"] == 1
        assert aq.get_combo(sid)["chain_active"] == 0
        with pytest.raises(AcademicError):
            svc.resolve_section(sid)
        assert sid not in [c["section_id"] for c in aq.list_combos(active_only=True)]
        assert sid in [c["section_id"] for c in aq.list_combos(active_only=False)]
        # the admin tree (active_only=False) still shows everything
        full = svc.get_tree(active_only=False)
        assert any(d["name"] == "AIML" for b in full for d in b["departments"])
        svc.set_active(level, pick(app), True)
        assert svc.resolve_section(sid)


def test_inactive_department_leaves_faculty_signup_and_department_list(app, client):
    with app.app_context():
        d = next(x for x in aq.list_departments() if x["name"] == "IoT")
        svc.set_active("department", d["id"], False)
        assert "IoT" not in aq.list_active_department_names()
    assert "IoT" not in [x for x in client.get("/api/auth/faculty-departments").json()["items"]]
    with app.app_context():
        svc.set_active("department", d["id"], True)
        assert "IoT" in aq.list_active_department_names()


def test_set_active_and_delete_reject_unknown_levels_and_ids(app):
    with app.app_context():
        for fn in (lambda: svc.set_active("galaxy", 1, True), lambda: svc.set_active("section", 99999, True),
                   lambda: svc.delete_unused("galaxy", 1), lambda: svc.delete_unused("section", 99999)):
            with pytest.raises(AcademicError, match="not found"):
                fn()


def test_delete_refused_when_students_exist_at_any_level(app):
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    create_student(app, "1AB21CS010", sid)
    with app.app_context():
        combo = aq.get_combo(sid)
        for level, key in (("section", "section_id"), ("year", "year_id"), ("department", "department_id"),
                           ("branch", "branch_id")):
            with pytest.raises(AcademicError, match="students or faculty assignments"):
                svc.delete_unused(level, combo[key])
        assert aq.get_section(sid) is not None
        # a sibling section with nobody in it can be deleted
        sib = section_id_for(app, "AIML", "3rd Year", "C")
        svc.delete_unused("section", sib)
        assert aq.get_section(sib) is None


def test_delete_refused_when_assignments_exist_even_inactive(app):
    admin_id = create_admin(app)
    fac = create_faculty(app, "FAC050")
    sid = section_id_for(app, "AIDE", "2nd Year", "A")
    assign(app, fac, sid, admin_id)
    with app.app_context():
        with pytest.raises(AcademicError):
            svc.delete_unused("section", sid)
        with pytest.raises(AcademicError):
            svc.delete_unused("department", aq.get_combo(sid)["department_id"])
        aq.deactivate_assignment(aq.get_assignment_for(fac["faculty_id"], sid)["id"])
        # an inactive assignment row still blocks deletion (history, FK cascade would destroy it)
        with pytest.raises(AcademicError):
            svc.delete_unused("section", sid)


def test_delete_empty_branch_cascades_to_children(app):
    with app.app_context():
        b = svc.add_branch("Temp")
        d = svc.add_department(b, "TD")
        y = svc.add_year(d, "1")
        svc.add_sections(y, "A,B")
        assert db_count(app, "sections") >= 2
        svc.delete_unused("branch", b)
        assert aq.get_branch(b) is None and aq.get_department(d) is None
        assert aq.get_year(y) is None and aq.list_sections(y) == []


def test_resolve_section_validation(app):
    sid = section_id_for(app)
    with app.app_context():
        assert svc.resolve_section(sid)["section_name"] == "A"
        assert svc.resolve_section(str(sid))["section_id"] == sid
        for bad in (None, "", "abc", "1.5", 99999, -1, [], "1 OR 1=1"):
            with pytest.raises(AcademicError):
                svc.resolve_section(bad)


def test_combo_label_and_lookup_helpers(app):
    with app.app_context():
        combo = aq.find_combo_by_names("cse", "aiml", "3rd year", "a")  # NOCASE collation
        assert combo is not None
        assert svc.combo_label(combo) == "CSE → AIML → 3rd Year → A"
        assert aq.find_combo_by_names("CSE", "AIML", "3rd Year", "Z") is None
        rows = aq.list_combos_with_counts()
        assert len(rows) == 72 and all(r["student_count"] == 0 and r["faculty_count"] == 0 for r in rows)


def test_list_combos_with_counts_counts_live_students_and_active_faculty(app, admin_client):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    create_student(app, "1AB21CS011", sid)
    create_student(app, "1AB21CS012", sid)
    gone = create_student(app, "1AB21CS013", sid)
    f1, f2 = create_faculty(app, "FAC060"), create_faculty(app, "FAC061")
    assign(app, f1, sid, admin_id)
    assign(app, f2, sid, admin_id)
    assert api_post(admin_client, f"/api/admin/students/{gone['student_id']}/remove-registration").status_code == 200
    with app.app_context():
        aq.deactivate_assignment(aq.get_assignment_for(f2["faculty_id"], sid)["id"])
        row = next(r for r in aq.list_combos_with_counts() if r["section_id"] == sid)
        assert (row["student_count"], row["faculty_count"]) == (2, 1)  # removed student and inactive faculty excluded


def test_tree_with_usage_rolls_counts_up_and_flags_deletable_nodes(app):
    admin_id = create_admin(app)
    sid = section_id_for(app, "AIDE", "2nd Year", "A")
    create_student(app, "1AB21CS014", sid)
    assign(app, create_faculty(app, "FAC062"), sid, admin_id)
    with app.app_context():
        tree = svc.get_tree(active_only=False, with_usage=True)
    branch = tree[0]
    aide = next(d for d in branch["departments"] if d["name"] == "AIDE")
    iot = next(d for d in branch["departments"] if d["name"] == "IoT")
    year2 = next(y for y in aide["years"] if y["name"] == "2nd Year")
    sec = next(s for s in year2["sections"] if s["name"] == "A")
    assert (sec["student_count"], sec["assignment_count"], sec["can_delete"]) == (1, 1, False)
    assert (year2["student_count"], year2["assignment_count"], year2["can_delete"]) == (1, 1, False)
    assert (aide["student_count"], branch["student_count"], branch["can_delete"]) == (1, 1, False)
    assert iot["can_delete"] and iot["student_count"] == 0
    assert next(s for s in year2["sections"] if s["name"] == "B")["can_delete"] is True


# ---------------------------------------------------------------------------
# admin API: authorisation (anonymous 401, student/faculty 403, no side effects)
# ---------------------------------------------------------------------------

ADMIN_ACADEMIC_GETS = ["/api/admin/academics", "/api/admin/assignments", "/api/admin/assignment-requests",
                       "/api/admin/classes", "/api/admin/classes/1"]
ADMIN_ACADEMIC_WRITES = [
    ("POST", "/api/admin/academics/branches", {"name": "Hack"}),
    ("POST", "/api/admin/academics/departments", {"branch_id": 1, "name": "Hack"}),
    ("POST", "/api/admin/academics/years", {"department_id": 1, "name": "5"}),
    ("POST", "/api/admin/academics/sections", {"year_id": 1, "names": "Z"}),
    ("POST", "/api/admin/academics/section/1/active", {"active": False}),
    ("DELETE", "/api/admin/academics/section/1", None),
    ("POST", "/api/admin/assignments", {"faculty_id": 1, "section_id": 1}),
    ("DELETE", "/api/admin/assignments/1", None),
    ("POST", "/api/admin/assignment-requests/1/decide", {"decision": "approve"}),
    ("POST", "/api/admin/students/1/remove-registration", None),
]


@pytest.mark.parametrize("path", ADMIN_ACADEMIC_GETS)
def test_admin_get_endpoints_anonymous_401_non_admin_403(app, path):
    create_admin(app)
    fac = create_faculty(app, "FAC070")
    stu = create_student(app, "1AB21CS020")
    err(TestClient(app).get(path), 401, "unauthenticated")
    for user in (fac, stu):
        err(login_client(app, user["email"]).get(path), 403, "forbidden")


@pytest.mark.parametrize("method,path,payload", ADMIN_ACADEMIC_WRITES)
def test_admin_write_endpoints_reject_non_admins_and_have_no_side_effects(app, method, path, payload):
    create_admin(app)
    fac = create_faculty(app, "FAC071")
    stu = create_student(app, "1AB21CS021")
    snapshot = lambda: (db_count(app, "branches"), db_count(app, "departments"), db_count(app, "academic_years"),
                        db_count(app, "sections", "is_active = 1"), db_count(app, "sections"),
                        db_count(app, "faculty_assignments"), db_count(app, "users", "is_active = 1"))
    before = snapshot()
    anonymous = TestClient(app)
    err(anonymous.request(method, path, json=payload), 401, "unauthenticated")
    # even a malformed body must not leak validation details to a non-admin
    err(anonymous.request(method, path, json={"junk": 1}) if payload is not None else anonymous.request(method, path),
        401, "unauthenticated")
    for user in (fac, stu):
        c = login_client(app, user["email"])
        err(c.request(method, path, json=payload), 403, "forbidden")
    assert snapshot() == before


def test_admin_endpoints_work_for_admin(app, admin_client):
    for path in ADMIN_ACADEMIC_GETS[:-1]:
        assert admin_client.get(path).status_code == 200, path
    sid = section_id_for(app)
    assert admin_client.get(f"/api/admin/classes/{sid}").status_code == 200
    err(admin_client.get("/api/admin/classes/99999"), 404, "not_found")


# ---------------------------------------------------------------------------
# admin API: academic structure
# ---------------------------------------------------------------------------

def test_admin_adds_full_chain_via_api(app, admin_client):
    post = lambda path, **d: api_post(admin_client, "/api/admin/academics/" + path, json=d)
    r = post("branches", name="ECE")
    assert r.status_code == 201 and r.json()["ok"] and r.json()["message"] == "Branch added."
    bid = r.json()["id"]
    assert db_one(app, "SELECT name FROM branches WHERE id = ?", (bid,))["name"] == "ECE"

    r = post("departments", branch_id=bid, name="VLSI")
    assert r.status_code == 201 and r.json()["name"] == "VLSI"
    did = r.json()["id"]

    r = post("years", department_id=did, name="2")
    assert r.status_code == 201 and r.json()["name"] == "2nd Year"
    yid = r.json()["id"]
    assert db_one(app, "SELECT sort_order FROM academic_years WHERE id = ?", (yid,))["sort_order"] == 2

    r = post("sections", year_id=yid, names="A, b")
    assert r.status_code == 201 and r.json()["created"] == ["A", "B"]
    assert [x["name"] for x in db_all(app, "SELECT name FROM sections WHERE academic_year_id = ?", (yid,))] == ["A", "B"]

    # the new class is immediately selectable on the public tree (no login) and visible in the admin tree
    assert "ECE" in [b["name"] for b in public_tree(TestClient(app))]
    admin_tree = admin_client.get("/api/admin/academics").json()["branches"]
    ece = next(b for b in admin_tree if b["name"] == "ECE")
    assert ece["can_delete"] is True and ece["departments"][0]["years"][0]["sections"][1]["name"] == "B"


@pytest.mark.parametrize("path,payload,status,code,field,needle", [
    ("branches", {"name": "CSE"}, 409, "conflict", "name", "already exists"),
    ("branches", {"name": "cse "}, 409, "conflict", "name", "already exists"),
    ("branches", {"name": ""}, 400, "validation_error", "name", "name must be"),
    ("branches", {"name": "Bad;Name"}, 400, "validation_error", "name", "name must be"),
    ("branches", {"name": 5}, 400, "validation_error", "name", ""),
    ("branches", {}, 400, "validation_error", "name", "required"),
    ("branches", {"name": "X", "is_active": True}, 400, "validation_error", "is_active", ""),
    ("departments", {"branch_id": 1, "name": "AIML"}, 409, "conflict", "name", "already exists"),
    ("departments", {"branch_id": 99999, "name": "X"}, 404, "not_found", None, "Branch not found"),
    ("departments", {"branch_id": "abc", "name": "X"}, 400, "validation_error", "branch_id", ""),
    ("departments", {"branch_id": 1.5, "name": "X"}, 400, "validation_error", "branch_id", ""),
    ("departments", {"branch_id": True, "name": "X"}, 400, "validation_error", "branch_id", ""),
    ("years", {"department_id": 1, "name": "3"}, 409, "conflict", "name", "already exists"),
    ("years", {"department_id": 1, "name": "Final"}, 400, "validation_error", "name", "Year must look like"),
    ("years", {"department_id": 99999, "name": "1"}, 404, "not_found", None, "Department not found"),
    ("sections", {"year_id": 1, "names": "3A"}, 400, "validation_error", "names", "single letter"),
    ("sections", {"year_id": 1, "names": "A, B, 3C"}, 400, "validation_error", "names", "single letter"),
    ("sections", {"year_id": 1, "names": "A B C"}, 409, "conflict", "names", "already exist"),
    ("sections", {"year_id": 1, "names": "  "}, 400, "validation_error", "names", "at least one"),
    ("sections", {"year_id": 99999, "names": "Z"}, 404, "not_found", None, "Year not found"),
    ("sections", {"year_id": None, "names": "Z"}, 400, "validation_error", "year_id", ""),
    ("galaxy/1/active", {"active": False}, 404, "not_found", None, "not found"),
    ("section/99999/active", {"active": False}, 404, "not_found", None, "not found"),
    ("section/1/active", {"active": "no"}, 400, "validation_error", "active", ""),
    ("section/1/active", {"active": 0}, 400, "validation_error", "active", ""),
    ("section/1/active", {}, 400, "validation_error", "active", ""),
])
def test_admin_structure_errors_use_the_error_shape_and_change_nothing(app, admin_client, path, payload, status,
                                                                       code, field, needle):
    counts = lambda: (db_count(app, "sections"), db_count(app, "branches"), db_count(app, "departments"),
                      db_count(app, "academic_years"), db_count(app, "sections", "is_active = 1"))
    before = counts()
    resp = api_post(admin_client, "/api/admin/academics/" + path, json=payload)
    body = err(resp, status, code)
    assert needle.lower() in body["message"].lower() or needle.lower() in json.dumps(body).lower(), body
    if field:
        assert field in body["fields"], body
    assert counts() == before


def test_admin_structure_rejects_non_json_bodies(app, admin_client):
    for content in ("not json", "[1,2]", ""):
        resp = admin_client.post("/api/admin/academics/branches", content=content,
                                 headers={"Content-Type": "application/json", "X-CSRFToken": "x"})
        assert resp.status_code == 400 and "code" in resp.json()["error"]
    assert db_count(app, "branches") == 1


def test_admin_deactivate_reactivate_and_delete_via_api(app, admin_client):
    sid = section_id_for(app, "IoT", "4th Year", "C")
    r = api_post(admin_client, f"/api/admin/academics/section/{sid}/active", json={"active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False and "deactivated" in r.json()["message"]
    assert db_one(app, "SELECT is_active FROM sections WHERE id = ?", (sid,))["is_active"] == 0
    iot = next(d for d in public_tree(TestClient(app))[0]["departments"] if d["name"] == "IoT")
    assert [s["name"] for s in iot["years"][3]["sections"]] == ["A", "B"]
    # the admin tree still lists it, flagged inactive
    admin_iot = next(d for d in admin_client.get("/api/admin/academics").json()["branches"][0]["departments"]
                     if d["name"] == "IoT")
    node = next(s for s in admin_iot["years"][3]["sections"] if s["id"] == sid)
    assert node["is_active"] is False and node["can_delete"] is True

    r = api_post(admin_client, f"/api/admin/academics/section/{sid}/active", json={"active": True})
    assert r.status_code == 200 and "reactivated" in r.json()["message"]
    assert db_one(app, "SELECT is_active FROM sections WHERE id = ?", (sid,))["is_active"] == 1

    r = api_delete(admin_client, f"/api/admin/academics/section/{sid}")
    assert r.status_code == 200 and "deleted" in r.json()["message"].lower()
    assert db_one(app, "SELECT id FROM sections WHERE id = ?", (sid,)) is None
    err(api_delete(admin_client, f"/api/admin/academics/section/{sid}"), 404, "not_found")  # already gone

    # deleting anything that is in use is refused at every level, and nothing is lost
    used = section_id_for(app, "IoT", "4th Year", "A")
    create_student(app, "1AB21CS030", used)
    combo = db_one(app, "SELECT y.id AS y, d.id AS d, b.id AS b FROM sections s JOIN academic_years y ON "
                        "y.id = s.academic_year_id JOIN departments d ON d.id = y.department_id JOIN branches b "
                        "ON b.id = d.branch_id WHERE s.id = ?", (used,))
    for level, row_id in (("section", used), ("year", combo["y"]), ("department", combo["d"]),
                          ("branch", combo["b"])):
        body = err(api_delete(admin_client, f"/api/admin/academics/{level}/{row_id}"), 409, "in_use")
        assert "deactivate it instead" in body["message"]
    assert db_one(app, "SELECT id FROM sections WHERE id = ?", (used,)) is not None
    assert db_count(app, "branches") == 1


def test_deleting_a_section_with_only_an_assignment_is_refused_via_api(app, admin_client):
    admin_id = create_admin(app)
    sid = section_id_for(app, "GenAI", "2nd Year", "B")
    assign(app, create_faculty(app, "FAC072"), sid, admin_id)
    body = err(api_delete(admin_client, f"/api/admin/academics/section/{sid}"), 409, "in_use")
    assert "faculty assignments" in body["message"]


def test_admin_tree_endpoint_returns_inactive_rows_and_usage(app, admin_client):
    sid = section_id_for(app, "AIML", "3rd Year", "B")
    create_student(app, "1AB21CS031", sid)
    api_post(admin_client, f"/api/admin/academics/section/{sid}/active", json={"active": False})
    branches = admin_client.get("/api/admin/academics").json()["branches"]
    aiml = next(d for d in branches[0]["departments"] if d["name"] == "AIML")
    year3 = next(y for y in aiml["years"] if y["name"] == "3rd Year")
    b = next(s for s in year3["sections"] if s["name"] == "B")
    assert b == {"id": sid, "name": "B", "is_active": False, "student_count": 1, "assignment_count": 0,
                 "can_delete": False}
    assert year3["student_count"] == 1 and year3["is_active"] is True
    assert [s["name"] for s in year3["sections"]] == ["A", "B", "C"]  # public tree would hide B


# ---------------------------------------------------------------------------
# admin API: class directory
# ---------------------------------------------------------------------------

def test_class_directory_list_and_detail(app, admin_client):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    s1, s2 = create_student(app, "1AB21CS040", sid), create_student(app, "1AB21CS041", sid)
    fac = create_faculty(app, "FAC073", name="Dr Directory")
    assign(app, fac, sid, admin_id)

    items = admin_client.get("/api/admin/classes").json()
    assert items["total"] == 72 and len(items["items"]) == 72
    row = next(c for c in items["items"] if c["section_id"] == sid)
    assert row == {
        "section_id": sid, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
        "label": "CSE → AIML → 3rd Year → A", "is_active": True, "student_count": 2, "faculty_count": 1,
        "faculty": [{"id": fac["faculty_id"], "assignment_id": row["faculty"][0]["assignment_id"],
                     "faculty_code": "FAC073", "full_name": "Dr Directory", "profile_picture_url": None}],
    }
    empty = next(c for c in items["items"] if c["section_id"] != sid)
    assert empty["student_count"] == 0 and empty["faculty"] == []

    detail = admin_client.get(f"/api/admin/classes/{sid}").json()
    assert detail["class"]["student_count"] == 2 and detail["class"]["faculty_count"] == 1
    assert [f["faculty_code"] for f in detail["faculty"]] == ["FAC073"]
    assert [s["usn"] for s in detail["students"]] == ["1AB21CS040", "1AB21CS041"]
    assert {"id", "full_name", "usn", "email", "phone", "profile_picture_url", "class", "is_removed", "is_active",
            "can_remove_registration"} <= set(detail["students"][0])
    assert detail["students"][0]["class"]["section_id"] == sid


def test_class_detail_marks_removed_students_and_hides_inactive_assignments(app, admin_client):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    gone, kept = create_student(app, "1AB21CS042", sid), create_student(app, "1AB21CS043", sid)
    fac = create_faculty(app, "FAC074")
    assign(app, fac, sid, admin_id)
    api_post(admin_client, f"/api/admin/students/{gone['student_id']}/remove-registration")
    with app.app_context():
        aq.deactivate_assignment(aq.get_assignment_for(fac["faculty_id"], sid)["id"])
    detail = admin_client.get(f"/api/admin/classes/{sid}").json()
    assert detail["faculty"] == [] and detail["class"]["faculty_count"] == 0
    by_usn = {s["usn"]: s for s in detail["students"]}
    assert set(by_usn) == {"1AB21CS042", "1AB21CS043"}  # tombstone stripped from the shown USN
    assert by_usn["1AB21CS042"]["is_removed"] is True and by_usn["1AB21CS042"]["is_active"] is False
    assert by_usn["1AB21CS042"]["can_remove_registration"] is False
    assert by_usn["1AB21CS043"]["is_removed"] is False
    assert detail["class"]["student_count"] == 1  # removed registrations do not count
    assert kept["email"] == by_usn["1AB21CS043"]["email"]


# ---------------------------------------------------------------------------
# student registration (HTTP signup + service)
# ---------------------------------------------------------------------------

def test_registration_with_valid_section_id_stores_text_and_link(app, client):
    sid = section_id_for(app, "AIDE", "2nd Year", "B")
    resp = http_student_signup(client, None, "reg1@college.edu", "1AB21CS100", sid)
    assert resp.status_code == 201, resp.text
    st = db_one(app, "SELECT * FROM students WHERE usn = '1AB21CS100'")
    assert st["section_id"] == sid
    assert (st["branch"], st["department"], st["year"], st["section"]) == ("CSE", "AIDE", "2nd Year", "B")
    assert st["college_email"] == "reg1@college.edu"


@pytest.mark.parametrize("bad", ["", "abc", 999999, -5, 0, "1; DROP TABLE students", "1 OR 1=1", 1.5, None,
                                 [1], {"a": 1}])
def test_registration_rejects_invalid_or_forged_section_ids(app, client, bad):
    resp = http_student_signup(client, None, "reg2@college.edu", "1AB21CS101", bad)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "validation_error"
    assert db_count(app, "students") == 0
    assert db_count(app, "users") == 0


def test_registration_rejects_missing_section_id_field(app, client):
    email = "reg3@college.edu"
    resp = api_post(client, "/api/auth/signup/student", json={
        "college_email": email, "full_name": "N", "usn": "1AB21CS102", "phone": "9999999999",
        "personal_email": "n@example.com", "password": PASSWORD, "confirm_password": PASSWORD,
        **solve_captcha(client)})
    body = err(resp, 400, "validation_error")
    assert "section_id" in body["fields"]
    assert db_count(app, "students") == 0


@pytest.mark.parametrize("level", ["section", "year", "department", "branch"])
def test_registration_rejects_inactive_chain_at_any_level(app, client, level):
    sid = section_id_for(app, "GenAI", "1st Year", "A")
    with app.app_context():
        combo = aq.get_combo(sid)
        svc.set_active(level, combo[f"{level}_id"], False)
    resp = http_student_signup(client, None, "reg4@college.edu", "1AB21CS103", sid)
    assert resp.status_code == 400
    assert db_count(app, "students") == 0


def test_free_text_class_fields_are_rejected_not_trusted(app, client):
    """The register body is strict: class names typed by the client are an error, only section_id counts."""
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    resp = http_student_signup(client, None, "reg5@college.edu", "1AB21CS104", sid, extra={
        "branch": "ECE", "department": "Hacking", "year": "9th Year", "section": "Z",
    })
    body = err(resp, 400, "validation_error")
    assert {"branch", "department", "year", "section"} <= set(body["fields"])
    assert db_count(app, "students") == 0


def test_free_text_only_registration_is_rejected_by_the_service(app):
    with app.app_context():
        from services import auth_service
        with pytest.raises(auth_service.ValidationError):
            auth_service.register_student({
                "full_name": "X", "usn": "1AB21CS105", "branch": "CSE", "department": "AIML", "year": "3rd Year",
                "section": "A", "phone": "9999999999", "personal_email": "x@example.com",
                "college_email": "x105@college.edu", "password": PASSWORD})
    assert db_count(app, "students") == 0


def test_registered_student_is_linked_to_faculty_assigned_to_their_section(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    stu = create_student(app, "1AB21CS106", sid)
    fac = create_faculty(app, "FAC080", name="Dr Visible")
    assign(app, fac, sid, admin_id)
    with app.app_context():
        assert [f["faculty_code"] for f in aq.list_assigned_faculty_for_student(stu["student_id"])] == ["FAC080"]


# ---------------------------------------------------------------------------
# students cannot change their class
# ---------------------------------------------------------------------------

def _student_with_faculty(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    stu = create_student(app, "1AB21CS200", sid)
    fac = create_faculty(app, "FAC090")
    assign(app, fac, sid, admin_id)
    return stu, fac, sid


def test_profile_change_service_ignores_class_fields_entirely(app):
    from services import permission_service
    stu, fac, sid = _student_with_faculty(app)
    with app.app_context():
        with pytest.raises(permission_service.PermissionError_, match="No valid profile fields"):
            permission_service.student_request_profile_change(stu["user_id"], {
                "branch": "ECE", "department": "AIDE", "year": "4th Year", "section": "C", "section_id": "5"},
                "moving")
    assert db_count(app, "permission_requests") == 0
    st = db_one(app, "SELECT * FROM students WHERE id = ?", (stu["student_id"],))
    assert (st["department"], st["year"], st["section"], st["section_id"]) == ("AIML", "3rd Year", "A", sid)


def test_profile_change_with_class_and_phone_only_keeps_phone_in_request(app):
    from services import permission_service
    stu, fac, sid = _student_with_faculty(app)
    with app.app_context():
        permission_service.student_request_profile_change(stu["user_id"], {
            "phone": "8888888888", "section": "C", "year": "1st Year", "branch": "ECE", "department": "IoT",
            "section_id": "7", "usn": "HACKED", "college_email": "h@x.com", "class_faculty_id": "1"})
    req = db_one(app, "SELECT * FROM permission_requests")
    assert json.loads(req["requested_changes"]) == {"phone": "8888888888"}


def test_student_editable_fields_never_include_class_or_identity():
    from services import permission_service
    assert permission_service.STUDENT_EDITABLE_FIELDS == {"phone", "personal_email"}
    for f in ("branch", "department", "year", "section", "section_id", "usn"):
        assert f not in permission_service.STUDENT_EDITABLE_FIELDS


def test_no_student_route_changes_section(app):
    """No unsafe route under /api/student, /api/account or /api/auth can move a student to another section."""
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if not (path.startswith(("/api/student", "/api/account")) and methods - {"GET", "HEAD", "OPTIONS"}):
            continue
        assert "section" not in path and "class" not in path, path
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    for path in ("/api/student/section", "/api/student/class", "/api/student/profile/section",
                 "/api/student/profile/class", "/api/student/change-section", "/api/academic/select"):
        for send in (c.post, c.put, c.patch):
            assert send(path, json={"section_id": 3}).status_code in (404, 405), path
    assert db_one(app, "SELECT section_id FROM students WHERE id = ?", (stu["student_id"],))["section_id"] == sid


def test_student_cannot_hit_admin_remove_registration_on_self(app):
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    err(api_post(c, f"/api/admin/students/{stu['student_id']}/remove-registration"), 403, "forbidden")
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (stu["user_id"],))["is_active"] == 1


# ---------------------------------------------------------------------------
# admin removes a registration
# ---------------------------------------------------------------------------

def _seed_history(app, stu, fac):
    """Create a chat, messages, a meeting and a pending supporting request for a student."""
    from services import chat_service, meeting_service
    with app.app_context():
        chat = chat_service.open_chat(stu["student_id"], fac["faculty_id"], stu["user_id"])
        chat_service.send_text_message(chat["id"], stu["user_id"], "hello sir")
        chat_service.send_text_message(chat["id"], fac["user_id"], "hello")
        m_open = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Doubt", "")
        m_acc = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Project", "")
        meeting_service.respond_to_meeting(m_acc, fac["faculty_id"], True, "ok", "Mon 10am")
        m_done = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Old", "")
        meeting_service.respond_to_meeting(m_done, fac["faculty_id"], True, "ok", "Tue")
        meeting_service.complete_meeting(m_done, stu["user_id"], "STUDENT")
        return chat["id"], m_open, m_acc, m_done


def test_remove_registration_blocks_login_keeps_history_and_frees_identifiers(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    chat_id, m_open, m_acc, m_done = _seed_history(app, stu, fac)
    student_client = login_client(app, stu["email"])
    assert student_client.get("/api/auth/session").json()["authenticated"] is True

    resp = api_post(admin_client, f"/api/admin/students/{stu['student_id']}/remove-registration")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True and "removed" in data["message"].lower() and stu["usn"] in data["message"]
    assert data["student"]["is_removed"] is True and data["student"]["usn"] == stu["usn"]

    # the live session is cut off, and nobody can sign in with the old e-mail or USN any more
    assert student_client.get("/api/auth/session").json()["authenticated"] is False
    anon = TestClient(app)
    for ident in (stu["email"], stu["usn"], stu["usn"].lower()):
        r = api_post(anon, "/api/auth/login", json={"identifier": ident, "password": PASSWORD})
        assert r.status_code == 401, ident
    assert anon.get("/api/auth/session").json()["authenticated"] is False

    user = db_one(app, "SELECT * FROM users WHERE id = ?", (stu["user_id"],))
    assert user["is_active"] == 0 and user["email"] != stu["email"]
    st = db_one(app, "SELECT * FROM students WHERE id = ?", (stu["student_id"],))
    assert st["usn"] != stu["usn"] and st["college_email"] != stu["email"]

    # history is preserved
    assert db_count(app, "chats", "id = ?", (chat_id,)) == 1
    assert db_count(app, "messages", "chat_id = ?", (chat_id,)) == 2
    assert db_count(app, "meeting_requests", "student_id = ?", (stu["student_id"],)) == 3
    status = {r["id"]: r["status"] for r in db_all(app, "SELECT id, status FROM meeting_requests")}
    assert status[m_open] == status[m_acc] == "CANCELLED"  # open ones are cancelled...
    assert status[m_done] == "COMPLETED"  # ...finished ones are untouched
    assert db_one(app, "SELECT cancelled_by FROM meeting_requests WHERE id = ?", (m_open,))["cancelled_by"] == "FACULTY"
    # notifications are kept too
    assert db_count(app, "notifications", "user_id = ?", (stu["user_id"],)) >= 1
    # ... and the admin can still read the conversation
    assert admin_client.get(f"/api/admin/chats/{chat_id}").json()["chat"]["message_count"] == 2


def test_removed_student_can_register_again_with_same_email_and_usn_and_other_class(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    _seed_history(app, stu, fac)
    api_post(admin_client, f"/api/admin/students/{stu['student_id']}/remove-registration")

    new_sid = section_id_for(app, "AIDE", "2nd Year", "C")
    c = TestClient(app)
    resp = http_student_signup(c, None, stu["email"], stu["usn"], new_sid, full_name="Same Person")
    assert resp.status_code == 201, resp.text

    new = db_one(app, "SELECT st.*, u.is_active, u.id AS uid FROM students st JOIN users u ON u.id = st.user_id "
                      "WHERE st.usn = ?", (stu["usn"],))
    assert new["section_id"] == new_sid and (new["department"], new["year"], new["section"]) == ("AIDE", "2nd Year", "C")
    assert new["uid"] != stu["user_id"] and new["id"] != stu["student_id"] and new["is_active"] == 1

    # the new account logs in; the old tombstoned rows still exist (history preserved)
    assert login_client(app, stu["email"]).get("/api/auth/session").json()["authenticated"] is True
    assert db_count(app, "students") == 2 and db_count(app, "users", "role = 'STUDENT'") == 2
    assert db_count(app, "messages") == 2
    # the old faculty (AIML 3rd A) cannot reach the re-registered student (now AIDE 2nd C)
    with app.app_context():
        assert not queries.is_faculty_accessible_to_student(new["id"], fac["faculty_id"])
    # the admin list shows both: one removed, one live, with the same displayed USN / e-mail
    rows = [s for s in admin_client.get("/api/admin/students").json()["items"] if s["usn"] == stu["usn"]]
    assert sorted(r["is_removed"] for r in rows) == [False, True]
    assert {r["email"] for r in rows} == {stu["email"]}


def test_remove_registration_is_idempotent_and_never_tombstones_twice(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    url = f"/api/admin/students/{stu['student_id']}/remove-registration"
    assert api_post(admin_client, url).status_code == 200
    snapshot = (db_one(app, "SELECT usn, college_email, updated_at FROM students WHERE id = ?", (stu["student_id"],)),
                db_one(app, "SELECT email FROM users WHERE id = ?", (stu["user_id"],)))
    for _ in range(3):
        body = err(api_post(admin_client, url), 409, "already_removed")
        assert "already removed" in body["message"]
    after = (db_one(app, "SELECT usn, college_email, updated_at FROM students WHERE id = ?", (stu["student_id"],)),
             db_one(app, "SELECT email FROM users WHERE id = ?", (stu["user_id"],)))
    assert after == snapshot
    assert db_one(app, "SELECT usn FROM students WHERE id = ?", (stu["student_id"],))["usn"].count("~removed-") == 1
    assert db_one(app, "SELECT college_email FROM students WHERE id = ?", (stu["student_id"],))[
        "college_email"].count("removed-") == 1
    # unknown / malformed ids
    err(api_post(admin_client, "/api/admin/students/99999/remove-registration"), 404, "not_found")
    err(api_post(admin_client, "/api/admin/students/abc/remove-registration"), 400, "validation_error")


def test_archive_student_registration_query_is_a_noop_the_second_time(app):
    stu, fac, sid = _student_with_faculty(app)
    with app.app_context():
        assert aq.archive_student_registration(424242) is False  # unknown id
        assert aq.archive_student_registration(stu["student_id"]) is True
        first = dict(queries.get_student_by_id(stu["student_id"]))
        assert aq.archive_student_registration(stu["student_id"]) is False
        assert dict(queries.get_student_by_id(stu["student_id"])) == first


def test_remove_registration_drops_pending_supporting_requests(app, admin_client):
    from services import supporting_service
    stu, fac, sid = _student_with_faculty(app)
    other = create_faculty(app, "FAC091")
    with app.app_context():
        supporting_service.student_request_faculty(stu["student_id"], other["faculty_id"])
    assert db_count(app, "supporting_relationships") == 1
    api_post(admin_client, f"/api/admin/students/{stu['student_id']}/remove-registration")
    assert db_count(app, "supporting_relationships") == 0


def test_removed_student_not_listed_in_class_views_and_search(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    api_post(admin_client, f"/api/admin/students/{stu['student_id']}/remove-registration")
    with app.app_context():
        assert aq.list_students_for_section(sid) == []
        assert aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS200") == []
        assert aq.list_assignments_for_faculty(fac["faculty_id"])[0]["student_count"] == 0


def test_admin_students_list_shape_filters_and_removed_flag(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    other = create_student(app, "1AB21CS201", section_id_for(app, "IoT", "1st Year", "B"))
    api_post(admin_client, f"/api/admin/students/{stu['student_id']}/remove-registration")
    data = admin_client.get("/api/admin/students").json()
    assert data["total"] == 2
    live, removed = data["items"]  # live registrations are listed first
    assert live["usn"] == other["usn"] and live["is_active"] is True and live["is_removed"] is False
    assert live["class"] == {"section_id": other["section_id"], "branch": "CSE", "department": "IoT",
                             "year": "1st Year", "section": "B", "label": "CSE → IoT → 1st Year → B"}
    assert live["can_remove_registration"] is True and live["is_unmapped"] is False
    assert removed["is_active"] is False and removed["is_removed"] is True
    assert removed["can_remove_registration"] is False and removed["usn"] == stu["usn"]
    assert removed["email"] == stu["email"]
    # filter by class
    only = admin_client.get(f"/api/admin/students?section_id={sid}").json()
    assert [s["id"] for s in only["items"]] == [stu["student_id"]]
    assert admin_client.get("/api/admin/students?section_id=99999").json()["items"] == []
    err(admin_client.get("/api/admin/students?section_id=abc"), 400, "validation_error")


def test_unmapped_legacy_student_is_flagged_with_legacy_text(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    db_exec(app, "UPDATE students SET section_id = NULL, branch = 'ECE', department = 'Physics', year = 'Final', "
                 "section = '9' WHERE id = ?", (stu["student_id"],))
    row = admin_client.get("/api/admin/students").json()["items"][0]
    assert row["class"] is None and row["is_unmapped"] is True
    assert row["legacy_class"] == {"branch": "ECE", "department": "Physics", "year": "Final", "section": "9"}
    assert admin_client.get("/api/admin/dashboard").json()["stats"]["unmapped_student_count"] == 1


# ---------------------------------------------------------------------------
# legacy (pre-hierarchy) database migration
# ---------------------------------------------------------------------------

LEGACY_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('STUDENT', 'FACULTY', 'ADMIN')),
    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, full_name TEXT NOT NULL,
    profile_picture_path TEXT, is_active INTEGER NOT NULL DEFAULT 1,
    theme_preference TEXT NOT NULL DEFAULT 'light',
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE faculty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    faculty_code TEXT NOT NULL UNIQUE, department TEXT NOT NULL, professional_email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    usn TEXT NOT NULL UNIQUE, branch TEXT NOT NULL, department TEXT NOT NULL, year TEXT NOT NULL,
    section TEXT NOT NULL, phone TEXT NOT NULL, personal_email TEXT NOT NULL, college_email TEXT NOT NULL UNIQUE,
    class_faculty_id INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE faculty_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    branch TEXT NOT NULL, department TEXT NOT NULL, year TEXT NOT NULL, section TEXT NOT NULL
);
"""

LEGACY_STUDENTS = [
    # (usn, branch, department, year, section, expected "(dept, year, sec)" or None when unmatched)
    ("L1", "CSE", "AIML", "3rd Year", "A", ("AIML", "3rd Year", "A")),
    ("L2", "CSE", "AIML", "3", "3A", ("AIML", "3rd Year", "A")),          # '3A' style section
    ("L3", "cse", "aiml", "3rd", "b", ("AIML", "3rd Year", "B")),          # case + short year
    ("L4", " CSE ", " AIDE ", "2nd year", "2C", ("AIDE", "2nd Year", "C")),
    ("L5", "CSE", "Physics", "3rd Year", "A", None),                      # unknown department
    ("L6", "ECE", "AIML", "3rd Year", "A", None),                         # unknown branch
    ("L7", "CSE", "AIML", "Final", "A", None),                            # unparseable year
    ("L8", "CSE", "AIML", "3rd Year", "", None),                          # empty section
    ("L9", "CSE", "AIML", "3rd Year", "12", None),                        # digits only
]
LEGACY_FACULTY_CLASSES = [
    # (faculty_code, branch, department, year, section, matches?)
    ("LF1", "CSE", "AIML", "3rd Year", "A", True),
    ("LF1", "CSE", "AIML", "3", "3B", True),
    ("LF1", "CSE", "Nowhere", "3rd Year", "A", False),
    ("LF2", "CSE", "AIML", "3rd Year", "A", True),
    ("LF2", "CSE", "GenAI", "Final", "A", False),
]


def _build_legacy_db(path):
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SCHEMA)
    for code in ("LF1", "LF2"):
        cur = con.execute("INSERT INTO users (role, email, password_hash, full_name) VALUES ('FACULTY', ?, 'x', ?)",
                          (f"{code.lower()}@college.edu", f"Legacy {code}"))
        con.execute("INSERT INTO faculty (user_id, faculty_code, department, professional_email) VALUES (?, ?, 'CSE', ?)",
                    (cur.lastrowid, code, f"{code.lower()}@college.edu"))
    for usn, branch, dept, year, sec, _ in LEGACY_STUDENTS:
        cur = con.execute("INSERT INTO users (role, email, password_hash, full_name) VALUES ('STUDENT', ?, 'x', ?)",
                          (f"{usn.lower()}@college.edu", f"Legacy {usn}"))
        con.execute(
            """INSERT INTO students (user_id, usn, branch, department, year, section, phone, personal_email, college_email)
               VALUES (?, ?, ?, ?, ?, ?, '9999999999', 'p@example.com', ?)""",
            (cur.lastrowid, usn, branch, dept, year, sec, f"{usn.lower()}@college.edu"))
    for code, branch, dept, year, sec, _ in LEGACY_FACULTY_CLASSES:
        fid = con.execute("SELECT id FROM faculty WHERE faculty_code = ?", (code,)).fetchone()[0]
        con.execute("INSERT INTO faculty_classes (faculty_id, branch, department, year, section) VALUES (?, ?, ?, ?, ?)",
                    (fid, branch, dept, year, sec))
    con.commit()
    con.close()


def _columns(path, table):
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def _legacy_settings(tmp_path, path):
    return make_settings(tmp_path, database_path=str(path), upload_root=str(tmp_path / "up"))


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "legacy.db"
    _build_legacy_db(str(path))
    assert "section_id" not in _columns(str(path), "students")
    return tmp_path, path


def test_legacy_migration_adds_columns_seeds_structure_and_backfills(legacy_db):
    tmp_path, path = legacy_db
    app = create_app(_legacy_settings(tmp_path, path))

    assert "section_id" in _columns(str(path), "students")
    assert "last_login_at" in _columns(str(path), "users")
    with app.app_context():
        assert len(aq.list_combos()) == 72  # default structure seeded on the legacy database

    rows = {r["usn"]: r for r in db_all(app, "SELECT * FROM students")}
    assert len(rows) == len(LEGACY_STUDENTS)  # nothing deleted
    for usn, branch, dept, year, sec, expected in LEGACY_STUDENTS:
        row = rows[usn]
        if expected:
            with app.app_context():
                combo = aq.get_combo(row["section_id"])
            assert (combo["department_name"], combo["year_name"], combo["section_name"]) == expected, usn
            # the free-text columns are normalised to the canonical names
            assert (row["department"], row["year"], row["section"]) == expected
        else:
            assert row["section_id"] is None, usn
            # unmatched rows keep their original text untouched
            assert (row["branch"], row["department"], row["year"], row["section"]) == (branch, dept, year, sec)
    # users / faculty rows survive too
    assert db_count(app, "users") == 2 + len(LEGACY_STUDENTS) and db_count(app, "faculty") == 2


def test_legacy_migration_backfills_faculty_assignments_and_keeps_legacy_rows(legacy_db):
    tmp_path, path = legacy_db
    app = create_app(_legacy_settings(tmp_path, path))
    assert db_count(app, "faculty_classes") == len(LEGACY_FACULTY_CLASSES)  # legacy table untouched
    with app.app_context():
        get = lambda code: db_one(app, "SELECT id FROM faculty WHERE faculty_code = ?", (code,))["id"]
        a1 = aq.list_assignments_for_faculty(get("LF1"))
        a2 = aq.list_assignments_for_faculty(get("LF2"))
    assert sorted((c["department_name"], c["year_name"], c["section_name"]) for c in a1) == [
        ("AIML", "3rd Year", "A"), ("AIML", "3rd Year", "B")]
    assert [(c["department_name"], c["year_name"], c["section_name"]) for c in a2] == [("AIML", "3rd Year", "A")]
    assert db_count(app, "faculty_assignments") == 3
    assert db_count(app, "faculty_assignments", "assigned_by IS NULL") == 3


def test_legacy_migration_grants_access_only_through_linked_assignments(legacy_db):
    tmp_path, path = legacy_db
    app = create_app(_legacy_settings(tmp_path, path))
    sid = lambda usn: db_one(app, "SELECT id FROM students WHERE usn = ?", (usn,))["id"]
    fid = lambda code: db_one(app, "SELECT id FROM faculty WHERE faculty_code = ?", (code,))["id"]
    with app.app_context():
        assert queries.is_faculty_accessible_to_student(sid("L1"), fid("LF1"))
        assert queries.is_faculty_accessible_to_student(sid("L3"), fid("LF1"))   # AIML 3rd B
        assert not queries.is_faculty_accessible_to_student(sid("L3"), fid("LF2"))  # LF2 only has 3rd A
        assert queries.is_faculty_accessible_to_student(sid("L2"), fid("LF2"))
        for unmatched in ("L5", "L6", "L7", "L8", "L9"):
            assert not queries.is_faculty_accessible_to_student(sid(unmatched), fid("LF1"))


def test_legacy_migration_is_idempotent_across_restarts(legacy_db):
    tmp_path, path = legacy_db
    cfg = _legacy_settings(tmp_path, path)
    app = create_app(cfg)
    first = (db_count(app, "faculty_assignments"), db_count(app, "students", "section_id IS NOT NULL"),
             db_count(app, "sections"), db_count(app, "faculty_classes"))
    for _ in range(2):
        app = create_app(cfg)
    assert (db_count(app, "faculty_assignments"), db_count(app, "students", "section_id IS NOT NULL"),
            db_count(app, "sections"), db_count(app, "faculty_classes")) == first


def test_backfill_does_not_resurrect_an_assignment_admin_removed(legacy_db):
    tmp_path, path = legacy_db
    cfg = _legacy_settings(tmp_path, path)
    app = create_app(cfg)
    db_exec(app, "UPDATE faculty_assignments SET is_active = 0, deactivated_at = datetime('now')")
    app = create_app(cfg)  # restart runs the backfill again
    assert db_count(app, "faculty_assignments", "is_active = 1") == 0
    assert db_count(app, "faculty_assignments") == 3


def test_backfill_links_a_student_added_later_with_legacy_values(legacy_db):
    """A row left unmatched is picked up once Admin creates the matching class."""
    tmp_path, path = legacy_db
    cfg = _legacy_settings(tmp_path, path)
    app = create_app(cfg)
    assert db_one(app, "SELECT section_id FROM students WHERE usn = 'L5'")["section_id"] is None
    with app.app_context():
        svc.add_department(aq.get_branch_by_name("CSE")["id"], "Physics")
        dept = next(d for d in aq.list_departments() if d["name"] == "Physics")
        year = svc.add_year(dept["id"], "3")
        svc.add_sections(year, "A")
    app = create_app(cfg)
    row = db_one(app, "SELECT section_id, department FROM students WHERE usn = 'L5'")
    assert row["section_id"] is not None and row["department"] == "Physics"


def test_legacy_database_is_usable_through_the_admin_api(legacy_db):
    """End to end on a migrated old database: unmapped rows are flagged, mapped rows carry their class."""
    tmp_path, path = legacy_db
    app = create_app(_legacy_settings(tmp_path, path))
    from tests.conftest import make_admin, ADMIN_EMAIL
    make_admin(app)
    c = login_client(app, ADMIN_EMAIL)
    rows = {s["usn"]: s for s in c.get("/api/admin/students").json()["items"]}
    assert rows["L1"]["class"]["label"] == "CSE → AIML → 3rd Year → A" and rows["L1"]["is_unmapped"] is False
    assert rows["L5"]["class"] is None and rows["L5"]["is_unmapped"] is True
    assert rows["L5"]["legacy_class"]["department"] == "Physics"
    stats = c.get("/api/admin/dashboard").json()["stats"]
    assert stats["student_count"] == len(LEGACY_STUDENTS) and stats["unmapped_student_count"] == 5
    assert stats["faculty_count"] == 2


def test_migrate_on_fresh_db_is_noop_and_columns_present(app):
    from api import db as dbmod
    with app.app_context() as db:
        dbmod._migrate(db)
        dbmod._migrate(db)  # idempotent
    assert {"section_id"} <= _columns(app.state.settings.database_path, "students")
    assert {"last_login_at"} <= _columns(app.state.settings.database_path, "users")
