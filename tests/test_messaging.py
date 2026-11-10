"""WhatsApp-style messaging on both message tables (student <-> faculty chats, faculty <-> admin messages):
delivery ticks, replies, unsend / delete-for-me, the 15-minute edit window, polling with ``updated_since``,
typing + presence, and the admin read-only viewer. Access rules themselves are covered in test_chat_service /
test_access_control; here we only re-check that the new endpoints honour them."""
import io
import os

import pytest

from services import presence
from tests.conftest import (
    ADMIN_EMAIL, api_post, assign, create_admin, create_faculty, create_student, db_count, db_exec, db_one,
    login_client, section_id_for, unassign,
)

from tests.conftest import REAL_PNG as PNG, blob_paths  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_presence():
    presence.reset()
    yield
    presence.reset()


@pytest.fixture
def pair(app):
    """Admin + an assigned faculty/student pair with logged-in clients and an opened chat."""
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F3")
    stu = create_student(app, "1AB21CS002", sec)
    assign(app, fac, sec, admin_id)
    sc, fc = login_client(app, stu["email"]), login_client(app, fac["email"])
    chat_id = api_post(sc, "/api/chat/open", json={"faculty_id": fac["faculty_id"]}).json()["chat_id"]
    return dict(admin=admin_id, sec=sec, fac=fac, stu=stu, sc=sc, fc=fc, chat_id=chat_id)


def _send(client, cid, text="hello", **extra):
    r = api_post(client, f"/api/chat/{cid}/messages", json={"message_text": text, **extra})
    assert r.status_code == 201, r.text
    return r.json()["item"]


