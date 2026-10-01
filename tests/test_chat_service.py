"""Chat: service rules (access, edit lock, validation) and the /api/chat endpoints."""
import io

import pytest

from models import queries
from services import chat_service, supporting_service
from tests.conftest import (
    api_post, assign, create_admin, create_faculty, create_student, db_count, db_exec, db_one, login_client,
    section_id_for, unassign,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def world(app):
    """One admin, one faculty and one student (AIML 3rd A). Faculty is NOT assigned yet."""
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F3")
    stu = create_student(app, "1AB21CS002", sec)
    return {"admin": admin_id, "sec": sec, "fac": fac, "stu": stu}


# ---------------------------------------------------------------------------
# service level
# ---------------------------------------------------------------------------

def test_chat_requires_relationship(app, world):
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                              world["fac"]["user_id"])
    assert db_count(app, "chats") == 0


def test_chat_allowed_after_assignment_to_students_section(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        c1 = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        c2 = chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                               world["fac"]["user_id"])
        assert c1["id"] == c2["id"]  # one chat per student/faculty pair


def test_chat_denied_for_assignment_to_other_section(app, world):
    assign(app, world["fac"], section_id_for(app, "AIML", "3rd Year", "B"), world["admin"])
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])


def test_chat_allowed_via_accepted_supporting_relationship(app, world):
    with app.app_context():
        rel = supporting_service.student_request_faculty(world["stu"]["student_id"], world["fac"]["faculty_id"])
        with pytest.raises(chat_service.ChatAccessError):  # still pending: no access
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        supporting_service.respond_to_request(rel, world["fac"]["user_id"], "FACULTY", True)
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        assert chat["id"]


