"""Faculty <-> class assignments: admin assign/remove (service + /api/admin endpoints), faculty requests and the
admin decision, multi-faculty sections and the access rules that hang off them (checked at service level; the
chat / meeting / faculty endpoints that call these rules are covered by their own routers' tests)."""
import itertools

import pytest

from models import academic_queries as aq
from models import queries
from services import academic_service, assignment_service, chat_service, meeting_service, permission_service
from services.assignment_service import AssignmentError
from tests.conftest import (
    ADMIN_EMAIL, create_admin, create_faculty, create_student, section_id_for, assign, unassign, login_client,
    api_post, api_delete, db_one, db_all, db_count,
)

AIML_3A = ("AIML", "3rd Year", "A")
AIML_3B = ("AIML", "3rd Year", "B")
AIML_3C = ("AIML", "3rd Year", "C")
AIDE_2A = ("AIDE", "2nd Year", "A")
AIDE_3A = ("AIDE", "3rd Year", "A")
GENAI_1B = ("GenAI", "1st Year", "B")


def err(resp, status, code=None):
    assert resp.status_code == status, resp.text
    body = resp.json()["error"]
    if code:
        assert body["code"] == code, body
    return body


@pytest.fixture
def world(app):
    """The scenario from the spec.

    FAC001 -> AIML 3rd A, AIML 3rd B, AIDE 2nd A
    FAC002 -> AIML 3rd A, GenAI 1st B
    FAC003 -> AIDE 3rd A (same year+section label as AIML 3rd A, different department), AIML 3rd C
    FAC004 -> nothing
    """
    admin_id = create_admin(app)
    sec = {name: section_id_for(app, *name) for name in
           (AIML_3A, AIML_3B, AIML_3C, AIDE_2A, AIDE_3A, GENAI_1B)}
    fac = {code: create_faculty(app, code, dept) for code, dept in
           (("FAC001", "AIML"), ("FAC002", "AIML"), ("FAC003", "AIDE"), ("FAC004", "IoT"))}
    for code, combos in (("FAC001", (AIML_3A, AIML_3B, AIDE_2A)), ("FAC002", (AIML_3A, GENAI_1B)),
                         ("FAC003", (AIDE_3A, AIML_3C))):
        for combo in combos:
            assign(app, fac[code], sec[combo], admin_id)
    stu = {name: create_student(app, f"1AB21CS{i:03d}", sec[name]) for i, name in enumerate(
        (AIML_3A, AIML_3B, AIML_3C, AIDE_2A, AIDE_3A, GENAI_1B), start=1)}
    return {"admin": admin_id, "sec": sec, "fac": fac, "stu": stu}


@pytest.fixture
def admin(app, world):
    return login_client(app, ADMIN_EMAIL)


def can_reach(app, fac, stu):
    with app.app_context():
        a = queries.is_faculty_accessible_to_student(stu["student_id"], fac["faculty_id"])
        b = queries.is_student_accessible_to_faculty(fac["faculty_id"], stu["student_id"])
        c = assignment_service.faculty_can_access_student(fac["faculty_id"], stu["student_id"])
        d = assignment_service.student_can_access_faculty(stu["student_id"], fac["faculty_id"])
        assert a == b == c == d, "all access helpers must agree"
        return a


def notification_titles(app, user_id):
    return [n["title"] for n in db_all(app, "SELECT title FROM notifications WHERE user_id = ? ORDER BY id", (user_id,))]


# ---------------------------------------------------------------------------
# the spec scenario
# ---------------------------------------------------------------------------

EXPECTED = {
    # faculty -> set of student classes reachable
    "FAC001": {AIML_3A, AIML_3B, AIDE_2A},
    "FAC002": {AIML_3A, GENAI_1B},
    "FAC003": {AIDE_3A, AIML_3C},
    "FAC004": set(),
}


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_access_matrix_follows_assignments_exactly(app, world, code):
    for combo, stu in world["stu"].items():
        assert can_reach(app, world["fac"][code], stu) == (combo in EXPECTED[code]), (code, combo)


def test_fac003_cannot_reach_students_of_aiml_3rd_a(app, world):
    fac003, aiml_3a_student = world["fac"]["FAC003"], world["stu"][AIML_3A]
    assert not can_reach(app, fac003, aiml_3a_student)
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(fac003["faculty_id"], aiml_3a_student["student_id"], fac003["user_id"])
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(aiml_3a_student["student_id"], fac003["faculty_id"], aiml_3a_student["user_id"])
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(aiml_3a_student["student_id"], fac003["faculty_id"], "Doubt", "")
        found = {r["usn"] for r in aq.search_students_in_faculty_scope(fac003["faculty_id"], "1AB21CS")}
        assert found == {world["stu"][AIDE_3A]["usn"], world["stu"][AIML_3C]["usn"]}
        assert aiml_3a_student["usn"] not in found
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.get_chat_for_participant(0, fac003["user_id"], "FACULTY")  # no such chat
    assert db_count(app, "chats") == 0 and db_count(app, "meeting_requests") == 0


def test_faculty_assignments_listing(app, world):
    with app.app_context():
        got = {code: sorted((c["department_name"], c["year_name"], c["section_name"])
                            for c in aq.list_assignments_for_faculty(f["faculty_id"]))
               for code, f in world["fac"].items()}
    assert got == {code: sorted(combos) for code, combos in EXPECTED.items()}


