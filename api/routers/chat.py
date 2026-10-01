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
from api.routers._people import Cards
from models import connect_queries as cq
from models import queries
from services import chat_service, file_service

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


def message_item(row, user_id: int) -> dict:
    mine = row["sender_user_id"] == user_id
    has_attachment = bool(row["attachment_path"])
    seen = bool(row["is_seen"])
    attachment = None
    if has_attachment:
        attachment = {
            "url": file_service.upload_url(row["attachment_path"]),
            "name": row["attachment_original_name"],
            "type": row["attachment_type"],
            "is_image": (row["attachment_type"] or "").lower() in ("png", "jpg", "jpeg"),
        }
    return {
        "id": row["id"],
        "is_mine": mine,
        "message_text": row["message_text"],
        "attachment": attachment,
        "is_seen": seen,
        "is_edited": bool(row["is_edited"]),
        "can_edit": mine and not seen and not has_attachment,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _chat_item(row, user: CurrentUser, cards: Cards) -> dict:
    student = user["role"] == "STUDENT"
    last = row["last_message_text"] or (("Attachment: " + (row["last_attachment_name"] or "file"))
                                        if row["last_attachment_name"] else None)
    return {
        "chat_id": row["chat_id"],
        "other": _faculty_party(
            {"id": row["faculty_id"], "faculty_code": row["faculty_code"], "department": row["department"],
             "full_name": row["full_name"], "profile_picture_path": row["profile_picture_path"]}, cards)
        if student else _student_party(
            {"id": row["student_id"], "usn": row["usn"], "full_name": row["full_name"],
             "profile_picture_path": row["profile_picture_path"], "section_id": row["section_id"]}, cards),
        "unread_count": row["unread_count"],
        "last_message": last,
        "last_message_at": row["last_message_at"],
        "last_message_is_mine": (row["last_sender_user_id"] == user["id"]) if row["last_sender_user_id"] else None,
        "updated_at": row["chat_updated_at"],
    }


# ---------------------------------------------------------------- request models

class OpenChatIn(ApiModel):
    faculty_id: Optional[int] = None   # students: the faculty member to talk to
    student_id: Optional[int] = None   # faculty: the student to talk to


class MessageIn(ApiModel):
    message_text: Stripped = Field(max_length=chat_service.MAX_MESSAGE_LENGTH)


class _SendPayload:
    def __init__(self, text, upload):
        self.text = text
        self.upload = upload


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
        return _SendPayload((text or "").strip(), upload)
    try:
        data = await request.json()
    except ValueError:
        raise ApiError(400, "bad_request", "The request body must be valid JSON.") from None
    try:
        model = MessageIn.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return _SendPayload(model.message_text, None)


# ---------------------------------------------------------------- endpoints

@router.get("")
def list_chats(user: CurrentUser = Depends(_PARTICIPANT)):
    """My conversations (newest activity first). Chats whose access was revoked are not listed."""
    if user["role"] == "STUDENT":
        rows = cq.list_chats_for_student(user["student_id"], user["id"])
    else:
        rows = cq.list_chats_for_faculty(user["faculty_id"], user["id"])
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
              user: CurrentUser = Depends(_PARTICIPANT)):
    """The conversation. Marks the viewer's incoming messages as seen."""
    with service_errors():
        chat = chat_service.get_chat_for_participant(chat_id, user["id"], user["role"])
    queries.mark_messages_seen(chat_id, user["id"])
    cards = Cards()
    if user["role"] == "STUDENT":
        other = _faculty_party(cq.get_faculty_card(chat["faculty_id"]), cards)
    else:
        other = _student_party(cq.get_student_card(chat["student_id"]), cards)
    rows = cq.list_messages(chat_id, after_id)
    messages = [message_item(r, user["id"]) for r in rows]
    return {
        "chat": {"id": chat_id, "other": other, "created_at": chat["created_at"], "updated_at": chat["updated_at"]},
        "messages": messages,
        "last_id": messages[-1]["id"] if messages else after_id,
    }


@router.post("/{chat_id}/messages", status_code=201)
def send_message(chat_id: int, user: CurrentUser = Depends(_PARTICIPANT),
                 payload: _SendPayload = Depends(_send_payload)):
    with service_errors():
        chat_service.get_chat_for_participant(chat_id, user["id"], user["role"])  # access first, store later
        if payload.upload is not None:
            relative_path, ext, original_name = file_service.save_chat_attachment(payload.upload)
            message_id = chat_service.send_attachment_message(
                chat_id, user["id"], relative_path, ext, original_name, caption=payload.text)
        elif payload.text:
            message_id = chat_service.send_text_message(chat_id, user["id"], payload.text)
        else:
            message = "Please enter a message or attach a file."
            raise ApiError(400, "validation_error", message, {"message_text": message})
    return ok("Message sent.", item=message_item(queries.get_message_by_id(message_id), user["id"]))


@router.post("/messages/{message_id}/edit")
def edit_message(message_id: int, body: MessageIn, user: CurrentUser = Depends(_PARTICIPANT)):
    """Edit one of my own, still unseen, text messages."""
    message = queries.get_message_by_id(message_id)
    if message is None:
        raise ApiError(404, "not_found", "Message not found.")
    with service_errors():
        chat_service.get_chat_for_participant(message["chat_id"], user["id"], user["role"])
        chat_service.edit_message(message_id, user["id"], body.message_text)
    return ok("Message updated.", item=message_item(queries.get_message_by_id(message_id), user["id"]))