def _thread(client, cid, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/chat/{cid}" + (f"?{qs}" if qs else ""))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# delivery ticks + incremental sync
# ---------------------------------------------------------------------------

def test_status_progresses_sent_delivered_seen(pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    item = _send(sc, cid)
    assert item["status"] == "sent" and item["delivered_at"] is None and item["is_seen"] is False
    assert _thread(sc, cid)["messages"][0]["status"] == "sent"  # my own fetch changes nothing
    assert sc.get("/api/chat").json()["items"][0]["last_message_status"] == "sent"

    fc.get("/api/chat")  # the recipient's client fetched the chat list -> delivered (double grey tick)
    assert _thread(sc, cid)["messages"][0]["status"] == "delivered"
    row = sc.get("/api/chat").json()["items"][0]
    assert row["last_message_status"] == "delivered" and row["unread_count"] == 0
    assert fc.get("/api/chat").json()["items"][0]["last_message_status"] is None  # not my message

    _thread(fc, cid)  # the recipient opened the thread -> seen (double blue tick)
    seen = _thread(sc, cid)["messages"][0]
    assert seen["status"] == "seen" and seen["is_seen"] is True and seen["delivered_at"] and seen["seen_at"]
    assert sc.get("/api/chat").json()["items"][0]["last_message_status"] == "seen"


def test_thread_fetch_alone_goes_straight_to_seen_with_delivered_at_set(pair):
    item = _send(pair["sc"], pair["chat_id"])
    _thread(pair["fc"], pair["chat_id"])
    seen = _thread(pair["sc"], pair["chat_id"])["messages"][0]
    assert seen["id"] == item["id"] and seen["status"] == "seen" and seen["delivered_at"]


def test_updated_since_returns_changed_messages_and_after_id_only_new_ones(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    first = _send(sc, cid, "one")
    t0 = _thread(sc, cid)
    assert t0["last_id"] == first["id"] and t0["server_time"]
    assert [m["id"] for m in t0["messages"]] == [first["id"]]

    db_exec(app, "UPDATE messages SET updated_at = '2000-01-01 00:00:00'")
    quiet = _thread(sc, cid, after_id=t0["last_id"], updated_since=t0["server_time"].replace(" ", "T") + "Z")
    assert quiet["messages"] == [] and quiet["last_id"] == first["id"]

    _thread(fc, cid)  # recipient reads -> the old message changed (seen) ...
    second = _send(fc, cid, "two")  # ... and a new one arrives
    changed = _thread(sc, cid, after_id=t0["last_id"], updated_since=t0["server_time"])
    by_id = {m["id"]: m for m in changed["messages"]}
    assert set(by_id) == {first["id"], second["id"]}
    assert by_id[first["id"]]["status"] == "seen" and changed["last_id"] == second["id"]
    # after_id alone never re-sends old messages
    assert [m["id"] for m in _thread(sc, cid, after_id=first["id"])["messages"]] == [second["id"]]


def test_updated_since_must_be_an_iso_timestamp(pair):
    r = pair["sc"].get(f"/api/chat/{pair['chat_id']}?updated_since=yesterday")
    assert r.status_code == 400 and "updated_since" in r.json()["error"]["fields"]


def test_list_exposes_preview_unread_presence_and_sorts_by_last_activity(app, pair):
    other = create_student(app, "1AB21CS004", pair["sec"])
    oc = login_client(app, other["email"])
    cid2 = api_post(oc, "/api/chat/open", json={"faculty_id": pair["fac"]["faculty_id"]}).json()["chat_id"]
    _send(pair["sc"], pair["chat_id"], "first")
    _send(oc, cid2, "second")
    db_exec(app, "UPDATE messages SET created_at = '2030-01-01 00:00:00' WHERE message_text = 'second'")
    listing = pair["fc"].get("/api/chat").json()
    assert [c["chat_id"] for c in listing["items"]] == [cid2, pair["chat_id"]]
    assert listing["total_unread"] == 2
    row = pair["sc"].get("/api/chat").json()["items"][0]
    pair["fc"].get("/api/chat")
    row = pair["sc"].get("/api/chat").json()["items"][0]
    assert row["other"]["online"] is True and row["other"]["last_active_at"]


# ---------------------------------------------------------------------------
# reply / quote
# ---------------------------------------------------------------------------

def test_reply_embeds_a_compact_quote(pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    original = _send(sc, cid, "Can we meet on Friday?")
    reply = _send(fc, cid, "Yes, 3pm works", reply_to_id=original["id"])
    quote = reply["reply_to"]
    assert quote["id"] == original["id"] and quote["text_preview"] == "Can we meet on Friday?"
    assert quote["is_mine"] is False and quote["sender_name"].startswith("Student")
    assert quote["attachment_kind"] is None and quote["unsent"] is False
    seen_by_student = _thread(sc, cid)["messages"][-1]
    assert seen_by_student["reply_to"]["is_mine"] is True and seen_by_student["reply_to"]["id"] == original["id"]
    assert _send(sc, cid, "plain")["reply_to"] is None


def test_reply_to_another_chat_or_missing_message_is_rejected(app, pair):
    other = create_student(app, "1AB21CS004", pair["sec"])
    oc = login_client(app, other["email"])
    cid2 = api_post(oc, "/api/chat/open", json={"faculty_id": pair["fac"]["faculty_id"]}).json()["chat_id"]
    foreign = _send(oc, cid2, "private to the other chat")
    before = db_count(app, "messages")
    for target in (foreign["id"], 99999):
        r = api_post(pair["sc"], f"/api/chat/{pair['chat_id']}/messages",
                     json={"message_text": "sneaky", "reply_to_id": target})
        assert r.status_code == 400, r.text
    files = {"attachment": ("x.png", io.BytesIO(PNG), "image/png")}
    r = api_post(pair["sc"], f"/api/chat/{pair['chat_id']}/messages", files=files,
                 data={"reply_to_id": str(foreign["id"])})
    assert r.status_code == 400
    assert db_count(app, "messages") == before
    assert blob_paths(app, "chat/") == []  # the refused reply stored no file


def test_reply_with_attachment_and_attachment_quote(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("pic.png", io.BytesIO(PNG), "image/png")})
    pic = r.json()["item"]
    quoted = _send(fc, cid, "nice", reply_to_id=pic["id"])["reply_to"]
    assert quoted["attachment_kind"] == "image" and quoted["attachment_name"] == "pic.png" and quoted["text_preview"] is None
    r = api_post(fc, f"/api/chat/{cid}/messages", files={"attachment": ("n.png", io.BytesIO(PNG), "image/png")},
                 data={"message_text": "re", "reply_to_id": str(pic["id"])})
    assert r.status_code == 201 and r.json()["item"]["reply_to"]["id"] == pic["id"]


# ---------------------------------------------------------------------------
# unsend ("Unsend for everyone")
# ---------------------------------------------------------------------------

def test_sender_unsends_and_the_recipient_sees_a_tombstone(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    msg = _send(sc, cid, "this was a mistake")
    _thread(fc, cid)  # already seen: unsend still works, any time
    db_exec(app, "UPDATE messages SET created_at = datetime('now', '-3 days')")
    r = api_post(sc, f"/api/chat/messages/{msg['id']}/unsend")
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["is_unsent"] is True and item["unsent_at"] and item["message_text"] is None
    assert item["attachment"] is None and item["can_edit"] is False and item["can_unsend"] is False
    row = db_one(app, "SELECT * FROM messages WHERE id = ?", (msg["id"],))
    assert row["message_text"] is None and row["is_unsent"] == 1 and row["unsent_at"]

    for client in (fc, sc):
        tomb = _thread(client, cid)["messages"][0]
        assert tomb["is_unsent"] is True and tomb["message_text"] is None and "mistake" not in str(tomb)
    assert sc.get("/api/chat").json()["items"][0]["last_message"] == "You unsent a message"
    preview = fc.get("/api/chat").json()["items"][0]
    assert preview["last_message"].endswith("unsent a message") and preview["last_message"] != "You unsent a message"
    assert preview["last_message_is_unsent"] is True

    # idempotent
    again = api_post(sc, f"/api/chat/messages/{msg['id']}/unsend")
    assert again.status_code == 200 and again.json()["item"]["is_unsent"] is True
    # an unsent message can no longer be edited
    r = api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "revive"})
    assert r.status_code == 409
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] is None


def test_only_the_sender_can_unsend(app, pair):
    msg = _send(pair["sc"], pair["chat_id"], "keep me")
    r = api_post(pair["fc"], f"/api/chat/messages/{msg['id']}/unsend")
    assert r.status_code == 403
    assert api_post(pair["fc"], "/api/chat/messages/99999/unsend").status_code == 404
    outsider = login_client(app, create_student(app, "1AB21CS009", pair["sec"])["email"])
    assert api_post(outsider, f"/api/chat/messages/{msg['id']}/unsend").status_code == 403
    assert db_one(app, "SELECT message_text, is_unsent FROM messages")["message_text"] == "keep me"


def test_unsend_deletes_the_uploaded_file_and_hides_it_from_everyone(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    r = api_post(sc, f"/api/chat/{cid}/messages", files={"attachment": ("notes.png", io.BytesIO(PNG), "image/png")},
                 data={"message_text": "secret caption"})
    item = r.json()["item"]
    assert len(blob_paths(app, "chat/")) == 1 and fc.get(item["attachment"]["url"]).status_code == 200

    done = api_post(sc, f"/api/chat/messages/{item['id']}/unsend").json()["item"]
    assert done["attachment"] is None and done["message_text"] is None
    assert blob_paths(app, "chat/") == []
    row = db_one(app, "SELECT * FROM messages")
    assert row["attachment_path"] is None and row["attachment_original_name"] is None and row["message_text"] is None
    assert fc.get(item["attachment"]["url"]).status_code == 404
    assert sc.get(item["attachment"]["url"]).status_code == 404
    assert _thread(fc, cid)["messages"][0]["attachment"] is None
    assert fc.get("/api/chat").json()["items"][0]["last_message"].endswith("unsent a message")


def test_unsent_content_never_leaks_to_the_admin_or_into_quotes(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    target = _send(sc, cid, "top secret")
    quoting = _send(fc, cid, "ok", reply_to_id=target["id"])
    api_post(sc, f"/api/chat/messages/{target['id']}/unsend")
    quote = {m["id"]: m for m in _thread(fc, cid)["messages"]}[quoting["id"]]["reply_to"]
    assert quote["unsent"] is True and quote["text_preview"] is None

    ac = login_client(app, ADMIN_EMAIL)
    detail = ac.get(f"/api/admin/chats/{cid}").json()
    tomb = detail["messages"][0]
    assert tomb["is_unsent"] is True and tomb["message_text"] is None and tomb["attachment_url"] is None
    assert "top secret" not in ac.get(f"/api/admin/chats/{cid}").text
    assert detail["messages"][1]["reply_to"]["unsent"] is True
    listing = ac.get("/api/admin/chats").json()["items"][0]
    assert "top secret" not in str(listing)
    # a message that quoted something and is then unsent forgets its quote
    api_post(fc, f"/api/chat/messages/{quoting['id']}/unsend")
    assert db_one(app, "SELECT reply_to_id FROM messages WHERE id = ?", (quoting["id"],))["reply_to_id"] is None
    assert ac.get("/api/admin/chats").json()["items"][0]["last_message"].endswith("unsent a message")


def test_unsend_and_delete_for_me_need_current_chat_access(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    msg = _send(sc, cid, "before revocation")
    unassign(app, pair["fac"], pair["sec"], pair["admin"])
    assert api_post(sc, f"/api/chat/messages/{msg['id']}/unsend").status_code == 403
    assert api_post(sc, f"/api/chat/messages/{msg['id']}/delete-for-me").status_code == 403
    assert api_post(fc, f"/api/chat/messages/{msg['id']}/delete-for-me").status_code == 403
    assert api_post(fc, f"/api/chat/{cid}/typing").status_code == 403
    row = db_one(app, "SELECT message_text, is_unsent, hidden_by_sender, hidden_by_recipient FROM messages")
    assert tuple(row.values()) == ("before revocation", 0, 0, 0)


# ---------------------------------------------------------------------------
# delete for me
# ---------------------------------------------------------------------------

def test_delete_for_me_hides_only_for_that_user(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    one, two = _send(sc, cid, "one"), _send(sc, cid, "two")
    r = api_post(fc, f"/api/chat/messages/{two['id']}/delete-for-me")  # the recipient hides it
    assert r.status_code == 200 and r.json()["ok"] is True
    assert [m["message_text"] for m in _thread(fc, cid)["messages"]] == ["one"]
    assert [m["message_text"] for m in _thread(sc, cid)["messages"]] == ["one", "two"]
    assert fc.get("/api/chat").json()["items"][0]["last_message"] == "one"
    assert sc.get("/api/chat").json()["items"][0]["last_message"] == "two"
    assert api_post(fc, f"/api/chat/messages/{two['id']}/delete-for-me").status_code == 200  # idempotent

    api_post(sc, f"/api/chat/messages/{one['id']}/delete-for-me")  # the sender hides their own copy
    assert [m["message_text"] for m in _thread(sc, cid)["messages"]] == ["two"]
    assert [m["message_text"] for m in _thread(fc, cid)["messages"]] == ["one"]
    # updated_since never resurrects a hidden message
    assert _thread(sc, cid, updated_since="2000-01-01T00:00:00Z")["messages"][0]["message_text"] == "two"
    # the admin viewer still sees everything
    admin_view = login_client(app, ADMIN_EMAIL).get(f"/api/admin/chats/{cid}").json()
    assert [m["message_text"] for m in admin_view["messages"]] == ["one", "two"]
    assert api_post(fc, "/api/chat/messages/99999/delete-for-me").status_code == 404


def test_hidden_incoming_messages_do_not_count_as_unread(pair):
    msg = _send(pair["sc"], pair["chat_id"], "hide before reading")
    api_post(pair["fc"], f"/api/chat/messages/{msg['id']}/delete-for-me")
    listing = pair["fc"].get("/api/chat").json()
    assert listing["total_unread"] == 0 and listing["items"][0]["last_message"] is None


# ---------------------------------------------------------------------------
# edit window
# ---------------------------------------------------------------------------

def test_edit_window_is_fifteen_minutes_from_sending(app, pair):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    msg = _send(sc, cid, "typo")
    _thread(fc, cid)  # seen messages remain editable
    r = api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "fixed"})
    assert r.status_code == 200 and r.json()["item"]["is_edited"] is True and r.json()["item"]["can_edit"] is True
    assert _thread(fc, cid, updated_since="2000-01-01T00:00:00Z")["messages"][0]["is_edited"] is True

    db_exec(app, "UPDATE messages SET created_at = datetime('now', '-14 minutes')")
    assert api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "still ok"}).status_code == 200
    db_exec(app, "UPDATE messages SET created_at = datetime('now', '-16 minutes')")
    r = api_post(sc, f"/api/chat/messages/{msg['id']}/edit", json={"message_text": "too late"})
    assert r.status_code == 409
    assert _thread(sc, cid)["messages"][0]["can_edit"] is False
    assert db_one(app, "SELECT message_text FROM messages")["message_text"] == "still ok"


# ---------------------------------------------------------------------------
# typing + presence
# ---------------------------------------------------------------------------

def test_typing_is_seen_by_the_other_side_and_expires(app, pair, monkeypatch):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    clock = {"t": 1000.0}
    monkeypatch.setattr(presence, "_mono", lambda: clock["t"])
    assert _thread(sc, cid)["chat"]["other"]["typing"] is False
    assert api_post(fc, f"/api/chat/{cid}/typing").json() == {"ok": True}
    assert _thread(sc, cid)["chat"]["other"]["typing"] is True
    assert _thread(fc, cid)["chat"]["other"]["typing"] is False  # my own typing is not shown to me
    assert sc.get("/api/chat").json()["items"][0]["other"]["typing"] is True
    clock["t"] += presence.TYPING_TTL + 0.1
    assert _thread(sc, cid)["chat"]["other"]["typing"] is False
    # sending a message clears the indicator
    api_post(fc, f"/api/chat/{cid}/typing")
    _send(fc, cid, "done typing")
    assert _thread(sc, cid)["chat"]["other"]["typing"] is False


def test_presence_online_then_last_active(app, pair, monkeypatch):
    sc, fc, cid = pair["sc"], pair["fc"], pair["chat_id"]
    assert _thread(sc, cid)["chat"]["other"]["online"] is False
    _thread(fc, cid)
    other = _thread(sc, cid)["chat"]["other"]
    assert other["online"] is True and len(other["last_active_at"]) == 19
    real = presence._wall()
    monkeypatch.setattr(presence, "_wall", lambda: real + presence.ONLINE_WINDOW + 5)
    other = _thread(sc, cid)["chat"]["other"]
    assert other["online"] is False and other["last_active_at"] is not None


def test_typing_requires_a_participant(app, pair):
    outsider = login_client(app, create_student(app, "1AB21CS009", pair["sec"])["email"])
    assert api_post(outsider, f"/api/chat/{pair['chat_id']}/typing").status_code == 403
    assert api_post(pair["sc"], "/api/chat/99999/typing").status_code in (403, 404)
    assert login_client(app, ADMIN_EMAIL).post(f"/api/chat/{pair['chat_id']}/typing").status_code in (400, 403)
    assert _thread(pair["fc"], pair["chat_id"])["chat"]["other"]["typing"] is False


# ---------------------------------------------------------------------------
# faculty <-> admin messages: the same behaviour on the second table
# ---------------------------------------------------------------------------

@pytest.fixture
def duo(app):
    admin_id = create_admin(app)
    fac = create_faculty(app, "F7")
    ac, fc = login_client(app, ADMIN_EMAIL), login_client(app, fac["email"])
    return dict(admin_id=admin_id, fac=fac, ac=ac, fc=fc, fid=fac["user_id"])


def _admin_thread(client, fid, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/admin-messages/{fid}" + (f"?{qs}" if qs else ""))
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_messages_ticks_conversations_and_unread(duo):
    fc, ac, fid = duo["fc"], duo["ac"], duo["fid"]
    r = api_post(fc, "/api/admin-messages", json={"message_text": "  Need a room  "})
    assert r.status_code == 201
    item = r.json()["item"]
    assert item["message_text"] == "Need a room" and item["status"] == "sent" and item["is_mine"] is True

    mine = fc.get("/api/admin-messages").json()
    assert mine["total"] == 1 and mine["items"][0]["other"]["role"] == "ADMIN" and mine["items"][0]["unread_count"] == 0
    assert mine["items"][0]["last_message_status"] == "sent"

    listing = ac.get("/api/admin-messages").json()  # the admin's client fetched the list -> delivered
    row = next(c for c in listing["items"] if c["conversation_id"] == fid)
    assert row["unread_count"] == 1 and row["last_message"] == "Need a room" and row["other"]["role"] == "FACULTY"
    assert listing["items"][0]["conversation_id"] == fid  # conversations with messages first
    assert fc.get("/api/admin-messages").json()["items"][0]["last_message_status"] == "delivered"
    assert _admin_thread(fc, fid)["messages"][0]["status"] == "delivered"

    seen = _admin_thread(ac, fid)  # opening the thread -> seen
    assert seen["messages"][0]["is_mine"] is False and seen["chat"]["other"]["role"] == "FACULTY"
    assert fc.get("/api/admin-messages").json()["items"][0]["last_message_status"] == "seen"
    assert next(c for c in ac.get("/api/admin-messages").json()["items"] if c["conversation_id"] == fid)["unread_count"] == 0

    reply = api_post(ac, "/api/admin-messages", json={"message_text": "Room 12", "recipient_user_id": fid,
                                                       "reply_to_id": item["id"]}).json()["item"]
    assert reply["reply_to"]["text_preview"] == "Need a room" and reply["reply_to"]["is_mine"] is False
    polled = _admin_thread(fc, fid, after_id=item["id"], updated_since="2000-01-01T00:00:00Z")
    assert polled["last_id"] == reply["id"] and {m["id"] for m in polled["messages"]} >= {reply["id"]}


def test_admin_messages_access_rules(app, duo):
    other = create_faculty(app, "F8")
    oc = login_client(app, other["email"])
    assert oc.get(f"/api/admin-messages/{duo['fid']}").status_code == 403
    assert api_post(oc, f"/api/admin-messages/{duo['fid']}/typing").status_code == 403
    assert duo["ac"].get("/api/admin-messages/99999").status_code == 404
    assert api_post(duo["ac"], "/api/admin-messages", json={"message_text": "hi"}).status_code == 422
    stu = login_client(app, create_student(app, "1AB21CS011", section_id_for(app))["email"])
    assert stu.get("/api/admin-messages").status_code == 403
    msg = api_post(duo["fc"], "/api/admin-messages", json={"message_text": "mine"}).json()["item"]
    for action in ("unsend", "delete-for-me"):
        assert api_post(oc, f"/api/admin-messages/messages/{msg['id']}/{action}").status_code == 403
    assert api_post(duo["ac"], f"/api/admin-messages/messages/{msg['id']}/unsend").status_code == 403  # not the sender
    assert api_post(duo["ac"], "/api/admin-messages/messages/99999/unsend").status_code == 404
    # a quote from another conversation is refused
    foreign = api_post(oc, "/api/admin-messages", json={"message_text": "other thread"}).json()["item"]
    r = api_post(duo["fc"], "/api/admin-messages", json={"message_text": "x", "reply_to_id": foreign["id"]})
    assert r.status_code == 400


def test_admin_messages_unsend_delete_for_me_and_edit_window(app, duo):
    fc, ac, fid = duo["fc"], duo["ac"], duo["fid"]
    secret = api_post(fc, "/api/admin-messages", json={"message_text": "classified"}).json()["item"]
    _admin_thread(ac, fid)
    db_exec(app, "UPDATE admin_messages SET created_at = datetime('now', '-2 hours')")
    assert api_post(fc, f"/api/admin-messages/messages/{secret['id']}/edit", json={"message_text": "x"}).status_code == 409
    done = api_post(fc, f"/api/admin-messages/messages/{secret['id']}/unsend")
    assert done.status_code == 200 and done.json()["item"]["is_unsent"] is True
    assert api_post(fc, f"/api/admin-messages/messages/{secret['id']}/unsend").status_code == 200  # idempotent
    row = db_one(app, "SELECT message_text, is_unsent FROM admin_messages")
    assert row["message_text"] is None and row["is_unsent"] == 1
    for client in (fc, ac):
        tomb = _admin_thread(client, fid)["messages"][0]
        assert tomb["is_unsent"] is True and tomb["message_text"] is None and "classified" not in str(tomb)
    assert ac.get("/api/admin-messages").json()["items"][0]["last_message"].endswith("unsent a message")
    assert fc.get("/api/admin-messages").json()["items"][0]["last_message"] == "You unsent a message"

    fresh = api_post(fc, "/api/admin-messages", json={"message_text": "typo"}).json()["item"]
    ok = api_post(fc, f"/api/admin-messages/messages/{fresh['id']}/edit", json={"message_text": "fixed"})
    assert ok.status_code == 200 and ok.json()["item"]["is_edited"] is True
    assert api_post(ac, f"/api/admin-messages/messages/{fresh['id']}/edit", json={"message_text": "no"}).status_code == 403

    api_post(ac, f"/api/admin-messages/messages/{fresh['id']}/delete-for-me")
    assert [m["id"] for m in _admin_thread(ac, fid)["messages"]] == [secret["id"]]
    assert [m["id"] for m in _admin_thread(fc, fid)["messages"]] == [secret["id"], fresh["id"]]


def test_admin_messages_typing_and_presence(duo, monkeypatch):
    clock = {"t": 50.0}
    monkeypatch.setattr(presence, "_mono", lambda: clock["t"])
    ac, fc, fid = duo["ac"], duo["fc"], duo["fid"]
    assert _admin_thread(fc, fid)["chat"]["other"]["online"] is False
    _admin_thread(ac, fid)
    assert _admin_thread(fc, fid)["chat"]["other"]["online"] is True
    assert api_post(ac, f"/api/admin-messages/{fid}/typing").status_code == 200
    assert _admin_thread(fc, fid)["chat"]["other"]["typing"] is True
    assert _admin_thread(ac, fid)["chat"]["other"]["typing"] is False
    clock["t"] += presence.TYPING_TTL + 1
    assert _admin_thread(fc, fid)["chat"]["other"]["typing"] is False
