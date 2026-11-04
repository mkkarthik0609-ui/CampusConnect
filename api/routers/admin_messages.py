"""Faculty <-> admin direct messages."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import CurrentUser, items, ok, require_role, service_errors
from api.errors import ApiError
from models import queries

router = APIRouter(prefix="/api/admin-messages")


class MessageBody(BaseModel):
    message_text: str = Field(min_length=1, max_length=5000)
    recipient_user_id: Optional[int] = None


def _row(row):
    return {
        "id": row["id"],
        "message_text": row["message_text"],
        "is_seen": bool(row["is_seen"]),
        "created_at": row["created_at"],
        "sender": {"id": row["sender_user_id"], "name": row["sender_name"], "role": row["sender_role"]},
        "recipient": {"id": row["recipient_user_id"], "name": row["recipient_name"], "role": row["recipient_role"]},
    }


def _admin_user():
    row = queries.get_db().execute(
        "SELECT * FROM users WHERE role = 'ADMIN' AND is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        raise ApiError(503, "admin_unavailable", "No active admin is available.")
    return row


@router.get("")
def list_messages(user: CurrentUser = Depends(require_role("FACULTY", "ADMIN"))):
    rows = queries.list_admin_messages(user["id"])
    if user["role"] == "ADMIN":
        rows = [r for r in rows if r["sender_role"] == "FACULTY" or r["recipient_role"] == "FACULTY"]
    queries.mark_admin_messages_seen(user["id"])
    return items([_row(r) for r in rows], total=len(rows))


@router.get("/{faculty_user_id}")
def thread(faculty_user_id: int, user: CurrentUser = Depends(require_role("FACULTY", "ADMIN"))):
    if user["role"] == "FACULTY" and faculty_user_id != user["id"]:
        raise ApiError(403, "forbidden", "You can only view your own admin conversation.")
    faculty = queries.get_user_by_id(faculty_user_id)
    if not faculty or faculty["role"] != "FACULTY" or not faculty["is_active"]:
        raise ApiError(404, "not_found", "Faculty member not found.")
    rows = queries.list_admin_messages(user["id"], faculty_user_id)
    queries.mark_admin_messages_seen(user["id"], faculty_user_id)
    return items([_row(r) for r in rows], total=len(rows), faculty={"id": faculty["id"], "name": faculty["full_name"]})


@router.post("", status_code=201)
def send_message(body: MessageBody, user: CurrentUser = Depends(require_role("FACULTY", "ADMIN"))):
    text = body.message_text.strip()
    if not text:
        raise ApiError(422, "validation_error", "Message cannot be blank.")
    if user["role"] == "FACULTY":
        recipient = _admin_user()
    else:
        if not body.recipient_user_id:
            raise ApiError(422, "validation_error", "Select a faculty member.")
        recipient = queries.get_user_by_id(body.recipient_user_id)
        if not recipient or recipient["role"] != "FACULTY" or not recipient["is_active"]:
            raise ApiError(404, "not_found", "Faculty member not found.")
    with service_errors():
        message_id = queries.create_admin_message(user["id"], recipient["id"], text)
    row = queries.list_admin_messages(user["id"], recipient["id"])[-1]
    return ok("Message sent.", id=message_id, item=_row(row))
