"""/api/admin: dashboard, meetings, chats, permission requests and admin accounts (+ their authorisation).
The academic-structure / assignment / class-directory endpoints are covered in test_academic_hierarchy.py and
test_assignments.py."""
import pytest
from fastapi.testclient import TestClient

from models import queries
from services import chat_service, meeting_service, permission_service
from tests.conftest import (
    ADMIN_EMAIL, PASSWORD, api_login, api_post, create_admin, create_faculty, create_student, assign, login_client,
    section_id_for, db_one, db_all, db_count, db_exec,
)

ADMIN_GETS = ["/api/admin/dashboard", "/api/admin/students", "/api/admin/faculty", "/api/admin/meetings",
              "/api/admin/chats", "/api/admin/chats/1", "/api/admin/permission-requests", "/api/admin/admins"]
NEW_ADMIN = {"full_name": "Second Admin", "email": "Second.Admin@College.edu", "password": "Sup3rSecret!",
             "confirm_password": "Sup3rSecret!"}


def err(resp, status, code=None):
    assert resp.status_code == status, resp.text
    body = resp.json()["error"]
    if code:
        assert body["code"] == code, body
    assert body["message"]
    return body


@pytest.fixture
def world(app):
    admin_id = create_admin(app)
    sid = section_id_for(app)
    fac = create_faculty(app, "FAC001", name="Dr One")
    other = create_faculty(app, "FAC002", "IoT", name="Dr Two")
    stu = create_student(app, "1AB21CS001", sid, name="Asha Student")
    assign(app, fac, sid, admin_id)
    return {"admin": admin_id, "sid": sid, "fac": fac, "other": other, "stu": stu}


@pytest.fixture
def admin(app, world):
    return login_client(app, ADMIN_EMAIL)


# ---------------------------------------------------------------- authorisation

@pytest.mark.parametrize("path", ADMIN_GETS)
def test_admin_reads_require_admin_role(app, world, path):
    err(TestClient(app).get(path), 401, "unauthenticated")
    for who in (world["fac"], world["stu"]):
        err(login_client(app, who["email"]).get(path), 403, "forbidden")
    assert login_client(app, ADMIN_EMAIL).get(path).status_code in (200, 404)  # /chats/1 may not exist


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/admin/permission-requests/1/decide", {"decision": "approve"}),
    ("POST", "/api/admin/admins", NEW_ADMIN),
])
def test_admin_writes_require_admin_role_and_change_nothing(app, world, method, path, payload):
    before = db_count(app, "users")
    err(TestClient(app).request(method, path, json=payload), 401, "unauthenticated")
    for who in (world["fac"], world["stu"]):
        err(login_client(app, who["email"]).request(method, path, json=payload), 403, "forbidden")
    assert db_count(app, "users") == before


def test_a_forged_session_cookie_does_not_grant_admin(app, world):
    c = TestClient(app)
    c.cookies.set("cc_session", "forged.value.here")
    err(c.get("/api/admin/dashboard"), 401, "unauthenticated")


def test_role_comes_from_the_database_not_the_session(app, world, admin):
    """Demoting the account in the database takes effect on the very next request."""
    assert admin.get("/api/admin/dashboard").status_code == 200
    db_exec(app, "UPDATE users SET role = 'STUDENT' WHERE id = ?", (world["admin"],))
    assert admin.get("/api/admin/dashboard").status_code == 403


def test_deactivated_admin_is_locked_out(app, world, admin):
    db_exec(app, "UPDATE users SET is_active = 0 WHERE id = ?", (world["admin"],))
    err(admin.get("/api/admin/dashboard"), 401, "unauthenticated")


# ---------------------------------------------------------------- dashboard

