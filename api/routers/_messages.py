"""Message serializers + helpers shared by the chat and admin-messages routers (not a router itself)."""
import re
from datetime import datetime, timezone
from typing import Optional

from api.errors import ApiError
from models import queries
from services import chat_service, file_service, presence

_IMAGE_TYPES = ("png", "jpg", "jpeg")
_SINCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def now_str() -> str:
    """Server clock in the API's timestamp format (UTC); clients send it back as ``updated_since``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_since(value: Optional[str]) -> Optional[str]:
    """``updated_since`` (ISO-8601, any offset) -> 'YYYY-MM-DD HH:MM:SS' UTC, or None. 400 when malformed."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    try:
        if not _SINCE_RE.match(text):
            raise ValueError(text)
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "validation_error", "updated_since must be an ISO timestamp.",
                       {"updated_since": "Use an ISO timestamp, e.g. 2026-10-01T03:12:49Z."}) from None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def status_of(is_seen, delivered_at) -> str:
    """WhatsApp ticks: sent (one tick) -> delivered (two grey) -> seen (two blue)."""
    if is_seen:
        return "seen"
    return "delivered" if delivered_at else "sent"


def _kind(row) -> Optional[str]:
    if "attachment_path" not in row.keys() or not row["attachment_path"]:
        return None
    return "image" if (row["attachment_type"] or "").lower() in _IMAGE_TYPES else "file"


def _preview(text) -> Optional[str]:
    text = " ".join((text or "").split())
    return (text[:117] + "...") if len(text) > 120 else (text or None)


def reply_embed(target, viewer_user_id, names) -> Optional[dict]:
    """Compact quote of the message that was replied to (never carries unsent content)."""
    if target is None:
        return None
    unsent = bool(target["is_unsent"])
    kind = None if unsent else _kind(target)
    return {
        "id": target["id"],
        "is_mine": target["sender_user_id"] == viewer_user_id,
        "sender_user_id": target["sender_user_id"],
        "sender_name": names.get(target["sender_user_id"]),
        "text_preview": None if unsent else _preview(target["message_text"]),
        "attachment_kind": kind,
        "attachment_name": target["attachment_original_name"] if kind else None,
        "unsent": unsent,
    }


def message_item(row, viewer_user_id, names, replies) -> dict:
    """One message for ``viewer_user_id``. An unsent message is a tombstone: no text, attachment or quote."""
    mine = row["sender_user_id"] == viewer_user_id
    unsent = bool(row["is_unsent"])
    attachment = None
    if not unsent and "attachment_path" in row.keys() and row["attachment_path"]:
        attachment = {
            "url": file_service.upload_url(row["attachment_path"]),
            "name": row["attachment_original_name"],
            "type": row["attachment_type"],
            "is_image": (row["attachment_type"] or "").lower() in _IMAGE_TYPES,
        }
    return {
        "id": row["id"],
        "is_mine": mine,
        "sender_name": names.get(row["sender_user_id"]),
        "message_text": None if unsent else row["message_text"],
        "attachment": attachment,
        "status": status_of(row["is_seen"], row["delivered_at"]),
        "is_seen": bool(row["is_seen"]),
        "delivered_at": row["delivered_at"],
        "seen_at": row["seen_at"],
        "is_edited": bool(row["is_edited"]) and not unsent,
        "is_unsent": unsent,
        "unsent_at": row["unsent_at"],
        "can_edit": chat_service.can_edit(row, viewer_user_id),
        "can_unsend": mine and not unsent,
        "reply_to": None if unsent else reply_embed(replies.get(row["reply_to_id"]), viewer_user_id, names),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def serialize_messages(table, rows, viewer_user_id, names) -> list:
    replies = queries.get_messages_by_ids(table, [r["reply_to_id"] for r in rows if r["reply_to_id"]])
    return [message_item(r, viewer_user_id, names, replies) for r in rows]


def with_presence(party: dict, user_id, scope: str, conversation_id) -> dict:
    """Add ``online`` / ``last_active_at`` / ``typing`` of the other participant to their card."""
    party.update(presence.status(user_id))
    party["typing"] = presence.is_typing(scope, conversation_id, user_id)
    return party


def last_preview(*, exists, is_unsent, mine, other_name, text, attachment_name) -> Optional[str]:
    """Chat-list preview of the last message; tombstones show who unsent, never the old content."""
    if not exists:
        return None
    if is_unsent:
        return "You unsent a message" if mine else f"{other_name} unsent a message"
    return text or (f"Attachment: {attachment_name or 'file'}" if attachment_name else None)
