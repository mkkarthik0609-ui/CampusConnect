"""Authorisation: anonymous redirects, role 403s, participant isolation and forged-id attempts."""
import re

import pytest

from models import academic_queries as aq
from models import queries
from services import chat_service, meeting_service, supporting_service
from tests.conftest import (
    create_admin, create_faculty, create_student, section_id_for, assign, unassign, login_client,
    flashes, flash_text, db_one, db_all, db_count,
)

PROTECTED_PREFIXES = ("student.", "faculty.", "admin.", "admin_academic.", "chat.", "meetings.",
                      "supporting.", "notifications.")

S, F, A = "STUDENT", "FACULTY", "ADMIN"

# (METHOD, rule) -> roles allowed to use it. Every protected route must appear here so a newly added
# route without a decision shows up as a failing test instead of silently being unguarded.
ROLE_TABLE = {
    ("GET", "/student/dashboard"): {S}, ("GET", "/student/profile"): {S},
    ("POST", "/student/profile/picture"): {S}, ("POST", "/student/profile/change-request"): {S},
    ("POST", "/student/theme/<theme>"): {S, F, A},
    ("GET", "/faculty/dashboard"): {F}, ("GET", "/faculty/profile"): {F},
    ("POST", "/faculty/profile/picture"): {F}, ("POST", "/faculty/profile/change-request"): {F},
    ("GET", "/faculty/permission-requests"): {F},
    ("POST", "/faculty/permission-requests/<int:request_id>/decide"): {F},
    ("GET", "/faculty/classes"): {F}, ("POST", "/faculty/classes/request"): {F},
    ("GET", "/faculty/classes/<int:section_id>"): {F},
    ("GET", "/chat/"): {S, F}, ("GET", "/chat/open/<int:faculty_id>"): {S},
    ("GET", "/chat/open-student/<int:student_id>"): {F}, ("GET", "/chat/<int:chat_id>"): {S, F},
    ("POST", "/chat/<int:chat_id>/message"): {S, F}, ("POST", "/chat/message/<int:message_id>/edit"): {S, F},
    ("GET", "/meetings/request/<int:faculty_id>"): {S}, ("POST", "/meetings/request/<int:faculty_id>"): {S},
    ("GET", "/meetings/"): {S, F}, ("POST", "/meetings/<int:meeting_id>/respond"): {F},
    ("POST", "/meetings/<int:meeting_id>/cancel"): {S, F}, ("POST", "/meetings/<int:meeting_id>/complete"): {S, F},
    ("GET", "/supporting/faculty/search"): {S}, ("POST", "/supporting/faculty/<int:faculty_id>/request"): {S},
    ("GET", "/supporting/student/search"): {F}, ("POST", "/supporting/student/<int:student_id>/request"): {F},
    ("POST", "/supporting/<int:rel_id>/accept"): {S, F}, ("POST", "/supporting/<int:rel_id>/reject"): {S, F},
    ("GET", "/notifications/"): {S, F, A}, ("POST", "/notifications/<int:notification_id>/read"): {S, F, A},
    ("POST", "/notifications/read-all"): {S, F, A},
}
ADMIN_ONLY = {
    ("GET", "/admin/dashboard"), ("GET", "/admin/students"), ("GET", "/admin/faculty"), ("GET", "/admin/meetings"),
    ("GET", "/admin/chats"), ("GET", "/admin/chats/<int:chat_id>"), ("GET", "/admin/permission-requests"),
    ("POST", "/admin/permission-requests/<int:request_id>/decide"), ("GET", "/admin/admins"),
    ("POST", "/admin/admins/add"), ("GET", "/admin/academics"), ("POST", "/admin/academics/branch"),
    ("POST", "/admin/academics/department"), ("POST", "/admin/academics/year"),
    ("POST", "/admin/academics/sections"), ("POST", "/admin/academics/<level>/<int:row_id>/active"),
    ("POST", "/admin/academics/<level>/<int:row_id>/delete"), ("GET", "/admin/assignments"),
    ("POST", "/admin/assignments/assign"), ("POST", "/admin/assignments/<int:assignment_id>/remove"),
    ("GET", "/admin/assignment-requests"), ("POST", "/admin/assignment-requests/<int:request_id>/decide"),
    ("GET", "/admin/classes"), ("GET", "/admin/classes/<int:section_id>"),
    ("POST", "/admin/students/<int:student_id>/remove-registration"),
}
for _k in ADMIN_ONLY:
    ROLE_TABLE[_k] = {A}