def test_admin_faculty_endpoint_lists_the_same_assignments_and_subjects(app, world, admin):
    data = admin.get("/api/admin/faculty").json()
    assert data["total"] == 4
    by_code = {f["faculty_code"]: f for f in data["items"]}
    for code, combos in EXPECTED.items():
        got = sorted((a["department"], a["year"], a["section"]) for a in by_code[code]["assignments"])
        assert got == sorted(combos), code
    fac1 = by_code["FAC001"]
    assert fac1["subjects"] == ["DSA"] and fac1["department"] == "AIML" and fac1["is_active"] is True
    assert fac1["full_name"] == "Prof FAC001" and fac1["profile_picture_url"] is None
    a = next(x for x in fac1["assignments"] if x["section"] == "B")
    assert a["student_count"] == 1 and a["class_active"] is True and a["can_remove"] is True
    assert a["label"] == "CSE → AIML → 3rd Year → B" and a["section_id"] == world["sec"][AIML_3B]
    assert by_code["FAC004"]["assignments"] == [] and by_code["FAC004"]["pending_request_count"] == 0
    # same list through the assignments console
    rows = {r["faculty_code"]: r for r in admin.get("/api/admin/assignments").json()["items"]}
    assert {c: len(r["assignments"]) for c, r in rows.items()} == {"FAC001": 3, "FAC002": 2, "FAC003": 2, "FAC004": 0}


def test_list_faculty_for_section_and_assigned_faculty_for_student(app, world):
    with app.app_context():
        codes = [r["faculty_code"] for r in aq.list_faculty_for_section(world["sec"][AIML_3A])]
        assert codes == ["FAC001", "FAC002"]
        assert [r["faculty_code"] for r in aq.list_faculty_for_section(world["sec"][AIML_3C])] == ["FAC003"]
        assigned = aq.list_assigned_faculty_for_student(world["stu"][AIML_3A]["student_id"])
        assert sorted(r["faculty_code"] for r in assigned) == ["FAC001", "FAC002"]
        assert aq.list_assigned_faculty_for_student(world["stu"][AIDE_3A]["student_id"])[0]["faculty_code"] == "FAC003"


# ---------------------------------------------------------------------------
# admin_assign / admin_remove (service)
# ---------------------------------------------------------------------------

def test_admin_assign_creates_row_records_admin_and_notifies_faculty(app, world):
    fac = world["fac"]["FAC004"]
    sid = world["sec"][AIML_3B]
    with app.app_context():
        combo = assignment_service.admin_assign(fac["faculty_id"], sid, world["admin"])
        assert combo["section_name"] == "B"
        row = aq.get_assignment_for(fac["faculty_id"], sid)
        assert row["is_active"] == 1 and row["assigned_by"] == world["admin"] and row["deactivated_at"] is None
        notes = queries.list_notifications_for_user(fac["user_id"])
        assert [n["notification_type"] for n in notes] == ["ASSIGNMENT_CHANGED"]
        assert "CSE → AIML → 3rd Year → B" in notes[0]["message"]
    assert can_reach(app, fac, world["stu"][AIML_3B])


def test_admin_assign_duplicate_is_refused(app, world):
    with app.app_context():
        with pytest.raises(AssignmentError, match="already assigned"):
            assignment_service.admin_assign(world["fac"]["FAC001"]["faculty_id"], world["sec"][AIML_3A],
                                            world["admin"])
    assert db_count(app, "faculty_assignments") == 7


@pytest.mark.parametrize("faculty_id,section", [(99999, "ok"), (None, "ok"), ("ok", 99999), ("ok", None),
                                               ("ok", "abc"), ("ok", "1; DROP TABLE faculty_assignments")])
def test_admin_assign_rejects_bad_ids(app, world, faculty_id, section):
    fid = world["fac"]["FAC004"]["faculty_id"] if faculty_id == "ok" else faculty_id
    sid = world["sec"][AIML_3B] if section == "ok" else section
    with app.app_context():
        with pytest.raises(AssignmentError):
            assignment_service.admin_assign(fid, sid, world["admin"])
    assert db_count(app, "faculty_assignments") == 7


def test_admin_assign_rejects_inactive_class(app, world):
    sid = world["sec"][GENAI_1B]
    with app.app_context():
        academic_service.set_active("section", sid, False)
        with pytest.raises(AssignmentError):
            assignment_service.admin_assign(world["fac"]["FAC004"]["faculty_id"], sid, world["admin"])


def test_admin_remove_deactivates_notifies_and_revokes_access(app, world):
    fac, sid = world["fac"]["FAC001"], world["sec"][AIML_3B]
    assert can_reach(app, fac, world["stu"][AIML_3B])
    with app.app_context():
        aid = aq.get_assignment_for(fac["faculty_id"], sid)["id"]
        combo = assignment_service.admin_remove(aid, world["admin"])
        assert combo["section_id"] == sid
        row = aq.get_assignment(aid)
        assert row["is_active"] == 0 and row["deactivated_at"]
        assert any(n["title"] == "Class assignment removed" for n in queries.list_notifications_for_user(fac["user_id"]))
        with pytest.raises(AssignmentError, match="already inactive"):
            assignment_service.admin_remove(aid, world["admin"])
        with pytest.raises(AssignmentError):
            assignment_service.admin_remove(99999, world["admin"])
    assert not can_reach(app, fac, world["stu"][AIML_3B])
    assert can_reach(app, fac, world["stu"][AIML_3A])  # other assignments untouched


