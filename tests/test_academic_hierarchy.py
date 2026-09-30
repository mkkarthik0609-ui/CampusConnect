"""Admin-controlled academic hierarchy: seed, validation, admin routes, student registration,
'students cannot change class', admin remove-registration and legacy-data migration."""
import sqlite3

import pytest

from app import create_app
from models import academic_queries as aq
from models import queries
from services import academic_service as svc
from services.academic_service import AcademicError
from tests.conftest import (
    PASSWORD, make_config, create_admin, create_faculty, create_student, section_id_for, assign,
    login_client, flashes, flash_text, db_one, db_all, db_count, db_exec, http_student_signup,
)

DEPARTMENTS = ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"]
YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]


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


def test_seed_not_rerun_after_admin_deletes_everything(tmp_path):
    """Once a branch exists the admin owns the structure; a restart must not resurrect defaults."""
    cfg = make_config(tmp_path / "x.db", tmp_path / "up")
    app1 = create_app(cfg)
    with app1.app_context():
        svc.set_active("branch", aq.get_branch_by_name("CSE")["id"], False)
    app2 = create_app(cfg)  # simulated restart
    with app2.app_context():
        assert [b["name"] for b in aq.list_branches()] == ["CSE"]
        assert aq.get_branch_by_name("CSE")["is_active"] == 0


def test_tree_json_endpoint_matches_seed_and_is_public(client):
    resp = client.get("/academic/tree.json")
    assert resp.status_code == 200
    tree = resp.get_json()
    assert [b["name"] for b in tree] == ["CSE"]
    depts = tree[0]["departments"]
    assert sorted(d["name"] for d in depts) == sorted(DEPARTMENTS)
    aiml = next(d for d in depts if d["name"] == "AIML")
    assert [y["name"] for y in aiml["years"]] == YEARS
    assert [s["name"] for s in aiml["years"][2]["sections"]] == ["A", "B", "C"]
    assert {"id", "name", "is_active"} <= set(tree[0])


# ---------------------------------------------------------------------------
# normalisation / validation
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
# activation / deletion
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
    data = client.get("/academic/tree.json").get_json()
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


def test_inactive_department_leaves_faculty_signup_and_department_list(app):
    with app.app_context():
        d = next(x for x in aq.list_departments() if x["name"] == "IoT")
        svc.set_active("department", d["id"], False)
        assert "IoT" not in aq.list_active_department_names()
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


