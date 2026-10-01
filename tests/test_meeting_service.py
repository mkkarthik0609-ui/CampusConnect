"""Meetings: service rules (transitions, ownership, reminders) and the /api/meetings endpoints."""
import pytest

from models import queries
from services import meeting_service
from tests.conftest import (
    api_post, assign, create_admin, create_faculty, create_student, db_count, db_one, login_client,
    section_id_for, unassign,
)


def _create_student_and_faculty(app):
    """Faculty F1 is assigned to the student's section (AIML 3rd A) by an admin."""
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F1")
    stu = create_student(app, "1AB21CS001", sec)
    assign(app, fac, sec, admin_id)
    return stu["student_id"], fac["faculty_id"], stu["user_id"], fac["user_id"]


# ---------------------------------------------------------------------------
# service level
# ---------------------------------------------------------------------------

def test_request_meeting_requires_reason(app):
    student_id, faculty_id, _, _ = _create_student_and_faculty(app)
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, faculty_id, "", "")


def test_request_meeting_requires_access(app):
    student_id, _, _, _ = _create_student_and_faculty(app)
    stranger = create_faculty(app, "F9")  # never assigned to the student's class
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, stranger["faculty_id"], "Doubt", "")


def test_meeting_status_transitions(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        meeting_id = meeting_service.request_meeting(student_id, faculty_id, "Doubt", "")
        assert queries.get_meeting_by_id(meeting_id)["status"] == "PENDING"

        with pytest.raises(meeting_service.MeetingError):  # accepting without timing must fail
            meeting_service.respond_to_meeting(meeting_id, faculty_id, True, "ok", "")

        meeting_service.respond_to_meeting(meeting_id, faculty_id, True, "Come by", "Tomorrow 3PM")
        meeting = queries.get_meeting_by_id(meeting_id)
        assert meeting["status"] == "ACCEPTED" and meeting["meeting_time_text"] == "Tomorrow 3PM"

        with pytest.raises(meeting_service.MeetingError):  # student cancel without reason must fail
            meeting_service.cancel_meeting(meeting_id, stu_user, "STUDENT", "")

        meeting_service.complete_meeting(meeting_id, stu_user, "STUDENT")
        assert queries.get_meeting_by_id(meeting_id)["status"] == "COMPLETED"

        with pytest.raises(meeting_service.MeetingError):  # cannot cancel a completed meeting
            meeting_service.cancel_meeting(meeting_id, stu_user, "STUDENT", "changed my mind")


def test_unauthorized_faculty_cannot_respond(app):
    student_id, faculty_id, _, _ = _create_student_and_faculty(app)
    other = create_faculty(app, "F2")
    with app.app_context():
        meeting_id = meeting_service.request_meeting(student_id, faculty_id, "Doubt", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(meeting_id, other["faculty_id"], True, "hi", "now")


def test_reject_and_faculty_cancel_and_complete(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m1 = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        assert meeting_service.respond_to_meeting(m1, faculty_id, False, "busy") == "REJECTED"
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(m1, faculty_id, True, "x", "now")  # already responded

        m2 = meeting_service.request_meeting(student_id, faculty_id, "B", "")
        meeting_service.cancel_meeting(m2, fac_user, "FACULTY", "")  # faculty need not give reason
        assert queries.get_meeting_by_id(m2)["status"] == "CANCELLED"

        m3 = meeting_service.request_meeting(student_id, faculty_id, "C", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(m3, fac_user, "FACULTY")  # only accepted can complete
        meeting_service.respond_to_meeting(m3, faculty_id, True, "ok", "Mon 10am")
        meeting_service.complete_meeting(m3, fac_user, "FACULTY")
        assert queries.get_meeting_by_id(m3)["completed_by"] == "FACULTY"
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(9999, fac_user, "FACULTY")


def test_other_student_cannot_cancel_or_complete(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    intruder = create_student(app, "1AB21CS777", section_id_for(app, "AIML", "3rd Year", "A"))
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.cancel_meeting(m, intruder["user_id"], "STUDENT", "because")
        meeting_service.respond_to_meeting(m, faculty_id, True, "ok", "now")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(m, intruder["user_id"], "STUDENT")
        with pytest.raises(meeting_service.MeetingError):  # an admin (or any other role) is not a party either
            meeting_service.cancel_meeting(m, 1, "ADMIN", "x")


def test_faculty_cannot_respond_after_assignment_removed(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
    unassign(app, {"faculty_id": faculty_id}, section_id_for(app, "AIML", "3rd Year", "A"), 1)
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(m, faculty_id, True, "ok", "now")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, faculty_id, "New", "")


def test_send_due_reminders(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        before = queries.get_unread_notification_count(stu_user)
    meeting_service.send_due_reminders(app)
    with app.app_context():
        assert queries.get_unread_notification_count(stu_user) == before + 1
        assert queries.get_meeting_by_id(m)["last_reminder_at"]
    meeting_service.send_due_reminders(app)  # interval not elapsed -> no duplicate reminder
    with app.app_context():
        assert queries.get_unread_notification_count(stu_user) == before + 1


# ---------------------------------------------------------------------------
# HTTP: /api/meetings
# ---------------------------------------------------------------------------

@pytest.fixture
def pair(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    stu = db_one(app, "SELECT email FROM users WHERE id = ?", (stu_user,))
    fac = db_one(app, "SELECT email FROM users WHERE id = ?", (fac_user,))
    return {"sc": login_client(app, stu["email"]), "fc": login_client(app, fac["email"]),
            "student_id": student_id, "faculty_id": faculty_id, "stu_user": stu_user, "fac_user": fac_user,
            "sec": section_id_for(app, "AIML", "3rd Year", "A")}


def _request(pair, reason="Doubt in DSA", details="Trees"):
    r = api_post(pair["sc"], "/api/meetings",
                 json={"faculty_id": pair["faculty_id"], "reason": reason, "details": details})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_meeting_flow_over_http(app, pair):
    sc, fc = pair["sc"], pair["fc"]
    body = _request(pair)
    mid = body["id"]
    m = body["meeting"]
    assert m["status"] == "PENDING" and m["reason"] == "Doubt in DSA" and m["student_message"] == "Trees"
    assert m["faculty"]["faculty_code"] == "F1" and m["student"]["usn"] == "1AB21CS001"
    assert m["counterpart"]["role"] == "FACULTY" and m["counterpart_code"] == "F1"
    assert (m["can_respond"], m["can_cancel"], m["can_complete"]) == (False, True, False)

    fm = fc.get("/api/meetings").json()["items"][0]
    assert fm["id"] == mid and fm["counterpart"]["role"] == "STUDENT" and fm["counterpart_code"] == "1AB21CS001"
    assert (fm["can_respond"], fm["can_cancel"], fm["can_complete"]) == (True, True, False)
    assert fm["student"]["class"]["label"].endswith("AIML → 3rd Year → A")

    # accepting needs a time
    r = api_post(fc, f"/api/meetings/{mid}/respond", json={"decision": "accept", "faculty_response": "ok"})
    assert r.status_code == 400 and "meeting_time_text" in r.json()["error"]["fields"]
    r = api_post(fc, f"/api/meetings/{mid}/respond",
                 json={"decision": "accept", "faculty_response": "Come", "meeting_time_text": "Mon 10am"})
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    assert r.json()["meeting"]["meeting_time_text"] == "Mon 10am" and r.json()["meeting"]["can_complete"] is True
    assert api_post(fc, f"/api/meetings/{mid}/respond",
                    json={"decision": "reject"}).status_code == 409  # already answered

    assert sc.get(f"/api/meetings/{mid}").json()["meeting"]["status"] == "ACCEPTED"
    r = api_post(sc, f"/api/meetings/{mid}/complete")
    assert r.status_code == 200 and r.json()["meeting"]["completed_by"] == "STUDENT"
    assert api_post(sc, f"/api/meetings/{mid}/cancel", json={"reason": "late"}).status_code == 400


def test_request_validation_and_access(app, pair):
    sc = pair["sc"]
    for body in ({"faculty_id": pair["faculty_id"], "reason": "  "}, {"faculty_id": pair["faculty_id"]},
                 {"reason": "x"}, {"faculty_id": "abc", "reason": "x"},
                 {"faculty_id": pair["faculty_id"], "reason": "x", "student_id": 1},
                 {"faculty_id": pair["faculty_id"], "reason": "x" * 201}):
        assert api_post(sc, "/api/meetings", json=body).status_code == 400, body
    stranger = create_faculty(app, "F9")
    assert api_post(sc, "/api/meetings", json={"faculty_id": stranger["faculty_id"], "reason": "x"}).status_code == 403
    assert api_post(sc, "/api/meetings", json={"faculty_id": 99999, "reason": "x"}).status_code == 403
    assert db_count(app, "meeting_requests") == 0
    assert api_post(pair["fc"], "/api/meetings",
                    json={"faculty_id": pair["faculty_id"], "reason": "x"}).status_code == 403  # faculty cannot request


def test_cancel_rules_and_status_filter(app, pair):
    sc, fc = pair["sc"], pair["fc"]
    m1, m2, m3 = (_request(pair, reason=f"R{i}")["id"] for i in range(3))
    r = api_post(sc, f"/api/meetings/{m1}/cancel", json={})
    assert r.status_code == 400 and "reason" in r.json()["error"]["fields"]
    assert api_post(sc, f"/api/meetings/{m1}/cancel").status_code == 400  # no body at all
    r = api_post(sc, f"/api/meetings/{m1}/cancel", json={"reason": "clash"})
    assert r.status_code == 200 and r.json()["meeting"]["cancellation_reason"] == "clash"
    assert r.json()["meeting"]["cancelled_by"] == "STUDENT" and r.json()["meeting"]["can_cancel"] is False
    r = api_post(fc, f"/api/meetings/{m2}/cancel")  # faculty needs no reason (and no body)
    assert r.status_code == 200 and r.json()["meeting"]["cancelled_by"] == "FACULTY"
    assert api_post(fc, f"/api/meetings/{m2}/cancel").status_code == 400  # cannot cancel twice

    listed = lambda q: [m["id"] for m in sc.get(f"/api/meetings{q}").json()["items"]]
    assert sorted(listed("")) == sorted([m1, m2, m3])
    assert listed("?status=PENDING") == [m3]
    assert sorted(listed("?status=cancelled,pending")) == sorted([m1, m2, m3])
    assert sc.get("/api/meetings?status=BOGUS").status_code == 400
    assert sc.get("/api/meetings").json()["total"] == 3


def test_reject_over_http_needs_no_time(app, pair):
    mid = _request(pair)["id"]
    r = api_post(pair["fc"], f"/api/meetings/{mid}/respond", json={"decision": "reject", "faculty_response": "busy"})
    assert r.status_code == 200 and r.json()["meeting"]["status"] == "REJECTED"
    assert r.json()["meeting"]["faculty_response"] == "busy"
    assert api_post(pair["fc"], f"/api/meetings/{mid}/respond", json={"decision": "maybe"}).status_code == 400
    assert api_post(pair["sc"], f"/api/meetings/{mid}/respond", json={"decision": "accept"}).status_code == 403


def test_faculty_loses_meeting_rights_with_the_assignment(app, pair):
    mid = _request(pair)["id"]
    unassign(app, {"faculty_id": pair["faculty_id"]}, pair["sec"], 1)
    fm = pair["fc"].get("/api/meetings").json()["items"][0]
    assert fm["can_respond"] is False
    r = api_post(pair["fc"], f"/api/meetings/{mid}/respond", json={"decision": "accept", "meeting_time_text": "now"})
    assert r.status_code == 403
    assert api_post(pair["sc"], "/api/meetings",
                    json={"faculty_id": pair["faculty_id"], "reason": "again"}).status_code == 403
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"


def test_meetings_of_others_are_invisible_and_untouchable(app, pair):
    mid = _request(pair)["id"]
    other_s = create_student(app, "1AB21CS320", pair["sec"])
    other_f = create_faculty(app, "F5")
    assign(app, other_f, pair["sec"], 1)
    osc, ofc = login_client(app, other_s["email"]), login_client(app, other_f["email"])
    for c in (osc, ofc):
        assert c.get("/api/meetings").json()["items"] == []
        assert c.get(f"/api/meetings/{mid}").status_code == 403
        assert api_post(c, f"/api/meetings/{mid}/complete").status_code == 403
        assert api_post(c, f"/api/meetings/{mid}/cancel", json={"reason": "mine now"}).status_code == 403
    assert api_post(ofc, f"/api/meetings/{mid}/respond",
                    json={"decision": "accept", "meeting_time_text": "now"}).status_code == 403
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"
    for action, body in (("respond", {"decision": "accept", "meeting_time_text": "x"}),
                         ("cancel", {"reason": "x"}), ("complete", None)):
        assert api_post(ofc, f"/api/meetings/99999/{action}", json=body).status_code == 404
    assert ofc.get("/api/meetings/99999").status_code == 404
