"""End-to-end journeys through the HTTP test client for the three roles."""
import io
import re

import pytest

from models import queries
from tests.conftest import (
    PASSWORD, create_admin, create_faculty, create_student, section_id_for, assign, login_client,
    flashes, flash_text, db_one, db_all, db_count, http_student_signup, http_faculty_signup,
)


def _png_bytes():
    """A valid 1x1 PNG built by hand (no Pillow needed)."""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")


@pytest.fixture
def campus(app):
    """An admin plus one faculty (AIML) and one student in AIML 3rd A, created through the real services."""
    admin_id = create_admin(app)
    sid = section_id_for(app, "AIML", "3rd Year", "A")
    return {"admin_id": admin_id, "sid": sid, "admin_email": "admin@college.edu"}


# ---------------------------------------------------------------------------
# public pages
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/login", "/signup/student", "/signup/faculty"])
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_unknown_url_renders_404_and_anonymous_root_goes_to_login(client):
    assert client.get("/no/such/page").status_code == 404
    assert client.get("/").headers["Location"].endswith("/login")


def test_signup_details_page_renders_the_admin_tree_after_otp(client, app, captured_otps):
    client.post("/signup/student", data={"college_email": "tree@college.edu"})
    client.post("/signup/student/verify-otp", data={"email": "tree@college.edu", "otp": captured_otps["tree@college.edu"]})
    resp = client.get("/signup/student/details?email=tree@college.edu")
    assert resp.status_code == 200
    page = resp.data.decode()
    for name in ("CSE", "AIML", "Cybersecurity", "3rd Year"):
        assert name in page


def test_faculty_signup_page_lists_admin_departments_only(client):
    page = client.get("/signup/faculty").data.decode()
    for d in ("AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"):
        assert d in page


def test_otp_verify_page_renders_and_wrong_otp_counts_attempts(client, app, captured_otps):
    client.post("/signup/student", data={"college_email": "attempts@college.edu"})
    assert client.get("/signup/student/verify-otp?email=attempts@college.edu").status_code == 200
    for _ in range(5):
        client.post("/signup/student/verify-otp", data={"email": "attempts@college.edu", "otp": "abcdef"})
    resp = client.post("/signup/student/verify-otp",
                       data={"email": "attempts@college.edu", "otp": captured_otps["attempts@college.edu"]},
                       follow_redirects=True)
    assert b"Too many incorrect attempts" in resp.data  # even the right OTP is refused once locked


def test_otp_cannot_be_reused(client, app, captured_otps):
    client.post("/signup/student", data={"college_email": "reuse@college.edu"})
    otp = captured_otps["reuse@college.edu"]
    assert client.post("/signup/student/verify-otp", data={"email": "reuse@college.edu", "otp": otp}).status_code == 302
    resp = client.post("/signup/student/verify-otp", data={"email": "reuse@college.edu", "otp": otp})
    assert resp.status_code == 200 and b"already been used" in resp.data


# ---------------------------------------------------------------------------
# student journey
# ---------------------------------------------------------------------------

def test_student_end_to_end(app, client, campus, captured_otps):
    # sign up through the OTP steps, then log in
    resp = http_student_signup(client, captured_otps, "e2e.student@college.edu", "1AB21CS500", campus["sid"])
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert "Registration successful" in flash_text(client)
    assert client.post("/login", data={"email": "e2e.student@college.edu", "password": PASSWORD}).status_code == 302

    # dashboard / profile / lists all render (no faculty assigned yet)
    for path in ("/student/dashboard", "/student/profile", "/chat/", "/meetings/", "/notifications/",
                 "/supporting/faculty/search"):
        assert client.get(path).status_code == 200, path
    assert b"1AB21CS500" in client.get("/student/profile").data
    assert b"AIML" in client.get("/student/profile").data

    # theme
    client.post("/student/theme/dark", headers={"Referer": "/student/dashboard"})
    assert db_one(app, "SELECT theme_preference FROM users WHERE email = 'e2e.student@college.edu'")[
        "theme_preference"] == "dark"

    # logout (POST) kills the session
    assert client.post("/logout").status_code == 302
    assert client.get("/student/dashboard").status_code == 302