def test_reactivation_reuses_the_same_row(app, world):
    fac, sid = world["fac"]["FAC001"], world["sec"][AIML_3B]
    with app.app_context():
        aid = aq.get_assignment_for(fac["faculty_id"], sid)["id"]
    unassign(app, fac, sid, world["admin"])
    admin2 = create_admin(app, "admin2@college.edu", name="Admin Two")
    assign(app, fac, sid, admin2)
    with app.app_context():
        row = aq.get_assignment_for(fac["faculty_id"], sid)
        assert row["id"] == aid and row["is_active"] == 1 and row["deactivated_at"] is None
        assert row["assigned_by"] == admin2
    assert db_count(app, "faculty_assignments", "faculty_id = ? AND section_id = ?",
                    (fac["faculty_id"], sid)) == 1  # UNIQUE(faculty, section) respected
    assert can_reach(app, fac, world["stu"][AIML_3B])


def test_upsert_assignment_is_idempotent(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        a = aq.upsert_assignment(fac["faculty_id"], sid, world["admin"])
        b = aq.upsert_assignment(fac["faculty_id"], sid, world["admin"])
        assert a == b


def test_inactive_assignments_hidden_unless_requested(app, world):
    fac, sid = world["fac"]["FAC001"], world["sec"][AIML_3B]
    unassign(app, fac, sid, world["admin"])
    with app.app_context():
        assert len(aq.list_assignments_for_faculty(fac["faculty_id"])) == 2
        allrows = aq.list_assignments_for_faculty(fac["faculty_id"], active_only=False)
        assert len(allrows) == 3 and sorted(r["assignment_active"] for r in allrows) == [0, 1, 1]
        assert "FAC001" not in [r["faculty_code"] for r in aq.list_faculty_for_section(sid)]
        assert "FAC001" in [r["faculty_code"] for r in aq.list_faculty_for_section(sid, active_only=False)]


def test_deactivating_the_class_chain_suspends_access_and_reactivating_restores_it(app, world, admin):
    fac, stu = world["fac"]["FAC001"], world["stu"][AIML_3A]
    with app.app_context():
        dept_id = aq.get_combo(world["sec"][AIML_3A])["department_id"]
        academic_service.set_active("department", dept_id, False)
    assert not can_reach(app, fac, stu)
    with app.app_context():
        assert aq.search_students_in_faculty_scope(fac["faculty_id"], stu["usn"]) == []
        assert not aq.is_faculty_assigned_to_section(fac["faculty_id"], world["sec"][AIML_3A])
        # AIDE 2nd A is in a different department and still works
        assert aq.is_faculty_assigned_to_section(fac["faculty_id"], world["sec"][AIDE_2A])
    # the admin console still lists the suspended assignment, flagged as belonging to an inactive class
    fac1 = next(f for f in admin.get("/api/admin/faculty").json()["items"] if f["faculty_code"] == "FAC001")
    flags = {(a["department"], a["section"]): a["class_active"] for a in fac1["assignments"]}
    assert flags == {("AIML", "A"): False, ("AIML", "B"): False, ("AIDE", "A"): True}
    with app.app_context():
        academic_service.set_active("department", dept_id, True)
    assert can_reach(app, fac, stu)


def test_admin_assign_satisfies_a_pending_request_for_the_same_class(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid, "please")
        assignment_service.admin_assign(fac["faculty_id"], sid, world["admin"])
        req = aq.get_assignment_request(rid)
        assert req["status"] == "APPROVED" and req["reviewed_by"] == world["admin"]
        assert not aq.has_pending_request(fac["faculty_id"], sid)


# ---------------------------------------------------------------------------
# five faculty on one class
# ---------------------------------------------------------------------------

@pytest.fixture
def crowded(app):
    admin_id = create_admin(app)
    sid = section_id_for(app, *AIML_3A)
    facs = [create_faculty(app, f"MF{i}", "AIML") for i in range(1, 6)]
    for f in facs:
        assign(app, f, sid, admin_id)
    studs = [create_student(app, f"1AB21MS{i:03d}", sid) for i in range(1, 4)]
    return {"admin": admin_id, "sid": sid, "facs": facs, "studs": studs}


def test_five_faculty_can_all_chat_with_every_student_of_the_section(app, crowded):
    with app.app_context():
        for f, s in itertools.product(crowded["facs"], crowded["studs"]):
            chat = chat_service.open_chat_as_faculty(f["faculty_id"], s["student_id"], f["user_id"])
            same = chat_service.open_chat(s["student_id"], f["faculty_id"], s["user_id"])
            assert chat["id"] == same["id"]
            chat_service.send_text_message(chat["id"], f["user_id"], f"hi {s['usn']}")
    assert db_count(app, "chats") == 15 and db_count(app, "messages") == 15


def test_five_faculty_can_all_be_met_by_students_and_respond(app, crowded):
    with app.app_context():
        student = crowded["studs"][0]
        ids = [meeting_service.request_meeting(student["student_id"], f["faculty_id"], "Doubt", "")
               for f in crowded["facs"]]
        for mid, f in zip(ids, crowded["facs"]):
            assert meeting_service.respond_to_meeting(mid, f["faculty_id"], True, "ok", "Mon") == "ACCEPTED"
        # each faculty only owns their own meeting
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(ids[0], crowded["facs"][1]["user_id"], "FACULTY")


def test_all_five_faculty_see_each_other_and_every_student_in_the_class_directory(app, crowded):
    admin = login_client(app, ADMIN_EMAIL)
    detail = admin.get(f"/api/admin/classes/{crowded['sid']}").json()
    assert [f["faculty_code"] for f in detail["faculty"]] == ["MF1", "MF2", "MF3", "MF4", "MF5"]
    assert [s["usn"] for s in detail["students"]] == [s["usn"] for s in crowded["studs"]]
    assert detail["class"]["faculty_count"] == 5 and detail["class"]["student_count"] == 3
    with app.app_context():
        for f in crowded["facs"]:  # search is scoped the same way for each of them
            found = {r["usn"] for r in aq.search_students_in_faculty_scope(f["faculty_id"], "1AB21MS")}
            assert found == {s["usn"] for s in crowded["studs"]}
            assert {x["faculty_code"] for x in aq.list_faculty_for_section(crowded["sid"])} == {
                o["code"] for o in crowded["facs"]}


def test_student_request_is_routed_to_all_five_and_any_one_can_approve(app, crowded):
    student = crowded["studs"][0]
    with app.app_context():
        rid = permission_service.student_request_profile_change(student["user_id"], {"phone": "7777777777"}, "new number")
    assert db_count(app, "permission_requests") == 1
    for f in crowded["facs"]:
        assert "Student profile change request" in notification_titles(app, f["user_id"])
        assert [r["id"] for r in queries_pending(app, f["user_id"])] == [rid]
    # the 4th faculty approves
    with app.app_context():
        assert permission_service.decide_permission_request(rid, crowded["facs"][3]["user_id"], True) == "APPROVED"
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "APPROVED"
    assert db_one(app, "SELECT phone FROM students WHERE id = ?", (student["student_id"],))["phone"] == "7777777777"
    # it is no longer pending for the others, and they cannot decide it again
    assert queries_pending(app, crowded["facs"][0]["user_id"]) == []
    with app.app_context():
        with pytest.raises(permission_service.PermissionError_, match="already been reviewed"):
            permission_service.decide_permission_request(rid, crowded["facs"][0]["user_id"], False)


def queries_pending(app, user_id):
    with app.app_context():
        return [dict(r) for r in queries.list_pending_permission_requests_for_approver(user_id)]


def test_removing_one_of_five_only_revokes_that_one(app, crowded):
    gone = crowded["facs"][2]
    unassign(app, gone, crowded["sid"], crowded["admin"])
    for f in crowded["facs"]:
        for s in crowded["studs"]:
            assert can_reach(app, f, s) == (f is not gone)
    assert [r["faculty_code"] for r in _faculty_for(app, crowded["sid"])] == ["MF1", "MF2", "MF4", "MF5"]


def _faculty_for(app, sid):
    with app.app_context():
        return [dict(r) for r in aq.list_faculty_for_section(sid)]


# ---------------------------------------------------------------------------
# faculty request -> admin decision (the request itself is made by the faculty router; here it is created
# through the service it calls)
# ---------------------------------------------------------------------------

def _request(app, fac, sid, note=None):
    with app.app_context():
        return assignment_service.faculty_request(fac["faculty_id"], sid, note)


def test_no_access_before_approval_and_full_access_after(app, world, admin):
    fac, sid, stu = world["fac"]["FAC004"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    rid = _request(app, fac, sid, "I teach DSA to 3B")
    req = db_one(app, "SELECT * FROM faculty_assignment_requests")
    assert (req["status"], req["section_id"], req["faculty_id"], req["note"]) == (
        "PENDING", sid, fac["faculty_id"], "I teach DSA to 3B")

    # a pending request grants NOTHING
    assert not can_reach(app, fac, stu)
    with app.app_context():
        assert aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS") == []
        assert not aq.is_faculty_assigned_to_section(fac["faculty_id"], sid)
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(fac["faculty_id"], stu["student_id"], fac["user_id"])
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "hi", "")
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0

    # it shows up for the admin with everything the console needs
    pending = admin.get("/api/admin/assignment-requests?status=pending").json()
    assert pending["total"] == 1 and pending["pending_count"] == 1
    item = pending["items"][0]
    assert item["id"] == rid and item["status"] == "PENDING" and item["note"] == "I teach DSA to 3B"
    assert item["can_decide"] is True and item["class_active"] is True and item["reviewed_at"] is None
    assert item["class"]["label"] == "CSE → AIML → 3rd Year → B"
    assert item["faculty"] == {"id": fac["faculty_id"], "faculty_code": "FAC004", "full_name": "Prof FAC004",
                               "department": "IoT", "profile_picture_url": None}

    # admin approves
    resp = api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"})
    assert resp.status_code == 200 and resp.json() == {"ok": True, "message": "Request approved.",
                                                       "status": "APPROVED"}
    done = db_one(app, "SELECT * FROM faculty_assignment_requests WHERE id = ?", (rid,))
    assert done["status"] == "APPROVED" and done["reviewed_by"] == world["admin"] and done["reviewed_at"]

    assert can_reach(app, fac, stu)
    with app.app_context():
        assert [r["usn"] for r in aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS")] == [stu["usn"]]
        assert chat_service.open_chat_as_faculty(fac["faculty_id"], stu["student_id"], fac["user_id"])["id"]
        assert meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "hi", "")
    assert db_count(app, "chats") == 1 and db_count(app, "meeting_requests") == 1
    assert "Class request approved" in notification_titles(app, fac["user_id"])
    # the decided request is now history: listed under APPROVED, not decidable, not pending
    approved = admin.get("/api/admin/assignment-requests?status=APPROVED").json()["items"][0]
    assert approved["can_decide"] is False and approved["reviewed_at"]
    assert admin.get("/api/admin/assignment-requests?status=PENDING").json()["items"] == []


def test_rejected_request_leaves_no_access(app, world, admin):
    fac, sid, stu = world["fac"]["FAC004"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    rid = _request(app, fac, sid)
    resp = api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "reject"})
    assert resp.status_code == 200 and resp.json()["status"] == "REJECTED"
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "REJECTED"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0
    assert not can_reach(app, fac, stu)
    assert "Class request rejected" in notification_titles(app, fac["user_id"])
    # after a rejection the faculty may ask again
    with app.app_context():
        assert assignment_service.faculty_request(fac["faculty_id"], sid, "second try")


