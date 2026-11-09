"""Faculty <-> admin direct messages. Same WhatsApp-style behaviour as /api/chat (delivery ticks, reply, edit
window, unsend, delete-for-me, typing, presence, incremental polling); the "conversation" id is the faculty
member's *user id*. Faculty can only reach the admin; an admin can reach any active faculty member."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import CurrentUser, items, ok, require_role, service_errors
from api.errors import ApiError
from api.routers._messages import last_preview, now_str, parse_since, serialize_messages, status_of, with_presence
from api.schemas import profile_picture_url
from models import queries
from services import chat_service, presence

router = APIRouter(prefix="/api/admin-messages")
_USER = require_role("FACULTY", "ADMIN")
_TABLE = "admin_messages"


class MessageBody(BaseModel):
    message_text: str = Field(min_length=1, max_length=chat_service.ADMIN_MAX_MESSAGE_LENGTH)
    recipient_user_id: Optional[int] = None   # admins: the faculty member to write to
    reply_to_id: Optional[int] = None         # a message of the same conversation to quote


class EditBody(BaseModel):
    message_text: str = Field(min_length=1, max_length=chat_service.ADMIN_MAX_MESSAGE_LENGTH)


def _first_admin():
    return queries.get_db().execute(
        "SELECT * FROM users WHERE role = 'ADMIN' AND is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()


def _admin_user():
    row = _first_admin()
    if not row:
        raise ApiError(503, "admin_unavailable", "No active admin is available.")
    return row


def _faculty_user(user: CurrentUser, faculty_user_id: int):
    """The faculty member whose admin conversation this is (404 / 403 as for a thread)."""
    if user["role"] == "FACULTY" and faculty_user_id != user["id"]:
        raise ApiError(403, "forbidden", "You can only view your own admin conversation.")
    faculty = queries.get_user_by_id(faculty_user_id)
    if not faculty or faculty["role"] != "FACULTY" or not faculty["is_active"]:
        raise ApiError(404, "not_found", "Faculty member not found.")
    return faculty


def _party(info, user: CurrentUser) -> dict:
    """The OTHER participant, with presence. ``info``: other_user_id, full_name, profile_picture_path,
    faculty_code, department (a faculty member's details; only used when the viewer is the admin)."""
    if user["role"] == "ADMIN":
        card = {"id": info["other_user_id"], "user_id": info["other_user_id"], "role": "FACULTY",
                "full_name": info["full_name"], "code": info["faculty_code"], "faculty_code": info["faculty_code"],
                "department": info["department"], "profile_picture_url": profile_picture_url(info["profile_picture_path"])}
        return with_presence(card, info["other_user_id"], "admin", info["other_user_id"])
    admin = _first_admin()
    card = {"id": admin["id"] if admin else None, "user_id": admin["id"] if admin else None, "role": "ADMIN",
            "full_name": admin["full_name"] if admin else "Campus Admin", "code": None,
            "profile_picture_url": profile_picture_url(admin["profile_picture_path"]) if admin else None}
    return with_presence(card, card["id"], "admin", user["id"])


def _items(rows, user: CurrentUser) -> list:
    ids = {user["id"], *(r["sender_user_id"] for r in rows), *(r["recipient_user_id"] for r in rows)}
    return serialize_messages(_TABLE, rows, user["id"], queries.get_user_names(ids))


def _message_for(message_id: int, user: CurrentUser):
    """The message, if it belongs to a conversation the user takes part in."""
    message = queries.get_message_by_id(message_id, _TABLE)
    if message is None:
        raise ApiError(404, "not_found", "Message not found.")
    if user["id"] not in (message["sender_user_id"], message["recipient_user_id"]):
        raise ApiError(403, "forbidden", "You do not have access to this message.")
    return message


@router.get("")
def list_conversations(user: CurrentUser = Depends(_USER)):
    """My admin conversations: faculty see one (with the admin); an admin sees every active faculty member
    (conversations with messages first, newest first). Marks incoming messages as delivered."""
    presence.touch(user["id"])
    queries.mark_admin_messages_delivered(user["id"])
    rows = queries.list_admin_conversations(user["id"], user["id"] if user["role"] == "FACULTY" else None)
    out = []
    for r in rows:
        exists = r["last_id"] is not None
        mine = r["last_sender_user_id"] == user["id"]
        other = _party(r, user)
        out.append({
            "conversation_id": r["other_user_id"],
            "other": other,
            "unread_count": r["unread_count"],
            "last_message": last_preview(exists=exists, is_unsent=bool(r["last_is_unsent"]), mine=mine,
                                         other_name=other["full_name"], text=r["last_message_text"],
                                         attachment_name=None),
            "last_message_at": r["last_message_at"],
            "last_message_is_mine": mine if exists else None,
            "last_message_is_unsent": bool(r["last_is_unsent"]) if exists else None,
            "last_message_status": status_of(r["last_is_seen"], r["last_delivered_at"]) if exists and mine else None,
        })
    return items(out, total=len(out), total_unread=sum(c["unread_count"] for c in out))


@router.get("/{faculty_user_id}")
def thread(faculty_user_id: int, after_id: int = Query(0, ge=0),
           updated_since: Optional[str] = Query(None, description="also messages changed at/after this ISO time"),
           user: CurrentUser = Depends(_USER)):
    """One conversation (same polling contract as ``GET /api/chat/{id}``). Marks incoming messages as seen."""
    since = parse_since(updated_since)
    faculty = _faculty_user(user, faculty_user_id)
    server_time = now_str()
    presence.touch(user["id"])
    queries.mark_admin_messages_seen(user["id"], faculty_user_id if user["role"] == "ADMIN" else None)
    rows = queries.list_thread_messages(
        _TABLE, "m.sender_user_id = :f OR m.recipient_user_id = :f", {"f": faculty_user_id}, user["id"], after_id, since)
    profile = queries.get_faculty_by_user_id(faculty_user_id)
    other = _party({"other_user_id": faculty_user_id, "full_name": faculty["full_name"],
                    "profile_picture_path": faculty["profile_picture_path"],
                    "faculty_code": profile["faculty_code"] if profile else None,
                    "department": profile["department"] if profile else None}, user)
    messages = _items(rows, user)
    return {
        "chat": {"id": faculty_user_id, "other": other},
        "messages": messages,
        "last_id": max([after_id, *(m["id"] for m in messages)]),
        "server_time": server_time,
    }


@router.post("/{faculty_user_id}/typing")
def typing(faculty_user_id: int, user: CurrentUser = Depends(_USER)):
    _faculty_user(user, faculty_user_id)
    presence.set_typing("admin", faculty_user_id, user["id"])
    return ok()


@router.post("", status_code=201)
def send_message(body: MessageBody, user: CurrentUser = Depends(_USER)):
    if user["role"] == "FACULTY":
        recipient = _admin_user()
    else:
        if not body.recipient_user_id:
            raise ApiError(422, "validation_error", "Select a faculty member.")
        recipient = queries.get_user_by_id(body.recipient_user_id)
        if not recipient or recipient["role"] != "FACULTY" or not recipient["is_active"]:
            raise ApiError(404, "not_found", "Faculty member not found.")
    with service_errors():
        message_id = chat_service.send_admin_message(user["id"], recipient["id"], body.message_text, body.reply_to_id)
    presence.clear_typing("admin", recipient["id"] if user["role"] == "ADMIN" else user["id"], user["id"])
    return ok("Message sent.", id=message_id, item=_items([queries.get_message_by_id(message_id, _TABLE)], user)[0])


@router.post("/messages/{message_id}/edit")
def edit_message(message_id: int, body: EditBody, user: CurrentUser = Depends(_USER)):
    """Edit one of my own messages within 15 minutes of sending it."""
    _message_for(message_id, user)
    with service_errors():
        chat_service.edit_message(message_id, user["id"], body.message_text, _TABLE)
    return ok("Message updated.", item=_items([queries.get_message_by_id(message_id, _TABLE)], user)[0])


@router.post("/messages/{message_id}/unsend")
def unsend_message(message_id: int, user: CurrentUser = Depends(_USER)):
    """Unsend for everyone (my own message only, any time). Idempotent."""
    _message_for(message_id, user)
    with service_errors():
        chat_service.unsend_message(message_id, user["id"], _TABLE)
    return ok("Message unsent.", item=_items([queries.get_message_by_id(message_id, _TABLE)], user)[0])


@router.post("/messages/{message_id}/delete-for-me")
def delete_message_for_me(message_id: int, user: CurrentUser = Depends(_USER)):
    """Hide a message for me only. Idempotent."""
    _message_for(message_id, user)
    with service_errors():
        chat_service.delete_message_for_me(message_id, user["id"], _TABLE)
    return ok("Message deleted for you.", id=message_id)