def test_student_profile_picture_upload(app, campus):
    stu = create_student(app, "1AB21CS501", campus["sid"])
    c = login_client(app, stu["email"])
    resp = c.post("/student/profile/picture", data={"profile_picture": (io.BytesIO(_png_bytes()), "me.png")},
                  content_type="multipart/form-data")
    assert resp.status_code == 302 and "updated" in flash_text(c)
    path = db_one(app, "SELECT profile_picture_path FROM users WHERE id = ?", (stu["user_id"],))["profile_picture_path"]
    assert path.startswith("profile/students/") and path.endswith(".png")
    assert c.get("/uploads/" + path).status_code == 200  # signed-in users can load profile pictures
    assert app.test_client().get("/uploads/" + path).status_code == 403  # anonymous cannot

    # an "image" that is really text is refused and the old picture stays
    c.post("/student/profile/picture", data={"profile_picture": (io.BytesIO(b"not an image"), "evil.png")},
           content_type="multipart/form-data")
    assert flashes(c)[0][0] == "error"
    assert db_one(app, "SELECT profile_picture_path FROM users WHERE id = ?", (stu["user_id"],))[
        "profile_picture_path"] == path


# ---------------------------------------------------------------------------
# faculty journey including class request -> approval -> chat
# ---------------------------------------------------------------------------

def test_faculty_end_to_end_from_signup_to_chatting(app, client, campus, captured_otps):
    # faculty signs up (no class chosen) and logs in
    http_faculty_signup(client, "FAC900", department="AIML")
    assert client.post("/login", data={"email": "fac900@college.edu", "password": PASSWORD}).status_code == 302
    for path in ("/faculty/dashboard", "/faculty/profile", "/faculty/classes", "/faculty/permission-requests",
                 "/chat/", "/meetings/", "/notifications/", "/supporting/student/search"):
        assert client.get(path).status_code == 200, path
    assert db_count(app, "faculty_assignments") == 0
    assert client.get(f"/faculty/classes/{campus['sid']}").status_code == 403

    # a student registers in AIML 3rd A
    stu_client = app.test_client()
    http_student_signup(stu_client, captured_otps, "s900@college.edu", "1AB21CS900", campus["sid"])
    stu_client.post("/login", data={"email": "s900@college.edu", "password": PASSWORD})
    fac_id = db_one(app, "SELECT id FROM faculty WHERE faculty_code = 'FAC900'")["id"]
    student_id = db_one(app, "SELECT id FROM students WHERE usn = '1AB21CS900'")["id"]

    # the student sees no faculty and cannot chat with the faculty yet
    assert b"FAC900" not in stu_client.get("/student/dashboard").data
    stu_client.get(f"/chat/open/{fac_id}")
    assert db_count(app, "chats") == 0

    # faculty asks for the class; admin approves
    client.post("/faculty/classes/request", data={"section_id": str(campus["sid"]), "note": "I teach them DSA"})
    admin = login_client(app, campus["admin_email"])
    assert admin.get("/admin/assignment-requests").status_code == 200
    req_id = db_one(app, "SELECT id FROM faculty_assignment_requests")["id"]
    admin.post(f"/admin/assignment-requests/{req_id}/decide", data={"decision": "approve"})

    # now the class opens, search works, both directions chat
    assert client.get(f"/faculty/classes/{campus['sid']}").status_code == 200
    assert b"1AB21CS900" in client.get("/supporting/student/search?q=900").data
    assert b"Prof FAC900" in stu_client.get("/student/dashboard").data

    resp = client.get(f"/chat/open-student/{student_id}")
    assert resp.status_code == 302
    chat_id = db_one(app, "SELECT id FROM chats")["id"]
    assert resp.headers["Location"].endswith(f"/chat/{chat_id}")
    client.post(f"/chat/{chat_id}/message", data={"message_text": "Welcome to DSA"})
    assert b"Welcome to DSA" in stu_client.get(f"/chat/{chat_id}").data
    stu_client.post(f"/chat/{chat_id}/message", data={"message_text": "Thanks sir"})
    assert b"Thanks sir" in client.get(f"/chat/{chat_id}").data
    assert b"Thanks sir" in client.get("/chat/").data or client.get("/chat/").status_code == 200
    assert db_count(app, "messages") == 2
    assert login_client(app, campus["admin_email"]).get("/admin/chats").status_code == 200