def test_dashboard_stats(app, world, admin):
    stats = admin.get("/api/admin/dashboard").json()["stats"]
    assert stats == {
        "student_count": 1, "removed_student_count": 0, "unmapped_student_count": 0, "faculty_count": 2,
        "admin_count": 1, "meeting_count": 0, "pending_permission_count": 0, "pending_assignment_count": 0,
        "class_count": 72,
    }
    with app.app_context():
        meeting_service.request_meeting(world["stu"]["student_id"], world["fac"]["faculty_id"], "Doubt", "")
        permission_service.faculty_request_profile_change(world["fac"]["user_id"], {"department": "IoT"}, "moved")
        from services import assignment_service
        assignment_service.faculty_request(world["other"]["faculty_id"], world["sid"])
    api_post(admin, f"/api/admin/students/{world['stu']['student_id']}/remove-registration")
    stats = admin.get("/api/admin/dashboard").json()["stats"]
    assert (stats["meeting_count"], stats["pending_permission_count"], stats["pending_assignment_count"]) == (1, 1, 1)
    assert (stats["student_count"], stats["removed_student_count"]) == (0, 1)
    # deactivating a section lowers the active class count
    api_post(admin, f"/api/admin/academics/section/{section_id_for(app, 'IoT', '1st Year', 'C')}/active",
             json={"active": False})
    assert admin.get("/api/admin/dashboard").json()["stats"]["class_count"] == 71


# ---------------------------------------------------------------- meetings

def test_meetings_list_carries_names_class_and_status(app, world, admin):
    with app.app_context():
        m1 = meeting_service.request_meeting(world["stu"]["student_id"], world["fac"]["faculty_id"], "Doubt", "msg")
        m2 = meeting_service.request_meeting(world["stu"]["student_id"], world["fac"]["faculty_id"], "Project", "")
        meeting_service.respond_to_meeting(m2, world["fac"]["faculty_id"], True, "Sure", "Mon 10am")
    data = admin.get("/api/admin/meetings").json()
    assert data["total"] == 2 and [m["id"] for m in data["items"]] == [m2, m1]  # newest first
    first = data["items"][1]
    assert first["status"] == "PENDING" and first["reason"] == "Doubt" and first["student_message"] == "msg"
    assert first["student"] == {"id": world["stu"]["student_id"], "full_name": "Asha Student",
                                "usn": "1AB21CS001", "profile_picture_url": None,
                                "class": {"section_id": world["sid"], "branch": "CSE", "department": "AIML",
                                          "year": "3rd Year", "section": "A",
                                          "label": "CSE → AIML → 3rd Year → A"}}
    assert first["faculty"]["faculty_code"] == "FAC001" and first["faculty"]["full_name"] == "Dr One"
    accepted = data["items"][0]
    assert accepted["status"] == "ACCEPTED" and accepted["meeting_time_text"] == "Mon 10am"
    assert accepted["faculty_response"] == "Sure" and accepted["responded_at"]
    assert {"requested_at", "completed_at", "cancelled_at", "cancelled_by", "cancellation_reason"} <= set(accepted)
    # filter
    assert [m["id"] for m in admin.get("/api/admin/meetings?status=accepted").json()["items"]] == [m2]
    assert admin.get("/api/admin/meetings?status=COMPLETED").json()["items"] == []
    err(admin.get("/api/admin/meetings?status=nope"), 400, "validation_error")


# ---------------------------------------------------------------- chats

def test_chats_list_and_read_only_detail(app, world, admin):
    stu, fac = world["stu"], world["fac"]
    with app.app_context():
        chat = chat_service.open_chat(stu["student_id"], fac["faculty_id"], stu["user_id"])
        chat_service.send_text_message(chat["id"], stu["user_id"], "hello sir")
        chat_service.send_text_message(chat["id"], fac["user_id"], "hello")
        queries.create_message(chat["id"], stu["user_id"], None, "chat/abc123.png", "image", "notes.png")
    data = admin.get("/api/admin/chats").json()
    assert data["total"] == 1
    row = data["items"][0]
    assert row["id"] == chat["id"] and row["message_count"] == 3
    assert row["student"]["full_name"] == "Asha Student" and row["student"]["usn"] == "1AB21CS001"
    assert row["student"]["class"]["label"] == "CSE → AIML → 3rd Year → A"
    assert row["faculty"]["faculty_code"] == "FAC001" and row["last_message_at"]

    detail = admin.get(f"/api/admin/chats/{chat['id']}").json()
    assert detail["chat"]["message_count"] == 3 and detail["chat"]["student"]["id"] == stu["student_id"]
    msgs = detail["messages"]
    assert [(m["sender_role"], m["message_text"]) for m in msgs] == [
        ("STUDENT", "hello sir"), ("FACULTY", "hello"), ("STUDENT", None)]
    assert msgs[0]["sender_name"] == "Asha Student" and msgs[1]["sender_name"] == "Dr One"
    assert msgs[2]["attachment_url"] == "/uploads/chat/abc123.png" and msgs[2]["attachment_name"] == "notes.png"
    assert msgs[0]["attachment_url"] is None and msgs[0]["is_seen"] is False and msgs[0]["is_edited"] is False
    assert {"id", "sender_user_id", "attachment_type", "seen_at", "created_at"} <= set(msgs[0])
    err(admin.get("/api/admin/chats/99999"), 404, "not_found")
    err(admin.get("/api/admin/chats/abc"), 400, "validation_error")
    # read-only: no mutating method exists on a chat
    for method in ("post", "put", "patch", "delete"):
        assert getattr(admin, method)(f"/api/admin/chats/{chat['id']}").status_code in (403, 400, 405, 404)
    assert db_count(app, "messages") == 3