@pytest.mark.parametrize("decision", ["APPROVE-ish", "", "approved", "APPROVE", None, 1, True])
def test_decision_other_than_approve_or_reject_is_a_validation_error(app, world, admin, decision):
    rid = _request(app, world["fac"]["FAC004"], world["sec"][AIML_3B])
    body = err(api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": decision}), 400,
               "validation_error")
    assert "decision" in body["fields"]
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "PENDING"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (world["fac"]["FAC004"]["faculty_id"],)) == 0


def test_decide_request_errors_over_http(app, world, admin):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    err(api_post(admin, "/api/admin/assignment-requests/99999/decide", json={"decision": "approve"}), 404, "not_found")
    err(api_post(admin, "/api/admin/assignment-requests/1/decide", json={}), 400, "validation_error")
    err(api_post(admin, "/api/admin/assignment-requests/1/decide", json={"decision": "approve", "x": 1}), 400)
    rid = _request(app, fac, sid)
    assert api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}).status_code == 200
    err(api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "reject"}), 409, "conflict")
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "APPROVED"  # 2nd call changed nothing


def test_duplicate_pending_and_already_assigned_requests_refused(app, world):
    fac4, fac1 = world["fac"]["FAC004"], world["fac"]["FAC001"]
    sid = world["sec"][AIML_3B]
    _request(app, fac4, sid)
    with app.app_context():
        with pytest.raises(AssignmentError, match="already have a pending request"):
            assignment_service.faculty_request(fac4["faculty_id"], sid)
        with pytest.raises(AssignmentError, match="already assigned"):
            assignment_service.faculty_request(fac1["faculty_id"], sid)
    assert db_count(app, "faculty_assignment_requests") == 1