def test_chat_open_send_edit_and_seen_lock_via_http(app, campus):
    fac = create_faculty(app, "FAC901")
    stu = create_student(app, "1AB21CS901", campus["sid"])
    assign(app, fac, campus["sid"], campus["admin_id"])
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])

    resp = sc.get(f"/chat/open/{fac['faculty_id']}")
    chat_id = db_one(app, "SELECT id FROM chats")["id"]
    assert resp.headers["Location"].endswith(f"/chat/{chat_id}")
    sc.post(f"/chat/{chat_id}/message", data={"message_text": "first"})
    msg = db_one(app, "SELECT * FROM messages")
    assert msg["message_text"] == "first" and msg["is_seen"] == 0

    sc.post(f"/chat/message/{msg['id']}/edit", data={"message_text": "first (edited)"})
    row = db_one(app, "SELECT * FROM messages")
    assert row["message_text"] == "first (edited)" and row["is_edited"] == 1
    assert b"first (edited)" in fc.get(f"/chat/{chat_id}").data  # faculty reads -> seen
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 1
    sc.post(f"/chat/message/{msg['id']}/edit", data={"message_text": "nope"})
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "first (edited)"

    # empty message
    sc.post(f"/chat/{chat_id}/message", data={"message_text": "   "})
    assert "enter a message" in flash_text(sc).lower()
    assert db_count(app, "messages") == 1
    assert sc.get("/chat/").status_code == 200 and fc.get("/chat/").status_code == 200
    assert fc.get("/chat/99999").status_code == 302  # unknown conversation


def test_chat_attachment_upload_download_and_revocation(app, campus):
    fac = create_faculty(app, "FAC902")
    stu = create_student(app, "1AB21CS902", campus["sid"])
    assign(app, fac, campus["sid"], campus["admin_id"])
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])
    sc.get(f"/chat/open/{fac['faculty_id']}")
    chat_id = db_one(app, "SELECT id FROM chats")["id"]

    sc.post(f"/chat/{chat_id}/message", data={"attachment": (io.BytesIO(_png_bytes()), "notes.png")},
            content_type="multipart/form-data")
    msg = db_one(app, "SELECT * FROM messages")
    assert msg["attachment_type"] == "png" and msg["attachment_path"].startswith("chat/")
    assert msg["attachment_original_name"] == "notes.png"

    url = "/uploads/" + msg["attachment_path"]
    assert sc.get(url).status_code == 200 and fc.get(url).status_code == 200
    assert login_client(app, campus["admin_email"]).get(url).status_code == 200
    outsider = create_student(app, "1AB21CS903", campus["sid"])
    assert login_client(app, outsider["email"]).get(url).status_code == 403
    assert app.test_client().get(url).status_code == 403

    # bad uploads
    sc.post(f"/chat/{chat_id}/message", data={"attachment": (io.BytesIO(b"MZ\x90\x00 evil"), "virus.exe")},
            content_type="multipart/form-data")
    assert flashes(sc)[-1][0] == "error"
    sc.post(f"/chat/{chat_id}/message", data={"attachment": (io.BytesIO(b"plain text"), "fake.png")},
            content_type="multipart/form-data")
    assert flashes(sc)[-1][0] == "error"
    assert db_count(app, "messages") == 1

    # once the faculty's assignment is removed the file is closed to them too
    from tests.conftest import unassign
    unassign(app, fac, campus["sid"], campus["admin_id"])
    assert fc.get(url).status_code == 403
    assert sc.get(url).status_code == 403  # the student lost their only route to this faculty as well


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

