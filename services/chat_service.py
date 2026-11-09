"""Business rules of the messaging screens: student <-> faculty chats (``messages``) and faculty <-> admin
messages (``admin_messages``). Both tables share the WhatsApp-style behaviour (reply, edit window, unsend,
delete-for-me), so those functions take the ``table`` they work on. Access control (who may touch which
conversation) is decided by the callers before they get here."""
from datetime import datetime, timedelta, timezone

from models import queries
from services import file_service
from services import notification_service as notif


class ChatAccessError(Exception):
    pass


class ChatEditError(Exception):
    pass


MAX_MESSAGE_LENGTH = 4000
ADMIN_MAX_MESSAGE_LENGTH = 5000
EDIT_WINDOW = timedelta(minutes=15)  # WhatsApp rule: a sender may edit a text message for 15 minutes
_MAX_LENGTH = {"messages": MAX_MESSAGE_LENGTH, "admin_messages": ADMIN_MAX_MESSAGE_LENGTH}


def open_chat(student_id, faculty_id, viewer_user_id=None):
    """Get-or-create the chat of this pair. Does NOT mark anything seen (reading the chat does);
    ``viewer_user_id`` is accepted for backwards compatibility only."""
    if not queries.is_faculty_accessible_to_student(student_id, faculty_id):
        raise ChatAccessError("You do not have permission to message this faculty member.")
    return queries.get_or_create_chat(student_id, faculty_id)


def open_chat_as_faculty(faculty_id, student_id, viewer_user_id=None):
    if not queries.is_student_accessible_to_faculty(faculty_id, student_id):
        raise ChatAccessError("You can only message students in your assigned classes or supporting students.")
    return queries.get_or_create_chat(student_id, faculty_id)


def get_chat_for_participant(chat_id, user_id, role):
    chat = queries.get_chat_by_id(chat_id)
    if not chat:
        raise ChatAccessError("Conversation not found.")
    if role == "STUDENT":
        student = queries.get_student_by_user_id(user_id)
        if not student or student["id"] != chat["student_id"]:
            raise ChatAccessError("You do not have access to this conversation.")
        if not queries.is_faculty_accessible_to_student(student["id"], chat["faculty_id"]):
            raise ChatAccessError("This faculty member is no longer assigned to your class.")
    elif role == "FACULTY":
        faculty = queries.get_faculty_by_user_id(user_id)
        if not faculty or faculty["id"] != chat["faculty_id"]:
            raise ChatAccessError("You do not have access to this conversation.")
        if not queries.is_student_accessible_to_faculty(faculty["id"], chat["student_id"]):
            raise ChatAccessError("This student is no longer in one of your assigned classes.")
    else:
        raise ChatAccessError("Only students and faculty can access chats.")
    return chat


# ---------------------------------------------------------------- sending

def _clean_text(text, table):
    text = (text or "").strip()
    if not text:
        raise ChatEditError("Message cannot be empty.")
    if len(text) > _MAX_LENGTH[table]:
        raise ChatEditError(f"Message is too long (max {_MAX_LENGTH[table]} characters).")
    return text


def check_reply_target(table, reply_to_id, in_conversation):
    """``reply_to_id`` must be an existing message of the SAME conversation (``in_conversation(row) -> bool``)."""
    if reply_to_id is None:
        return None
    target = queries.get_message_by_id(reply_to_id, table)
    if target is None or not in_conversation(target):
        raise ChatEditError("You can only reply to a message in this conversation.")
    return reply_to_id


def send_text_message(chat_id, sender_user_id, text, reply_to_id=None):
    text = _clean_text(text, "messages")
    reply_to_id = check_reply_target("messages", reply_to_id, lambda r: r["chat_id"] == chat_id)
    return _send_and_notify(chat_id, sender_user_id, message_text=text, reply_to_id=reply_to_id)


