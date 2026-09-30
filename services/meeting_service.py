from models import queries
from services import notification_service as notif

VALID_TRANSITIONS = {
    "PENDING": {"ACCEPTED", "REJECTED", "CANCELLED"},
    "ACCEPTED": {"COMPLETED", "CANCELLED"},
    "REJECTED": set(),
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class MeetingError(Exception):
    pass


def request_meeting(student_id, faculty_id, reason, student_message):
    reason = (reason or "").strip()
    if not reason:
        raise MeetingError("Please provide a reason/topic for the meeting.")
    if not queries.is_faculty_accessible_to_student(student_id, faculty_id):
        raise MeetingError("You do not have permission to request a meeting with this faculty member.")

    meeting_id = queries.create_meeting_request(student_id, faculty_id, reason, (student_message or "").strip())
    faculty = queries.get_faculty_by_id(faculty_id)
    notif.notify(
        faculty["user_id"], notif.MEETING_REQUESTED, "New meeting request",
        f"A student has requested a meeting: {reason}", "meeting", meeting_id,
    )
    return meeting_id


def _require_faculty_owns_meeting(meeting, faculty_id):
    if meeting["faculty_id"] != faculty_id:
        raise MeetingError("You are not authorized to act on this meeting request.")


def _require_student_owns_meeting(meeting, student_id):
    if meeting["student_id"] != student_id:
        raise MeetingError("You are not authorized to act on this meeting request.")


def respond_to_meeting(meeting_id, faculty_id, accept: bool, faculty_response, meeting_time_text=None):
    meeting = queries.get_meeting_by_id(meeting_id)
    if not meeting:
        raise MeetingError("Meeting request not found.")
    _require_faculty_owns_meeting(meeting, faculty_id)
    if meeting["status"] != "PENDING":
        raise MeetingError("This meeting request has already been responded to.")
    if not queries.is_student_accessible_to_faculty(faculty_id, meeting["student_id"]):
        raise MeetingError("This student is no longer in one of your assigned classes.")

    if accept:
        meeting_time_text = (meeting_time_text or "").strip()
        if not meeting_time_text:
            raise MeetingError("Please provide the meeting timing when accepting a request.")
        new_status = "ACCEPTED"
    else:
        new_status = "REJECTED"
        meeting_time_text = None

    queries.respond_meeting_request(meeting_id, new_status, (faculty_response or "").strip(), meeting_time_text)
    student = queries.get_student_by_id(meeting["student_id"])
    notif_type = notif.MEETING_ACCEPTED if accept else notif.MEETING_REJECTED
    body = (
        f"Your meeting request was accepted. Timing: {meeting_time_text}"
        if accept else "Your meeting request was rejected."
    )
    notif.notify(student["user_id"], notif_type, "Meeting request update", body, "meeting", meeting_id)
    return new_status


def cancel_meeting(meeting_id, actor_user_id, actor_role, reason):
    meeting = queries.get_meeting_by_id(meeting_id)
    if not meeting:
        raise MeetingError("Meeting request not found.")
    if meeting["status"] not in VALID_TRANSITIONS or "CANCELLED" not in VALID_TRANSITIONS[meeting["status"]]:
        raise MeetingError("This meeting cannot be cancelled from its current status.")

    reason = (reason or "").strip()
    if actor_role == "STUDENT":
        student = queries.get_student_by_user_id(actor_user_id)
        _require_student_owns_meeting(meeting, student["id"])
        if not reason:
            raise MeetingError("Please provide a reason for cancelling this meeting.")
        cancelled_by = "STUDENT"
        recipient_user_id = queries.get_faculty_by_id(meeting["faculty_id"])["user_id"]
    else:
        faculty = queries.get_faculty_by_user_id(actor_user_id)
        _require_faculty_owns_meeting(meeting, faculty["id"])
        cancelled_by = "FACULTY"
        recipient_user_id = queries.get_student_by_id(meeting["student_id"])["user_id"]

    queries.cancel_meeting_request(meeting_id, cancelled_by, reason or None)
    notif.notify(
        recipient_user_id, notif.MEETING_CANCELLED, "Meeting cancelled",
        f"The meeting was cancelled by the {cancelled_by.lower()}." + (f" Reason: {reason}" if reason else ""),
        "meeting", meeting_id,
    )


def complete_meeting(meeting_id, actor_user_id, actor_role):
    meeting = queries.get_meeting_by_id(meeting_id)
    if not meeting:
        raise MeetingError("Meeting request not found.")
    if meeting["status"] != "ACCEPTED":
        raise MeetingError("Only an accepted meeting can be marked completed.")

    if actor_role == "STUDENT":
        student = queries.get_student_by_user_id(actor_user_id)
        _require_student_owns_meeting(meeting, student["id"])
        completed_by = "STUDENT"
        recipient_user_id = queries.get_faculty_by_id(meeting["faculty_id"])["user_id"]
    else:
        faculty = queries.get_faculty_by_user_id(actor_user_id)
        _require_faculty_owns_meeting(meeting, faculty["id"])
        completed_by = "FACULTY"
        recipient_user_id = queries.get_student_by_id(meeting["student_id"])["user_id"]

    queries.complete_meeting_request(meeting_id, completed_by)
    notif.notify(
        recipient_user_id, notif.MEETING_COMPLETED, "Meeting marked completed",
        f"The meeting was marked completed by the {completed_by.lower()}.", "meeting", meeting_id,
    )


def send_due_reminders(app):
    """Called by the APScheduler job. Sends a reminder for every PENDING/ACCEPTED meeting
    whose last reminder was sent more than REMINDER_INTERVAL_MINUTES ago (or never)."""
    from datetime import datetime, timedelta
    with app.app_context():
        interval = timedelta(minutes=app.config["REMINDER_INTERVAL_MINUTES"])
        cutoff = datetime.utcnow() - interval
        for meeting in queries.list_active_meetings_for_reminders():
            last = meeting["last_reminder_at"]
            # last_reminder_at is stored by SQLite as 'YYYY-MM-DD HH:MM:SS' (space, not 'T'),
            # so compare in that same format or same-day comparisons always look "old".
            if last and last > cutoff.strftime("%Y-%m-%d %H:%M:%S"):
                continue
            student = queries.get_student_by_id(meeting["student_id"])
            faculty = queries.get_faculty_by_id(meeting["faculty_id"])
            label = "pending response" if meeting["status"] == "PENDING" else "upcoming/active meeting"
            notif.notify(
                student["user_id"], notif.MEETING_REMINDER, "Meeting reminder",
                f"Reminder: you have a {label} ({meeting['reason']}).", "meeting", meeting["id"],
            )
            notif.notify(
                faculty["user_id"], notif.MEETING_REMINDER, "Meeting reminder",
                f"Reminder: you have a {label} ({meeting['reason']}).", "meeting", meeting["id"],
            )
            queries.update_meeting_reminder_time(meeting["id"])