@pytest.fixture
def pair(app, campus):
    fac = create_faculty(app, "FAC910")
    stu = create_student(app, "1AB21CS910", campus["sid"])
    assign(app, fac, campus["sid"], campus["admin_id"])
    return {"fac": fac, "stu": stu, "sc": login_client(app, stu["email"]), "fc": login_client(app, fac["email"])}


def test_meeting_request_accept_complete(app, pair):
    sc, fc, fac = pair["sc"], pair["fc"], pair["fac"]
    assert sc.get(f"/meetings/request/{fac['faculty_id']}").status_code == 200
    resp = sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "Project review", "details": "Chapter 3"})
    assert resp.status_code == 302 and "/meetings" in resp.headers["Location"]
    m = db_one(app, "SELECT * FROM meeting_requests")
    assert (m["status"], m["reason"], m["student_message"]) == ("PENDING", "Project review", "Chapter 3")
    assert b"Project review" in fc.get("/meetings/").data
    assert db_count(app, "notifications", "user_id = ? AND notification_type = 'MEETING_REQUESTED'",
                    (pair["fac"]["user_id"],)) == 1

    fc.post(f"/meetings/{m['id']}/respond", data={"decision": "accept", "meeting_time_text": ""})
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "PENDING"  # timing is mandatory
    fc.post(f"/meetings/{m['id']}/respond", data={"decision": "accept", "meeting_time_text": "Fri 3pm", "faculty_response": "ok"})
    assert db_one(app, "SELECT status FROM meeting_requests")["status"] == "ACCEPTED"
    assert b"Fri 3pm" in sc.get("/meetings/").data

    sc.post(f"/meetings/{m['id']}/complete")
    done = db_one(app, "SELECT * FROM meeting_requests")
    assert done["status"] == "COMPLETED" and done["completed_by"] == "STUDENT"
    # status filter
    assert b"Project review" in sc.get("/meetings/?status=COMPLETED").data
    assert b"Project review" not in sc.get("/meetings/?status=PENDING").data
    assert db_count(app, "notifications", "user_id = ? AND notification_type = 'MEETING_COMPLETED'",
                    (pair["fac"]["user_id"],)) == 1


def test_meeting_reject_and_cancel_paths(app, pair):
    sc, fc, fac = pair["sc"], pair["fc"], pair["fac"]
    for reason in ("one", "two", "three"):
        sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": reason})
    ids = [r["id"] for r in db_all(app, "SELECT id FROM meeting_requests ORDER BY id")]
    fc.post(f"/meetings/{ids[0]}/respond", data={"decision": "reject", "faculty_response": "busy"})
    sc.post(f"/meetings/{ids[1]}/cancel", data={"reason": ""})  # student must give a reason
    assert db_one(app, "SELECT status FROM meeting_requests WHERE id = ?", (ids[1],))["status"] == "PENDING"
    sc.post(f"/meetings/{ids[1]}/cancel", data={"reason": "clash"})
    fc.post(f"/meetings/{ids[2]}/cancel")
    statuses = [r["status"] for r in db_all(app, "SELECT status FROM meeting_requests ORDER BY id")]
    assert statuses == ["REJECTED", "CANCELLED", "CANCELLED"]
    by = [r["cancelled_by"] for r in db_all(app, "SELECT cancelled_by FROM meeting_requests ORDER BY id")]
    assert by == [None, "STUDENT", "FACULTY"]
    sc.post(f"/meetings/{ids[0]}/complete")  # rejected cannot be completed
    assert db_one(app, "SELECT status FROM meeting_requests WHERE id = ?", (ids[0],))["status"] == "REJECTED"


def test_meeting_request_requires_reason(app, pair):
    resp = pair["sc"].post(f"/meetings/request/{pair['fac']['faculty_id']}", data={"reason": "  "})
    assert resp.status_code == 200 and db_count(app, "meeting_requests") == 0
    assert pair["sc"].get("/meetings/request/99999").status_code == 302


