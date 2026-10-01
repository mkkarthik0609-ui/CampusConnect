"""Authorisation across /api/faculty, /api/chat, /api/meetings, /api/supporting (+ notifications, uploads):
anonymous 401s, role 403s, participant isolation, forged ids, the Admin-controlled class scope and the
immediate revocation of every right when an assignment is removed."""
import io
import re

import pytest
from fastapi.testclient import TestClient

from models import academic_queries as aq
from services import assignment_service, chat_service, meeting_service, permission_service, supporting_service
from tests.conftest import (
    api_post, assign, create_admin, create_faculty, create_student, db_count, db_exec, db_one, login_client,
    section_id_for, unassign,
)

S, F = "STUDENT", "FACULTY"
PREFIXES = ("/api/faculty", "/api/chat", "/api/meetings", "/api/supporting")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

# (METHOD, path pattern) -> roles allowed. Every route of the four routers must be listed, so a newly added
# endpoint without an authorisation decision fails test_role_table_covers_every_route.
ROLE_TABLE = {
    ("GET", "/api/faculty/dashboard"): {F}, ("GET", "/api/faculty/profile"): {F},
    ("POST", "/api/faculty/profile/picture"): {F}, ("POST", "/api/faculty/profile/change-request"): {F},
    ("GET", "/api/faculty/classes"): {F}, ("POST", "/api/faculty/classes/request"): {F},
    ("GET", "/api/faculty/classes/{section_id}"): {F},
    ("GET", "/api/faculty/permission-requests"): {F},
    ("POST", "/api/faculty/permission-requests/{request_id}/decide"): {F},
    ("GET", "/api/chat"): {S, F}, ("POST", "/api/chat/open"): {S, F}, ("GET", "/api/chat/{chat_id}"): {S, F},
    ("POST", "/api/chat/{chat_id}/messages"): {S, F}, ("POST", "/api/chat/messages/{message_id}/edit"): {S, F},
    ("GET", "/api/meetings"): {S, F}, ("POST", "/api/meetings"): {S}, ("GET", "/api/meetings/{meeting_id}"): {S, F},
    ("POST", "/api/meetings/{meeting_id}/respond"): {F},
    ("POST", "/api/meetings/{meeting_id}/cancel"): {S, F}, ("POST", "/api/meetings/{meeting_id}/complete"): {S, F},
    ("GET", "/api/supporting"): {S, F},
    ("GET", "/api/supporting/faculty/search"): {S}, ("GET", "/api/supporting/students/search"): {F},
    ("POST", "/api/supporting/faculty/{faculty_id}/request"): {S},
    ("POST", "/api/supporting/students/{student_id}/request"): {F},
    ("POST", "/api/supporting/{rel_id}/accept"): {S, F}, ("POST", "/api/supporting/{rel_id}/reject"): {S, F},
}


def _routes(app):
    """(METHOD, path) of every endpoint of the four routers (read from the OpenAPI schema)."""
    out = set()
    for path, item in app.openapi()["paths"].items():
        if any(path == p or path.startswith(p + "/") for p in PREFIXES):
            for method in item:
                out.add((method.upper(), path))
    return out


def _concrete(path):
    return re.sub(r"\{[a-z_]+\}", "1", path)


def _send(client, method, path):
    if method == "GET":
        return client.get(_concrete(path))
    return api_post(client, _concrete(path), json={})


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


def _snapshot(app):
    return [db_count(app, t) for t in ("users", "chats", "messages", "meeting_requests", "faculty_assignments",
                                        "faculty_assignment_requests", "supporting_relationships",
                                        "permission_requests")]


def test_role_table_covers_every_route(app):
    actual = _routes(app)
    assert actual == set(ROLE_TABLE), {"unlisted": actual - set(ROLE_TABLE), "stale": set(ROLE_TABLE) - actual}


def test_anonymous_users_get_401_from_every_route(app, client):
    for method, path in sorted(ROLE_TABLE):
        resp = _send(client, method, path)
        assert resp.status_code == 401, (method, path, resp.status_code)
        assert resp.json()["error"]["code"] == "unauthenticated"


def test_wrong_roles_get_403_on_every_route_and_nothing_changes(app, people):
    admin = login_client(app, people["admin"]["email"])
    clients = {S: login_client(app, people["stu"]["email"]), F: login_client(app, people["fac"]["email"]),
               "ADMIN": admin}
    before = _snapshot(app)
    for (method, path), allowed in sorted(ROLE_TABLE.items()):
        for role, c in clients.items():
            if role in allowed:
                continue
            resp = _send(c, method, path)
            assert resp.status_code == 403, (role, method, path, resp.status_code)
            assert resp.json()["error"]["code"] == "forbidden"
    assert _snapshot(app) == before


