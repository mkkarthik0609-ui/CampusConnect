"""Faculty <-> class assignments: admin assign/remove, faculty requests, multi-faculty sections and
the access rules that hang off them (chat, meetings, class view, search, profile-change approval)."""
import itertools

import pytest

from models import academic_queries as aq
from models import queries
from services import academic_service, assignment_service, chat_service, meeting_service
from services.assignment_service import AssignmentError
from tests.conftest import (
    create_admin, create_faculty, create_student, section_id_for, assign, unassign, login_client,
    flashes, flash_text, db_one, db_all, db_count, db_exec,
)

AIML_3A = ("AIML", "3rd Year", "A")
AIML_3B = ("AIML", "3rd Year", "B")
AIML_3C = ("AIML", "3rd Year", "C")
AIDE_2A = ("AIDE", "2nd Year", "A")
AIDE_3A = ("AIDE", "3rd Year", "A")
GENAI_1B = ("GenAI", "1st Year", "B")


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


def can_reach(app, fac, stu):
    with app.app_context():
        a = queries.is_faculty_accessible_to_student(stu["student_id"], fac["faculty_id"])
        b = queries.is_student_accessible_to_faculty(fac["faculty_id"], stu["student_id"])
        c = assignment_service.faculty_can_access_student(fac["faculty_id"], stu["student_id"])
        d = assignment_service.student_can_access_faculty(stu["student_id"], fac["faculty_id"])
        assert a == b == c == d, "all access helpers must agree"
        return a


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
        assert aq.search_students_in_faculty_scope(fac003["faculty_id"], "1AB21CS") != []
        found = {r["usn"] for r in aq.search_students_in_faculty_scope(fac003["faculty_id"], "1AB21CS")}
        assert aiml_3a_student["usn"] not in found
    # same over HTTP with a forged student id
    c = login_client(app, fac003["email"])
    c.get(f"/chat/open-student/{aiml_3a_student['student_id']}")
    assert db_count(app, "chats") == 0
    assert c.get(f"/faculty/classes/{world['sec'][AIML_3A]}").status_code == 403


def test_faculty_assignments_listing(app, world):
    with app.app_context():
        got = {code: sorted((c["department_name"], c["year_name"], c["section_name"])
                            for c in aq.list_assignments_for_faculty(f["faculty_id"]))
               for code, f in world["fac"].items()}
    assert got == {code: sorted(combos) for code, combos in EXPECTED.items()}


def test_list_faculty_for_section_and_assigned_faculty_for_student(app, world):
    with app.app_context():
        codes = [r["faculty_code"] for r in aq.list_faculty_for_section(world["sec"][AIML_3A])]
        assert codes == ["FAC001", "FAC002"]
        assert [r["faculty_code"] for r in aq.list_faculty_for_section(world["sec"][AIML_3C])] == ["FAC003"]
        assigned = aq.list_assigned_faculty_for_student(world["stu"][AIML_3A]["student_id"])
        assert sorted(r["faculty_code"] for r in assigned) == ["FAC001", "FAC002"]
        assert aq.list_assigned_faculty_for_student(world["stu"][AIDE_3A]["student_id"])[0]["faculty_code"] == "FAC003"


def test_student_dashboard_and_faculty_dashboard_show_assignments(app, world):
    c = login_client(app, world["fac"]["FAC001"]["email"])
    resp = c.get("/faculty/dashboard")
    assert resp.status_code == 200
    assert c.get("/faculty/classes").status_code == 200
    s = login_client(app, world["stu"][AIML_3A]["email"])
    page = s.get("/student/dashboard").data
    assert b"Prof FAC001" in page and b"Prof FAC002" in page and b"Prof FAC003" not in page


# ---------------------------------------------------------------------------
# admin_assign / admin_remove
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


def test_deactivating_the_class_chain_suspends_access_and_reactivating_restores_it(app, world):
    fac, stu = world["fac"]["FAC001"], world["stu"][AIML_3A]
    with app.app_context():
        dept_id = aq.get_combo(world["sec"][AIML_3A])["department_id"]
        academic_service.set_active("department", dept_id, False)
    assert not can_reach(app, fac, stu)
    c = login_client(app, fac["email"])
    assert c.get(f"/faculty/classes/{world['sec'][AIML_3A]}").status_code == 403
    with app.app_context():
        assert aq.search_students_in_faculty_scope(fac["faculty_id"], stu["usn"]) == []
        assert not aq.is_faculty_assigned_to_section(fac["faculty_id"], world["sec"][AIML_3A])
        # AIDE 2nd A is in a different department and still works
        assert aq.is_faculty_assigned_to_section(fac["faculty_id"], world["sec"][AIDE_2A])
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