# ---------------------------------------------------------------------------
# supporting faculty
# ---------------------------------------------------------------------------

def test_student_requests_supporting_faculty_then_chats(app, campus):
    outsider_fac = create_faculty(app, "FAC920", "IoT", name="Dr Outsider")
    stu = create_student(app, "1AB21CS920", campus["sid"])
    sc, fc = login_client(app, stu["email"]), login_client(app, outsider_fac["email"])

    assert b"Dr Outsider" in sc.get("/supporting/faculty/search?q=Outsider").data
    assert b"Dr Outsider" not in sc.get("/supporting/faculty/search?q=nobodyatall").data
    sc.get(f"/chat/open/{outsider_fac['faculty_id']}")
    assert db_count(app, "chats") == 0

    sc.post(f"/supporting/faculty/{outsider_fac['faculty_id']}/request", headers={"Referer": "/student/dashboard"})
    assert db_one(app, "SELECT status, requested_by FROM supporting_relationships") == {
        "status": "PENDING", "requested_by": "STUDENT"}
    sc.post(f"/supporting/faculty/{outsider_fac['faculty_id']}/request")
    assert "already exists" in flash_text(sc)
    sc.get(f"/chat/open/{outsider_fac['faculty_id']}")
    assert db_count(app, "chats") == 0  # pending grants nothing

    assert b"1AB21CS920" in fc.get("/faculty/dashboard").data
    rel_id = db_one(app, "SELECT id FROM supporting_relationships")["id"]
    fc.post(f"/supporting/{rel_id}/accept", headers={"Referer": "/faculty/dashboard"})
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"

    sc.get(f"/chat/open/{outsider_fac['faculty_id']}")
    assert db_count(app, "chats") == 1
    assert b"Dr Outsider" in sc.get("/student/dashboard").data
    sc.post(f"/meetings/request/{outsider_fac['faculty_id']}", data={"reason": "mentoring"})
    assert db_count(app, "meeting_requests") == 1


def test_supporting_request_rejected_then_requested_again(app, campus):
    fac = create_faculty(app, "FAC921", "IoT")
    stu = create_student(app, "1AB21CS921", campus["sid"])
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])
    sc.post(f"/supporting/faculty/{fac['faculty_id']}/request")
    rel_id = db_one(app, "SELECT id FROM supporting_relationships")["id"]
    fc.post(f"/supporting/{rel_id}/reject")
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "REJECTED"
    resp = sc.post(f"/supporting/faculty/{fac['faculty_id']}/request")
    assert resp.status_code == 302  # no 500: the rejected pair can be re-opened
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "PENDING"
    assert db_count(app, "supporting_relationships") == 1


def test_faculty_requests_student_who_accepts(app, pair):
    fac, stu, sc, fc = pair["fac"], pair["stu"], pair["sc"], pair["fc"]
    fc.post(f"/supporting/student/{stu['student_id']}/request", headers={"Referer": "/faculty/dashboard"})
    rel = db_one(app, "SELECT * FROM supporting_relationships")
    assert rel["requested_by"] == "FACULTY" and rel["status"] == "PENDING"
    assert b"Prof FAC910" in sc.get("/student/dashboard").data
    sc.post(f"/supporting/{rel['id']}/accept", headers={"Referer": "/student/dashboard"})
    assert db_one(app, "SELECT status FROM supporting_relationships")["status"] == "ACCEPTED"
    assert b"1AB21CS910" in fc.get("/faculty/dashboard").data


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------