def test_allowed_roles_reach_their_endpoints(app, people):
    reach = {S: ["/api/chat", "/api/meetings", "/api/supporting", "/api/supporting/faculty/search?q=a",
                 "/api/notifications"],
             F: ["/api/faculty/dashboard", "/api/faculty/profile", "/api/faculty/classes",
                 "/api/faculty/permission-requests", "/api/chat", "/api/meetings", "/api/supporting",
                 "/api/supporting/students/search?q=a", "/api/notifications"]}
    who = {S: people["stu"]["email"], F: people["fac"]["email"]}
    for role, paths in reach.items():
        c = login_client(app, who[role])
        for p in paths:
            assert c.get(p).status_code == 200, (role, p)


def test_deactivated_account_loses_its_session_and_cannot_log_in(app, people):
    c = login_client(app, people["fac"]["email"])
    assert c.get("/api/faculty/dashboard").status_code == 200
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (people["fac"]["user_id"],))
    assert c.get("/api/faculty/dashboard").status_code == 401
    r = api_post(TestClient(app), "/api/auth/login",
                 json={"identifier": people["fac"]["email"], "password": "Passw0rd!x"})
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# the Admin-controlled class scope (spec scenario)
# ---------------------------------------------------------------------------

@pytest.fixture
def spec(app):
    """FAC001: AIML 3rd A, AIML 3rd B, AIDE 2nd A. FAC003: AIML 3rd B only. Students everywhere."""
    admin_id = create_admin(app)
    sec = {k: section_id_for(app, *k) for k in (("AIML", "3rd Year", "A"), ("AIML", "3rd Year", "B"),
                                                ("AIDE", "2nd Year", "A"), ("AIML", "2nd Year", "A"))}
    fac1, fac3 = create_faculty(app, "FAC001"), create_faculty(app, "FAC003")
    for key in (("AIML", "3rd Year", "A"), ("AIML", "3rd Year", "B"), ("AIDE", "2nd Year", "A")):
        assign(app, fac1, sec[key], admin_id)
    assign(app, fac3, sec[("AIML", "3rd Year", "B")], admin_id)
    studs = {
        "3A": create_student(app, "1AB21CS101", sec[("AIML", "3rd Year", "A")], name="Alice ThreeA"),
        "3B": create_student(app, "1AB21CS102", sec[("AIML", "3rd Year", "B")], name="Bob ThreeB"),
        "2A": create_student(app, "1AB21CS103", sec[("AIDE", "2nd Year", "A")], name="Cara AideTwoA"),
        "X": create_student(app, "1AB21CS104", sec[("AIML", "2nd Year", "A")], name="Dan Outside"),
    }
    return {"admin": admin_id, "sec": sec, "fac1": fac1, "fac3": fac3, "stud": studs,
            "c1": login_client(app, fac1["email"]), "c3": login_client(app, fac3["email"])}


def test_fac001_multi_section_scope(app, spec):
    c1, sec, studs = spec["c1"], spec["sec"], spec["stud"]
    classes = c1.get("/api/faculty/classes").json()["assignments"]
    assert sorted(c["label"] for c in classes) == [
        "CSE → AIDE → 2nd Year → A", "CSE → AIML → 3rd Year → A", "CSE → AIML → 3rd Year → B"]
    assert all(c["student_count"] == 1 for c in classes)
    dash = c1.get("/api/faculty/dashboard").json()
    assert len(dash["classes"]) == 3 and dash["counts"]["classes"] == 3

    expect = {("AIML", "3rd Year", "A"): "1AB21CS101", ("AIML", "3rd Year", "B"): "1AB21CS102",
              ("AIDE", "2nd Year", "A"): "1AB21CS103"}
    for key, usn in expect.items():
        detail = c1.get(f"/api/faculty/classes/{sec[key]}")
        assert detail.status_code == 200
        assert [s["usn"] for s in detail.json()["students"]] == [usn]
    assert c1.get(f"/api/faculty/classes/{sec[('AIML', '2nd Year', 'A')]}").status_code == 403

    # chat with the three assigned classes' students, not with the outsider
    for key in ("3A", "3B", "2A"):
        r = api_post(c1, "/api/chat/open", json={"student_id": studs[key]["student_id"]})
        assert r.status_code == 200, key
    assert api_post(c1, "/api/chat/open", json={"student_id": studs["X"]["student_id"]}).status_code == 403
    assert db_count(app, "chats") == 3
    # student search only finds the assigned classes
    found = c1.get("/api/supporting/students/search?q=1AB21").json()["items"]
    assert sorted(s["usn"] for s in found) == ["1AB21CS101", "1AB21CS102", "1AB21CS103"]
    assert all(s["class"] for s in found)
    assert c1.get("/api/supporting/students/search?q=Dan").json()["items"] == []


