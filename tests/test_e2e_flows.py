"""End-to-end journeys through the HTTP API (TestClient + real signed session cookies).

Everything here goes through ``/api/*`` exactly like the React SPA does. Setup that the product does
not expose over HTTP (the first admin) is created through the services.
"""
import base64
import io

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.conftest import (
    PASSWORD, api_login, api_post, csrf_token, db_all, db_count, db_one, find_section, http_faculty_signup,
    http_student_signup, login_client, make_admin, make_settings, register_faculty, register_student, assign, unassign,
)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")


def err(resp):
    return resp.json()["error"]


@pytest.fixture
def campus(app):
    """An admin (service level) plus the id of the seeded CSE / AIML / 3rd Year / A section."""
    return {"admin_id": make_admin(app), "admin_email": "admin@college.edu",
            "sid": find_section("CSE", "AIML", "3rd Year", "A", app=app)}


def anon(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# signup + login
# ---------------------------------------------------------------------------

def test_student_signup_otp_register_then_login_by_email_and_usn(app, client, campus):
    # step 1: start -> demo OTP is returned because there is no SMTP configured
    email = "e2e.student@college.edu"
    start = api_post(client, "/api/auth/signup/student/start", json={"college_email": email})
    assert start.status_code == 200
    body = start.json()
    assert body["ok"] and body["delivery"] == "demo" and len(body["demo_otp"]) == 6

    # registering before verifying the OTP is refused
    payload = {"college_email": email, "full_name": "E2E Student", "usn": "1AB21CS500",
               "section_id": campus["sid"], "phone": "9876543210", "personal_email": "e2e@example.com",
               "password": PASSWORD, "confirm_password": PASSWORD}
    early = api_post(client, "/api/auth/signup/student/register", json=payload)
    assert early.status_code == 403 and err(early)["code"] == "otp_not_verified"

    # a wrong OTP is a field error, the right one verifies
    wrong = api_post(client, "/api/auth/signup/student/verify", json={"college_email": email, "otp": "000000"})
    if body["demo_otp"] == "000000":  # pragma: no cover - 1 in a million
        wrong = api_post(client, "/api/auth/signup/student/verify", json={"college_email": email, "otp": "111111"})
    assert wrong.status_code == 400 and "otp" in err(wrong).get("fields", {})
    verify = api_post(client, "/api/auth/signup/student/verify",
                      json={"college_email": email, "otp": body["demo_otp"]})
    assert verify.status_code == 200, verify.text

    # step 3: register with the admin-defined section id
    reg = api_post(client, "/api/auth/signup/student/register", json=payload)
    assert reg.status_code == 201, reg.text
    student = db_one(app, "SELECT * FROM students WHERE usn = '1AB21CS500'")
    assert student["section_id"] == campus["sid"]
    assert (student["branch"], student["department"], student["year"], student["section"]) == (
        "CSE", "AIML", "3rd Year", "A")

    # the same OTP cannot be used to register a second account
    again = api_post(client, "/api/auth/signup/student/register", json={**payload, "usn": "1AB21CS501"})
    assert again.status_code in (400, 403)

    # login by college email AND by USN (case-insensitive), each in a fresh browser
    by_email = TestClient(app)
    login = api_login(by_email, email)
    assert login["user"]["role"] == "STUDENT" and login["user"]["student_id"] == student["id"]
    by_usn = TestClient(app)
    assert api_login(by_usn, "1ab21cs500")["user"]["email"] == email
    assert api_login(TestClient(app), "1AB21CS500")["user"]["role"] == "STUDENT"

    session = by_email.get("/api/auth/session").json()
    assert session["authenticated"] and session["user"]["full_name"] == "E2E Student"
    assert session["csrf_token"]


def test_student_signup_validation_errors(app, client, campus):
    email = "bad.student@college.edu"
    otp = api_post(client, "/api/auth/signup/student/start", json={"college_email": email}).json()["demo_otp"]
    api_post(client, "/api/auth/signup/student/verify", json={"college_email": email, "otp": otp})
    base = {"college_email": email, "full_name": "Bad", "usn": "1AB21CS510", "section_id": campus["sid"],
            "phone": "9876543210", "personal_email": "b@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD}
    mismatch = api_post(client, "/api/auth/signup/student/register", json={**base, "confirm_password": "Other1!aaa"})
    assert mismatch.status_code == 400 and "confirm_password" in err(mismatch)["fields"]
    weak = api_post(client, "/api/auth/signup/student/register",
                    json={**base, "password": "abc", "confirm_password": "abc"})
    assert weak.status_code == 400
    nosection = api_post(client, "/api/auth/signup/student/register", json={**base, "section_id": 999999})
    assert nosection.status_code == 400
    missing = api_post(client, "/api/auth/signup/student/register", json={"college_email": email})
    assert missing.status_code == 400 and err(missing)["code"] == "validation_error"
    # nothing was created by the failed attempts
    assert db_count(app, "students") == 0


def test_faculty_signup_then_login_by_faculty_id_and_email(app, client):
    resp = http_faculty_signup(client, "FAC900", department="AIML")
    assert resp.status_code == 201, resp.text
    row = db_one(app, "SELECT * FROM faculty WHERE faculty_code = 'FAC900'")
    assert row and row["department"] == "AIML"

    by_code = TestClient(app)
    login = api_login(by_code, "FAC900")
    assert login["user"]["role"] == "FACULTY" and login["user"]["faculty_id"] == row["id"]
    assert api_login(TestClient(app), "fac900@college.edu")["user"]["role"] == "FACULTY"
    # a duplicate Faculty ID is a conflict
    dup = http_faculty_signup(TestClient(app), "FAC900", extra={"professional_email": "other@college.edu"})
    assert dup.status_code in (400, 409)
    # wrong password: one generic 401
    bad = api_post(TestClient(app), "/api/auth/login", json={"identifier": "FAC900", "password": "nope"})
    assert bad.status_code == 401 and err(bad)["code"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# student area
# ---------------------------------------------------------------------------

def test_student_dashboard_empty_then_lists_assigned_faculty(app, campus):
    stu = register_student(app, "1AB21CS600", campus["sid"])
    fac = register_faculty(app, "FAC600")
    sc = login_client(app, stu["email"])

    empty = sc.get("/api/student/dashboard")
    assert empty.status_code == 200
    data = empty.json()
    assert data["assigned_faculty"] == [] and data["supporting_faculty"] == []
    assert data["pending_supporting_requests"] == [] and data["recent_meetings"] == []
    assert data["counts"]["assigned_faculty"] == 0
    assert data["student"]["usn"] == "1AB21CS600"
    assert data["student"]["class"] == {
        "section_id": campus["sid"], "branch": "CSE", "department": "AIML", "year": "3rd Year",
        "section": "A", "label": "CSE → AIML → 3rd Year → A"}

    # an unassigned faculty never shows up; the admin assignment makes it appear
    assign(app, fac, campus["sid"], campus["admin_id"])
    data = sc.get("/api/student/dashboard").json()
    assert [f["faculty_code"] for f in data["assigned_faculty"]] == ["FAC600"]
    card = data["assigned_faculty"][0]
    assert card["id"] == fac["faculty_id"] and card["full_name"] == "Prof FAC600"
    assert card["profile_picture_url"] is None and card["department"] == "AIML"
    assert data["counts"]["assigned_faculty"] == 1

    profile = sc.get("/api/student/profile").json()
    assert profile["student"]["phone"] == "9999999999"
    assert [f["faculty_code"] for f in profile["assigned_faculty"]] == ["FAC600"]
    assert profile["permission_requests"] == []


def test_student_profile_picture_upload_and_rejects(app, campus):
    stu = register_student(app, "1AB21CS601", campus["sid"])
    sc = login_client(app, stu["email"])
    ok_resp = api_post(sc, "/api/student/profile/picture",
                       files={"profile_picture": ("me.png", io.BytesIO(PNG), "image/png")})
    assert ok_resp.status_code == 200, ok_resp.text
    url = ok_resp.json()["profile_picture_url"]
    assert url.startswith("/uploads/profile/students/") and url.endswith(".png")
    assert sc.get("/api/student/profile").json()["student"]["profile_picture_url"] == url
    assert sc.get("/api/auth/session").json()["user"]["profile_picture_url"] == url
    assert sc.get(url).status_code == 200                      # signed-in users can load it
    assert anon(app).get(url).status_code == 401               # anonymous cannot

    # an "image" that is really text, a bad type and a missing part leave the picture untouched
    fake = api_post(sc, "/api/student/profile/picture",
                    files={"profile_picture": ("evil.png", io.BytesIO(b"not an image"), "image/png")})
    assert fake.status_code == 400
    exe = api_post(sc, "/api/student/profile/picture",
                   files={"profile_picture": ("evil.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")})
    assert exe.status_code == 400
    assert api_post(sc, "/api/student/profile/picture").status_code == 400
    assert sc.get("/api/student/profile").json()["student"]["profile_picture_url"] == url


def test_student_profile_change_request_rules(app, campus):
    stu = register_student(app, "1AB21CS602", campus["sid"])
    sc = login_client(app, stu["email"])

    # no faculty assigned: the request cannot be routed
    nobody = api_post(sc, "/api/student/profile/change-request", json={"phone": "9876500000", "reason": "x"})
    assert nobody.status_code == 400 and "faculty" in err(nobody)["message"].lower()

    fac = register_faculty(app, "FAC602")
    assign(app, fac, campus["sid"], campus["admin_id"])
    # the class can NEVER be changed by the student, whatever the field is called
    for field in ("branch", "department", "year", "section", "section_id", "usn"):
        resp = api_post(sc, "/api/student/profile/change-request", json={field: "X", "reason": "please"})
        assert resp.status_code == 400, field
        assert field in err(resp)["fields"] and "administrator" in err(resp)["message"]
    assert db_count(app, "permission_requests") == 0

    # nothing to change / missing reason / invalid values / unknown keys
    assert api_post(sc, "/api/student/profile/change-request", json={"reason": "x"}).status_code == 400
    assert api_post(sc, "/api/student/profile/change-request", json={"phone": "9876500000"}).status_code == 400
    assert api_post(sc, "/api/student/profile/change-request",
                    json={"phone": "12", "reason": "x"}).status_code == 400
    assert api_post(sc, "/api/student/profile/change-request",
                    json={"personal_email": "nope", "reason": "x"}).status_code == 400
    assert api_post(sc, "/api/student/profile/change-request",
                    json={"phone": "9876500000", "reason": "x", "role": "ADMIN"}).status_code == 400

    ok_resp = api_post(sc, "/api/student/profile/change-request",
                       json={"phone": "9876500000", "personal_email": "New@Example.com", "reason": "Changed SIM"})
    assert ok_resp.status_code == 201 and ok_resp.json()["ok"] is True
    history = sc.get("/api/student/profile").json()["permission_requests"]
    assert len(history) == 1
    assert history[0]["status"] == "PENDING" and history[0]["reason"] == "Changed SIM"
    assert history[0]["requested_changes"] == {"phone": "9876500000", "personal_email": "new@example.com"}
    # the student record is NOT changed until a faculty approves
    assert db_one(app, "SELECT phone FROM students WHERE usn = '1AB21CS602'")["phone"] == "9999999999"


def test_logout_ends_the_session_and_roles_are_enforced(app, campus):
    stu = register_student(app, "1AB21CS603", campus["sid"])
    fac = register_faculty(app, "FAC603")
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])

    # anonymous: 401 everywhere that needs a session
    for path in ("/api/student/dashboard", "/api/student/profile", "/api/notifications"):
        resp = anon(app).get(path)
        assert resp.status_code == 401 and err(resp)["code"] == "unauthenticated", path

    # faculty / admin are not students
    admin = login_client(app, campus["admin_email"])
    for client in (fc, admin):
        assert client.get("/api/student/dashboard").status_code == 403
        assert client.get("/api/student/profile").status_code == 403
        assert api_post(client, "/api/student/profile/change-request",
                        json={"phone": "9876500000", "reason": "x"}).status_code == 403
    assert err(fc.get("/api/student/dashboard"))["code"] == "forbidden"

    assert sc.get("/api/student/dashboard").status_code == 200
    out = api_post(sc, "/api/auth/logout")
    assert out.status_code == 200 and out.json()["csrf_token"]
    assert sc.get("/api/student/dashboard").status_code == 401
    assert sc.get("/api/auth/session").json()["authenticated"] is False
    # an old copy of the cookie cannot be replayed after sign-out? (cookie sessions: the client dropped the
    # state, so the server sees an empty session)
    assert sc.get("/api/notifications").status_code == 401


def test_csrf_is_enforced_for_a_full_student_flow(tmp_path):
    app = create_app(make_settings(tmp_path, csrf_enabled=True))
    admin_id = make_admin(app)
    sid = find_section(app=app)
    stu = register_student(app, "1AB21CS604", sid)
    fac = register_faculty(app, "FAC604")
    assign(app, fac, sid, admin_id)

    c = TestClient(app)
    token = c.get("/api/auth/session").json()["csrf_token"]
    body = {"identifier": stu["email"], "password": PASSWORD}
    assert c.post("/api/auth/login", json=body).status_code == 400        # no token
    resp = c.post("/api/auth/login", json=body, headers={"X-CSRFToken": token})
    assert resp.status_code == 200
    fresh = resp.json()["csrf_token"]
    assert fresh != token                                                   # rotated on login
    # reads need no token
    assert c.get("/api/student/dashboard").status_code == 200

    change = {"phone": "9876500001", "reason": "csrf check"}
    missing = c.post("/api/student/profile/change-request", json=change)
    assert missing.status_code == 400 and err(missing)["code"] == "csrf_failed"
    stale = c.post("/api/student/profile/change-request", json=change, headers={"X-CSRFToken": token})
    assert stale.status_code == 400 and err(stale)["code"] == "csrf_failed"
    assert db_count(app, "permission_requests") == 0
    good = c.post("/api/student/profile/change-request", json=change, headers={"X-CSRFToken": fresh})
    assert good.status_code == 201
    # multipart uploads need the header too
    files = {"profile_picture": ("me.png", io.BytesIO(PNG), "image/png")}
    assert c.post("/api/student/profile/picture", files=files).status_code == 400
    files = {"profile_picture": ("me.png", io.BytesIO(PNG), "image/png")}
    assert c.post("/api/student/profile/picture", files=files, headers={"X-CSRFToken": fresh}).status_code == 200
    # logout also needs it and rotates it again
    assert c.post("/api/auth/logout").status_code == 400
    assert c.post("/api/auth/logout", headers={"X-CSRFToken": fresh}).status_code == 200
    assert c.get("/api/student/dashboard").status_code == 401


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------

def test_notifications_are_created_listed_and_marked_read(app, campus):
    stu = register_student(app, "1AB21CS605", campus["sid"])
    fac = register_faculty(app, "FAC605")
    assign(app, fac, campus["sid"], campus["admin_id"])
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])
    # the admin assignment itself already notified the faculty
    before = fc.get("/api/notifications").json()
    base = before["unread_count"]
    assert base >= 1 and {i["type"] for i in before["items"]} == {"ASSIGNMENT_CHANGED"}

    # the student's change request notifies the faculty of that class (and nobody else)
    assert api_post(sc, "/api/student/profile/change-request",
                    json={"phone": "9876500005", "reason": "notify me"}).status_code == 201
    inbox = fc.get("/api/notifications").json()
    assert inbox["unread_count"] == base + 1 and len(inbox["items"]) == base + 1
    item = next(i for i in inbox["items"] if i["type"] == "PERMISSION_REQUESTED")
    assert item["is_read"] is False and item["related_entity_type"] == "permission_request"
    assert sc.get("/api/notifications").json()["items"] == []
    assert fc.get("/api/auth/session").json()["unread_notifications"] == base + 1

    # a student cannot read (or mark) someone else's notification
    resp = api_post(sc, f"/api/notifications/{item['id']}/read")
    assert resp.status_code == 404
    assert api_post(fc, f"/api/notifications/{item['id']}/read").json()["unread_count"] == base
    assert next(i for i in fc.get("/api/notifications").json()["items"] if i["id"] == item["id"])["is_read"] is True
    assert api_post(fc, "/api/notifications/999999/read").status_code == 404

    api_post(sc, "/api/student/profile/change-request", json={"phone": "9876500006", "reason": "again"})
    api_post(sc, "/api/student/profile/change-request", json={"phone": "9876500007", "reason": "again"})
    assert fc.get("/api/notifications").json()["unread_count"] == base + 2
    assert api_post(fc, "/api/notifications/read-all").json()["unread_count"] == 0
    assert fc.get("/api/auth/session").json()["unread_notifications"] == 0


