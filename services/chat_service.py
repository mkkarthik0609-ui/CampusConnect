from models import queries
from services import notification_service as notif


class ChatAccessError(Exception):
    pass


class ChatEditError(Exception):
    pass


MAX_MESSAGE_LENGTH = 4000


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


def send_text_message(chat_id, sender_user_id, text):
    text = (text or "").strip()
    if not text:
        raise ChatEditError("Message cannot be empty.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ChatEditError(f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).")
    return _send_and_notify(chat_id, sender_user_id, message_text=text)


def send_attachment_message(chat_id, sender_user_id, relative_path, attachment_type, original_name, caption=None):
    caption = (caption or "").strip() or None
    if caption and len(caption) > MAX_MESSAGE_LENGTH:
        raise ChatEditError(f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).")
    return _send_and_notify(
        chat_id, sender_user_id, message_text=caption, attachment_path=relative_path,
        attachment_type=attachment_type, attachment_original_name=original_name,
    )


def _send_and_notify(chat_id, sender_user_id, message_text=None, attachment_path=None,
                      attachment_type=None, attachment_original_name=None):
    message_id = queries.create_message(
        chat_id, sender_user_id, message_text, attachment_path, attachment_type, attachment_original_name
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


def edit_message(message_id, editor_user_id, new_text):
    message = queries.get_message_by_id(message_id)
    if not message:
        raise ChatEditError("Message not found.")
    if message["sender_user_id"] != editor_user_id:
        raise ChatEditError("You can only edit your own messages.")
    if message["is_seen"]:
        raise ChatEditError("This message has already been seen and can no longer be edited.")
    if message["attachment_path"]:
        raise ChatEditError("Attachments cannot be edited.")
    new_text = (new_text or "").strip()
    if not new_text:
        raise ChatEditError("Message cannot be empty.")
    if len(new_text) > MAX_MESSAGE_LENGTH:
        raise ChatEditError(f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).")
    queries.edit_message(message_id, new_text)


def list_messages(chat_id):
    return queries.list_messages_for_chat(chat_id)