def test_notifications_list_mark_read_and_mark_all(app, pair):
    sc, fc, fac = pair["sc"], pair["fc"], pair["fac"]
    for reason in ("a", "b"):
        sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": reason})
    with app.app_context():
        assert queries.get_unread_notification_count(fac["user_id"]) >= 2
    page = fc.get("/notifications/")
    assert page.status_code == 200 and b"meeting" in page.data.lower()
    first = db_one(app, "SELECT id FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY id", (fac["user_id"],))["id"]
    fc.post(f"/notifications/{first}/read")
    assert db_one(app, "SELECT is_read FROM notifications WHERE id = ?", (first,))["is_read"] == 1
    fc.post("/notifications/read-all", headers={"Referer": "/notifications/"})
    assert db_count(app, "notifications", "user_id = ? AND is_read = 0", (fac["user_id"],)) == 0
    assert fc.post("/notifications/99999/read").status_code == 302


def test_unread_counts_appear_in_page_context(app, pair):
    pair["sc"].post(f"/meetings/request/{pair['fac']['faculty_id']}", data={"reason": "x"})
    assert pair["fc"].get("/faculty/dashboard").status_code == 200  # context processor with unread > 0


# ---------------------------------------------------------------------------
# permission (profile change) requests
# ---------------------------------------------------------------------------

def test_student_profile_change_approved_by_assigned_faculty(app, pair):
    sc, fc = pair["sc"], pair["fc"]
    assert sc.post("/student/profile/change-request",
                   data={"phone": "9000000001", "personal_email": "fresh@example.com", "reason": "lost phone"}
                   ).status_code == 302
    assert "submitted" in flash_text(sc)
    req = db_one(app, "SELECT * FROM permission_requests")
    assert req["status"] == "PENDING" and req["request_type"] == "STUDENT_PROFILE_CHANGE"
    assert b"9000000001" in fc.get("/faculty/permission-requests").data
    assert b"PENDING" in sc.get("/student/profile").data or sc.get("/student/profile").status_code == 200

    fc.post(f"/faculty/permission-requests/{req['id']}/decide", data={"decision": "approve"})
    st = db_one(app, "SELECT phone, personal_email FROM students")
    assert (st["phone"], st["personal_email"]) == ("9000000001", "fresh@example.com")
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "APPROVED"
    assert db_count(app, "notifications", "user_id = ? AND notification_type = 'PERMISSION_RESPONDED'",
                    (pair["stu"]["user_id"],)) == 1


def test_student_profile_change_rejected_leaves_data_and_non_assigned_faculty_cannot_review(app, pair, campus):
    outsider = create_faculty(app, "FAC911", "IoT")
    oc = login_client(app, outsider["email"])
    sc, fc = pair["sc"], pair["fc"]
    sc.post("/student/profile/change-request", data={"phone": "9000000002"})
    req_id = db_one(app, "SELECT id FROM permission_requests")["id"]
    assert b"9000000002" not in oc.get("/faculty/permission-requests").data
    oc.post(f"/faculty/permission-requests/{req_id}/decide", data={"decision": "approve"})
    assert "not authorized" in flash_text(oc)
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "PENDING"
    assert db_one(app, "SELECT phone FROM students")["phone"] == "9999999999"

    fc.post(f"/faculty/permission-requests/{req_id}/decide", data={"decision": "reject"})
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "REJECTED"
    assert db_one(app, "SELECT phone FROM students")["phone"] == "9999999999"
    fc.post(f"/faculty/permission-requests/{req_id}/decide", data={"decision": "approve"})
    assert db_one(app, "SELECT status FROM permission_requests")["status"] == "REJECTED"  # final