# ---------------------------------------------------------------------------
# world helpers for the multi-actor journeys
# ---------------------------------------------------------------------------

@pytest.fixture
def world(app, campus):
    """Student + assigned faculty + an unrelated faculty + admin, all with their own logged-in browser."""
    stu = register_student(app, "1AB21CS700", campus["sid"])
    fac = register_faculty(app, "FAC700")
    outsider = register_faculty(app, "FAC701")          # never assigned to the class
    assign(app, fac, campus["sid"], campus["admin_id"])
    return {
        "stu": stu, "fac": fac, "out": outsider, "sid": campus["sid"], "admin_id": campus["admin_id"],
        "sc": login_client(app, stu["email"]), "fc": login_client(app, fac["email"]),
        "oc": login_client(app, outsider["email"]), "ac": login_client(app, campus["admin_email"]),
    }


def api_delete_json(client, url):
    from tests.conftest import api_delete
    return api_delete(client, url)


# ---------------------------------------------------------------------------
# admin assigns faculty over HTTP -> the student sees them
# ---------------------------------------------------------------------------

def test_admin_assigns_and_removes_faculty_and_student_dashboard_follows(app, campus):
    stu = register_student(app, "1AB21CS701", campus["sid"])
    fac = register_faculty(app, "FAC710")
    sc, ac = login_client(app, stu["email"]), login_client(app, campus["admin_email"])
    assert sc.get("/api/student/dashboard").json()["assigned_faculty"] == []

    resp = api_post(ac, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": campus["sid"]})
    assert resp.status_code == 201, resp.text
    assignment_id = resp.json()["assignment"]["assignment_id"]
    dash = sc.get("/api/student/dashboard").json()
    assert [f["faculty_code"] for f in dash["assigned_faculty"]] == ["FAC710"]
    assert dash["assigned_faculty"][0]["full_name"] == "Prof FAC710"
    # assigning twice is an error, never a duplicate
    again = api_post(ac, "/api/admin/assignments", json={"faculty_id": fac["faculty_id"], "section_id": campus["sid"]})
    assert again.status_code in (400, 409)
    assert db_count(app, "faculty_assignments", "is_active = 1") == 1
    # the class shows up in the faculty's own area
    fc = login_client(app, fac["email"])
    assert [c["section_id"] for c in fc.get("/api/faculty/classes").json()["assignments"]] == [campus["sid"]]
    assert fc.get(f"/api/faculty/classes/{campus['sid']}").status_code == 200

    out = api_delete_json(ac, f"/api/admin/assignments/{assignment_id}")
    assert out.status_code == 200, out.text
    assert sc.get("/api/student/dashboard").json()["assigned_faculty"] == []
    assert fc.get(f"/api/faculty/classes/{campus['sid']}").status_code == 403
    assert api_delete_json(ac, f"/api/admin/assignments/{assignment_id}").status_code == 409


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

def test_chat_open_send_edit_seen_lock_and_listing(app, world):
    sc, fc, fac, stu = world["sc"], world["fc"], world["fac"], world["stu"]
    # nobody has a chat yet
    assert sc.get("/api/chat").json() == {"items": [], "total": 0, "total_unread": 0}

    opened = api_post(sc, "/api/chat/open", json={"faculty_id": fac["faculty_id"]})
    assert opened.status_code == 200, opened.text
    chat_id = opened.json()["chat_id"]
    # opening again returns the same conversation; the faculty opens the same one from their side
    assert api_post(sc, "/api/chat/open", json={"faculty_id": fac["faculty_id"]}).json()["chat_id"] == chat_id
    assert api_post(fc, "/api/chat/open", json={"student_id": stu["student_id"]}).json()["chat_id"] == chat_id
    assert db_count(app, "chats") == 1

    sent = api_post(sc, f"/api/chat/{chat_id}/messages", json={"message_text": "  Hello sir  "})
    assert sent.status_code == 201, sent.text
    msg = sent.json()["item"]
    assert msg["message_text"] == "Hello sir" and msg["is_mine"] and not msg["is_seen"] and msg["can_edit"]

    # the faculty sees it as unread in the list, and in the session counter
    listing = fc.get("/api/chat").json()
    assert listing["total"] == 1 and listing["total_unread"] == 1
    assert listing["items"][0]["last_message"] == "Hello sir"
    assert listing["items"][0]["other"]["usn"] == "1AB21CS700"
    assert fc.get("/api/auth/session").json()["unread_messages"] == 1

    # edit while unseen works
    edited = api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "Hello sir (edited)"})
    assert edited.status_code == 200 and edited.json()["item"]["is_edited"] is True
    # the other party cannot edit it
    assert api_post(fc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "hax"}).status_code in (400, 403)

    # the faculty opens the conversation -> the message is marked seen and becomes locked
    view = fc.get(f"/api/chat/{chat_id}").json()
    assert [m["message_text"] for m in view["messages"]] == ["Hello sir (edited)"]
    assert view["messages"][0]["is_mine"] is False
    assert view["chat"]["other"]["usn"] == "1AB21CS700"
    assert fc.get("/api/chat").json()["total_unread"] == 0
    locked = api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "too late"})
    assert locked.status_code in (400, 409) and "seen" in err(locked)["message"].lower()
    seen_view = sc.get(f"/api/chat/{chat_id}").json()["messages"][0]
    assert seen_view["is_seen"] is True and seen_view["can_edit"] is False
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "Hello sir (edited)"

    # faculty replies; the student gets it (incremental polling with after_id)
    reply = api_post(fc, f"/api/chat/{chat_id}/messages", json={"message_text": "Welcome"}).json()["item"]
    after = sc.get(f"/api/chat/{chat_id}?after_id={msg['id']}").json()
    assert [m["id"] for m in after["messages"]] == [reply["id"]] and after["last_id"] == reply["id"]

    # validation: empty / whitespace / missing body / unknown chat / unknown message
    assert api_post(sc, f"/api/chat/{chat_id}/messages", json={"message_text": "   "}).status_code == 400
    assert api_post(sc, f"/api/chat/{chat_id}/messages", json={}).status_code == 400
    assert sc.get("/api/chat/99999").status_code in (403, 404)
    assert api_post(sc, "/api/chat/messages/99999/edit", json={"message_text": "x"}).status_code == 404
    assert db_count(app, "messages") == 2
    # the admin can read every conversation (read-only)
    detail = world["ac"].get(f"/api/admin/chats/{chat_id}").json()
    assert [m["message_text"] for m in detail["messages"]] == ["Hello sir (edited)", "Welcome"]