def test_fac003_cannot_reach_3rd_year_a_students(app, spec):
    c3, sec, studs = spec["c3"], spec["sec"], spec["stud"]
    key_a = ("AIML", "3rd Year", "A")
    assert c3.get(f"/api/faculty/classes/{sec[key_a]}").status_code == 403
    assert c3.get(f"/api/faculty/classes/{sec[('AIML', '3rd Year', 'B')]}").status_code == 200
    assert api_post(c3, "/api/chat/open", json={"student_id": studs["3A"]["student_id"]}).status_code == 403
    assert api_post(c3, "/api/chat/open", json={"student_id": studs["3B"]["student_id"]}).status_code == 200
    assert c3.get("/api/supporting/students/search?q=Alice").json()["items"] == []
    assert c3.get("/api/supporting/students/search?q=1AB21CS101").json()["items"] == []
    assert [s["usn"] for s in c3.get("/api/supporting/students/search?q=1AB21").json()["items"]] == ["1AB21CS102"]
    assert api_post(c3, f"/api/supporting/students/{studs['3A']['student_id']}/request").status_code == 403
    # the 3A student cannot reach FAC003 either, in either direction
    s3a = login_client(app, studs["3A"]["email"])
    assert api_post(s3a, "/api/chat/open", json={"faculty_id": spec["fac3"]["faculty_id"]}).status_code == 403
    assert api_post(s3a, "/api/meetings", json={"faculty_id": spec["fac3"]["faculty_id"], "reason": "x"}).status_code == 403
    assert api_post(s3a, "/api/chat/open", json={"faculty_id": spec["fac1"]["faculty_id"]}).status_code == 200
    # the 3B student reaches both
    s3b = login_client(app, studs["3B"]["email"])
    for fac in ("fac1", "fac3"):
        assert api_post(s3b, "/api/chat/open", json={"faculty_id": spec[fac]["faculty_id"]}).status_code == 200
    assert db_count(app, "chats", "student_id = ? AND faculty_id = ?",
                    (studs["3A"]["student_id"], spec["fac3"]["faculty_id"])) == 0


def test_five_faculty_on_one_section_can_all_chat_and_meet(app, people):
    sid = people["sid"]
    facs = [create_faculty(app, f"FAC20{i}") for i in range(5)]
    for f in facs:
        assign(app, f, sid, people["admin"]["user_id"])
    sc = login_client(app, people["stu"]["email"])
    for f in facs:
        r = api_post(sc, "/api/chat/open", json={"faculty_id": f["faculty_id"]})
        assert r.status_code == 200
        assert api_post(sc, f"/api/chat/{r.json()['chat_id']}/messages", json={"message_text": "hello"}).status_code == 201
        assert api_post(sc, "/api/meetings", json={"faculty_id": f["faculty_id"], "reason": "r"}).status_code == 201
    assert len(sc.get("/api/chat").json()["items"]) == 5
    for f in facs:
        fc = login_client(app, f["email"])
        chat = fc.get("/api/chat").json()["items"]
        assert len(chat) == 1 and chat[0]["unread_count"] == 1
        meetings = fc.get("/api/meetings").json()["items"]
        assert len(meetings) == 1 and meetings[0]["can_respond"] is True
        detail = fc.get(f"/api/faculty/classes/{sid}").json()
        assert len(detail["co_faculty"]) == 5 and sum(1 for c in detail["co_faculty"] if c["is_me"]) == 1


def test_request_then_approve_flow_grants_access_only_after_approval(app, people):
    sid, fid = people["sid"], people["fac"]["faculty_id"]
    fc, sc = login_client(app, people["fac"]["email"]), login_client(app, people["stu"]["email"])
    r = api_post(fc, "/api/faculty/classes/request", json={"section_id": sid, "note": "I teach DSA"})
    assert r.status_code == 201
    req_id = r.json()["id"]
    listing = fc.get("/api/faculty/classes").json()
    assert listing["assignments"] == [] and listing["requests"][0]["status"] == "PENDING"
    assert listing["requests"][0]["note"] == "I teach DSA" and listing["requests"][0]["class"]["section_id"] == sid
    assert fc.get("/api/faculty/dashboard").json()["pending_class_requests"][0]["id"] == req_id
    # a duplicate request, an unknown class and a forged payload are refused
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": sid}).status_code == 409
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": 99999}).status_code == 404
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": sid, "faculty_id": 5}).status_code == 400
    # nothing is granted yet
    assert fc.get(f"/api/faculty/classes/{sid}").status_code == 403
    assert api_post(fc, "/api/chat/open", json={"student_id": people["stu"]["student_id"]}).status_code == 403
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fid}).status_code == 403
    assert api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "x"}).status_code == 403
    assert fc.get("/api/supporting/students/search?q=1AB21").json()["items"] == []
    # approve (the Admin's action)
    with app.app_context():
        assignment_service.decide_request(req_id, people["admin"]["user_id"], True)
    assert fc.get(f"/api/faculty/classes/{sid}").status_code == 200
    assert api_post(fc, "/api/chat/open", json={"student_id": people["stu"]["student_id"]}).status_code == 200
    assert api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "x"}).status_code == 201
    assert fc.get("/api/faculty/classes").json()["requests"][0]["status"] == "APPROVED"
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": sid}).status_code == 409  # already assigned