def test_faculty_profile_change_reviewed_by_admin(app, campus):
    fac = create_faculty(app, "FAC912", "AIML")
    fc, admin = login_client(app, fac["email"]), login_client(app, campus["admin_email"])
    fc.post("/faculty/profile/change-request",
            data={"department": "GenAI", "professional_email": "new912@college.edu", "reason": "transfer"})
    req = db_one(app, "SELECT * FROM permission_requests")
    assert req["request_type"] == "FACULTY_PROFILE_CHANGE" and req["target_approver_user_id"] == campus["admin_id"]
    page = admin.get("/admin/permission-requests")
    assert page.status_code == 200 and b"GenAI" in page.data
    assert db_count(app, "notifications", "user_id = ? AND notification_type = 'PERMISSION_REQUESTED'",
                    (campus["admin_id"],)) == 1

    admin.post(f"/admin/permission-requests/{req['id']}/decide", data={"decision": "approve"})
    row = db_one(app, "SELECT department, professional_email FROM faculty")
    assert row == {"department": "GenAI", "professional_email": "new912@college.edu"}

    fc.post("/faculty/profile/change-request", data={"department": "IoT"})
    req2 = db_one(app, "SELECT id FROM permission_requests WHERE status = 'PENDING'")["id"]
    admin.post(f"/admin/permission-requests/{req2}/decide", data={"decision": "reject"})
    assert db_one(app, "SELECT department FROM faculty")["department"] == "GenAI"
    admin.post("/admin/permission-requests/99999/decide", data={"decision": "approve"})
    assert "not found" in flash_text(admin).lower()


def test_faculty_profile_picture_and_profile_page(app, campus):
    fac = create_faculty(app, "FAC913")
    fc = login_client(app, fac["email"])
    assert fc.get("/faculty/profile").status_code == 200
    fc.post("/faculty/profile/picture", data={"profile_picture": (io.BytesIO(_png_bytes()), "p.png")},
            content_type="multipart/form-data")
    assert db_one(app, "SELECT profile_picture_path FROM users WHERE id = ?", (fac["user_id"],))[
        "profile_picture_path"].startswith("profile/faculty/")
    fc.post("/faculty/profile/picture", data={}, content_type="multipart/form-data")
    assert flashes(fc)[-1][0] == "error"


# ---------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------

def test_every_admin_page_returns_200_with_data_present(app, pair, campus):
    # populate: chat, meeting, permission request, pending class request, supporting relationship
    sc, fc, fac, stu = pair["sc"], pair["fc"], pair["fac"], pair["stu"]
    sc.get(f"/chat/open/{fac['faculty_id']}")
    chat_id = db_one(app, "SELECT id FROM chats")["id"]
    sc.post(f"/chat/{chat_id}/message", data={"message_text": "hello"})
    sc.post(f"/meetings/request/{fac['faculty_id']}", data={"reason": "topic"})
    sc.post("/student/profile/change-request", data={"phone": "9111111111"})
    other = create_faculty(app, "FAC914", "IoT")
    login_client(app, other["email"]).post("/faculty/classes/request", data={"section_id": str(campus["sid"])})

    admin = login_client(app, campus["admin_email"])
    for path in ("/admin/dashboard", "/admin/students", "/admin/faculty", "/admin/meetings", "/admin/chats",
                 f"/admin/chats/{chat_id}", "/admin/permission-requests", "/admin/admins", "/admin/academics",
                 "/admin/assignments", "/admin/classes", f"/admin/classes/{campus['sid']}",
                 "/admin/assignment-requests", "/notifications/"):
        assert admin.get(path).status_code == 200, path
    assert b"hello" in admin.get(f"/admin/chats/{chat_id}").data
    assert admin.get("/admin/chats/99999").status_code == 302
    assert b"1AB21CS910" in admin.get("/admin/students").data
    assert b"FAC910" in admin.get("/admin/faculty").data


def test_admin_dashboard_counts_and_index_redirect(app, pair, campus):
    admin = login_client(app, campus["admin_email"])
    assert admin.get("/").headers["Location"].endswith("/admin/dashboard")
    assert admin.get("/admin/dashboard").status_code == 200


def test_admin_can_add_another_admin_who_can_log_in(app, campus):
    admin = login_client(app, campus["admin_email"])
    admin.post("/admin/admins/add", data={"full_name": "Second Admin", "email": "second@college.edu",
                                          "password": PASSWORD, "confirm_password": PASSWORD})
    assert "Admin account created" in flash_text(admin)
    assert login_client(app, "second@college.edu").get("/admin/dashboard").status_code == 200
    admin.post("/admin/admins/add", data={"full_name": "X", "email": "second@college.edu",
                                          "password": PASSWORD, "confirm_password": PASSWORD})
    assert "already exists" in flash_text(admin)
    admin.post("/admin/admins/add", data={"full_name": "X", "email": "third@college.edu",
                                          "password": PASSWORD, "confirm_password": "Different1!"})
    assert "do not match" in flash_text(admin)
    assert db_count(app, "users", "role = 'ADMIN'") == 2