def test_chat_access_rules_and_attachments(app, world):
    sc, fc, oc, fac, out, stu = world["sc"], world["fc"], world["oc"], world["fac"], world["out"], world["stu"]
    # an unassigned faculty can neither be opened by the student nor open the student
    assert api_post(sc, "/api/chat/open", json={"faculty_id": out["faculty_id"]}).status_code == 403
    assert api_post(oc, "/api/chat/open", json={"student_id": stu["student_id"]}).status_code == 403
    assert db_count(app, "chats") == 0
    # wrong parameter for the role / missing parameter
    assert api_post(sc, "/api/chat/open", json={"student_id": 1}).status_code == 400
    assert api_post(fc, "/api/chat/open", json={"faculty_id": 1}).status_code == 400
    assert api_post(sc, "/api/chat/open", json={}).status_code == 400

    chat_id = api_post(sc, "/api/chat/open", json={"faculty_id": fac["faculty_id"]}).json()["chat_id"]
    # strangers cannot read or write in it
    assert oc.get(f"/api/chat/{chat_id}").status_code == 403
    assert api_post(oc, f"/api/chat/{chat_id}/messages", json={"message_text": "hi"}).status_code == 403
    assert world["ac"].get("/api/chat").status_code == 403           # admins have no chat inbox

    # attachment (multipart) + caption
    resp = api_post(sc, f"/api/chat/{chat_id}/messages", data={"message_text": "notes"},
                    files={"attachment": ("notes.png", io.BytesIO(PNG), "image/png")})
    assert resp.status_code == 201, resp.text
    att = resp.json()["item"]["attachment"]
    assert att["name"] == "notes.png" and att["is_image"] and att["url"].startswith("/uploads/chat/")
    assert sc.get(att["url"]).status_code == 200 and fc.get(att["url"]).status_code == 200
    assert world["ac"].get(att["url"]).status_code == 200
    assert oc.get(att["url"]).status_code == 403 and anon(app).get(att["url"]).status_code == 401
    # bad attachments are refused and not stored
    bad = api_post(sc, f"/api/chat/{chat_id}/messages",
                   files={"attachment": ("virus.exe", io.BytesIO(b"MZ\x90\x00 evil"), "application/octet-stream")})
    fake = api_post(sc, f"/api/chat/{chat_id}/messages",
                    files={"attachment": ("fake.png", io.BytesIO(b"plain text"), "image/png")})
    assert bad.status_code == 400 and fake.status_code == 400
    assert db_count(app, "messages") == 1

    # revoking the assignment closes the conversation for both sides immediately
    unassign(app, fac, world["sid"], world["admin_id"])
    assert fc.get(f"/api/chat/{chat_id}").status_code == 403
    assert sc.get(f"/api/chat/{chat_id}").status_code == 403
    assert fc.get(att["url"]).status_code == 403
    assert sc.get("/api/chat").json()["items"] == []
    assert api_post(sc, f"/api/chat/{chat_id}/messages", json={"message_text": "still there?"}).status_code == 403


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