def test_five_faculty_all_open_class_view_and_see_each_other(app, crowded):
    for f in crowded["facs"]:
        c = login_client(app, f["email"])
        resp = c.get(f"/faculty/classes/{crowded['sid']}")
        assert resp.status_code == 200
        body = resp.data.decode()
        for other in crowded["facs"]:
            assert other["code"] in body
        for s in crowded["studs"]:
            assert s["usn"] in body
        # search is scoped the same way
        found = c.get("/supporting/student/search?q=1AB21MS").data.decode()
        assert all(s["usn"] in found for s in crowded["studs"])


def test_student_request_is_routed_to_all_five_and_any_one_can_approve(app, crowded):
    student = crowded["studs"][0]
    sc = login_client(app, student["email"])
    sc.post("/student/profile/change-request", data={"phone": "7777777777", "reason": "new number"})
    assert db_count(app, "permission_requests") == 1
    for f in crowded["facs"]:
        titles = [n["title"] for n in db_all(app, "SELECT * FROM notifications WHERE user_id = ?", (f["user_id"],))]
        assert "Student profile change request" in titles
        c = login_client(app, f["email"])
        assert len(queries_pending(app, f["user_id"])) == 1
    # the 4th faculty approves
    c = login_client(app, crowded["facs"][3]["email"])
    rid = db_one(app, "SELECT id FROM permission_requests")["id"]
    assert c.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"}).status_code == 302
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "APPROVED"
    assert db_one(app, "SELECT phone FROM students WHERE id = ?", (student["student_id"],))["phone"] == "7777777777"
    # it is no longer pending for the others, and they cannot decide it again
    assert queries_pending(app, crowded["facs"][0]["user_id"]) == []
    c0 = login_client(app, crowded["facs"][0]["email"])
    c0.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "reject"})
    assert "already been reviewed" in flash_text(c0)


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
# faculty request -> admin decision
# ---------------------------------------------------------------------------

def test_no_access_before_approval_and_full_access_after(app, world):
    fac, sid, stu = world["fac"]["FAC004"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    c = login_client(app, fac["email"])
    resp = c.post("/faculty/classes/request", data={"section_id": str(sid), "note": "I teach DSA to 3B"})
    assert resp.status_code == 302 and "sent to Admin" in flash_text(c)
    req = db_one(app, "SELECT * FROM faculty_assignment_requests")
    assert (req["status"], req["section_id"], req["faculty_id"], req["note"]) == (
        "PENDING", sid, fac["faculty_id"], "I teach DSA to 3B")

    # a pending request grants NOTHING
    assert not can_reach(app, fac, stu)
    assert c.get(f"/faculty/classes/{sid}").status_code == 403
    assert "1AB21CS002" not in c.get("/supporting/student/search?q=1AB21CS").data.decode()
    c.get(f"/chat/open-student/{stu['student_id']}")
    assert db_count(app, "chats") == 0
    sc = login_client(app, stu["email"])
    sc.get(f"/chat/open/{fac['faculty_id']}")
    sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "hi"})
    assert db_count(app, "chats") == 0 and db_count(app, "meeting_requests") == 0
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0

    # admin approves
    admin = login_client(app, "admin@college.edu")
    resp = admin.post(f"/admin/assignment-requests/{req['id']}/decide", data={"decision": "approve"})
    assert resp.status_code == 302 and "approved" in flash_text(admin)
    done = db_one(app, "SELECT * FROM faculty_assignment_requests WHERE id = ?", (req["id"],))
    assert done["status"] == "APPROVED" and done["reviewed_by"] == world["admin"] and done["reviewed_at"]

    assert can_reach(app, fac, stu)
    assert c.get(f"/faculty/classes/{sid}").status_code == 200
    assert stu["usn"] in c.get("/supporting/student/search?q=1AB21CS").data.decode()
    c.get(f"/chat/open-student/{stu['student_id']}")
    assert db_count(app, "chats") == 1
    sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "hi"})
    assert db_count(app, "meeting_requests") == 1
    # the faculty was told
    assert "Class request approved" in [n["title"] for n in db_all(
        app, "SELECT title FROM notifications WHERE user_id = ?", (fac["user_id"],))]