def test_list_combos_with_counts_counts_students_and_active_faculty(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    create_student(app, "1AB21CS011", sid)
    create_student(app, "1AB21CS012", sid)
    f1, f2 = create_faculty(app, "FAC060"), create_faculty(app, "FAC061")
    assign(app, f1, sid, admin_id)
    assign(app, f2, sid, admin_id)
    with app.app_context():
        aq.deactivate_assignment(aq.get_assignment_for(f2["faculty_id"], sid)["id"])
        row = next(r for r in aq.list_combos_with_counts() if r["section_id"] == sid)
        assert (row["student_count"], row["faculty_count"]) == (2, 1)


# ---------------------------------------------------------------------------
# admin routes: authorisation
# ---------------------------------------------------------------------------

ADMIN_ACADEMIC_GETS = ["/admin/academics", "/admin/assignments", "/admin/assignment-requests",
                       "/admin/classes", "/admin/classes/1"]
ADMIN_ACADEMIC_POSTS = [
    ("/admin/academics/branch", {"name": "Hack"}),
    ("/admin/academics/department", {"branch_id": "1", "name": "Hack"}),
    ("/admin/academics/year", {"department_id": "1", "name": "5"}),
    ("/admin/academics/sections", {"year_id": "1", "names": "Z"}),
    ("/admin/academics/section/1/active", {"active": "0"}),
    ("/admin/academics/section/1/delete", {}),
    ("/admin/assignments/assign", {"faculty_id": "1", "section_id": "1"}),
    ("/admin/assignments/1/remove", {}),
    ("/admin/assignment-requests/1/decide", {"decision": "approve"}),
    ("/admin/students/1/remove-registration", {}),
]


@pytest.mark.parametrize("path", ADMIN_ACADEMIC_GETS)
def test_admin_get_pages_anonymous_redirected_non_admin_forbidden(app, path):
    create_admin(app)
    fac = create_faculty(app, "FAC070")
    stu = create_student(app, "1AB21CS020")
    anon = app.test_client()
    resp = anon.get(path)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    for user in (fac, stu):
        assert login_client(app, user["email"]).get(path).status_code == 403


@pytest.mark.parametrize("path,data", ADMIN_ACADEMIC_POSTS)
def test_admin_post_actions_anonymous_redirected_non_admin_forbidden_and_no_side_effects(app, path, data):
    create_admin(app)
    fac = create_faculty(app, "FAC071")
    stu = create_student(app, "1AB21CS021")
    snapshot = lambda: (db_count(app, "branches"), db_count(app, "departments"), db_count(app, "academic_years"),
                        db_count(app, "sections", "is_active = 1"), db_count(app, "faculty_assignments"),
                        db_count(app, "users", "is_active = 1"))
    before = snapshot()
    resp = app.test_client().post(path, data=data)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    for user in (fac, stu):
        assert login_client(app, user["email"]).post(path, data=data).status_code == 403
    assert snapshot() == before


def test_admin_pages_render_for_admin(app, admin_client):
    for path in ADMIN_ACADEMIC_GETS[:-1]:
        assert admin_client.get(path).status_code == 200, path
    sid = section_id_for(app)
    assert admin_client.get(f"/admin/classes/{sid}").status_code == 200
    resp = admin_client.get("/admin/classes/99999")
    assert resp.status_code == 302 and "/admin/classes" in resp.headers["Location"]
    assert "not found" in flash_text(admin_client).lower()


# ---------------------------------------------------------------------------
# admin routes: behaviour
# ---------------------------------------------------------------------------

def test_admin_adds_full_chain_via_http(app, admin_client):
    post = lambda path, **d: admin_client.post(path, data=d)
    assert post("/admin/academics/branch", name="ECE").status_code == 302
    assert "Branch added" in flash_text(admin_client)
    bid = db_one(app, "SELECT id FROM branches WHERE name = 'ECE'")["id"]

    post("/admin/academics/department", branch_id=bid, name="VLSI")
    assert "Department added" in flash_text(admin_client)
    did = db_one(app, "SELECT id FROM departments WHERE name = 'VLSI'")["id"]

    post("/admin/academics/year", department_id=did, name="2")
    assert "year added" in flash_text(admin_client).lower()
    yid = db_one(app, "SELECT id FROM academic_years WHERE department_id = ?", (did,))["id"]
    assert db_one(app, "SELECT name FROM academic_years WHERE id = ?", (yid,))["name"] == "2nd Year"

    post("/admin/academics/sections", year_id=yid, names="A, B")
    assert [r["name"] for r in db_all(app, "SELECT name FROM sections WHERE academic_year_id = ?", (yid,))] == ["A", "B"]

    # the new class is immediately selectable on the public tree
    names = [b["name"] for b in app.test_client().get("/academic/tree.json").get_json()]
    assert "ECE" in names


@pytest.mark.parametrize("path,data,needle", [
    ("/admin/academics/branch", {"name": "CSE"}, "already exists"),
    ("/admin/academics/branch", {"name": ""}, "name must be"),
    ("/admin/academics/department", {"branch_id": "1", "name": "AIML"}, "already exists"),
    ("/admin/academics/department", {"branch_id": "abc", "name": "X"}, "Branch not found"),
    ("/admin/academics/year", {"department_id": "1", "name": "3"}, "already exists"),
    ("/admin/academics/year", {"department_id": "1", "name": "Final"}, "Year must look like"),
    ("/admin/academics/sections", {"year_id": "1", "names": "3A"}, "single letter"),
    ("/admin/academics/sections", {"year_id": "1", "names": "A B C"}, "already exist"),
    ("/admin/academics/sections", {"year_id": "", "names": "Z"}, "Year not found"),
    ("/admin/academics/galaxy/1/active", {"active": "0"}, "not found"),
    ("/admin/academics/section/99999/delete", {}, "not found"),
])
def test_admin_structure_errors_are_flashed_not_crashes(app, admin_client, path, data, needle):
    before = db_count(app, "sections")
    resp = admin_client.post(path, data=data)
    assert resp.status_code == 302
    cats = flashes(admin_client)
    assert cats and cats[0][0] == "error" and needle.lower() in cats[0][1].lower(), cats
    assert db_count(app, "sections") == before


def test_admin_deactivate_reactivate_and_delete_via_http(app, admin_client):
    sid = section_id_for(app, "IoT", "4th Year", "C")
    admin_client.post(f"/admin/academics/section/{sid}/active", data={"active": "0"})
    assert db_one(app, "SELECT is_active FROM sections WHERE id = ?", (sid,))["is_active"] == 0
    tree = app.test_client().get("/academic/tree.json").get_json()
    iot = next(d for d in tree[0]["departments"] if d["name"] == "IoT")
    assert [s["name"] for s in iot["years"][3]["sections"]] == ["A", "B"]

    admin_client.post(f"/admin/academics/section/{sid}/active", data={"active": "1"})
    assert db_one(app, "SELECT is_active FROM sections WHERE id = ?", (sid,))["is_active"] == 1

    admin_client.post(f"/admin/academics/section/{sid}/delete")
    assert db_one(app, "SELECT id FROM sections WHERE id = ?", (sid,)) is None
    assert "deleted" in flash_text(admin_client).lower()

    # deleting a section that has a student is refused
    used = section_id_for(app, "IoT", "4th Year", "A")
    create_student(app, "1AB21CS030", used)
    admin_client.post(f"/admin/academics/section/{used}/delete")
    assert db_one(app, "SELECT id FROM sections WHERE id = ?", (used,)) is not None
    assert "deactivate it instead" in flash_text(admin_client)


# ---------------------------------------------------------------------------
# student registration (HTTP and service)
# ---------------------------------------------------------------------------

def test_registration_with_valid_section_id_stores_text_and_link(app, client, captured_otps):
    sid = section_id_for(app, "AIDE", "2nd Year", "B")
    resp = http_student_signup(client, captured_otps, "reg1@college.edu", "1AB21CS100", sid)
    assert resp.status_code == 302
    st = db_one(app, "SELECT * FROM students WHERE usn = '1AB21CS100'")
    assert st["section_id"] == sid
    assert (st["branch"], st["department"], st["year"], st["section"]) == ("CSE", "AIDE", "2nd Year", "B")
    assert st["college_email"] == "reg1@college.edu"


@pytest.mark.parametrize("bad", ["", "abc", "999999", "-5", "0", "1; DROP TABLE students", "1 OR 1=1"])
def test_registration_rejects_invalid_or_forged_section_ids(app, client, captured_otps, bad):
    http_student_signup(client, captured_otps, "reg2@college.edu", "1AB21CS101", bad)
    assert db_count(app, "students") == 0
    assert db_count(app, "users") == 0


def test_registration_rejects_missing_section_id_field(app, client, captured_otps):
    client.post("/signup/student", data={"college_email": "reg3@college.edu"})
    client.post("/signup/student/verify-otp", data={"email": "reg3@college.edu", "otp": captured_otps["reg3@college.edu"]})
    resp = client.post("/signup/student/details?email=reg3@college.edu", data={
        "college_email": "reg3@college.edu", "full_name": "N", "usn": "1AB21CS102", "phone": "9999999999",
        "personal_email": "n@example.com", "password": PASSWORD, "confirm_password": PASSWORD,
        "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
    })
    assert resp.status_code == 200  # form re-rendered, nothing created
    assert db_count(app, "students") == 0


@pytest.mark.parametrize("level", ["section", "year", "department", "branch"])
def test_registration_rejects_inactive_chain_at_any_level(app, client, captured_otps, level):
    sid = section_id_for(app, "GenAI", "1st Year", "A")
    with app.app_context():
        combo = aq.get_combo(sid)
        svc.set_active(level, combo[f"{level}_id"], False)
    http_student_signup(client, captured_otps, "reg4@college.edu", "1AB21CS103", sid)
    assert db_count(app, "students") == 0


def test_free_text_class_fields_are_ignored_in_favour_of_section_id(app, client, captured_otps):
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    http_student_signup(client, captured_otps, "reg5@college.edu", "1AB21CS104", sid, extra={
        "branch": "ECE", "department": "Hacking", "year": "9th Year", "section": "Z",
    })
    st = db_one(app, "SELECT * FROM students WHERE usn = '1AB21CS104'")
    assert (st["branch"], st["department"], st["year"], st["section"]) == ("CSE", "AIML", "3rd Year", "A")
    assert st["section_id"] == sid


def test_free_text_only_registration_is_rejected(app):
    with app.app_context():
        from services import auth_service
        with pytest.raises(auth_service.ValidationError):
            auth_service.register_student({
                "full_name": "X", "usn": "1AB21CS105", "branch": "CSE", "department": "AIML", "year": "3rd Year",
                "section": "A", "phone": "9999999999", "personal_email": "x@example.com",
                "college_email": "x105@college.edu", "password": PASSWORD})
    assert db_count(app, "students") == 0


def test_student_dashboard_lists_faculty_assigned_to_their_section(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    stu = create_student(app, "1AB21CS106", sid)
    fac = create_faculty(app, "FAC080", name="Dr Visible")
    assign(app, fac, sid, admin_id)
    c = login_client(app, stu["email"])
    resp = c.get("/student/dashboard")
    assert resp.status_code == 200 and b"Dr Visible" in resp.data
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


def test_profile_change_ignores_class_fields_entirely(app):
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    resp = c.post("/student/profile/change-request", data={
        "branch": "ECE", "department": "AIDE", "year": "4th Year", "section": "C", "section_id": "5",
        "reason": "moving",
    })
    assert resp.status_code == 302
    assert "No valid profile fields" in flash_text(c)
    assert db_count(app, "permission_requests") == 0
    st = db_one(app, "SELECT * FROM students WHERE id = ?", (stu["student_id"],))
    assert (st["department"], st["year"], st["section"], st["section_id"]) == ("AIML", "3rd Year", "A", sid)


def test_profile_change_with_class_and_phone_only_keeps_phone_in_request(app):
    import json
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    c.post("/student/profile/change-request", data={
        "phone": "8888888888", "section": "C", "year": "1st Year", "branch": "ECE", "department": "IoT",
        "section_id": "7", "usn": "HACKED", "college_email": "h@x.com", "class_faculty_id": "1",
    })
    req = db_one(app, "SELECT * FROM permission_requests")
    assert json.loads(req["requested_changes"]) == {"phone": "8888888888"}


def test_approved_profile_change_cannot_alter_class_even_if_row_was_forged(app):
    """Defence in depth: even a forged pending request containing class fields applies... only what the
    service-layer filter allowed at creation; verify the service filter itself."""
    from services import permission_service
    assert permission_service.STUDENT_EDITABLE_FIELDS == {"phone", "personal_email"}
    for f in ("branch", "department", "year", "section", "section_id", "usn"):
        assert f not in permission_service.STUDENT_EDITABLE_FIELDS


def test_no_student_route_changes_section(app):
    """No URL rule exposes a way for a student to move to another section."""
    rules = [(r.rule, sorted(r.methods - {"HEAD", "OPTIONS"})) for r in app.url_map.iter_rules()]
    student_rules = [r for r, _ in rules if r.startswith("/student")]
    assert sorted(student_rules) == sorted([
        "/student/dashboard", "/student/profile", "/student/profile/picture",
        "/student/profile/change-request", "/student/theme/<theme>",
    ])
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    for path in ("/student/profile/section", "/student/section", "/student/class", "/student/profile/class",
                 "/student/change-section", "/academic/select"):
        for method in (c.get, c.post):
            assert method(path, data={"section_id": "3"}).status_code in (404, 405), path
    assert db_one(app, "SELECT section_id FROM students WHERE id = ?", (stu["student_id"],))["section_id"] == sid


def test_student_cannot_hit_admin_remove_registration_on_self(app):
    stu, fac, sid = _student_with_faculty(app)
    c = login_client(app, stu["email"])
    assert c.post(f"/admin/students/{stu['student_id']}/remove-registration").status_code == 403
    assert db_one(app, "SELECT is_active FROM users WHERE id = ?", (stu["user_id"],))["is_active"] == 1


# ---------------------------------------------------------------------------
# admin removes registration
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
    assert login_client(app, stu["email"]).get("/student/dashboard").status_code == 200

    resp = admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration")
    assert resp.status_code == 302 and "/admin/students" in resp.headers["Location"]
    assert "removed" in flash_text(admin_client).lower()

    # cannot log in any more (email or USN)
    c = app.test_client()
    for ident in (stu["email"], stu["usn"], stu["usn"].lower()):
        r = c.post("/login", data={"email": ident, "password": PASSWORD})
        assert r.status_code == 200 and c.get("/student/dashboard").status_code == 302

    user = db_one(app, "SELECT * FROM users WHERE id = ?", (stu["user_id"],))
    assert user["is_active"] == 0 and user["email"] != stu["email"]
    st = db_one(app, "SELECT * FROM students WHERE id = ?", (stu["student_id"],))
    assert st["usn"] != stu["usn"] and st["college_email"] != stu["email"]

    # history is preserved
    assert db_one(app, "SELECT COUNT(*) AS c FROM chats WHERE id = ?", (chat_id,))["c"] == 1
    assert db_count(app, "messages", "chat_id = ?", (chat_id,)) == 2
    assert db_count(app, "meeting_requests", "student_id = ?", (stu["student_id"],)) == 3
    status = {r["id"]: r["status"] for r in db_all(app, "SELECT id, status FROM meeting_requests")}
    assert status[m_open] == status[m_acc] == "CANCELLED"  # open ones are cancelled...
    assert status[m_done] == "COMPLETED"  # ...finished ones are untouched
    assert db_one(app, "SELECT cancelled_by FROM meeting_requests WHERE id = ?", (m_open,))["cancelled_by"] == "FACULTY"
    # notifications are kept too
    assert db_count(app, "notifications", "user_id = ?", (stu["user_id"],)) >= 1


def test_removed_student_can_register_again_with_same_email_and_usn_and_other_class(app, admin_client, captured_otps):
    stu, fac, sid = _student_with_faculty(app)
    _seed_history(app, stu, fac)
    admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration")

    new_sid = section_id_for(app, "AIDE", "2nd Year", "C")
    c = app.test_client()
    resp = http_student_signup(c, captured_otps, stu["email"], stu["usn"], new_sid, full_name="Same Person")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")

    new = db_one(app, "SELECT st.*, u.is_active, u.id AS uid FROM students st JOIN users u ON u.id = st.user_id "
                      "WHERE st.usn = ?", (stu["usn"],))
    assert new["section_id"] == new_sid and (new["department"], new["year"], new["section"]) == ("AIDE", "2nd Year", "C")
    assert new["uid"] != stu["user_id"] and new["id"] != stu["student_id"] and new["is_active"] == 1

    # the new account logs in; the old tombstoned rows still exist (history preserved)
    assert login_client(app, stu["email"]).get("/student/dashboard").status_code == 200
    assert db_count(app, "students") == 2 and db_count(app, "users", "role = 'STUDENT'") == 2
    assert db_count(app, "messages") == 2
    # the old faculty (AIML 3rd A) cannot reach the re-registered student (now AIDE 2nd C)
    with app.app_context():
        assert not queries.is_faculty_accessible_to_student(new["id"], fac["faculty_id"])


def test_remove_registration_twice_and_unknown_student(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    assert admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration").status_code == 302
    flashes(admin_client)
    assert admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration").status_code == 302
    assert "already removed" in flash_text(admin_client)
    st = db_one(app, "SELECT usn FROM students WHERE id = ?", (stu["student_id"],))
    assert st["usn"].count("~removed-") == 1  # tombstoned exactly once
    admin_client.post("/admin/students/99999/remove-registration")
    assert "not found" in flash_text(admin_client).lower()


def test_archive_student_registration_unknown_id_returns_false(app):
    with app.app_context():
        assert aq.archive_student_registration(424242) is False


def test_remove_registration_drops_pending_supporting_requests(app, admin_client):
    from services import supporting_service
    stu, fac, sid = _student_with_faculty(app)
    other = create_faculty(app, "FAC091")
    with app.app_context():
        supporting_service.student_request_faculty(stu["student_id"], other["faculty_id"])
    assert db_count(app, "supporting_relationships") == 1
    admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration")
    assert db_count(app, "supporting_relationships") == 0


def test_removed_student_not_listed_in_class_views_and_search(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration")
    with app.app_context():
        assert aq.list_students_for_section(sid) == []
        assert aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS200") == []
        assert aq.list_assignments_for_faculty(fac["faculty_id"])[0]["student_count"] == 0


def test_admin_students_page_lists_removed_students_as_inactive(app, admin_client):
    stu, fac, sid = _student_with_faculty(app)
    admin_client.post(f"/admin/students/{stu['student_id']}/remove-registration")
    assert admin_client.get("/admin/students").status_code == 200
    with app.app_context():
        rows = aq.list_students_admin()
        assert len(rows) == 1 and rows[0]["is_active"] == 0
        assert aq.list_students_admin(section_id=sid)[0]["id"] == stu["student_id"]
        assert aq.list_students_admin(section_id=99999) == []


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


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "legacy.db"
    _build_legacy_db(str(path))
    assert "section_id" not in _columns(str(path), "students")
    return tmp_path, path


def test_legacy_migration_adds_columns_seeds_structure_and_backfills(legacy_db):
    tmp_path, path = legacy_db
    app = create_app(make_config(path, tmp_path / "up"))

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


def test_legacy_migration_backfills_faculty_assignments_and_keeps_legacy_rows(legacy_db):
    tmp_path, path = legacy_db
    app = create_app(make_config(path, tmp_path / "up"))
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
    app = create_app(make_config(path, tmp_path / "up"))
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
    cfg = make_config(path, tmp_path / "up")
    app = create_app(cfg)
    first = (db_count(app, "faculty_assignments"), db_count(app, "students", "section_id IS NOT NULL"),
             db_count(app, "sections"), db_count(app, "faculty_classes"))
    for _ in range(2):
        app = create_app(cfg)
    assert (db_count(app, "faculty_assignments"), db_count(app, "students", "section_id IS NOT NULL"),
            db_count(app, "sections"), db_count(app, "faculty_classes")) == first


def test_backfill_does_not_resurrect_an_assignment_admin_removed(legacy_db):
    tmp_path, path = legacy_db
    cfg = make_config(path, tmp_path / "up")
    app = create_app(cfg)
    db_exec(app, "UPDATE faculty_assignments SET is_active = 0, deactivated_at = datetime('now')")
    app = create_app(cfg)  # restart runs the backfill again
    assert db_count(app, "faculty_assignments", "is_active = 1") == 0
    assert db_count(app, "faculty_assignments") == 3


def test_backfill_links_a_student_added_later_with_legacy_values(legacy_db):
    """A row left unmatched is picked up once Admin creates the matching class."""
    tmp_path, path = legacy_db
    cfg = make_config(path, tmp_path / "up")
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


def test_migrate_on_fresh_db_is_noop_and_columns_present(app):
    with app.app_context():
        from models import database
        from models.database import get_db
        database._migrate(get_db())
        database._migrate(get_db())  # idempotent
    assert {"section_id"} <= {c for c in _columns(app.config["DATABASE_PATH"], "students")}