@pytest.mark.parametrize("bad", ["", "abc", "99999", "-1", "0", "1 OR 1=1", None])
def test_request_with_forged_section_id_refused(app, world, bad):
    with app.app_context():
        with pytest.raises(AssignmentError):
            assignment_service.faculty_request(world["fac"]["FAC004"]["faculty_id"], bad)
    assert db_count(app, "faculty_assignment_requests") == 0


def test_request_for_inactive_class_refused(app, world):
    sid = world["sec"][AIML_3B]
    with app.app_context():
        academic_service.set_active("section", sid, False)
        with pytest.raises(AssignmentError):
            assignment_service.faculty_request(world["fac"]["FAC004"]["faculty_id"], sid)
    assert db_count(app, "faculty_assignment_requests") == 0


def test_note_is_trimmed_and_capped(app, world):
    with app.app_context():
        rid = assignment_service.faculty_request(world["fac"]["FAC004"]["faculty_id"], world["sec"][AIML_3B],
                                                 "  " + "x" * 900)
        assert len(aq.get_assignment_request(rid)["note"]) == 500
        rid2 = assignment_service.faculty_request(world["fac"]["FAC004"]["faculty_id"], world["sec"][AIML_3C], "   ")
        assert aq.get_assignment_request(rid2)["note"] is None


def test_request_notifies_every_admin(app, world):
    admin2 = create_admin(app, "admin2@college.edu", name="Admin Two")
    rid = _request(app, world["fac"]["FAC004"], world["sec"][AIML_3B])
    for admin_id in (world["admin"], admin2):
        notes = db_all(app, "SELECT * FROM notifications WHERE user_id = ? AND notification_type = 'ASSIGNMENT_REQUESTED'",
                       (admin_id,))
        assert len(notes) == 1 and notes[0]["related_entity_id"] == rid
        assert "FAC004" in notes[0]["message"]
    # faculty themselves are not spammed
    assert db_count(app, "notifications", "user_id = ?", (world["fac"]["FAC004"]["user_id"],)) == 0