def send_attachment_message(chat_id, sender_user_id, relative_path, attachment_type, original_name, caption=None,
                            reply_to_id=None):
    caption = (caption or "").strip() or None
    if caption and len(caption) > MAX_MESSAGE_LENGTH:
        raise ChatEditError(f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).")
    reply_to_id = check_reply_target("messages", reply_to_id, lambda r: r["chat_id"] == chat_id)
    return _send_and_notify(
        chat_id, sender_user_id, message_text=caption, attachment_path=relative_path,
        attachment_type=attachment_type, attachment_original_name=original_name, reply_to_id=reply_to_id,
    )


def _send_and_notify(chat_id, sender_user_id, message_text=None, attachment_path=None,
                      attachment_type=None, attachment_original_name=None, reply_to_id=None):
    message_id = queries.create_message(
        chat_id, sender_user_id, message_text, attachment_path, attachment_type, attachment_original_name,
        reply_to_id,
    )
    chat = queries.get_chat_by_id(chat_id)
    student = queries.get_student_by_id(chat["student_id"])
    faculty = queries.get_faculty_by_id(chat["faculty_id"])
    recipient_user_id = faculty["user_id"] if sender_user_id == student["user_id"] else student["user_id"]
    notif.notify(
        recipient_user_id, notif.NEW_MESSAGE, "New Mentor-Connect message",
        "You have a new message in Mentor-Connect.", "chat", chat_id,
    )
    return message_id


def send_admin_message(sender_user_id, recipient_user_id, text, reply_to_id=None):
    """Faculty <-> admin message. The caller has already decided that these two may talk."""
    text = _clean_text(text, "admin_messages")
    pair = {sender_user_id, recipient_user_id}
    reply_to_id = check_reply_target("admin_messages", reply_to_id,
                                     lambda r: {r["sender_user_id"], r["recipient_user_id"]} == pair)
    return queries.create_admin_message(sender_user_id, recipient_user_id, text, reply_to_id)


# ---------------------------------------------------------------- edit / unsend / delete for me

def _parse_utc(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def edit_window_open(created_at, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        return now - _parse_utc(created_at) <= EDIT_WINDOW
    except (TypeError, ValueError):
        return False


def can_edit(row, user_id):
    """Sender, own text-only message, not unsent, within the edit window (also what the API reports)."""
    keys = row.keys()
    has_attachment = "attachment_path" in keys and bool(row["attachment_path"])
    return (row["sender_user_id"] == user_id and not row["is_unsent"] and not has_attachment
            and edit_window_open(row["created_at"]))


def edit_message(message_id, editor_user_id, new_text, table="messages"):
    message = queries.get_message_by_id(message_id, table)
    if not message:
        raise ChatEditError("Message not found.")
    if message["sender_user_id"] != editor_user_id:
        raise ChatEditError("You can only edit your own messages.")
    if message["is_unsent"]:
        raise ChatEditError("This message was already unsent.")
    if "attachment_path" in message.keys() and message["attachment_path"]:
        raise ChatEditError("Attachments cannot be edited.")
    if not edit_window_open(message["created_at"]):
        raise ChatEditError("The 15-minute edit window has already passed for this message.")
    queries.edit_message(message_id, _clean_text(new_text, table), table)


def unsend_message(message_id, user_id, table="messages"):
    """Unsend for everyone: only the sender, at any time. Idempotent. The uploaded file is deleted from disk."""
    message = queries.get_message_by_id(message_id, table)
    if not message:
        raise ChatEditError("Message not found.")
    if message["sender_user_id"] != user_id:
        raise ChatEditError("You do not have permission to unsend this message.")
    if message["is_unsent"]:
        return
    queries.unsend_message(message_id, table)
    if "attachment_path" in message.keys():
        file_service.delete_chat_attachment(message["attachment_path"])


def delete_message_for_me(message_id, user_id, table="messages"):
    """Hide a message for ``user_id`` only (they must be one of the two participants - the caller checks).
    Idempotent."""
    message = queries.get_message_by_id(message_id, table)
    if not message:
        raise ChatEditError("Message not found.")
    queries.hide_message(message_id, message["sender_user_id"] == user_id, table)


def list_messages(chat_id):
    return queries.list_messages_for_chat(chat_id)