def test_meeting_request_accept_with_time_then_complete(app, world):
    sc, fc, oc, fac = world["sc"], world["fc"], world["oc"], world["fac"]
    created = api_post(sc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "Project review",
                                                  "details": "Chapter 3"})
    assert created.status_code == 201, created.text
    meeting = created.json()["meeting"]
    mid = meeting["id"]
    assert meeting["status"] == "PENDING" and meeting["reason"] == "Project review"
    assert meeting["student_message"] == "Chapter 3" and meeting["counterpart_code"] == "FAC700"
    assert meeting["can_cancel"] and not meeting["can_complete"]

    # the faculty is notified and sees the request (with can_respond); strangers do not
    assert fc.get("/api/auth/session").json()["unread_notifications"] >= 1
    pending = fc.get("/api/meetings?status=PENDING").json()
    assert [m["id"] for m in pending["items"]] == [mid] and pending["items"][0]["can_respond"] is True
    assert pending["items"][0]["counterpart_code"] == "1AB21CS700"
    assert oc.get("/api/meetings").json()["items"] == []
    assert oc.get(f"/api/meetings/{mid}").status_code == 403
    assert sc.get("/api/meetings/99999").status_code == 404

    # roles: students cannot respond, other faculty cannot respond, accepting needs a time text
    assert api_post(sc, f"/api/meetings/{mid}/respond", json={"decision": "accept",
                                                            "meeting_time_text": "10 am"}).status_code == 403
    assert api_post(oc, f"/api/meetings/{mid}/respond", json={"decision": "accept",
                                                            "meeting_time_text": "10 am"}).status_code == 403
    no_time = api_post(fc, f"/api/meetings/{mid}/respond", json={"decision": "accept"})
    assert no_time.status_code == 400 and "meeting_time_text" in err(no_time)["fields"]
    assert api_post(fc, f"/api/meetings/{mid}/respond", json={"decision": "maybe"}).status_code == 400
    assert api_post(sc, f"/api/meetings/{mid}/complete").status_code == 400    # not accepted yet

    accepted = api_post(fc, f"/api/meetings/{mid}/respond",
                        json={"decision": "accept", "meeting_time_text": "Friday 3 pm, cabin 12",
                              "faculty_response": "See you"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    row = db_one(app, "SELECT * FROM meeting_requests WHERE id = ?", (mid,))
    assert (row["status"], row["meeting_time_text"], row["faculty_response"]) == (
        "ACCEPTED", "Friday 3 pm, cabin 12", "See you")
    seen_by_student = sc.get(f"/api/meetings/{mid}").json()["meeting"]
    assert seen_by_student["meeting_time_text"] == "Friday 3 pm, cabin 12" and seen_by_student["can_complete"]
    assert sc.get("/api/student/dashboard").json()["counts"]["meetings_accepted"] == 1
    # the student is notified of the decision
    types = [n["type"] for n in sc.get("/api/notifications").json()["items"]]
    assert "MEETING_ACCEPTED" in types
    # answering twice is refused
    assert api_post(fc, f"/api/meetings/{mid}/respond", json={"decision": "reject"}).status_code in (400, 409)

    done = api_post(sc, f"/api/meetings/{mid}/complete")
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"
    final = fc.get(f"/api/meetings/{mid}").json()["meeting"]
    assert final["status"] == "COMPLETED" and final["completed_by"] == "STUDENT" and not final["can_cancel"]
    assert api_post(fc, f"/api/meetings/{mid}/cancel").status_code == 400      # no longer cancellable
    # shows up in the student's dashboard + the admin console
    dash = sc.get("/api/student/dashboard").json()
    assert dash["recent_meetings"][0]["id"] == mid and dash["counts"]["meetings_total"] == 1
    assert [m["id"] for m in world["ac"].get("/api/admin/meetings?status=COMPLETED").json()["items"]] == [mid]


def test_meeting_reject_cancel_and_validation(app, world):
    sc, fc, fac = world["sc"], world["fc"], world["fac"]
    # validation + access
    assert api_post(sc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "  "}).status_code == 400
    assert api_post(sc, "/api/meetings", json={"reason": "x"}).status_code == 400
    assert api_post(sc, "/api/meetings", json={"faculty_id": world["out"]["faculty_id"],
                                              "reason": "x"}).status_code in (400, 403)
    assert api_post(fc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "x"}).status_code == 403
    assert db_count(app, "meeting_requests") == 0

    # rejection
    m1 = api_post(sc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "Doubt"}).json()["id"]
    rej = api_post(fc, f"/api/meetings/{m1}/respond", json={"decision": "reject", "faculty_response": "Busy"})
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED"
    assert sc.get(f"/api/meetings/{m1}").json()["meeting"]["faculty_response"] == "Busy"

    # a student must give a reason to cancel, faculty may cancel an accepted meeting
    m2 = api_post(sc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "Viva"}).json()["id"]
    no_reason = api_post(sc, f"/api/meetings/{m2}/cancel", json={})
    assert no_reason.status_code == 400 and "reason" in err(no_reason)["fields"]
    cancelled = api_post(sc, f"/api/meetings/{m2}/cancel", json={"reason": "Clash with exam"})
    assert cancelled.status_code == 200 and cancelled.json()["meeting"]["cancelled_by"] == "STUDENT"

    m3 = api_post(sc, "/api/meetings", json={"faculty_id": fac["faculty_id"], "reason": "Lab"}).json()["id"]
    api_post(fc, f"/api/meetings/{m3}/respond", json={"decision": "accept", "meeting_time_text": "Mon 9"})
    fcancel = api_post(fc, f"/api/meetings/{m3}/cancel", json={"reason": "Travelling"})
    assert fcancel.status_code == 200 and fcancel.json()["meeting"]["cancelled_by"] == "FACULTY"
    assert {m["status"] for m in sc.get("/api/meetings").json()["items"]} == {"REJECTED", "CANCELLED"}
    assert sc.get("/api/meetings?status=bogus").status_code == 400
    c = sc.get("/api/student/dashboard").json()["counts"]
    assert c["meetings_total"] == 3 and c["meetings_pending"] == 0