def test_decide_request_guards_service(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
        with pytest.raises(AssignmentError, match="not found"):
            assignment_service.decide_request(99999, world["admin"], True)
        assert assignment_service.decide_request(rid, world["admin"], True) == "APPROVED"
        with pytest.raises(AssignmentError, match="already been reviewed"):
            assignment_service.decide_request(rid, world["admin"], False)
        assert aq.get_assignment_for(fac["faculty_id"], sid)["is_active"] == 1  # 2nd decision changed nothing


def test_cannot_approve_request_for_class_deactivated_meanwhile(app, world, admin):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    rid = _request(app, fac, sid)
    with app.app_context():
        academic_service.set_active("section", sid, False)
    pending = admin.get("/api/admin/assignment-requests").json()["items"][0]
    assert pending["class_active"] is False and pending["can_decide"] is True
    body = err(api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}), 400,
               "validation_error")
    assert "no longer active" in body["message"]
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "PENDING"
    # rejecting it is still possible
    assert api_post(admin, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "reject"}).status_code == 200


def test_approval_reactivates_a_previously_removed_assignment(app, world):
    fac, sid = world["fac"]["FAC001"], world["sec"][AIML_3B]
    unassign(app, fac, sid, world["admin"])
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
        assignment_service.decide_request(rid, world["admin"], True)
    assert can_reach(app, fac, world["stu"][AIML_3B])
    assert db_count(app, "faculty_assignments", "faculty_id = ? AND section_id = ?", (fac["faculty_id"], sid)) == 1


def test_assignment_request_listing_filters_and_counts(app, world, admin):
    fac4, fac1 = world["fac"]["FAC004"], world["fac"]["FAC001"]
    r1 = _request(app, fac4, world["sec"][AIML_3B], "note")
    r2 = _request(app, fac1, world["sec"][AIML_3C])
    api_post(admin, f"/api/admin/assignment-requests/{r2}/decide", json={"decision": "reject"})
    data = admin.get("/api/admin/assignment-requests").json()
    assert data["total"] == 2 and data["pending_count"] == 1
    assert [i["id"] for i in data["items"]] == [r1, r2]  # pending first
    assert [i["id"] for i in admin.get("/api/admin/assignment-requests?status=rejected").json()["items"]] == [r2]
    assert admin.get("/api/admin/assignment-requests?status=APPROVED").json()["items"] == []
    err(admin.get("/api/admin/assignment-requests?status=bogus"), 400, "validation_error")
    # the assignments console carries the pending ones per faculty
    rows = {r["faculty_code"]: r for r in admin.get("/api/admin/assignments").json()["items"]}
    assert [p["id"] for p in rows["FAC004"]["pending_requests"]] == [r1] and rows["FAC001"]["pending_requests"] == []
    assert admin.get("/api/admin/assignments").json()["pending_count"] == 1
    assert next(f for f in admin.get("/api/admin/faculty").json()["items"]
                if f["faculty_code"] == "FAC004")["pending_request_count"] == 1
    assert admin.get("/api/admin/dashboard").json()["stats"]["pending_assignment_count"] == 1