def test_rejected_request_leaves_no_access(app, world):
    fac, sid, stu = world["fac"]["FAC004"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid, None)
    admin = login_client(app, "admin@college.edu")
    admin.post(f"/admin/assignment-requests/{rid}/decide", data={"decision": "reject"})
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "REJECTED"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0
    assert not can_reach(app, fac, stu)
    assert login_client(app, fac["email"]).get(f"/faculty/classes/{sid}").status_code == 403
    assert "Class request rejected" in [n["title"] for n in db_all(
        app, "SELECT title FROM notifications WHERE user_id = ?", (fac["user_id"],))]
    # after a rejection the faculty may ask again
    with app.app_context():
        assert assignment_service.faculty_request(fac["faculty_id"], sid, "second try")


def test_decision_other_than_approve_is_a_rejection(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
    admin = login_client(app, "admin@college.edu")
    admin.post(f"/admin/assignment-requests/{rid}/decide", data={"decision": "APPROVE-ish"})
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "REJECTED"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0


def test_duplicate_pending_and_already_assigned_requests_refused(app, world):
    fac4, fac1 = world["fac"]["FAC004"], world["fac"]["FAC001"]
    sid = world["sec"][AIML_3B]
    c = login_client(app, fac4["email"])
    c.post("/faculty/classes/request", data={"section_id": str(sid)})
    flashes(c)
    c.post("/faculty/classes/request", data={"section_id": str(sid)})
    assert "already have a pending request" in flash_text(c)
    assert db_count(app, "faculty_assignment_requests") == 1

    c1 = login_client(app, fac1["email"])
    c1.post("/faculty/classes/request", data={"section_id": str(sid)})
    assert "already assigned" in flash_text(c1)
    assert db_count(app, "faculty_assignment_requests") == 1


@pytest.mark.parametrize("bad", ["", "abc", "99999", "-1", "0", "1 OR 1=1"])
def test_request_with_forged_section_id_refused(app, world, bad):
    c = login_client(app, world["fac"]["FAC004"]["email"])
    resp = c.post("/faculty/classes/request", data={"section_id": bad})
    assert resp.status_code == 302
    assert flashes(c)[0][0] == "error"
    assert db_count(app, "faculty_assignment_requests") == 0


def test_request_for_inactive_class_refused(app, world):
    sid = world["sec"][AIML_3B]
    with app.app_context():
        academic_service.set_active("section", sid, False)
    c = login_client(app, world["fac"]["FAC004"]["email"])
    c.post("/faculty/classes/request", data={"section_id": str(sid)})
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
    with app.app_context():
        rid = assignment_service.faculty_request(world["fac"]["FAC004"]["faculty_id"], world["sec"][AIML_3B])
    for admin_id in (world["admin"], admin2):
        notes = db_all(app, "SELECT * FROM notifications WHERE user_id = ? AND notification_type = 'ASSIGNMENT_REQUESTED'",
                       (admin_id,))
        assert len(notes) == 1 and notes[0]["related_entity_id"] == rid
        assert "FAC004" in notes[0]["message"]
    # faculty themselves are not spammed
    assert db_count(app, "notifications", "user_id = ?", (world["fac"]["FAC004"]["user_id"],)) == 0


def test_decide_request_guards(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
        with pytest.raises(AssignmentError, match="not found"):
            assignment_service.decide_request(99999, world["admin"], True)
        assert assignment_service.decide_request(rid, world["admin"], True) == "APPROVED"
        with pytest.raises(AssignmentError, match="already been reviewed"):
            assignment_service.decide_request(rid, world["admin"], False)
        assert aq.get_assignment_for(fac["faculty_id"], sid)["is_active"] == 1  # 2nd decision changed nothing


def test_cannot_approve_request_for_class_deactivated_meanwhile(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
        academic_service.set_active("section", sid, False)
        with pytest.raises(AssignmentError, match="no longer active"):
            assignment_service.decide_request(rid, world["admin"], True)
        assert aq.get_assignment_request(rid)["status"] == "PENDING"
        # rejecting it is still possible
        assert assignment_service.decide_request(rid, world["admin"], False) == "REJECTED"


def test_approval_reactivates_a_previously_removed_assignment(app, world):
    fac, sid = world["fac"]["FAC001"], world["sec"][AIML_3B]
    unassign(app, fac, sid, world["admin"])
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
        assignment_service.decide_request(rid, world["admin"], True)
    assert can_reach(app, fac, world["stu"][AIML_3B])
    assert db_count(app, "faculty_assignments", "faculty_id = ? AND section_id = ?", (fac["faculty_id"], sid)) == 1


def test_request_pages_render_and_list_entries(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        assignment_service.faculty_request(fac["faculty_id"], sid, "note")
    c = login_client(app, fac["email"])
    assert c.get("/faculty/classes").status_code == 200
    assert c.get("/faculty/dashboard").status_code == 200
    admin = login_client(app, "admin@college.edu")
    assert admin.get("/admin/assignment-requests").status_code == 200
    assert admin.get("/admin/assignments").status_code == 200
    with app.app_context():
        assert aq.count_pending_assignment_requests() == 1
        assert len(aq.list_assignment_requests(status="PENDING")) == 1
        assert aq.list_assignment_requests(status="APPROVED") == []
        assert len(aq.list_assignment_requests(faculty_id=fac["faculty_id"])) == 1
        assert aq.list_assignment_requests(faculty_id=world["fac"]["FAC001"]["faculty_id"]) == []


def test_only_admin_can_decide_requests_and_assign(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    with app.app_context():
        rid = assignment_service.faculty_request(fac["faculty_id"], sid)
    for who in (fac["email"], world["stu"][AIML_3B]["email"], world["fac"]["FAC001"]["email"]):
        c = login_client(app, who)
        assert c.post(f"/admin/assignment-requests/{rid}/decide", data={"decision": "approve"}).status_code == 403
        assert c.post("/admin/assignments/assign", data={"faculty_id": fac["faculty_id"],
                                                        "section_id": sid}).status_code == 403
    assert db_one(app, "SELECT status FROM faculty_assignment_requests")["status"] == "PENDING"
    assert db_count(app, "faculty_assignments", "faculty_id = ?", (fac["faculty_id"],)) == 0


def test_students_cannot_use_the_faculty_request_route(app, world):
    c = login_client(app, world["stu"][AIML_3A]["email"])
    assert c.post("/faculty/classes/request", data={"section_id": str(world["sec"][AIML_3B])}).status_code == 403
    assert db_count(app, "faculty_assignment_requests") == 0


# ---------------------------------------------------------------------------
# admin assignment routes
# ---------------------------------------------------------------------------

def test_admin_assign_and_remove_via_http(app, world):
    fac, sid = world["fac"]["FAC004"], world["sec"][AIML_3B]
    admin = login_client(app, "admin@college.edu")
    resp = admin.post("/admin/assignments/assign", data={"faculty_id": fac["faculty_id"], "section_id": sid})
    assert resp.status_code == 302 and "Assigned to" in flash_text(admin)
    row = db_one(app, "SELECT * FROM faculty_assignments WHERE faculty_id = ?", (fac["faculty_id"],))
    assert row["is_active"] == 1
    assert can_reach(app, fac, world["stu"][AIML_3B])

    admin.post("/admin/assignments/assign", data={"faculty_id": fac["faculty_id"], "section_id": sid})
    assert "already assigned" in flash_text(admin)

    admin.post(f"/admin/assignments/{row['id']}/remove")
    assert "Assignment removed" in flash_text(admin)
    assert not can_reach(app, fac, world["stu"][AIML_3B])
    admin.post(f"/admin/assignments/{row['id']}/remove")
    assert "already inactive" in flash_text(admin)
    admin.post("/admin/assignments/99999/remove")
    assert flashes(admin)[0][0] == "error"


@pytest.mark.parametrize("data", [{}, {"faculty_id": "x", "section_id": "1"}, {"faculty_id": "99999", "section_id": "1"},
                                  {"faculty_id": "1", "section_id": "99999"}, {"faculty_id": "1"}])
def test_admin_assign_with_forged_form_values_is_handled(app, world, data):
    admin = login_client(app, "admin@college.edu")
    before = db_count(app, "faculty_assignments")
    resp = admin.post("/admin/assignments/assign", data=data)
    assert resp.status_code == 302
    assert flashes(admin)[0][0] == "error"
    assert db_count(app, "faculty_assignments") == before


def test_admin_class_directory_lists_all_assigned_faculty(app, world):
    admin = login_client(app, "admin@college.edu")
    page = admin.get("/admin/classes").data.decode()
    assert "FAC001" in page and "FAC002" in page and "FAC003" in page
    detail = admin.get(f"/admin/classes/{world['sec'][AIML_3A]}").data.decode()
    assert "FAC001" in detail and "FAC002" in detail and "FAC003" not in detail
    assert world["stu"][AIML_3A]["usn"] in detail


# ---------------------------------------------------------------------------
# removing an assignment revokes everything immediately, server-side
# ---------------------------------------------------------------------------

def test_removal_revokes_chat_meeting_class_view_and_search_even_with_forged_ids(app, world):
    fac, sid, stu = world["fac"]["FAC001"], world["sec"][AIML_3B], world["stu"][AIML_3B]
    fc, sc = login_client(app, fac["email"]), login_client(app, stu["email"])

    # while assigned: everything works
    fc.get(f"/chat/open-student/{stu['student_id']}")
    chat = db_one(app, "SELECT * FROM chats")
    assert fc.get(f"/chat/{chat['id']}").status_code == 200
    sc.post(f"/chat/{chat['id']}/message", data={"message_text": "before"})
    sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "before"})
    meeting = db_one(app, "SELECT * FROM meeting_requests")
    assert fc.get(f"/faculty/classes/{sid}").status_code == 200
    assert stu["usn"] in fc.get("/supporting/student/search?q=1AB21CS").data.decode()

    unassign(app, fac, sid, world["admin"])  # <- admin removes FAC001 from AIML 3rd B

    # faculty side: every door is shut
    assert fc.get(f"/faculty/classes/{sid}").status_code == 403
    assert stu["usn"] not in fc.get("/supporting/student/search?q=1AB21CS").data.decode()
    resp = fc.get(f"/chat/{chat['id']}")
    assert resp.status_code == 302  # redirected away with an error, no page
    assert "no longer" in flash_text(fc)
    fc.post(f"/chat/{chat['id']}/message", data={"message_text": "sneaky"})
    assert db_count(app, "messages", "message_text = 'sneaky'") == 0
    fc.post(f"/meetings/{meeting['id']}/respond", data={"decision": "accept", "meeting_time_text": "now"})
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"
    fc.post(f"/supporting/student/{stu['student_id']}/request")
    assert db_count(app, "supporting_relationships") == 0
    fc.get(f"/chat/open-student/{stu['student_id']}")
    # student side: cannot open new conversations / meetings with the removed faculty
    before = db_count(app, "meeting_requests")
    sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "after"})
    assert db_count(app, "meeting_requests") == before
    sc.get(f"/chat/open/{fac['faculty_id']}")
    assert sc.get(f"/chat/{chat['id']}").status_code == 302  # the student's old conversation is closed too
    sc.post(f"/chat/{chat['id']}/message", data={"message_text": "still there?"})
    assert db_count(app, "messages", "message_text = 'still there?'") == 0
    # history is kept for the admin
    assert db_count(app, "messages") == 1
    admin = login_client(app, "admin@college.edu")
    assert admin.get(f"/admin/chats/{chat['id']}").status_code == 200

    # FAC001's other classes and FAC002's access are unaffected
    assert can_reach(app, fac, world["stu"][AIML_3A])
    assert fc.get(f"/faculty/classes/{world['sec'][AIML_3A]}").status_code == 200


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
    # ...but the class itself stays closed
    assert login_client(app, fac["email"]).get(f"/faculty/classes/{sid}").status_code == 403


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
    sc = login_client(app, stu["email"])
    sc.post("/student/profile/change-request", data={"personal_email": "new@example.com"})
    rid = db_one(app, "SELECT id FROM permission_requests")["id"]
    pend = {code: [r["id"] for r in queries_pending(app, f["user_id"])] for code, f in world["fac"].items()}
    assert pend == {"FAC001": [rid], "FAC002": [rid], "FAC003": [], "FAC004": []}
    # forged decision by an unrelated faculty is refused
    c3 = login_client(app, world["fac"]["FAC003"]["email"])
    c3.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"})
    assert "not authorized" in flash_text(c3)
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    # after FAC001 is removed from the class it can no longer decide either; FAC002 still can
    unassign(app, world["fac"]["FAC001"], world["sec"][AIML_3A], world["admin"])
    c1 = login_client(app, world["fac"]["FAC001"]["email"])
    c1.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"})
    assert "not authorized" in flash_text(c1)
    c2 = login_client(app, world["fac"]["FAC002"]["email"])
    c2.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"})
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "APPROVED"
    assert db_one(app, "SELECT personal_email FROM students WHERE id = ?", (stu["student_id"],))[
        "personal_email"] == "new@example.com"


def test_student_profile_change_without_assigned_faculty_cannot_be_routed(app):
    create_admin(app)
    stu = create_student(app, "1AB21CS555")
    c = login_client(app, stu["email"])
    c.post("/student/profile/change-request", data={"phone": "8888888888"})
    assert "No faculty is assigned" in flash_text(c)
    assert db_count(app, "permission_requests") == 0


def test_migrating_from_class_faculty_column_is_not_used_for_access(app, world):
    """The legacy students.class_faculty_id column must never grant access on its own."""
    fac4, stu = world["fac"]["FAC004"], world["stu"][AIML_3B]
    with app.app_context():
        queries.set_student_class_faculty(stu["student_id"], fac4["faculty_id"])
    assert not can_reach(app, fac4, stu)