# ---------------------------------------------------------------------------
# supporting faculty
# ---------------------------------------------------------------------------

def test_supporting_faculty_request_accept_reject_and_rerequest(app, world):
    sc, oc, out = world["sc"], world["oc"], world["out"]
    # student searches a faculty they are not assigned to
    found = sc.get("/api/supporting/faculty/search?q=FAC701").json()
    assert found["total"] == 1
    hit = found["items"][0]
    assert hit["faculty_code"] == "FAC701" and hit["has_access"] is False and hit["can_request"] is True
    assert sc.get("/api/supporting/faculty/search?q=").json()["items"] == []
    assigned_hit = sc.get("/api/supporting/faculty/search?q=FAC700").json()["items"][0]
    assert assigned_hit["has_access"] is True and assigned_hit["access_via"] == "class"
    # no chat before acceptance
    assert api_post(sc, "/api/chat/open", json={"faculty_id": out["faculty_id"]}).status_code == 403

    req = api_post(sc, f"/api/supporting/faculty/{out['faculty_id']}/request")
    assert req.status_code == 201, req.text
    rel_id = req.json()["id"]
    assert req.json()["relationship"]["direction"] == "outgoing"
    assert api_post(sc, f"/api/supporting/faculty/{out['faculty_id']}/request").status_code in (400, 409)

    incoming = oc.get("/api/supporting").json()["items"]
    assert [r["id"] for r in incoming] == [rel_id] and incoming[0]["can_respond"] is True
    assert oc.get("/api/faculty/dashboard").json()["counts"]["pending_supporting_requests"] == 1
    # the requester cannot answer their own request; a third party cannot either
    assert api_post(sc, f"/api/supporting/{rel_id}/accept").status_code in (400, 403)
    assert api_post(world["fc"], f"/api/supporting/{rel_id}/accept").status_code in (400, 403)

    # reject -> can request again
    rej = api_post(oc, f"/api/supporting/{rel_id}/reject")
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED"
    assert api_post(oc, f"/api/supporting/{rel_id}/accept").status_code in (400, 409)   # already answered
    assert sc.get("/api/supporting/faculty/search?q=FAC701").json()["items"][0]["can_request"] is True
    again = api_post(sc, f"/api/supporting/faculty/{out['faculty_id']}/request")
    assert again.status_code == 201
    assert db_count(app, "supporting_relationships") == 1                           # same row re-opened
    assert api_post(oc, f"/api/supporting/{again.json()['id']}/accept").json()["status"] == "ACCEPTED"

    # accepted: both sides see it, chat + meeting open up, dashboard lists the supporting faculty
    dash = sc.get("/api/student/dashboard").json()
    assert [f["faculty_code"] for f in dash["supporting_faculty"]] == ["FAC701"]
    assert dash["counts"]["supporting_faculty"] == 1
    assert [r["status"] for r in oc.get("/api/supporting?status=ACCEPTED").json()["items"]] == ["ACCEPTED"]
    assert api_post(sc, "/api/chat/open", json={"faculty_id": out["faculty_id"]}).status_code == 200
    assert api_post(sc, "/api/meetings", json={"faculty_id": out["faculty_id"], "reason": "Mentoring"}).status_code == 201
    assert sc.get("/api/supporting/faculty/search?q=FAC701").json()["items"][0]["has_access"] is True