def test_rejected_class_request_grants_nothing(app, people):
    fc = login_client(app, people["fac"]["email"])
    req_id = api_post(fc, "/api/faculty/classes/request", json={"section_id": people["sid"]}).json()["id"]
    with app.app_context():
        assignment_service.decide_request(req_id, people["admin"]["user_id"], False)
    assert fc.get(f"/api/faculty/classes/{people['sid']}").status_code == 403
    assert db_count(app, "faculty_assignments") == 0


def test_removing_an_assignment_revokes_everything_immediately(app, people):
    sid = people["sid"]
    other_sid = section_id_for(app, "AIML", "3rd Year", "B")
    assign(app, people["fac"], sid, people["admin"]["user_id"])
    fc, sc = login_client(app, people["fac"]["email"]), login_client(app, people["stu"]["email"])
    fid, stid = people["fac"]["faculty_id"], people["stu"]["student_id"]
    chat_id = api_post(fc, "/api/chat/open", json={"student_id": stid}).json()["chat_id"]
    api_post(sc, f"/api/chat/{chat_id}/messages", json={"message_text": "hi"})
    mid = api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "doubt"}).json()["id"]
    with app.app_context():  # a pending student profile-change request addressed to the class
        req_id = permission_service.student_request_profile_change(
            people["stu"]["user_id"], {"phone": "8000000000"}, "new number")
    assert len(fc.get("/api/faculty/permission-requests").json()["items"]) == 1
    assert fc.get(f"/api/faculty/classes/{sid}").status_code == 200

    unassign(app, people["fac"], sid, people["admin"]["user_id"])

    assert fc.get(f"/api/faculty/classes/{sid}").status_code == 403
    assert fc.get("/api/faculty/classes").json()["assignments"] == []
    assert fc.get("/api/faculty/dashboard").json()["classes"] == []
    assert fc.get("/api/supporting/students/search?q=1AB21").json()["items"] == []
    # chat
    assert fc.get(f"/api/chat/{chat_id}").status_code == 403
    assert sc.get(f"/api/chat/{chat_id}").status_code == 403
    assert api_post(fc, f"/api/chat/{chat_id}/messages", json={"message_text": "x"}).status_code == 403
    assert api_post(fc, "/api/chat/open", json={"student_id": stid}).status_code == 403
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fid}).status_code == 403
    assert fc.get("/api/chat").json()["items"] == []
    first_msg = db_one(app, "SELECT id FROM messages")["id"]
    assert api_post(sc, f"/api/chat/messages/{first_msg}/edit", json={"message_text": "edit"}).status_code == 403
    # meetings
    r = api_post(fc, f"/api/meetings/{mid}/respond", json={"decision": "accept", "meeting_time_text": "now"})
    assert r.status_code == 403
    assert api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "again"}).status_code == 403
    # permission-request review
    assert fc.get("/api/faculty/permission-requests").json()["items"] == []
    assert api_post(fc, f"/api/faculty/permission-requests/{req_id}/decide", json={"decision": "approve"}).status_code == 403
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    # supporting invitations
    assert api_post(fc, f"/api/supporting/students/{stid}/request").status_code == 403
    # a different class does not bring anything back
    assign(app, people["fac"], other_sid, people["admin"]["user_id"])
    assert fc.get(f"/api/faculty/classes/{sid}").status_code == 403
    assert api_post(fc, "/api/chat/open", json={"student_id": stid}).status_code == 403