def test_message_edit_locked_after_seen(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    stu_user, fac_user = world["stu"]["user_id"], world["fac"]["user_id"]
    sid, fid = world["stu"]["student_id"], world["fac"]["faculty_id"]
    with app.app_context():
        chat = chat_service.open_chat(sid, fid, stu_user)
        message_id = chat_service.send_text_message(chat["id"], stu_user, "Hello")

        chat_service.edit_message(message_id, stu_user, "Hello edited")  # editable while unseen
        message = queries.get_message_by_id(message_id)
        assert message["message_text"] == "Hello edited"
        assert message["is_edited"] == 1

        # merely opening the chat does not mark anything seen ...
        chat_service.open_chat_as_faculty(fid, sid, fac_user)
        chat_service.edit_message(message_id, stu_user, "Still editable")
        # ... reading it does
        queries.mark_messages_seen(chat["id"], fac_user)
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(message_id, stu_user, "Too late")


def test_only_sender_can_edit(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        message_id = chat_service.send_text_message(chat["id"], world["stu"]["user_id"], "Hello")
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(message_id, world["fac"]["user_id"], "Hijacked")


@pytest.mark.parametrize("text,err", [("", "empty"), ("   ", "empty"), (None, "empty"), ("x" * 4001, "long")])
def test_send_text_validation(app, world, text, err):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatEditError):
            chat_service.send_text_message(chat["id"], world["stu"]["user_id"], text)
    assert db_count(app, "messages") == 0


def test_send_notifies_recipient_and_attachment_cannot_be_edited(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        chat_service.send_text_message(chat["id"], world["stu"]["user_id"], "Hi sir")
        assert queries.get_unread_notification_count(world["fac"]["user_id"]) >= 1
        att = chat_service.send_attachment_message(chat["id"], world["fac"]["user_id"], "chat/x.pdf", "pdf", "x.pdf")
        assert queries.get_unread_notification_count(world["stu"]["user_id"]) >= 1
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(att, world["fac"]["user_id"], "new")
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(99999, world["fac"]["user_id"], "new")
        assert len(chat_service.list_messages(chat["id"])) == 2


def test_get_chat_for_participant_rules(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    other_stu = create_student(app, "1AB21CS003", world["sec"])
    other_fac = create_faculty(app, "F4")
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        assert chat_service.get_chat_for_participant(chat["id"], world["stu"]["user_id"], "STUDENT")
        assert chat_service.get_chat_for_participant(chat["id"], world["fac"]["user_id"], "FACULTY")
        for user, role in ((other_stu["user_id"], "STUDENT"), (other_fac["user_id"], "FACULTY"),
                           (world["admin"], "ADMIN")):
            with pytest.raises(chat_service.ChatAccessError):
                chat_service.get_chat_for_participant(chat["id"], user, role)
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.get_chat_for_participant(9999, world["stu"]["user_id"], "STUDENT")


def test_faculty_loses_chat_access_when_assignment_removed(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
    unassign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.get_chat_for_participant(chat["id"], world["fac"]["user_id"], "FACULTY")
        with pytest.raises(chat_service.ChatAccessError):  # ...and the student side is closed as well
            chat_service.get_chat_for_participant(chat["id"], world["stu"]["user_id"], "STUDENT")
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                              world["fac"]["user_id"])
    assert db_count(app, "chats") == 1  # history is preserved


# ---------------------------------------------------------------------------
# HTTP: /api/chat
# ---------------------------------------------------------------------------

@pytest.fixture
def pair(app, world):
    """Assigned faculty + student, logged-in clients, and an opened chat."""
    assign(app, world["fac"], world["sec"], world["admin"])
    sc = login_client(app, world["stu"]["email"])
    fc = login_client(app, world["fac"]["email"])
    chat_id = api_post(sc, "/api/chat/open", json={"faculty_id": world["fac"]["faculty_id"]}).json()["chat_id"]
    return dict(world, sc=sc, fc=fc, chat_id=chat_id)


def test_open_chat_both_sides_get_the_same_chat(app, pair):
    r = api_post(pair["fc"], "/api/chat/open", json={"student_id": pair["stu"]["student_id"]})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["chat_id"] == pair["chat_id"]
    assert db_count(app, "chats") == 1


def test_open_chat_validates_who_is_who(app, pair):
    sc, fc = pair["sc"], pair["fc"]
    r = api_post(sc, "/api/chat/open", json={"student_id": pair["stu"]["student_id"]})
    assert r.status_code == 400 and "student_id" in r.json()["error"]["fields"]
    assert api_post(sc, "/api/chat/open", json={}).status_code == 400
    r = api_post(fc, "/api/chat/open", json={"faculty_id": pair["fac"]["faculty_id"]})
    assert r.status_code == 400 and "faculty_id" in r.json()["error"]["fields"]
    assert api_post(sc, "/api/chat/open", json={"faculty_id": "x"}).status_code == 400
    assert api_post(sc, "/api/chat/open", json={"faculty_id": 99999}).status_code == 403  # no existence oracle


def test_send_view_and_seen_flow(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    r = api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": "  Hello sir  "})
    assert r.status_code == 201
    item = r.json()["item"]
    assert item["message_text"] == "Hello sir" and item["is_mine"] is True and item["is_seen"] is False
    assert item["can_edit"] is True and item["attachment"] is None and item["is_edited"] is False

    # the faculty list shows an unread message; nothing is marked seen by listing
    listing = fc.get("/api/chat").json()
    assert listing["total_unread"] == 1
    row = listing["items"][0]
    assert row["chat_id"] == cid and row["unread_count"] == 1 and row["last_message"] == "Hello sir"
    assert row["other"]["usn"] == "1AB21CS002" and row["other"]["role"] == "STUDENT"
    assert row["other"]["class"]["label"].endswith("3rd Year → A")
    assert row["last_message_is_mine"] is False
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 0

    # session counter uses the same number
    assert fc.get("/api/auth/session").json()["unread_messages"] == 1

    detail = fc.get(f"/api/chat/{cid}").json()
    assert detail["chat"]["other"]["full_name"].startswith("Student")
    msg = detail["messages"][0]
    assert msg["is_mine"] is False and msg["can_edit"] is False and msg["message_text"] == "Hello sir"
    assert db_one(app, "SELECT is_seen FROM messages")["is_seen"] == 1
    assert fc.get("/api/chat").json()["total_unread"] == 0

    # the sender sees "seen" and can no longer edit
    mine = sc.get(f"/api/chat/{cid}").json()["messages"][0]
    assert mine["is_mine"] is True and mine["is_seen"] is True and mine["can_edit"] is False
    # after_id polling
    assert sc.get(f"/api/chat/{cid}?after_id={mine['id']}").json()["messages"] == []


def test_edit_message_rules_over_http(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    mid = api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": "orig"}).json()["item"]["id"]
    r = api_post(fc, f"/api/chat/messages/{mid}/edit", json={"message_text": "faculty edit"})
    assert r.status_code == 403
    r = api_post(sc, f"/api/chat/messages/{mid}/edit", json={"message_text": "student edit"})
    assert r.status_code == 200 and r.json()["item"]["message_text"] == "student edit"
    assert r.json()["item"]["is_edited"] is True
    assert api_post(sc, f"/api/chat/messages/{mid}/edit", json={"message_text": "   "}).status_code == 400
    assert api_post(sc, f"/api/chat/messages/{mid}/edit", json={"message_text": "x" * 4001}).status_code == 400
    fc.get(f"/api/chat/{cid}")  # faculty reads it
    r = api_post(sc, f"/api/chat/messages/{mid}/edit", json={"message_text": "too late"})
    assert r.status_code == 409 and "already been seen" in r.json()["error"]["message"]
    assert api_post(sc, "/api/chat/messages/99999/edit", json={"message_text": "x"}).status_code == 404
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "student edit"


def test_send_validation(app, pair):
    sc, cid = pair["sc"], pair["chat_id"]
    for body in ({"message_text": ""}, {"message_text": "   "}):
        r = api_post(sc, f"/api/chat/{cid}/messages", json=body)
        assert r.status_code == 400 and "message_text" in r.json()["error"]["fields"]
    assert api_post(sc, f"/api/chat/{cid}/messages", json={}).status_code == 400
    assert api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": 5}).status_code == 400
    assert api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": "x" * 4001}).status_code == 400
    assert api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": "a", "sender": 1}).status_code == 400
    assert api_post(sc, f"/api/chat/{cid}/messages", content=b"not json",
                    headers={"Content-Type": "application/json"}).status_code == 400
    assert api_post(sc, f"/api/chat/{cid}/messages", data={}).status_code == 400  # empty form
    assert db_count(app, "messages") == 0


def test_attachment_upload_and_download(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("notes.png", io.BytesIO(PNG), "image/png")},
                 data={"message_text": "see this"})
    assert r.status_code == 201, r.text
    att = r.json()["item"]["attachment"]
    assert att["name"] == "notes.png" and att["type"] == "png" and att["url"].startswith("/uploads/chat/")
    assert r.json()["item"]["message_text"] == "see this" and r.json()["item"]["can_edit"] is False
    assert fc.get(att["url"]).status_code == 200  # participant
    assert sc.get(att["url"]).status_code == 200
    outsider = create_student(app, "1AB21CS009", pair["sec"])
    assert login_client(app, outsider["email"]).get(att["url"]).status_code == 403
    assert fc.get(f"/api/chat/{cid}").json()["messages"][0]["attachment"]["url"] == att["url"]
    assert fc.get("/api/chat").json()["items"][0]["last_message"] == "see this"

    # bad uploads are refused and store nothing
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("evil.exe", io.BytesIO(b"MZ1234"), "x/y")})
    assert r.status_code == 400
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("fake.png", io.BytesIO(b"not a png"), "image/png")})
    assert r.status_code == 400
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("big.png", io.BytesIO(PNG + b"0" * (9 * 1024 * 1024)), "image/png")})
    assert r.status_code == 413
    assert db_count(app, "messages") == 1
    # an (unseen) attachment can't be edited
    r = api_post(fc, f"/api/chat/{cid}/messages", files={"attachment": ("a.png", io.BytesIO(PNG), "image/png")})
    mid = r.json()["item"]["id"]
    assert r.json()["item"]["can_edit"] is False
    r = api_post(fc, f"/api/chat/messages/{mid}/edit", json={"message_text": "x"})
    assert r.status_code == 400 and "Attachments" in r.json()["error"]["message"]