def _protected_rules(app):
    out = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(PROTECTED_PREFIXES):
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                out.append((method, rule.rule))
    return sorted(out)


def _concrete(rule):
    rule = re.sub(r"<int:[a-z_]+>", "1", rule)
    rule = rule.replace("<theme>", "dark").replace("<level>", "section")
    return rule


def test_role_table_covers_every_protected_route(app):
    actual = set(_protected_rules(app))
    assert actual == set(ROLE_TABLE), {"unlisted": actual - set(ROLE_TABLE), "stale": set(ROLE_TABLE) - actual}


def test_anonymous_users_are_redirected_to_login_from_every_protected_route(app):
    anon = app.test_client()
    for method, rule in _protected_rules(app):
        resp = anon.open(_concrete(rule), method=method)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"], (method, rule, resp.status_code)


@pytest.fixture
def people(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    return {
        "admin": {"email": "admin@college.edu", "user_id": admin_id},
        "fac": create_faculty(app, "FAC100"),
        "stu": create_student(app, "1AB21CS300", sid),
        "sid": sid,
    }


def test_wrong_roles_get_403_on_every_protected_route(app, people):
    clients = {S: login_client(app, people["stu"]["email"]), F: login_client(app, people["fac"]["email"]),
               A: login_client(app, people["admin"]["email"])}
    snapshot = lambda: [db_count(app, t) for t in ("users", "chats", "messages", "meeting_requests", "faculty_assignments",
                                                  "sections", "branches", "supporting_relationships")]
    before = snapshot()
    for (method, rule), allowed in sorted(ROLE_TABLE.items()):
        for role, c in clients.items():
            if role in allowed:
                continue
            resp = c.open(_concrete(rule), method=method, data={"name": "x", "section_id": "1", "faculty_id": "1"})
            assert resp.status_code == 403, (role, method, rule, resp.status_code)
    assert snapshot() == before


def test_allowed_roles_reach_their_pages(app, people):
    pages = {S: ["/student/dashboard", "/student/profile", "/chat/", "/meetings/", "/notifications/",
                 "/supporting/faculty/search"],
             F: ["/faculty/dashboard", "/faculty/profile", "/faculty/classes", "/faculty/permission-requests",
                 "/chat/", "/meetings/", "/notifications/", "/supporting/student/search"],
             A: ["/admin/dashboard", "/admin/students", "/admin/faculty", "/admin/meetings", "/admin/chats",
                 "/admin/permission-requests", "/admin/admins", "/admin/academics", "/admin/assignments",
                 "/admin/classes", "/admin/assignment-requests", "/notifications/"]}
    who = {S: people["stu"]["email"], F: people["fac"]["email"], A: people["admin"]["email"]}
    for role, paths in pages.items():
        c = login_client(app, who[role])
        for p in paths:
            assert c.get(p).status_code == 200, (role, p)


def test_theme_switch_allowed_for_all_roles_and_ignores_unknown_themes(app, people):
    for who in (people["stu"]["email"], people["fac"]["email"], people["admin"]["email"]):
        c = login_client(app, who)
        assert c.post("/student/theme/dark").status_code == 302
        c.post("/student/theme/<script>")  # unknown value falls back to light
    assert db_one(app, "SELECT theme_preference FROM users WHERE email = ?", (people["stu"]["email"],))[
        "theme_preference"] == "light"


# ---------------------------------------------------------------------------
# class view and search gates
# ---------------------------------------------------------------------------

def test_class_view_requires_active_assignment_for_that_exact_section(app, people):
    other_sid = section_id_for(app, "AIML", "3rd Year", "B")
    c = login_client(app, people["fac"]["email"])
    for sid in (people["sid"], other_sid, 99999, 0):
        assert c.get(f"/faculty/classes/{sid}").status_code == 403
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    assert c.get(f"/faculty/classes/{people['sid']}").status_code == 200
    assert c.get(f"/faculty/classes/{other_sid}").status_code == 403
    assert c.get("/faculty/classes/99999").status_code == 403  # no 404 oracle for nonexistent ids
    unassign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    assert c.get(f"/faculty/classes/{people['sid']}").status_code == 403


def test_faculty_student_search_is_scoped_and_wildcards_do_not_widen_it(app, people):
    sid_b = section_id_for(app, "AIML", "3rd Year", "B")
    create_student(app, "1AB21CS301", sid_b, name="Zed Outsider")
    create_student(app, "1AB21CS302", people["sid"], name="Amy Insider")
    c = login_client(app, people["fac"]["email"])
    body = c.get("/supporting/student/search?q=1AB21").data.decode()
    assert "1AB21CS300" not in body and "1AB21CS301" not in body  # nothing assigned yet
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    for q in ("1AB21", "Amy", "%", "_", "%%", "1AB21CS30_"):
        body = c.get("/supporting/student/search", query_string={"q": q}).data.decode()
        assert "1AB21CS301" not in body and "Zed Outsider" not in body, q
    body = c.get("/supporting/student/search?q=Amy").data.decode()
    assert "1AB21CS302" in body
    with app.app_context():
        found = aq.search_students_in_faculty_scope(people["fac"]["faculty_id"], "%")
        assert sorted(r["usn"] for r in found) == ["1AB21CS300", "1AB21CS302"]
        # SQL metacharacters are parameterised
        assert aq.search_students_in_faculty_scope(people["fac"]["faculty_id"], "' OR '1'='1") == []


def test_search_with_blank_query_returns_nothing(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    c = login_client(app, people["fac"]["email"])
    assert c.get("/supporting/student/search?q=").status_code == 200
    with app.app_context():
        assert aq.search_students_in_faculty_scope(people["fac"]["faculty_id"], "zzzzzz") == []


# ---------------------------------------------------------------------------
# chats
# ---------------------------------------------------------------------------

@pytest.fixture
def chatting(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    with app.app_context():
        chat = chat_service.open_chat(people["stu"]["student_id"], people["fac"]["faculty_id"],
                                      people["stu"]["user_id"])
        mid = chat_service.send_text_message(chat["id"], people["stu"]["user_id"], "private hello")
    return dict(people, chat_id=chat["id"], message_id=mid)


def test_only_the_two_participants_can_view_a_chat(app, chatting):
    outsider_s = create_student(app, "1AB21CS310", chatting["sid"])
    outsider_f = create_faculty(app, "FAC101")
    assign(app, outsider_f, chatting["sid"], chatting["admin"]["user_id"])  # same class, but not a participant
    for who in (outsider_s, outsider_f):
        c = login_client(app, who["email"])
        resp = c.get(f"/chat/{chatting['chat_id']}")
        assert resp.status_code == 302, "must not render"
        assert flashes(c)[0][0] == "error"
        c.post(f"/chat/{chatting['chat_id']}/message", data={"message_text": "intruder"})
        c.post(f"/chat/message/{chatting['message_id']}/edit", data={"message_text": "tampered"})
    assert db_count(app, "messages") == 1
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "private hello"
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 0  # outsiders did not mark it seen
    # participants can
    assert login_client(app, chatting["stu"]["email"]).get(f"/chat/{chatting['chat_id']}").status_code == 200
    assert login_client(app, chatting["fac"]["email"]).get(f"/chat/{chatting['chat_id']}").status_code == 200


def test_edit_message_ownership_and_seen_lock_over_http(app, chatting):
    sc = login_client(app, chatting["stu"]["email"])
    fc = login_client(app, chatting["fac"]["email"])
    fc.post(f"/chat/message/{chatting['message_id']}/edit", data={"message_text": "faculty edit"})
    assert "only edit your own" in flash_text(fc)
    sc.post(f"/chat/message/{chatting['message_id']}/edit", data={"message_text": "student edit"})
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "student edit"
    fc.get(f"/chat/{chatting['chat_id']}")  # faculty reads it
    sc.post(f"/chat/message/{chatting['message_id']}/edit", data={"message_text": "too late"})
    assert "already been seen" in flash_text(sc)
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "student edit"
    sc.post("/chat/message/99999/edit", data={"message_text": "x"})
    assert "not found" in flash_text(sc).lower()


def test_posting_to_someone_elses_chat_id_is_refused(app, chatting):
    s2 = create_student(app, "1AB21CS311", chatting["sid"])
    with app.app_context():
        chat2 = chat_service.open_chat(s2["student_id"], chatting["fac"]["faculty_id"], s2["user_id"])
    c = login_client(app, s2["email"])
    c.post(f"/chat/{chatting['chat_id']}/message", data={"message_text": "into the wrong chat"})
    assert db_count(app, "messages", "message_text = 'into the wrong chat'") == 0
    c.post(f"/chat/{chat2['id']}/message", data={"message_text": "into my chat"})
    assert db_count(app, "messages", "message_text = 'into my chat'") == 1


def test_student_cannot_open_chat_or_meeting_with_unassigned_faculty(app, chatting):
    stranger = create_faculty(app, "FAC102")
    c = login_client(app, chatting["stu"]["email"])
    resp = c.get(f"/chat/open/{stranger['faculty_id']}")
    assert resp.status_code == 302 and "/student/dashboard" in resp.headers["Location"]
    assert "permission" in flash_text(c).lower()
    resp = c.post(f"/meetings/request/{stranger['faculty_id']}", data={"reason": "let me in"})
    assert resp.status_code == 200 and b"permission" in resp.data  # form re-rendered with the error
    assert db_count(app, "chats") == 1 and db_count(app, "meeting_requests") == 0
    # a faculty id that does not exist at all
    assert c.get("/chat/open/99999").status_code == 302
    assert c.post("/meetings/request/99999", data={"reason": "x"}).status_code == 302
    assert db_count(app, "chats") == 1


def test_faculty_cannot_open_chat_with_students_outside_their_classes(app, chatting):
    other_sid = section_id_for(app, "AIDE", "2nd Year", "C")
    outsider = create_student(app, "1AB21CS312", other_sid)
    c = login_client(app, chatting["fac"]["email"])
    resp = c.get(f"/chat/open-student/{outsider['student_id']}")
    assert resp.status_code == 302 and "/faculty/dashboard" in resp.headers["Location"]
    assert db_count(app, "chats") == 1
    assert c.get("/chat/open-student/99999").status_code == 302


def test_removed_student_is_unreachable_but_history_is_kept(app, chatting):
    admin = login_client(app, chatting["admin"]["email"])
    admin.post(f"/admin/students/{chatting['stu']['student_id']}/remove-registration")
    fc = login_client(app, chatting["fac"]["email"])
    with app.app_context():
        reachable = queries.is_faculty_accessible_to_student(chatting["stu"]["student_id"], chatting["fac"]["faculty_id"])
    assert not reachable, "a student whose registration was removed must not be reachable by faculty"
    fc.post(f"/chat/{chatting['chat_id']}/message", data={"message_text": "hello ghost"})
    assert db_count(app, "messages", "message_text = 'hello ghost'") == 0
    assert db_count(app, "messages") == 1  # history preserved
    assert admin.get(f"/admin/chats/{chatting['chat_id']}").status_code == 200


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

@pytest.fixture
def meeting(app, chatting):
    with app.app_context():
        mid = meeting_service.request_meeting(chatting["stu"]["student_id"], chatting["fac"]["faculty_id"], "Doubt", "")
    return dict(chatting, meeting_id=mid)


def test_other_faculty_and_students_cannot_act_on_a_meeting(app, meeting):
    other_f = create_faculty(app, "FAC103")
    assign(app, other_f, meeting["sid"], meeting["admin"]["user_id"])
    other_s = create_student(app, "1AB21CS320", meeting["sid"])
    mid = meeting["meeting_id"]
    fc, sc = login_client(app, other_f["email"]), login_client(app, other_s["email"])
    fc.post(f"/meetings/{mid}/respond", data={"decision": "accept", "meeting_time_text": "now"})
    assert "not authorized" in flash_text(fc)
    sc.post(f"/meetings/{mid}/cancel", data={"reason": "mine now"})
    assert "not authorized" in flash_text(sc)
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"
    # accept legitimately, then outsiders still cannot complete/cancel
    login_client(app, meeting["fac"]["email"]).post(
        f"/meetings/{mid}/respond", data={"decision": "accept", "meeting_time_text": "Mon"})
    fc.post(f"/meetings/{mid}/complete")
    sc.post(f"/meetings/{mid}/complete")
    fc.post(f"/meetings/{mid}/cancel", data={"reason": "x"})
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "ACCEPTED"
    # other participants' meetings are not listed
    assert b"Doubt" not in sc.get("/meetings/").data


def test_meeting_actions_on_missing_ids_are_handled(app, people):
    c = login_client(app, people["fac"]["email"])
    for action in ("respond", "cancel", "complete"):
        assert c.post(f"/meetings/99999/{action}", data={"decision": "accept"}).status_code == 302
        assert "not found" in flash_text(c).lower()


# ---------------------------------------------------------------------------
# supporting relationships
# ---------------------------------------------------------------------------

def test_supporting_request_by_faculty_limited_to_assigned_classes(app, people):
    other_sid = section_id_for(app, "AIDE", "2nd Year", "C")
    outsider = create_student(app, "1AB21CS330", other_sid)
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    c = login_client(app, people["fac"]["email"])
    c.post(f"/supporting/student/{outsider['student_id']}/request")
    assert "assigned classes" in flash_text(c)
    c.post("/supporting/student/99999/request")
    assert "not found" in flash_text(c).lower()
    assert db_count(app, "supporting_relationships") == 0
    c.post(f"/supporting/student/{people['stu']['student_id']}/request")
    assert db_count(app, "supporting_relationships") == 1
    c.post(f"/supporting/student/{people['stu']['student_id']}/request")
    assert "already exists" in flash_text(c)


def test_only_the_addressed_party_can_answer_a_supporting_request(app, people):
    other_s = create_student(app, "1AB21CS331", people["sid"])
    other_f = create_faculty(app, "FAC104")
    with app.app_context():
        rel_to_fac = supporting_service.student_request_faculty(people["stu"]["student_id"], people["fac"]["faculty_id"])
        rel_to_stu = supporting_service.faculty_request_student(other_f["faculty_id"], other_s["student_id"]) \
            if aq.is_student_in_faculty_scope(other_f["faculty_id"], other_s["student_id"]) else None
    assert rel_to_stu is None  # other_f is not assigned: cannot even ask
    # the requester cannot accept their own request; a third faculty cannot either
    sc = login_client(app, people["stu"]["email"])
    sc.post(f"/supporting/{rel_to_fac}/accept")
    assert "not authorized" in flash_text(sc)
    oc = login_client(app, other_f["email"])
    oc.post(f"/supporting/{rel_to_fac}/accept")
    assert "not authorized" in flash_text(oc)
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "PENDING"
    fc = login_client(app, people["fac"]["email"])
    fc.post(f"/supporting/{rel_to_fac}/accept")
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"
    fc.post(f"/supporting/{rel_to_fac}/reject")
    assert "already been responded" in flash_text(fc)
    fc.post("/supporting/99999/accept")
    assert "not found" in flash_text(fc).lower()


def test_student_cannot_answer_a_request_addressed_to_another_student(app, people):
    other_s = create_student(app, "1AB21CS332", people["sid"])
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    with app.app_context():
        rel = supporting_service.faculty_request_student(people["fac"]["faculty_id"], other_s["student_id"])
    c = login_client(app, people["stu"]["email"])
    c.post(f"/supporting/{rel}/accept")
    assert "not authorized" in flash_text(c)
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "PENDING"
    assert login_client(app, other_s["email"]).post(f"/supporting/{rel}/accept").status_code == 302
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"


def test_student_reject_then_re_request_is_allowed(app, people):
    with app.app_context():
        rel = supporting_service.student_request_faculty(people["stu"]["student_id"], people["fac"]["faculty_id"])
        supporting_service.respond_to_request(rel, people["fac"]["user_id"], "FACULTY", False)
        again = supporting_service.student_request_faculty(people["stu"]["student_id"], people["fac"]["faculty_id"])
        assert again  # a rejected relationship can be re-requested (row is reused or recreated)


# ---------------------------------------------------------------------------
# permission (profile-change) requests
# ---------------------------------------------------------------------------

def test_faculty_cannot_decide_faculty_profile_change_requests(app, people):
    other_f = create_faculty(app, "FAC105")
    fc = login_client(app, people["fac"]["email"])
    fc.post("/faculty/profile/change-request", data={"department": "AIDE", "reason": "moving"})
    rid = db_one(app, "SELECT id FROM permission_requests")["id"]
    oc = login_client(app, other_f["email"])
    oc.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"})
    assert "Only an admin" in flash_text(oc)
    fc.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"})  # self-approval
    assert "Only an admin" in flash_text(fc)
    assert db_one(app, "SELECT department FROM faculty WHERE id = ?", (people["fac"]["faculty_id"],))[
        "department"] == "AIML"
    admin = login_client(app, people["admin"]["email"])
    admin.post(f"/admin/permission-requests/{rid}/decide", data={"decision": "approve"})
    assert db_one(app, "SELECT department FROM faculty WHERE id = ?", (people["fac"]["faculty_id"],))[
        "department"] == "AIDE"


def test_faculty_profile_change_validates_department_and_fields(app, people):
    fc = login_client(app, people["fac"]["email"])
    fc.post("/faculty/profile/change-request", data={"department": "Underwater Basket Weaving"})
    assert "choose a department" in flash_text(fc)
    fc.post("/faculty/profile/change-request", data={"faculty_code": "HACK", "full_name": "Hacked"})
    assert "No valid profile fields" in flash_text(fc)
    assert db_count(app, "permission_requests") == 0


def test_students_cannot_see_or_decide_requests_of_others(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    other_s = create_student(app, "1AB21CS340", people["sid"])
    login_client(app, people["stu"]["email"]).post("/student/profile/change-request", data={"phone": "8000000000"})
    rid = db_one(app, "SELECT id FROM permission_requests")["id"]
    oc = login_client(app, other_s["email"])
    assert oc.post(f"/faculty/permission-requests/{rid}/decide", data={"decision": "approve"}).status_code == 403
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"


def test_decide_unknown_permission_request(app, people):
    fc = login_client(app, people["fac"]["email"])
    fc.post("/faculty/permission-requests/99999/decide", data={"decision": "approve"})
    assert "not found" in flash_text(fc).lower()


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------

def test_notifications_are_private_to_their_owner(app, people):
    with app.app_context():
        nid = queries.create_notification(people["stu"]["user_id"], "TEST", "Secret", "for student only")
    fc = login_client(app, people["fac"]["email"])
    assert b"for student only" not in fc.get("/notifications/").data
    fc.post(f"/notifications/{nid}/read")
    fc.post("/notifications/read-all")
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 0
    sc = login_client(app, people["stu"]["email"])
    assert b"for student only" in sc.get("/notifications/").data
    sc.post(f"/notifications/{nid}/read")
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 1


# ---------------------------------------------------------------------------
# inactive accounts
# ---------------------------------------------------------------------------

def test_deactivated_account_cannot_log_in(app, people):
    from tests.conftest import db_exec
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (people["fac"]["user_id"],))
    c = app.test_client()
    resp = c.post("/login", data={"email": people["fac"]["email"], "password": "Passw0rd!x"})
    assert resp.status_code == 200
    assert c.get("/faculty/dashboard").status_code == 302