def test_only_admin_can_decide_requests_and_assign(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    rid = _request(app, fac, sid)
    for who in (fac["email"], world["stu"][AIML_3B]["email"], world["fac"]["FAC001"]["email"]):
        c = login_client(app, who)
        err(api_post(c, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}), 403, "forbidden")
        err(api_post(c, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": sid}), 403)
        err(api_delete(c, "/api/admin/assignments/1"), 403)
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "PENDING"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0
    assert db_count(app, "faculty_assignments", "is_active = 0") == 0


# ---------------------------------------------------------------------------
# admin assignment endpoints
# ---------------------------------------------------------------------------

def test_admin_assign_and_remove_via_api(app, world, admin):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    resp = api_post(admin, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": sid})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] and body["message"] == "Assigned to CSE → AIML → 3rd Year → B."
    row = db_one(app, "SELECT * FROM faculty_assignments WHERE faculty_id = ?", (fac["faculty_id"],))
    assert row["is_active"] == 1 and row["assigned_by"] == world["admin"]
    assert body["assignment"]["assignment_id"] == row["id"] and body["assignment"]["student_count"] == 1
    assert body["assignment"]["section_id"] == sid and body["assignment"]["can_remove"] is True
    assert can_reach(app, fac, world["stu"][AIML_3B])
    assert "New class assignment" in notification_titles(app, fac["user_id"])

    dup = err(api_post(admin, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": sid}),
              409, "conflict")
    assert "already assigned" in dup["message"]
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 1

    resp = api_delete(admin, f"/api/admin/assignments/{row['id']}")
    assert resp.status_code == 200 and resp.json()["assignment_id"] == row["id"]
    assert resp.json()["message"] == "Assignment removed: CSE → AIML → 3rd Year → B."
    assert not can_reach(app, fac, world["stu"][AIML_3B])
    assert "Class assignment removed" in notification_titles(app, fac["user_id"])
    err(api_delete(admin, f"/api/admin/assignments/{row['id']}"), 409, "already_inactive")
    err(api_delete(admin, "/api/admin/assignments/99999"), 404, "not_found")
    err(api_delete(admin, "/api/admin/assignments/abc"), 400, "validation_error")
    # assigning again re-activates the very same row
    again = api_post(admin, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": sid})
    assert again.status_code == 201 and again.json()["assignment"]["assignment_id"] == row["id"]
    assert can_reach(app, fac, world["stu"][AIML_3B])


@pytest.mark.parametrize("payload,status,code,field", [
    ({}, 400, "validation_error", "faculty_id"),
    ({"faculty_id": "x", "section_id": 1}, 400, "validation_error", "faculty_id"),
    ({"faculty_id": 1}, 400, "validation_error", "section_id"),
    ({"faculty_id": None, "section_id": 1}, 400, "validation_error", "faculty_id"),
    ({"faculty_id": 1, "section_id": "7"}, 400, "validation_error", "section_id"),
    ({"faculty_id": 1, "section_id": 0}, 400, "validation_error", "section_id"),
    ({"faculty_id": 99999, "section_id": 1}, 404, "not_found", None),
    ({"faculty_id": 1, "section_id": 99999}, 404, "not_found", None),
    ({"faculty_id": 1, "section_id": 1, "assigned_by": 5}, 400, "validation_error", "assigned_by"),
])
def test_admin_assign_with_forged_values_is_handled(app, world, admin, payload, status, code, field):
    before = db_count(app, "faculty_assignments")
    body = err(api_post(admin, "/api/admin/assignments", json=payload), status, code)
    if field:
        assert field in body["fields"]
    assert db_count(app, "faculty_assignments") == before


def test_admin_assign_to_inactive_class_is_refused_via_api(app, world, admin):
    sid = world["sec"][GENAI_1B]
    with app.app_context():
        academic_service.set_active("section", sid, False)
    before = db_count(app, "faculty_assignments")
    err(api_post(admin, "/api/admin/assignments", json={"faculty_id": world["fac"]["FAC004"]["faculty_id"],
                                                        "section_id": sid}), 404)
    assert db_count(app, "faculty_assignments") == before


def test_admin_class_directory_lists_all_assigned_faculty(app, world, admin):
    rows = {c["section_id"]: c for c in admin.get("/api/admin/classes").json()["items"]}
    assert [f["faculty_code"] for f in rows[world["sec"][AIML_3A]]["faculty"]] == ["FAC001", "FAC002"]
    assert [f["faculty_code"] for f in rows[world["sec"][AIDE_3A]]["faculty"]] == ["FAC003"]
    assert rows[world["sec"][AIML_3A]]["faculty_count"] == 2 and rows[world["sec"][AIML_3A]]["student_count"] == 1
    detail = admin.get(f"/api/admin/classes/{world['sec'][AIML_3A]}").json()
    assert [f["faculty_code"] for f in detail["faculty"]] == ["FAC001", "FAC002"]
    assert [s["usn"] for s in detail["students"]] == [world["stu"][AIML_3A]["usn"]]
    # removing an assignment updates the directory immediately
    unassign(app, world["fac"]["FAC001"], world["sec"][AIML_3A], world["admin"])
    detail = admin.get(f"/api/admin/classes/{world['sec'][AIML_3A]}").json()
    assert [f["faculty_code"] for f in detail["faculty"]] == ["FAC002"] and detail["class"]["faculty_count"] == 1


# ---------------------------------------------------------------------------
# removing an assignment revokes everything immediately, server-side
# ---------------------------------------------------------------------------

def test_removal_revokes_chat_meeting_and_search_even_for_existing_history(app, world, admin):
    fac, sid, stu = world["fac"]["FAC001"], world["sec"][AIML_3B], world["stu"][AIML_3B]

    # while assigned: everything works
    with app.app_context():
        chat = chat_service.open_chat_as_faculty(fac["faculty_id"], stu["student_id"], fac["user_id"])
        assert chat_service.get_chat_for_participant(chat["id"], fac["user_id"], "FACULTY")["id"] == chat["id"]
        assert chat_service.get_chat_for_participant(chat["id"], stu["user_id"], "STUDENT")["id"] == chat["id"]
        chat_service.send_text_message(chat["id"], stu["user_id"], "before")
        meeting_id = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "before", "")
        assert [r["usn"] for r in aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS")] != []
        assert aq.is_faculty_assigned_to_section(fac["faculty_id"], sid)

    unassign(app, fac, sid, world["admin"])  # <- admin removes FAC001 from AIML 3rd B

    with app.app_context():
        # faculty side: every door is shut
        assert not aq.is_faculty_assigned_to_section(fac["faculty_id"], sid)
        assert stu["usn"] not in {r["usn"] for r in aq.search_students_in_faculty_scope(fac["faculty_id"], "1AB21CS")}
        with pytest.raises(chat_service.ChatAccessError, match="no longer"):
            chat_service.get_chat_for_participant(chat["id"], fac["user_id"], "FACULTY")
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(fac["faculty_id"], stu["student_id"], fac["user_id"])
        with pytest.raises(meeting_service.MeetingError, match="no longer"):
            meeting_service.respond_to_meeting(meeting_id, fac["faculty_id"], True, "ok", "now")
        from services import supporting_service
        with pytest.raises(supporting_service.SupportingError):
            supporting_service.faculty_request_student(fac["faculty_id"], stu["student_id"])
        # student side: the old conversation is closed and no new one / meeting can be opened
        with pytest.raises(chat_service.ChatAccessError, match="no longer"):
            chat_service.get_chat_for_participant(chat["id"], stu["user_id"], "STUDENT")
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(stu["student_id"], fac["faculty_id"], stu["user_id"])
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "after", "")
    assert db_one(app, "SELECT status FROM meeting_requests WHERE id = ?", (meeting_id,))["status"] == "PENDING"
    assert db_count(app, "supporting_relationships") == 0

    # history is kept, and the admin can still read it
    assert db_count(app, "messages") == 1
    assert admin.get(f"/api/admin/chats/{chat['id']}").status_code == 200

    # FAC001's other classes and FAC002's access are unaffected
    assert can_reach(app, fac, world["stu"][AIML_3A])
    with app.app_context():
        assert aq.is_faculty_assigned_to_section(fac["faculty_id"], world["sec"][AIML_3A])


def test_removed_assignment_does_not_revoke_an_accepted_supporting_relationship(app, world):
    from services import supporting_service
    fac, sid, stu = world["fac"]["FAC001"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    with app.app_context():
        rel = supporting_service.faculty_request_student(fac["faculty_id"], stu["student_id"])
        supporting_service.respond_to_request(rel, stu["user_id"], "STUDENT", True)
    unassign(app, fac, sid, world["admin"])
    assert can_reach(app, fac, stu)  # the student agreed to support -> independent of class assignment
    with app.app_context():
        chat = chat_service.open_chat_as_faculty(fac["faculty_id"], stu["student_id"], fac["user_id"])
        assert chat["id"]
        assert not aq.is_faculty_assigned_to_section(fac["faculty_id"], sid)  # ...but the class itself stays closed


def test_pending_supporting_relationship_grants_nothing(app, world):
    from services import supporting_service
    fac4, stu = world["fac"]["FAC004"], world["stu"][AIML_3B]
    with app.app_context():
        supporting_service.student_request_faculty(stu["student_id"], fac4["faculty_id"])
    assert not can_reach(app, fac4, stu)


def test_rejected_supporting_relationship_grants_nothing(app, world):
    from services import supporting_service
    fac4, stu = world["fac"]["FAC004"], world["stu"][AIML_3B]
    with app.app_context():
        rel = supporting_service.student_request_faculty(stu["student_id"], fac4["faculty_id"])
        supporting_service.respond_to_request(rel, fac4["user_id"], "FACULTY", False)
    assert not can_reach(app, fac4, stu)


def test_profile_change_routing_follows_assignments(app, world):
    """A request from a student in AIML 3rd A reaches FAC001 and FAC002 but never FAC003/FAC004."""
    stu = world["stu"][AIML_3A]
    with app.app_context():
        rid = permission_service.student_request_profile_change(stu["user_id"], {"personal_email": "new@example.com"})
    pend = {code: [r["id"] for r in queries_pending(app, f["user_id"])] for code, f in world["fac"].items()}
    assert pend == {"FAC001": [rid], "FAC002": [rid], "FAC003": [], "FAC004": []}
    # forged decision by an unrelated faculty is refused
    with app.app_context():
        with pytest.raises(permission_service.PermissionError_, match="not authorized"):
            permission_service.decide_permission_request(rid, world["fac"]["FAC003"]["user_id"], True)
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    # after FAC001 is removed from the class it can no longer decide either; FAC002 still can
    unassign(app, world["fac"]["FAC001"], world["sec"][AIML_3A], world["admin"])
    with app.app_context():
        with pytest.raises(permission_service.PermissionError_, match="not authorized"):
            permission_service.decide_permission_request(rid, world["fac"]["FAC001"]["user_id"], True)
        assert permission_service.decide_permission_request(rid, world["fac"]["FAC002"]["user_id"], True) == "APPROVED"
    assert db_one(app, "SELECT personal_email FROM students WHERE id = ?", (stu["student_id"],))[
        "personal_email"] == "new@example.com"


def test_admin_cannot_decide_a_student_profile_request_it_is_not_routed_to(app, world, admin):
    """Student requests belong to the class faculty; the admin endpoint refuses them (403) and flags them."""
    stu = world["stu"][AIML_3A]
    with app.app_context():
        rid = permission_service.student_request_profile_change(stu["user_id"], {"phone": "7000000000"})
    item = admin.get("/api/admin/permission-requests").json()["items"][0]
    assert item["id"] == rid and item["can_decide"] is False
    err(api_post(admin, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "approve"}), 403, "forbidden")
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"


def test_student_profile_change_without_assigned_faculty_cannot_be_routed(app):
    create_admin(app)
    stu = create_student(app, "1AB21CS555")
    with app.app_context():
        with pytest.raises(permission_service.PermissionError_, match="No faculty is assigned"):
            permission_service.student_request_profile_change(stu["user_id"], {"phone": "8888888888"})
    assert db_count(app, "permission_requests") == 0


def test_migrating_from_class_faculty_column_is_not_used_for_access(app, world):
    """The legacy students.class_faculty_id column must never grant access on its own."""
    fac4, stu = world["fac"]["FAC004"], world["stu"][AIML_3B]
    with app.app_context():
        queries.set_student_class_faculty(stu["student_id"], fac4["faculty_id"])
    assert not can_reach(app, fac4, stu)