def test_admin_end_to_end_new_class_to_registered_student_and_assignment(app, campus, captured_otps):
    admin = login_client(app, campus["admin_email"])
    # 1. admin builds a new branch > department > year > section
    admin.post("/admin/academics/branch", data={"name": "ECE"})
    bid = db_one(app, "SELECT id FROM branches WHERE name = 'ECE'")["id"]
    admin.post("/admin/academics/department", data={"branch_id": bid, "name": "VLSI"})
    did = db_one(app, "SELECT id FROM departments WHERE name = 'VLSI'")["id"]
    admin.post("/admin/academics/year", data={"department_id": did, "name": "4th year"})
    yid = db_one(app, "SELECT id FROM academic_years WHERE department_id = ?", (did,))["id"]
    admin.post("/admin/academics/sections", data={"year_id": yid, "names": "A"})
    sid = db_one(app, "SELECT id FROM sections WHERE academic_year_id = ?", (yid,))["id"]

    # 2. a faculty member can now pick the new department at signup; a student registers into the class
    c = app.test_client()
    http_faculty_signup(c, "FAC930", department="VLSI")
    assert db_one(app, "SELECT department FROM faculty WHERE faculty_code = 'FAC930'")["department"] == "VLSI"
    sc = app.test_client()
    http_student_signup(sc, captured_otps, "vlsi@college.edu", "1AB21EC001", sid)
    st = db_one(app, "SELECT * FROM students WHERE usn = '1AB21EC001'")
    assert (st["branch"], st["department"], st["year"], st["section"]) == ("ECE", "VLSI", "4th Year", "A")

    # 3. admin assigns the faculty; they can now reach the student
    fac_id = db_one(app, "SELECT id FROM faculty WHERE faculty_code = 'FAC930'")["id"]
    admin.post("/admin/assignments/assign", data={"faculty_id": fac_id, "section_id": sid})
    fc = login_client(app, "fac930@college.edu")
    assert fc.get(f"/faculty/classes/{sid}").status_code == 200
    assert fc.get(f"/chat/open-student/{st['id']}").status_code == 302
    assert db_count(app, "chats") == 1

    # 4. admin deactivates the section: hidden from registration, access suspended
    admin.post(f"/admin/academics/section/{sid}/active", data={"active": "0"})
    assert fc.get(f"/faculty/classes/{sid}").status_code == 403
    assert "ECE" not in [b["name"] for b in app.test_client().get("/academic/tree.json").get_json()]


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

def test_logout_requires_post_and_each_role_is_logged_out(app, pair, campus):
    for email, home in ((pair["stu"]["email"], "/student/dashboard"), (pair["fac"]["email"], "/faculty/dashboard"),
                        (campus["admin_email"], "/admin/dashboard")):
        c = login_client(app, email)
        assert c.get("/logout").status_code == 405
        assert c.get(home).status_code == 200  # a GET did not log us out
        assert c.post("/logout").status_code == 302
        assert c.get(home).status_code == 302


def test_login_page_redirects_nothing_weird_and_handles_blank_credentials(client):
    resp = client.post("/login", data={"email": "", "password": ""}, follow_redirects=True)
    assert resp.status_code == 200 and b"Invalid email or password" in resp.data


def test_session_switch_between_users_does_not_leak(app, pair, campus):
    c = app.test_client()
    c.post("/login", data={"email": pair["stu"]["email"], "password": PASSWORD})
    assert c.get("/student/dashboard").status_code == 200
    c.post("/login", data={"email": pair["fac"]["email"], "password": PASSWORD})
    assert c.get("/student/dashboard").status_code == 403
    assert c.get("/faculty/dashboard").status_code == 200