def test_deactivated_class_chain_closes_access(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    fc = login_client(app, people["fac"]["email"])
    assert api_post(fc, "/api/chat/open", json={"student_id": people["stu"]["student_id"]}).status_code == 200
    with app.app_context():
        aq.set_level_active("section", people["sid"], False)
    assert fc.get(f"/api/faculty/classes/{people['sid']}").status_code == 403
    assert api_post(fc, "/api/chat/open", json={"student_id": people["stu"]["student_id"]}).status_code == 403
    assert fc.get("/api/chat").json()["items"] == []


def test_class_detail_403_for_unassigned_and_nonexistent_ids(app, people):
    c = login_client(app, people["fac"]["email"])
    for sid in (people["sid"], section_id_for(app, "AIML", "3rd Year", "B"), 99999, 0, -1):
        r = c.get(f"/api/faculty/classes/{sid}")
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden", sid
    assert c.get("/api/faculty/classes/abc").status_code == 400
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    assert c.get(f"/api/faculty/classes/{people['sid']}").status_code == 200
    assert c.get("/api/faculty/classes/99999").status_code == 403  # still no 404 oracle


def test_faculty_student_search_is_scoped_and_wildcards_do_not_widen_it(app, people):
    sid_b = section_id_for(app, "AIML", "3rd Year", "B")
    create_student(app, "1AB21CS301", sid_b, name="Zed Outsider")
    create_student(app, "1AB21CS302", people["sid"], name="Amy Insider")
    c = login_client(app, people["fac"]["email"])
    search = lambda q: c.get("/api/supporting/students/search", params={"q": q}).json()["items"]
    assert search("1AB21") == []  # nothing assigned yet
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    for q in ("1AB21", "Amy", "%", "_", "%%", "1AB21CS30_", "' OR '1'='1", "Zed"):
        usns = {s["usn"] for s in search(q)}
        assert "1AB21CS301" not in usns, q
    assert [s["usn"] for s in search("Amy")] == ["1AB21CS302"]
    assert {s["usn"] for s in search("%")} == {"1AB21CS300", "1AB21CS302"}
    assert search("") == [] and search("   ") == []
    assert c.get("/api/supporting/students/search").json()["items"] == []
    assert c.get("/api/supporting/students/search?q=" + "a" * 101).status_code == 400
    with app.app_context():
        assert aq.search_students_in_faculty_scope(people["fac"]["faculty_id"], "' OR '1'='1") == []


# ---------------------------------------------------------------------------
# chats
# ---------------------------------------------------------------------------

@pytest.fixture
def chatting(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    with app.app_context():
        chat = chat_service.open_chat(people["stu"]["student_id"], people["fac"]["faculty_id"])
        mid = chat_service.send_text_message(chat["id"], people["stu"]["user_id"], "private hello")
    return dict(people, chat_id=chat["id"], message_id=mid)


def test_only_the_two_participants_can_use_a_chat(app, chatting):
    outsider_s = create_student(app, "1AB21CS310", chatting["sid"])
    outsider_f = create_faculty(app, "FAC101")
    assign(app, outsider_f, chatting["sid"], chatting["admin"]["user_id"])  # same class, but not a participant
    cid, mid = chatting["chat_id"], chatting["message_id"]
    for who in (outsider_s, outsider_f):
        c = login_client(app, who["email"])
        assert c.get(f"/api/chat/{cid}").status_code == 403
        assert api_post(c, f"/api/chat/{cid}/messages", json={"message_text": "intruder"}).status_code == 403
        files = {"attachment": ("x.png", io.BytesIO(PNG), "image/png")}
        assert api_post(c, f"/api/chat/{cid}/messages", files=files).status_code == 403
        assert api_post(c, f"/api/chat/messages/{mid}/edit", json={"message_text": "tampered"}).status_code == 403
        assert c.get("/api/chat").json()["items"] == []
    assert db_count(app, "messages") == 1
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "private hello"
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 0  # outsiders did not mark it seen
    assert db_count(app, "chats") == 1
    assert len(db_all_files(app)) == 0  # refused uploads were not stored
    assert login_client(app, chatting["stu"]["email"]).get(f"/api/chat/{cid}").status_code == 200
    assert login_client(app, chatting["fac"]["email"]).get(f"/api/chat/{cid}").status_code == 200
    assert login_client(app, chatting["admin"]["email"]).get(f"/api/chat/{cid}").status_code == 403


def db_all_files(app):
    import os
    root = app.state.settings.chat_upload_dir
    return os.listdir(root) if os.path.isdir(root) else []


def test_chat_ids_must_be_integers_and_forged_body_ids_are_rejected(app, chatting):
    sc = login_client(app, chatting["stu"]["email"])
    assert sc.get("/api/chat/abc").status_code == 400
    assert sc.get("/api/chat/99999").status_code == 404
    assert api_post(sc, "/api/chat/99999/messages", json={"message_text": "x"}).status_code == 404
    forged = {"message_text": "x", "sender_user_id": chatting["fac"]["user_id"], "chat_id": 1}
    assert api_post(sc, f"/api/chat/{chatting['chat_id']}/messages", json=forged).status_code == 400
    assert api_post(sc, f"/api/chat/messages/{chatting['message_id']}/edit",
                    json={"message_text": "x", "sender_user_id": 1}).status_code == 400
    assert db_one(app, "SELECT sender_user_id FROM messages")["sender_user_id"] == chatting["stu"]["user_id"]


def test_posting_to_someone_elses_chat_id_is_refused(app, chatting):
    s2 = create_student(app, "1AB21CS311", chatting["sid"])
    c = login_client(app, s2["email"])
    chat2 = api_post(c, "/api/chat/open", json={"faculty_id": chatting["fac"]["faculty_id"]}).json()["chat_id"]
    assert api_post(c, f"/api/chat/{chatting['chat_id']}/messages", json={"message_text": "wrong chat"}).status_code == 403
    assert db_count(app, "messages", "message_text = 'wrong chat'") == 0
    assert api_post(c, f"/api/chat/{chat2}/messages", json={"message_text": "my chat"}).status_code == 201
    assert db_count(app, "messages", "message_text = 'my chat'") == 1


def test_student_cannot_open_chat_or_meeting_with_unassigned_faculty(app, chatting):
    stranger = create_faculty(app, "FAC102")
    c = login_client(app, chatting["stu"]["email"])
    r = api_post(c, "/api/chat/open", json={"faculty_id": stranger["faculty_id"]})
    assert r.status_code == 403 and "permission" in r.json()["error"]["message"].lower()
    r = api_post(c, "/api/meetings", json={"faculty_id": stranger["faculty_id"], "reason": "let me in"})
    assert r.status_code == 403
    assert api_post(c, "/api/chat/open", json={"faculty_id": 99999}).status_code == 403
    assert api_post(c, "/api/meetings", json={"faculty_id": 99999, "reason": "x"}).status_code == 403
    assert db_count(app, "chats") == 1 and db_count(app, "meeting_requests") == 0


def test_faculty_cannot_open_chat_with_students_outside_their_classes(app, chatting):
    outsider = create_student(app, "1AB21CS312", section_id_for(app, "AIDE", "2nd Year", "C"))
    c = login_client(app, chatting["fac"]["email"])
    assert api_post(c, "/api/chat/open", json={"student_id": outsider["student_id"]}).status_code == 403
    assert api_post(c, "/api/chat/open", json={"student_id": 99999}).status_code == 403
    assert db_count(app, "chats") == 1


def test_removed_student_is_unreachable_but_history_is_kept(app, chatting):
    with app.app_context():
        aq.archive_student_registration(chatting["stu"]["student_id"])
    fc = login_client(app, chatting["fac"]["email"])
    assert api_post(fc, f"/api/chat/{chatting['chat_id']}/messages", json={"message_text": "hello ghost"}).status_code == 403
    assert fc.get(f"/api/chat/{chatting['chat_id']}").status_code == 403
    assert fc.get("/api/chat").json()["items"] == []
    assert fc.get(f"/api/faculty/classes/{chatting['sid']}").json()["students"] == []
    assert db_count(app, "messages") == 1  # history preserved


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

def test_student_reaches_faculty_outside_class_only_via_accepted_supporting(app, people):
    stranger = create_faculty(app, "FAC103")
    sc, fc = login_client(app, people["stu"]["email"]), login_client(app, stranger["email"])
    fid, stid = stranger["faculty_id"], people["stu"]["student_id"]
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fid}).status_code == 403
    r = api_post(sc, f"/api/supporting/faculty/{fid}/request")
    assert r.status_code == 201
    rel = r.json()["id"]
    assert r.json()["relationship"]["status"] == "PENDING" and r.json()["relationship"]["direction"] == "outgoing"
    # pending is not enough
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fid}).status_code == 403
    assert api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "x"}).status_code == 403
    assert api_post(fc, "/api/chat/open", json={"student_id": stid}).status_code == 403
    # the requester cannot accept their own request
    assert api_post(sc, f"/api/supporting/{rel}/accept").status_code == 403
    # accepted by the addressed faculty -> both directions open
    r = api_post(fc, f"/api/supporting/{rel}/accept")
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fid}).status_code == 200
    assert api_post(fc, "/api/chat/open", json={"student_id": stid}).status_code == 200
    assert api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": "x"}).status_code == 201
    # the faculty dashboard lists the supporting student
    assert [s["usn"] for s in fc.get("/api/faculty/dashboard").json()["supporting_students"]] == ["1AB21CS300"]