def test_list_hides_chats_after_access_is_revoked_and_counter_drops(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    api_post(sc, f"/api/chat/{cid}/messages", json={"message_text": "ping"})
    assert fc.get("/api/auth/session").json()["unread_messages"] == 1
    unassign(app, pair["fac"], pair["sec"], pair["admin"])
    assert fc.get("/api/chat").json()["items"] == []
    assert sc.get("/api/chat").json()["items"] == []
    assert fc.get("/api/auth/session").json()["unread_messages"] == 0
    assert fc.get(f"/api/chat/{cid}").status_code == 403
    assert sc.get(f"/api/chat/{cid}").status_code == 403
    assert api_post(fc, f"/api/chat/{cid}/messages", json={"message_text": "still there?"}).status_code == 403
    assert db_count(app, "messages") == 1
    assign(app, pair["fac"], pair["sec"], pair["admin"])  # access is restored with the assignment
    assert len(fc.get("/api/chat").json()["items"]) == 1
    assert fc.get(f"/api/chat/{cid}").status_code == 200


def test_chat_list_orders_by_latest_activity(app, pair):
    other = create_student(app, "1AB21CS004", pair["sec"])
    oc = login_client(app, other["email"])
    cid2 = api_post(oc, "/api/chat/open", json={"faculty_id": pair["fac"]["faculty_id"]}).json()["chat_id"]
    api_post(pair["sc"], f"/api/chat/{pair['chat_id']}/messages", json={"message_text": "first"})
    api_post(oc, f"/api/chat/{cid2}/messages", json={"message_text": "second"})
    db_exec(app, "UPDATE messages SET created_at = '2030-01-01 00:00:00' WHERE message_text = 'second'")
    ids = [c["chat_id"] for c in pair["fc"].get("/api/chat").json()["items"]]
    assert ids == [cid2, pair["chat_id"]]