def test_faculty_invites_student_who_accepts_or_rejects(app, world):
    sc, fc, fac, stu = world["sc"], world["fc"], world["fac"], world["stu"]
    # faculty search is scoped to their own classes
    hits = fc.get("/api/supporting/students/search?q=700").json()["items"]
    assert [h["usn"] for h in hits] == ["1AB21CS700"] and hits[0]["class"]["label"].endswith("A")
    assert world["oc"].get("/api/supporting/students/search?q=700").json()["items"] == []
    assert api_post(world["oc"], f"/api/supporting/students/{stu['student_id']}/request").status_code in (400, 403)

    rel_id = api_post(fc, f"/api/supporting/students/{stu['student_id']}/request").json()["id"]
    pend = sc.get("/api/student/dashboard").json()
    assert [r["id"] for r in pend["pending_supporting_requests"]] == [rel_id]
    assert pend["pending_supporting_requests"][0]["faculty"]["faculty_code"] == "FAC700"
    assert pend["pending_supporting_requests"][0]["can_respond"] is True
    assert api_post(fc, f"/api/supporting/{rel_id}/accept").status_code in (400, 403)  # not theirs to answer
    assert api_post(sc, f"/api/supporting/{rel_id}/reject").json()["status"] == "REJECTED"
    assert sc.get("/api/student/dashboard").json()["pending_supporting_requests"] == []
    rel2 = api_post(fc, f"/api/supporting/students/{stu['student_id']}/request").json()["id"]
    assert api_post(sc, f"/api/supporting/{rel2}/accept").json()["status"] == "ACCEPTED"
    assert [f["faculty_code"] for f in sc.get("/api/student/dashboard").json()["supporting_faculty"]] == ["FAC700"]
    assert [s["usn"] for s in fc.get("/api/faculty/dashboard").json()["supporting_students"]] == ["1AB21CS700"]


# ---------------------------------------------------------------------------
# profile change request decided by faculty
# ---------------------------------------------------------------------------