def test_other_faculty_and_students_cannot_act_on_a_meeting(app, chatting):
    mid = db_meeting(app, chatting)
    other_f = create_faculty(app, "FAC104")
    assign(app, other_f, chatting["sid"], chatting["admin"]["user_id"])
    other_s = create_student(app, "1AB21CS320", chatting["sid"])
    fc, sc = login_client(app, other_f["email"]), login_client(app, other_s["email"])
    assert api_post(fc, f"/api/meetings/{mid}/respond",
                    json={"decision": "accept", "meeting_time_text": "now"}).status_code == 403
    assert api_post(sc, f"/api/meetings/{mid}/cancel", json={"reason": "mine now"}).status_code == 403
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"
    r = login_client(app, chatting["fac"]["email"])
    assert api_post(r, f"/api/meetings/{mid}/respond",
                    json={"decision": "accept", "meeting_time_text": "Mon"}).status_code == 200
    for c in (fc, sc):
        assert api_post(c, f"/api/meetings/{mid}/complete").status_code == 403
        assert api_post(c, f"/api/meetings/{mid}/cancel", json={"reason": "x"}).status_code == 403
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "ACCEPTED"
    assert sc.get("/api/meetings").json()["items"] == []


def db_meeting(app, chatting):
    with app.app_context():
        return meeting_service.request_meeting(chatting["stu"]["student_id"], chatting["fac"]["faculty_id"], "Doubt", "")


# ---------------------------------------------------------------------------
# supporting relationships
# ---------------------------------------------------------------------------