def test_admin_reading_a_chat_does_not_mark_messages_seen(app, world, admin):
    stu, fac = world["stu"], world["fac"]
    with app.app_context():
        chat = chat_service.open_chat(stu["student_id"], fac["faculty_id"], stu["user_id"])
        chat_service.send_text_message(chat["id"], stu["user_id"], "unread")
    admin.get(f"/api/admin/chats/{chat['id']}")
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 0


# ---------------------------------------------------------------- permission requests

def test_faculty_profile_change_request_listing_and_decision(app, world, admin):
    fac = world["fac"]
    with app.app_context():
        rid = permission_service.faculty_request_profile_change(
            fac["user_id"], {"department": "IoT", "professional_email": "new.dr@college.edu", "bogus": "x"}, "moved")
    data = admin.get("/api/admin/permission-requests").json()
    assert data["total"] == 1 and data["pending"] == 1
    item = data["items"][0]
    assert item["id"] == rid and item["request_type"] == "FACULTY_PROFILE_CHANGE" and item["status"] == "PENDING"
    assert item["requested_changes"] == {"department": "IoT", "professional_email": "new.dr@college.edu"}
    assert item["reason"] == "moved" and item["can_decide"] is True and item["reviewed_at"] is None
    assert item["requester"] == {"user_id": fac["user_id"], "full_name": "Dr One", "role": "FACULTY", "usn": None,
                                 "faculty_code": "FAC001", "profile_picture_url": None}
    assert item["approver"]["user_id"] == world["admin"]

    err(api_post(admin, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "maybe"}), 400,
        "validation_error")
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"

    resp = api_post(admin, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "approve"})
    assert resp.status_code == 200 and resp.json() == {"ok": True, "message": "Request approved.",
                                                       "status": "APPROVED"}
    fac_row = db_one(app, "SELECT * FROM faculty WHERE id = ?", (fac["faculty_id"],))
    assert (fac_row["department"], fac_row["professional_email"]) == ("IoT", "new.dr@college.edu")
    assert "Profile change request approved" in [
        r["title"] for r in db_all(app, "SELECT title FROM notifications WHERE user_id = ?", (fac["user_id"],))]
    after = admin.get("/api/admin/permission-requests").json()
    assert after["pending"] == 0 and after["items"][0]["can_decide"] is False and after["items"][0]["reviewed_at"]
    err(api_post(admin, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "reject"}), 409, "conflict")
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "APPROVED"
    err(api_post(admin, "/api/admin/permission-requests/99999/decide", json={"decision": "approve"}), 404, "not_found")


def test_rejecting_a_faculty_request_changes_nothing(app, world, admin):
    fac = world["fac"]
    with app.app_context():
        rid = permission_service.faculty_request_profile_change(fac["user_id"], {"department": "IoT"})
    assert api_post(admin, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "reject"}).json()[
        "status"] == "REJECTED"
    assert db_one(app, "SELECT department FROM faculty WHERE id = ?", (fac["faculty_id"],))["department"] == "AIML"


