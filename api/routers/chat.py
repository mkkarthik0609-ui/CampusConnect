"""/api/chat/* - one-to-one conversations between a student and a faculty member (STUDENT or FACULTY).

Access rule (enforced by ``chat_service`` on every call, so it is revoked immediately when it stops
holding): the student's registered section is an ACTIVE assignment of the faculty member, or they have an
ACCEPTED supporting relationship. Only the two participants can read or write a conversation.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import Field, ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from api.deps import ApiModel, CurrentUser, Stripped, items, ok, require_role, service_errors
from api.errors import ApiError
from api.routers._messages import (
    last_preview, now_str, parse_since, serialize_messages, status_of, with_presence,
)
from api.routers._people import Cards
from models import connect_queries as cq
from models import queries
from services import chat_service, file_service, presence

router = APIRouter(prefix="/api/chat")
_PARTICIPANT = require_role("STUDENT", "FACULTY")


# ---------------------------------------------------------------- serializers

def _faculty_party(row, cards: Cards) -> dict:
    card = cards.faculty(id=row["id"], faculty_code=row["faculty_code"], department=row["department"],
                         full_name=row["full_name"], picture_path=row["profile_picture_path"])
    return dict(card, role="FACULTY", code=card["faculty_code"])


def _student_party(row, cards: Cards) -> dict:
    card = cards.student(id=row["id"], usn=row["usn"], full_name=row["full_name"],
                         picture_path=row["profile_picture_path"], section_id=row["section_id"])
    return dict(card, role="STUDENT", code=card["usn"])


def _names(chat) -> dict:
    """{user_id: full_name} of the two participants (for quotes and "<Name> unsent a message")."""
    student, faculty = cq.get_student_card(chat["student_id"]), cq.get_faculty_card(chat["faculty_id"])
    return {student["user_id"]: student["full_name"], faculty["user_id"]: faculty["full_name"]}


def _item(message_id: int, user: CurrentUser, chat) -> dict:
    return serialize_messages("messages", [queries.get_message_by_id(message_id)], user["id"], _names(chat))[0]


def _chat_item(row, user: CurrentUser, cards: Cards) -> dict:
    student = user["role"] == "STUDENT"
    mine = row["last_sender_user_id"] == user["id"]
    other = (
        _faculty_party(
            {"id": row["faculty_id"], "faculty_code": row["faculty_code"], "department": row["department"],
             "full_name": row["full_name"], "profile_picture_path": row["profile_picture_path"]}, cards)
        if student else _student_party(
            {"id": row["student_id"], "usn": row["usn"], "full_name": row["full_name"],
             "profile_picture_path": row["profile_picture_path"], "section_id": row["section_id"]}, cards)
    )
    exists = row["last_message_id"] is not None
    return {
        "chat_id": row["chat_id"],
        "other": with_presence(other, row["other_user_id"], "chat", row["chat_id"]),
        "unread_count": row["unread_count"],
        "last_message": last_preview(
            exists=exists, is_unsent=bool(row["last_is_unsent"]), mine=mine, other_name=row["full_name"],
            text=row["last_message_text"], attachment_name=row["last_attachment_name"]),
        "last_message_at": row["last_message_at"],
        "last_message_is_mine": mine if exists else None,
        "last_message_is_unsent": bool(row["last_is_unsent"]) if exists else None,
        "last_message_status": status_of(row["last_is_seen"], row["last_delivered_at"]) if exists and mine else None,
        "updated_at": row["chat_updated_at"],
    }


# ---------------------------------------------------------------- request models

class OpenChatIn(ApiModel):
    faculty_id: Optional[int] = None   # students: the faculty member to talk to
    student_id: Optional[int] = None   # faculty: the student to talk to


class MessageIn(ApiModel):
    message_text: Stripped = Field(max_length=chat_service.MAX_MESSAGE_LENGTH)


class SendIn(MessageIn):
    reply_to_id: Optional[int] = None   # a message of the same chat to quote


class _SendPayload:
    def __init__(self, text, upload, reply_to_id=None):
        self.text = text
        self.upload = upload
        self.reply_to_id = reply_to_id


async def _send_payload(request: Request, _user: CurrentUser = Depends(_PARTICIPANT)) -> _SendPayload:
    """Body of POST /{chat_id}/messages: JSON ``{"message_text"}`` or multipart / form with an optional
    ``attachment`` file (+ optional ``message_text`` caption). Parsing only; nothing is stored here."""
    ctype = request.headers.get("content-type", "").lower()
    if ctype.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form = await request.form()
        text = form.get("message_text")
        upload = form.get("attachment")
        if text is not None and not isinstance(text, str):
            raise ApiError(400, "validation_error", "Enter a valid text value.", {"message_text": "Enter a valid text value."})
        if upload is not None and not isinstance(upload, StarletteUploadFile):
            upload = None  # an empty text field named "attachment": no file was chosen
        if upload is not None and not upload.filename:
            upload = None
        reply_to = form.get("reply_to_id")
        if reply_to in (None, ""):
            reply_to = None
        elif not isinstance(reply_to, str) or not reply_to.isdigit():
            raise ApiError(400, "validation_error", "reply_to_id must be a message id.", {"reply_to_id": "Enter a valid message id."})
        return _SendPayload((text or "").strip(), upload, int(reply_to) if reply_to else None)
    try:
        data = await request.json()
    except ValueError:
        raise ApiError(400, "bad_request", "The request body must be valid JSON.") from None
    try:
        model = SendIn.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return _SendPayload(model.message_text, None, model.reply_to_id)


# ---------------------------------------------------------------- endpoints

@router.get("")
def list_chats(user: CurrentUser = Depends(_PARTICIPANT)):
    """My conversations (newest activity first). Chats whose access was revoked are not listed.
    Fetching the list marks the incoming messages of these chats as delivered (double grey tick)."""
    if user["role"] == "STUDENT":
        rows = cq.list_chats_for_student(user["student_id"], user["id"])
    else:
        rows = cq.list_chats_for_faculty(user["faculty_id"], user["id"])
    presence.touch(user["id"])
    queries.mark_messages_delivered([r["chat_id"] for r in rows], user["id"])
    cards = Cards()
    chats = [_chat_item(r, user, cards) for r in rows]
    return items(chats, total=len(chats), total_unread=sum(c["unread_count"] for c in chats))


@router.post("/open")
def open_chat(body: OpenChatIn, user: CurrentUser = Depends(_PARTICIPANT)):
    """Get-or-create the conversation with a faculty member (students) / student (faculty)."""
    if user["role"] == "STUDENT":
        if body.student_id is not None:
            raise ApiError(400, "validation_error", "Students cannot specify a student.",
                           {"student_id": "Students cannot specify a student."})
        if body.faculty_id is None:
            raise ApiError(400, "validation_error", "faculty_id is required.", {"faculty_id": "This field is required."})
        with service_errors():
            chat = chat_service.open_chat(user["student_id"], body.faculty_id, user["id"])
    else:
        if body.faculty_id is not None:
            raise ApiError(400, "validation_error", "Faculty cannot specify a faculty member.",
                           {"faculty_id": "Faculty cannot specify a faculty member."})
        if body.student_id is None:
            raise ApiError(400, "validation_error", "student_id is required.", {"student_id": "This field is required."})
        with service_errors():
            chat = chat_service.open_chat_as_faculty(user["faculty_id"], body.student_id, user["id"])
    return ok("Chat opened.", chat_id=chat["id"])


@router.get("/{chat_id}")
def view_chat(chat_id: int, after_id: int = Query(0, ge=0, description="only messages with a larger id"),
              updated_since: Optional[str] = Query(None, description="also messages changed at/after this ISO time"),
              user: CurrentUser = Depends(_PARTICIPANT)):
    """The conversation. Marks the viewer's incoming messages as seen. For polling pass ``after_id=last_id`` and
    ``updated_since=server_time`` from the previous response: new messages AND older ones whose status /
    edit / unsend state changed come back (merge them by id)."""
    since = parse_since(updated_since)
    with service_errors():
        chat = chat_service.get_chat_for_participant(chat_id, user["id"], user["role"])
    server_time = now_str()
    presence.touch(user["id"])
    queries.mark_messages_seen(chat_id, user["id"])
    cards = Cards()
    if user["role"] == "STUDENT":
        card = cq.get_faculty_card(chat["faculty_id"])
        other = _faculty_party(card, cards)
    else:
        card = cq.get_student_card(chat["student_id"])
        other = _student_party(card, cards)
    rows = cq.list_messages(chat_id, after_id, since, user["id"])
    messages = serialize_messages("messages", rows, user["id"], _names(chat))
    return {
        "chat": {"id": chat_id, "other": with_presence(other, card["user_id"], "chat", chat_id),
                 "created_at": chat["created_at"], "updated_at": chat["updated_at"]},
        "messages": messages,
        "last_id": max([after_id, *(m["id"] for m in messages)]),
        "server_time": server_time,
    }


@router.post("/{chat_id}/typing")
def typing(chat_id: int, user: CurrentUser = Depends(_PARTICIPANT)):
    """'I am typing' signal (valid for a few seconds); the other side sees ``chat.other.typing``."""
    with service_errors():
        chat_service.get_chat_for_participant(chat_id, user["id"], user["role"])
    presence.set_typing("chat", chat_id, user["id"])
    return ok()


@router.post("/{chat_id}/messages", status_code=201)
def send_message(chat_id: int, user: CurrentUser = Depends(_PARTICIPANT),
                 payload: _SendPayload = Depends(_send_payload)):
    with service_errors():
        chat = chat_service.get_chat_for_participant(chat_id, user["id"], user["role"])  # access first, store later
        if payload.upload is None and not payload.text:
            message = "Please enter a message or attach a file."
            raise ApiError(400, "validation_error", message, {"message_text": message})
        # validate the quote before a file is stored
        chat_service.check_reply_target("messages", payload.reply_to_id, lambda r: r["chat_id"] == chat_id)
        if payload.upload is not None:
            relative_path, ext, original_name = file_service.save_chat_attachment(payload.upload)
            message_id = chat_service.send_attachment_message(
                chat_id, user["id"], relative_path, ext, original_name, caption=payload.text,
                reply_to_id=payload.reply_to_id)
        else:
            message_id = chat_service.send_text_message(chat_id, user["id"], payload.text, payload.reply_to_id)
    presence.clear_typing("chat", chat_id, user["id"])
    return ok("Message sent.", item=_item(message_id, user, chat))


def _my_message(message_id: int, user: CurrentUser):
    """(message, chat) for a message of a chat the user may still use; 404 / 403 otherwise."""
    message = queries.get_message_by_id(message_id)
    if message is None:
        raise ApiError(404, "not_found", "Message not found.")
    with service_errors():
        chat = chat_service.get_chat_for_participant(message["chat_id"], user["id"], user["role"])
    return message, chat


@router.post("/messages/{message_id}/edit")
def edit_message(message_id: int, body: MessageIn, user: CurrentUser = Depends(_PARTICIPANT)):
    """Edit one of my own text messages within 15 minutes of sending it."""
    _, chat = _my_message(message_id, user)
    with service_errors():
        chat_service.edit_message(message_id, user["id"], body.message_text)
    return ok("Message updated.", item=_item(message_id, user, chat))


@router.post("/messages/{message_id}/unsend")
def unsend_message(message_id: int, user: CurrentUser = Depends(_PARTICIPANT)):
    """Unsend for everyone: my own message becomes a tombstone (text and attachment are gone). Idempotent."""
    _, chat = _my_message(message_id, user)
    with service_errors():
        chat_service.unsend_message(message_id, user["id"])
    return ok("Message unsent.", item=_item(message_id, user, chat))


@router.post("/messages/{message_id}/delete-for-me")
def delete_message_for_me(message_id: int, user: CurrentUser = Depends(_PARTICIPANT)):
    """Hide a message for me only; the other participant still sees it. Idempotent."""
    _my_message(message_id, user)
    with service_errors():
        chat_service.delete_message_for_me(message_id, user["id"])
    return ok("Message deleted for you.", id=message_id)