def test_supporting_request_by_faculty_limited_to_assigned_classes(app, people):
    outsider = create_student(app, "1AB21CS330", section_id_for(app, "AIDE", "2nd Year", "C"))
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    c = login_client(app, people["fac"]["email"])
    r = api_post(c, f"/api/supporting/students/{outsider['student_id']}/request")
    assert r.status_code == 403 and "assigned classes" in r.json()["error"]["message"]
    assert api_post(c, "/api/supporting/students/99999/request").status_code == 404
    assert db_count(app, "supporting_relationships") == 0
    assert api_post(c, f"/api/supporting/students/{people['stu']['student_id']}/request").status_code == 201
    assert db_count(app, "supporting_relationships") == 1
    r = api_post(c, f"/api/supporting/students/{people['stu']['student_id']}/request")
    assert r.status_code == 409 and "already exists" in r.json()["error"]["message"]


def test_only_the_addressed_party_can_answer_a_supporting_request(app, people):
    other_s = create_student(app, "1AB21CS331", people["sid"])
    other_f = create_faculty(app, "FAC105")
    with app.app_context():
        rel = supporting_service.student_request_faculty(people["stu"]["student_id"], people["fac"]["faculty_id"])
    sc, oc, fc = (login_client(app, x["email"]) for x in (people["stu"], other_f, people["fac"]))
    osc = login_client(app, other_s["email"])
    for c in (sc, oc, osc):  # requester, an unrelated faculty, an unrelated student
        assert api_post(c, f"/api/supporting/{rel}/accept").status_code == 403
        assert api_post(c, f"/api/supporting/{rel}/reject").status_code == 403
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "PENDING"
    assert api_post(fc, f"/api/supporting/{rel}/accept").status_code == 200
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"
    r = api_post(fc, f"/api/supporting/{rel}/reject")
    assert r.status_code == 409 and "already" in r.json()["error"]["message"]
    for c in (sc, oc, osc):  # authorisation is checked before the state: no status oracle for outsiders
        assert api_post(c, f"/api/supporting/{rel}/reject").status_code == 403
    assert api_post(fc, "/api/supporting/99999/accept").status_code == 404
    # relationship listings are private
    assert oc.get("/api/supporting").json()["items"] == [] and osc.get("/api/supporting").json()["items"] == []
    assert len(fc.get("/api/supporting").json()["items"]) == 1


def test_student_cannot_answer_a_request_addressed_to_another_student(app, people):
    other_s = create_student(app, "1AB21CS332", people["sid"])
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    with app.app_context():
        rel = supporting_service.faculty_request_student(people["fac"]["faculty_id"], other_s["student_id"])
    c = login_client(app, people["stu"]["email"])
    assert api_post(c, f"/api/supporting/{rel}/accept").status_code == 403
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "PENDING"
    # the requesting faculty cannot accept it on the student's behalf either
    assert api_post(login_client(app, people["fac"]["email"]), f"/api/supporting/{rel}/accept").status_code == 403
    r = api_post(login_client(app, other_s["email"]), f"/api/supporting/{rel}/accept")
    assert r.status_code == 200
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"


def test_reject_then_re_request_reopens_the_same_row(app, people):
    fid, stid = people["fac"]["faculty_id"], people["stu"]["student_id"]
    sc, fc = login_client(app, people["stu"]["email"]), login_client(app, people["fac"]["email"])
    rel = api_post(sc, f"/api/supporting/faculty/{fid}/request").json()["id"]
    assert api_post(fc, f"/api/supporting/{rel}/reject").json()["status"] == "REJECTED"
    assert sc.get("/api/supporting/faculty/search?q=FAC100").json()["items"][0]["can_request"] is True
    again = api_post(sc, f"/api/supporting/faculty/{fid}/request")
    assert again.status_code == 201 and again.json()["id"] == rel
    assert again.json()["relationship"]["status"] == "PENDING"
    assert db_count(app, "supporting_relationships") == 1
    # ...also when the OTHER side re-asks after a rejection: requested_by flips and the student must answer
    assert api_post(fc, f"/api/supporting/{rel}/reject").status_code == 200
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    r = api_post(fc, f"/api/supporting/students/{stid}/request")
    assert r.status_code == 201 and r.json()["id"] == rel
    assert db_one(app, "SELECT requested_by, status FROM supporting_relationships") == {
        "requested_by": "FACULTY", "status": "PENDING"}
    assert api_post(fc, f"/api/supporting/{rel}/accept").status_code == 403
    assert api_post(sc, f"/api/supporting/{rel}/accept").status_code == 200
    assert api_post(sc, f"/api/supporting/faculty/{fid}/request").status_code == 409  # accepted: nothing to re-request