def test_student_request_item_shows_usn_and_is_listed_after_pending_ones(app, world, admin):
    with app.app_context():
        student_req = permission_service.student_request_profile_change(world["stu"]["user_id"], {"phone": "7000000000"})
        faculty_req = permission_service.faculty_request_profile_change(world["fac"]["user_id"], {"department": "IoT"})
        queries.decide_permission_request(student_req, "REJECTED")
    items = admin.get("/api/admin/permission-requests").json()["items"]
    assert [i["id"] for i in items] == [faculty_req, student_req]  # pending first
    s = items[1]
    assert s["requester"]["usn"] == "1AB21CS001" and s["requester"]["role"] == "STUDENT"
    assert s["requested_changes"] == {"phone": "7000000000"} and s["can_decide"] is False


# ---------------------------------------------------------------- admin accounts

def test_admins_list_and_create(app, world, admin):
    data = admin.get("/api/admin/admins").json()
    assert data["total"] == 1
    me = data["items"][0]
    assert me["email"] == ADMIN_EMAIL and me["is_you"] is True and me["is_active"] is True
    assert "password_hash" not in me and {"id", "full_name", "created_at", "last_login_at",
                                          "profile_picture_url"} <= set(me)

    resp = api_post(admin, "/api/admin/admins", json=NEW_ADMIN)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] and body["message"] == "Admin account created."
    assert body["admin"]["email"] == "second.admin@college.edu" and body["admin"]["is_you"] is False  # lower-cased
    row = db_one(app, "SELECT * FROM users WHERE email = 'second.admin@college.edu'")
    assert row["role"] == "ADMIN" and row["is_active"] == 1 and row["password_hash"] != NEW_ADMIN["password"]
    assert [a["email"] for a in admin.get("/api/admin/admins").json()["items"]] == [
        ADMIN_EMAIL, "second.admin@college.edu"]

    # the new admin can sign in and use the console
    other = TestClient(app)
    api_login(other, "second.admin@college.edu", NEW_ADMIN["password"])
    assert other.get("/api/admin/dashboard").status_code == 200
    assert other.get("/api/admin/admins").json()["items"][1]["is_you"] is True


def test_create_admin_email_must_be_unique_case_insensitively(app, world, admin):
    before = db_count(app, "users")
    for email in (ADMIN_EMAIL, ADMIN_EMAIL.upper(), world["fac"]["email"], world["stu"]["email"]):
        body = err(api_post(admin, "/api/admin/admins", json={**NEW_ADMIN, "email": email}), 409, "conflict")
        assert "email" in body["fields"]
    assert db_count(app, "users") == before


@pytest.mark.parametrize("patch,field", [
    ({"password": "short1A", "confirm_password": "short1A"}, "password"),
    ({"password": "alllowercase1", "confirm_password": "alllowercase1"}, "password"),
    ({"password": "NoDigitsHere", "confirm_password": "NoDigitsHere"}, "password"),
    ({"password": "NOLOWER123", "confirm_password": "NOLOWER123"}, "password"),
    ({"confirm_password": "Different1!"}, "confirm_password"),
    ({"email": "not-an-email"}, "email"),
    ({"email": ""}, "email"),
    ({"full_name": "   "}, "full_name"),
    ({"password": "Aa1" + "x" * 126, "confirm_password": "Aa1" + "x" * 126}, "password"),
])
def test_create_admin_validation(app, world, admin, patch, field):
    before = db_count(app, "users")
    body = err(api_post(admin, "/api/admin/admins", json={**NEW_ADMIN, **patch}), 400, "validation_error")
    assert field in body["fields"]
    assert db_count(app, "users") == before


def test_create_admin_rejects_unknown_and_missing_fields(app, world, admin):
    err(api_post(admin, "/api/admin/admins", json={**NEW_ADMIN, "role": "STUDENT"}), 400, "validation_error")
    err(api_post(admin, "/api/admin/admins", json={"email": "a@b.co"}), 400, "validation_error")
    err(api_post(admin, "/api/admin/admins", json={**NEW_ADMIN, "email": 5}), 400, "validation_error")
    assert db_count(app, "users", "role = 'ADMIN'") == 1


def test_admin_password_may_not_equal_the_email_local_part(app, world, admin):
    body = err(api_post(admin, "/api/admin/admins", json={
        **NEW_ADMIN, "email": "Passw0rd1@college.edu", "password": "Passw0rd1", "confirm_password": "Passw0rd1"}),
        400, "validation_error")
    assert "password" in body["fields"]