def test_student_profile_change_approved_by_assigned_faculty_only(app, world):
    sc, fc, oc, stu = world["sc"], world["fc"], world["oc"], world["stu"]
    rid = api_post(sc, "/api/student/profile/change-request",
                   json={"phone": "9123456780", "personal_email": "fresh@example.com", "reason": "New SIM"}).json()["id"]
    queue = fc.get("/api/faculty/permission-requests").json()
    assert queue["total"] == 1 and queue["items"][0]["id"] == rid
    assert queue["items"][0]["requested_changes"] == {"phone": "9123456780", "personal_email": "fresh@example.com"}
    assert queue["items"][0]["student"]["usn"] == "1AB21CS700"
    assert fc.get("/api/faculty/dashboard").json()["counts"]["pending_permission_requests"] == 1
    # a faculty member who does not teach the class sees nothing and cannot decide
    assert oc.get("/api/faculty/permission-requests").json()["items"] == []
    denied = api_post(oc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"})
    assert denied.status_code == 403
    # admins cannot decide student requests either (they are routed to the class faculty)
    assert api_post(world["ac"], f"/api/admin/permission-requests/{rid}/decide",
                    json={"decision": "approve"}).status_code in (400, 403)
    # the student cannot approve their own request
    assert api_post(sc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    assert db_one(app, "SELECT phone FROM students")["phone"] == "9999999999"

    ok_resp = api_post(fc, f"/api/faculty/permission-requests/{rid}/decide", json={"decision": "approve"})
    assert ok_resp.status_code == 200 and ok_resp.json()["status"] == "APPROVED"
    row = db_one(app, "SELECT phone, personal_email, usn, department, section_id FROM students")
    assert row["phone"] == "9123456780" and row["personal_email"] == "fresh@example.com"
    assert (row["usn"], row["department"], row["section_id"]) == ("1AB21CS700", "AIML", world["sid"])  # class untouched
    history = sc.get("/api/student/profile").json()
    assert history["permission_requests"][0]["status"] == "APPROVED" and history["student"]["phone"] == "9123456780"
    assert history["permission_requests"][0]["reviewed_at"]
    assert "PERMISSION_RESPONDED" in [n["type"] for n in sc.get("/api/notifications").json()["items"]]
    assert api_post(fc, f"/api/faculty/permission-requests/{rid}/decide",
                    json={"decision": "reject"}).status_code in (400, 409)       # already reviewed
    assert fc.get("/api/faculty/permission-requests").json()["items"] == []

    # rejection leaves the data alone
    rid2 = api_post(sc, "/api/student/profile/change-request", json={"phone": "9000000001", "reason": "oops"}).json()["id"]
    assert api_post(fc, f"/api/faculty/permission-requests/{rid2}/decide",
                    json={"decision": "reject"}).json()["status"] == "REJECTED"
    assert db_one(app, "SELECT phone FROM students")["phone"] == "9123456780"
    assert [r["status"] for r in sc.get("/api/student/profile").json()["permission_requests"]] == ["REJECTED", "APPROVED"]

    # a request filed while assigned can no longer be decided once the faculty is removed from the class
    rid3 = api_post(sc, "/api/student/profile/change-request", json={"phone": "9000000002", "reason": "late"}).json()["id"]
    unassign(app, world["fac"], world["sid"], world["admin_id"])
    assert api_post(fc, f"/api/faculty/permission-requests/{rid3}/decide",
                    json={"decision": "approve"}).status_code == 403
    assert db_one(app, "SELECT phone FROM students")["phone"] == "9123456780"


def test_faculty_profile_change_goes_to_the_admin(app, world):
    fc, ac = world["fc"], world["ac"]
    assert api_post(fc, "/api/faculty/profile/change-request", json={"department": "Not A Dept", "reason": "x"}).status_code == 400
    rid = api_post(fc, "/api/faculty/profile/change-request",
                   json={"professional_email": "new.fac700@college.edu", "reason": "Renamed"}).json()["id"]
    queue = ac.get("/api/admin/permission-requests").json()
    assert queue["pending"] == 1 and queue["items"][0]["can_decide"] is True
    assert queue["items"][0]["requester"]["faculty_code"] == "FAC700"
    assert api_post(world["oc"], f"/api/admin/permission-requests/{rid}/decide",
                    json={"decision": "approve"}).status_code == 403
    assert api_post(ac, f"/api/admin/permission-requests/{rid}/decide", json={"decision": "approve"}).json()["status"] == "APPROVED"
    assert db_one(app, "SELECT professional_email FROM faculty WHERE faculty_code = 'FAC700'")[
        "professional_email"] == "new.fac700@college.edu"
    assert fc.get("/api/faculty/profile").json()["change_requests"][0]["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# faculty class request -> admin decision
# ---------------------------------------------------------------------------

def test_faculty_class_request_then_admin_approval_opens_the_class(app, campus):
    fac = register_faculty(app, "FAC720")
    stu = register_student(app, "1AB21CS720", campus["sid"])
    fc, sc, ac = (login_client(app, fac["email"]), login_client(app, stu["email"]),
                  login_client(app, campus["admin_email"]))
    # no access to the class and no way to chat before approval
    assert fc.get(f"/api/faculty/classes/{campus['sid']}").status_code == 403
    assert fc.get("/api/faculty/classes").json() == {"assignments": [], "requests": []}
    assert fc.get("/api/supporting/students/search?q=720").json()["items"] == []
    assert api_post(fc, "/api/chat/open", json={"student_id": stu["student_id"]}).status_code == 403

    req = api_post(fc, "/api/faculty/classes/request", json={"section_id": campus["sid"], "note": "I teach DSA"})
    assert req.status_code == 201, req.text
    # asking again while pending, or for a non-existent class, is refused
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": campus["sid"]}).status_code in (400, 409)
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": 999999}).status_code in (400, 404)
    assert api_post(fc, "/api/faculty/classes/request", json={}).status_code == 400
    # a request alone grants nothing
    assert fc.get(f"/api/faculty/classes/{campus['sid']}").status_code == 403

    queue = ac.get("/api/admin/assignment-requests?status=PENDING").json()
    assert queue["pending_count"] == 1 and queue["items"][0]["faculty"]["faculty_code"] == "FAC720"
    assert queue["items"][0]["note"] == "I teach DSA" and queue["items"][0]["class"]["section_id"] == campus["sid"]
    rid = queue["items"][0]["id"]
    # only admins decide
    assert api_post(fc, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}).status_code == 403
    assert api_post(ac, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}).json()["status"] == "APPROVED"
    assert api_post(ac, f"/api/admin/assignment-requests/{rid}/decide", json={"decision": "approve"}).status_code in (400, 409)

    detail = fc.get(f"/api/faculty/classes/{campus['sid']}")
    assert detail.status_code == 200
    assert [s["usn"] for s in detail.json()["students"]] == ["1AB21CS720"]
    assert [c["section_id"] for c in fc.get("/api/faculty/classes").json()["assignments"]] == [campus["sid"]]
    assert [f["faculty_code"] for f in sc.get("/api/student/dashboard").json()["assigned_faculty"]] == ["FAC720"]
    assert api_post(fc, "/api/chat/open", json={"student_id": stu["student_id"]}).status_code == 200
    types = [n["type"] for n in fc.get("/api/notifications").json()["items"]]
    assert "ASSIGNMENT_RESPONDED" in types

    # a rejected request grants nothing and can be filed again
    other = find_section("CSE", "AIML", "3rd Year", "B", app=app)
    rid2 = api_post(fc, "/api/faculty/classes/request", json={"section_id": other}).json()["id"]
    assert api_post(ac, f"/api/admin/assignment-requests/{rid2}/decide", json={"decision": "reject"}).json()["status"] == "REJECTED"
    assert fc.get(f"/api/faculty/classes/{other}").status_code == 403
    assert api_post(fc, "/api/faculty/classes/request", json={"section_id": other}).status_code == 201


# ---------------------------------------------------------------------------
# admin console
# ---------------------------------------------------------------------------

def test_every_admin_page_loads_with_real_data(app, world):
    sc, fc, ac = world["sc"], world["fc"], world["ac"]
    chat_id = api_post(sc, "/api/chat/open", json={"faculty_id": world["fac"]["faculty_id"]}).json()["chat_id"]
    api_post(sc, f"/api/chat/{chat_id}/messages", json={"message_text": "hello"})
    api_post(sc, "/api/meetings", json={"faculty_id": world["fac"]["faculty_id"], "reason": "Admin page check"})
    api_post(sc, "/api/student/profile/change-request", json={"phone": "9000000009", "reason": "page"})
    api_post(world["oc"], "/api/faculty/classes/request", json={"section_id": world["sid"]})

    paths = [
        "/api/admin/dashboard", "/api/admin/students", "/api/admin/faculty", "/api/admin/meetings",
        "/api/admin/chats", f"/api/admin/chats/{chat_id}", "/api/admin/permission-requests", "/api/admin/admins",
        "/api/admin/academics", "/api/admin/assignments", "/api/admin/classes", f"/api/admin/classes/{world['sid']}",
        "/api/admin/assignment-requests", f"/api/admin/students?section_id={world['sid']}",
        "/api/admin/meetings?status=PENDING",
    ]
    for path in paths + ["/api/research/results"]:
        resp = ac.get(path)
        assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:200]}"
    assert ac.get("/api/admin/dashboard").json()["stats"]["class_count"] >= 1
    students = ac.get("/api/admin/students").json()
    assert students["total"] == 1 and students["items"][0]["usn"] == "1AB21CS700"
    assert students["items"][0]["class"]["department"] == "AIML"
    faculty = {f["faculty_code"]: f for f in ac.get("/api/admin/faculty").json()["items"]}
    assert set(faculty) == {"FAC700", "FAC701"}
    assert [a["section_id"] for a in faculty["FAC700"]["assignments"]] == [world["sid"]]
    assert faculty["FAC701"]["pending_request_count"] == 1
    assert ac.get("/api/admin/chats").json()["items"][0]["message_count"] == 1
    assert ac.get("/api/admin/chats/99999").status_code == 404
    assert ac.get("/api/admin/classes/99999").status_code == 404
    assert ac.get("/api/admin/meetings?status=bogus").status_code == 400
    assert ac.get("/api/admin/assignments").json()["pending_count"] == 1

    # not for anyone else
    for client, expected in ((sc, 403), (fc, 403), (anon(app), 401)):
        for path in paths + ["/api/research/results"]:
            assert client.get(path).status_code == expected, (expected, path)