def test_supporting_search_shapes_and_unknown_targets(app, people):
    sc = login_client(app, people["stu"]["email"])
    create_faculty(app, "FAC106", name="Ada Lovelace")
    items = sc.get("/api/supporting/faculty/search?q=lovelace").json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["faculty_code"] == "FAC106" and item["relationship"] is None and item["has_access"] is False
    assert item["can_request"] is True and item["access_via"] is None
    assert sc.get("/api/supporting/faculty/search?q=").json()["items"] == []
    assert sc.get("/api/supporting/faculty/search?q=%25").json()["items"] == []  # '%' is a literal, not a wildcard
    assert api_post(sc, "/api/supporting/faculty/99999/request").status_code == 404
    assert db_count(app, "supporting_relationships") == 0


# ---------------------------------------------------------------------------
# permission (profile-change) requests
# ---------------------------------------------------------------------------

def test_faculty_cannot_decide_faculty_profile_change_requests(app, people):
    other_f = create_faculty(app, "FAC107")
    fc = login_client(app, people["fac"]["email"])
    r = api_post(fc, "/api/faculty/profile/change-request", json={"department": "AIDE", "reason": "moving"})
    assert r.status_code == 201
    rid = r.json()["id"]
    oc = login_client(app, other_f["email"])
    assert api_post(oc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    assert api_post(fc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    assert fc.get("/api/faculty/permission-requests").json()["items"] == []  # their own request is not theirs to review
    assert db_one(app, "SELECT department FROM faculty WHERE id = ?", (people["fac"]["faculty_id"],))["department"] == "AIML"
    mine = fc.get("/api/faculty/profile").json()["change_requests"]
    assert mine[0]["requested_changes"] == {"department": "AIDE"} and mine[0]["status"] == "PENDING"
    with app.app_context():  # the Admin's decision still works
        permission_service.decide_permission_request(rid, people["admin"]["user_id"], True)
    assert db_one(app, "SELECT department FROM faculty WHERE id = ?", (people["fac"]["faculty_id"],))["department"] == "AIDE"


def test_faculty_profile_change_validates_department_and_fields(app, people):
    fc = login_client(app, people["fac"]["email"])
    url = "/api/faculty/profile/change-request"
    r = api_post(fc, url, json={"department": "Underwater Basket Weaving", "reason": "x"})
    assert r.status_code == 400 and "department" in r.json()["error"]["message"].lower()
    assert api_post(fc, url, json={"reason": "nothing to change"}).status_code == 400
    assert api_post(fc, url, json={"faculty_code": "HACK", "full_name": "Hacked", "reason": "x"}).status_code == 400
    assert api_post(fc, url, json={"department": "AIDE"}).status_code == 400  # reason is required
    assert api_post(fc, url, json={"department": "AIDE", "reason": "  "}).status_code == 400
    r = api_post(fc, url, json={"professional_email": "not-an-email", "reason": "x"})
    assert r.status_code == 400 and "professional_email" in r.json()["error"]["fields"]
    taken = create_faculty(app, "FAC108")
    r = api_post(fc, url, json={"professional_email": taken["email"], "reason": "x"})
    assert r.status_code in (400, 409)
    assert db_count(app, "permission_requests") == 0


def test_students_cannot_decide_or_see_requests_of_others(app, people):
    assign(app, people["fac"], people["sid"], people["admin"]["user_id"])
    other_s = create_student(app, "1AB21CS340", people["sid"])
    outsider_f = create_faculty(app, "FAC109")
    with app.app_context():
        rid = permission_service.student_request_profile_change(people["stu"]["user_id"], {"phone": "8000000000"}, "n")
    assert api_post(login_client(app, other_s["email"]),
                    f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    oc = login_client(app, outsider_f["email"])  # faculty of ANOTHER class
    assert oc.get("/api/faculty/permission-requests").json()["items"] == []
    assert api_post(oc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    fc = login_client(app, people["fac"]["email"])
    item = fc.get("/api/faculty/permission-requests").json()["items"][0]
    assert item["id"] == rid and item["requested_changes"] == {"phone": "8000000000"}
    assert item["student"]["usn"] == "1AB21CS300" and item["student"]["class"]["section"] == "A"
    assert api_post(fc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "maybe"}).status_code == 400
    r = api_post(fc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert db_one(app, "SELECT phone FROM students WHERE id = ?", (people["stu"]["student_id"],))["phone"] == "8000000000"
    assert api_post(fc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "reject"}).status_code == 409
    assert api_post(fc, "/api/faculty/permission-requests/99999/decide", json={"decision": "approve"}).status_code == 404


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------

def test_notifications_are_private_to_their_owner(app, people):
    from models import queries
    with app.app_context():
        nid = queries.create_notification(people["stu"]["user_id"], "TEST", "Secret", "for student only")
    fc = login_client(app, people["fac"]["email"])
    assert "for student only" not in fc.get("/api/notifications").text
    assert api_post(fc, f"/api/notifications/{nid}/read").status_code == 404
    api_post(fc, "/api/notifications/read-all")
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 0
    sc = login_client(app, people["stu"]["email"])
    assert "for student only" in sc.get("/api/notifications").text
    assert api_post(sc, f"/api/notifications/{nid}/read").status_code == 200
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (nid,))["is_read"] == 1