def test_admin_creates_another_admin_who_can_log_in(app, campus):
    ac = login_client(app, campus["admin_email"])
    payload = {"full_name": "Second Admin", "email": "admin2@college.edu", "password": PASSWORD,
               "confirm_password": PASSWORD}
    assert api_post(ac, "/api/admin/admins", json={**payload, "confirm_password": "nope"}).status_code == 400
    assert api_post(ac, "/api/admin/admins", json=payload).status_code == 201
    assert api_post(ac, "/api/admin/admins", json=payload).status_code == 409
    second = login_client(app, "admin2@college.edu")
    emails = {a["email"] for a in second.get("/api/admin/admins").json()["items"]}
    assert emails == {"admin@college.edu", "admin2@college.edu"}
    assert second.get("/api/admin/dashboard").status_code == 200


def test_admin_builds_a_class_and_a_student_registers_into_it(app, campus):
    ac = login_client(app, campus["admin_email"])
    branch = api_post(ac, "/api/admin/academics/branches", json={"name": "Mechanical"})
    assert branch.status_code == 201, branch.text
    dept = api_post(ac, "/api/admin/academics/departments", json={"branch_id": branch.json()["id"], "name": "Thermal"})
    assert dept.status_code == 201, dept.text
    year = api_post(ac, "/api/admin/academics/years", json={"department_id": dept.json()["id"], "name": "2"})
    assert year.status_code == 201, year.text
    assert year.json()["name"] == "2nd Year"
    sections = api_post(ac, "/api/admin/academics/sections", json={"year_id": year.json()["id"], "names": "A, B"})
    assert sections.status_code == 201 and sections.json()["created"] == ["A", "B"]
    assert api_post(ac, "/api/admin/academics/branches", json={"name": "mechanical"}).status_code in (400, 409)

    tree = anon(app).get("/api/academic/tree").json()["branches"]
    mech = next(b for b in tree if b["name"] == "Mechanical")
    section_id = mech["departments"][0]["years"][0]["sections"][0]["id"]

    resp = http_student_signup(TestClient(app), None, "mech.student@college.edu", "1AB21ME001", section_id)
    assert resp.status_code == 201, resp.text
    me = login_client(app, "1AB21ME001").get("/api/student/dashboard").json()["student"]
    assert (me["branch"], me["department"], me["year"], me["section"]) == ("Mechanical", "Thermal", "2nd Year", "A")
    assert me["class"]["label"] == "Mechanical → Thermal → 2nd Year → A"

    # a used class cannot be deleted; a deactivated one disappears from the public tree
    from tests.conftest import api_delete
    assert api_delete(ac, f"/api/admin/academics/section/{section_id}").status_code == 409
    assert api_post(ac, f"/api/admin/academics/section/{section_id}/active", json={"active": False}).status_code == 200
    tree = anon(app).get("/api/academic/tree").json()["branches"]
    names = [s["name"] for b in tree if b["name"] == "Mechanical"
             for d in b["departments"] for y in d["years"] for s in y["sections"]]
    assert "A" not in names


def test_admin_removes_registration_and_student_can_register_again(app, campus):
    stu = register_student(app, "1AB21CS730", campus["sid"])
    ac = login_client(app, campus["admin_email"])
    resp = api_post(ac, f"/api/admin/students/{stu['student_id']}/remove-registration")
    assert resp.status_code == 200, resp.text
    assert resp.json()["student"]["is_removed"] is True
    assert api_post(ac, f"/api/admin/students/{stu['student_id']}/remove-registration").status_code == 409
    assert api_post(ac, "/api/admin/students/99999/remove-registration").status_code == 404
    # the same USN / e-mail can register again
    again = http_student_signup(TestClient(app), None, stu["email"], "1AB21CS730", campus["sid"])
    assert again.status_code == 201, again.text
    assert api_login(TestClient(app), "1AB21CS730")["user"]["role"] == "STUDENT"


# ---------------------------------------------------------------------------
# role matrix
# ---------------------------------------------------------------------------

def test_role_matrix_for_every_area(app, world):
    sc, fc, ac, ano = world["sc"], world["fc"], world["ac"], anon(app)
    areas = [  # (path, roles allowed to GET it)
        ("/api/student/dashboard", {"STUDENT"}), ("/api/student/profile", {"STUDENT"}),
        ("/api/faculty/dashboard", {"FACULTY"}), ("/api/faculty/profile", {"FACULTY"}),
        ("/api/faculty/classes", {"FACULTY"}), ("/api/faculty/permission-requests", {"FACULTY"}),
        ("/api/chat", {"STUDENT", "FACULTY"}), ("/api/meetings", {"STUDENT", "FACULTY"}),
        ("/api/supporting", {"STUDENT", "FACULTY"}),
        ("/api/admin/dashboard", {"ADMIN"}), ("/api/research/results", {"ADMIN"}),
        ("/api/notifications", {"STUDENT", "FACULTY", "ADMIN"}),
    ]
    for path, allowed in areas:
        for role, client in (("STUDENT", sc), ("FACULTY", fc), ("ADMIN", ac)):
            status = client.get(path).status_code
            assert status == (200 if role in allowed else 403), f"{role} {path}: {status}"
        assert ano.get(path).status_code == 401, path
    # student-only / faculty-only searches
    assert fc.get("/api/supporting/faculty/search?q=a").status_code == 403
    assert sc.get("/api/supporting/students/search?q=a").status_code == 403
    assert ac.get("/api/supporting/faculty/search?q=a").status_code == 403
    # mutations are role-checked before anything is touched
    assert api_post(fc, "/api/meetings", json={"faculty_id": 1, "reason": "x"}).status_code == 403
    assert api_post(sc, "/api/faculty/classes/request", json={"section_id": world["sid"]}).status_code == 403
    assert api_post(sc, "/api/admin/assignments", json={"faculty_id": 1, "section_id": world["sid"]}).status_code == 403
    assert api_post(fc, "/api/admin/admins", json={"full_name": "x", "email": "x@y.z", "password": "x",
                                                   "confirm_password": "x"}).status_code == 403
    assert api_post(ac, "/api/meetings", json={"faculty_id": 1, "reason": "x"}).status_code == 403
    # unknown API paths are JSON 404s
    nf = sc.get("/api/does/not/exist")
    assert nf.status_code == 404 and err(nf)["code"] == "not_found"
    # browsers are independent: logging the faculty out does not log the student out
    api_post(fc, "/api/auth/logout")
    assert fc.get("/api/faculty/dashboard").status_code == 401
    assert sc.get("/api/student/dashboard").status_code == 200
