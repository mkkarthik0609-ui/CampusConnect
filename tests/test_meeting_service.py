import pytest

from models import queries
from services import meeting_service
from tests.conftest import (
    create_admin, create_faculty, create_student, section_id_for, assign, unassign,
)


def _create_student_and_faculty(app):
    """Faculty F1 is assigned to the student's section (AIML 3rd A) by an admin."""
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F1")
    stu = create_student(app, "1AB21CS001", sec)
    assign(app, fac, sec, admin_id)
    return stu["student_id"], fac["faculty_id"], stu["user_id"], fac["user_id"]


def test_request_meeting_requires_reason(app):
    student_id, faculty_id, _, _ = _create_student_and_faculty(app)
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, faculty_id, "", "")


def test_request_meeting_requires_access(app):
    student_id, _, _, _ = _create_student_and_faculty(app)
    stranger = create_faculty(app, "F9")  # never assigned to the student's class
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, stranger["faculty_id"], "Doubt", "")


def test_meeting_status_transitions(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        meeting_id = meeting_service.request_meeting(student_id, faculty_id, "Doubt", "")
        meeting = queries.get_meeting_by_id(meeting_id)
        assert meeting["status"] == "PENDING"

        # accepting without timing must fail
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(meeting_id, faculty_id, True, "ok", "")

        meeting_service.respond_to_meeting(meeting_id, faculty_id, True, "Come by", "Tomorrow 3PM")
        meeting = queries.get_meeting_by_id(meeting_id)
        assert meeting["status"] == "ACCEPTED"
        assert meeting["meeting_time_text"] == "Tomorrow 3PM"

        # student cancel without reason must fail
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.cancel_meeting(meeting_id, stu_user, "STUDENT", "")

        meeting_service.complete_meeting(meeting_id, stu_user, "STUDENT")
        meeting = queries.get_meeting_by_id(meeting_id)
        assert meeting["status"] == "COMPLETED"

        # cannot cancel a completed meeting
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.cancel_meeting(meeting_id, stu_user, "STUDENT", "changed my mind")


def test_unauthorized_faculty_cannot_respond(app):
    student_id, faculty_id, _, _ = _create_student_and_faculty(app)
    other = create_faculty(app, "F2")
    with app.app_context():
        meeting_id = meeting_service.request_meeting(student_id, faculty_id, "Doubt", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(meeting_id, other["faculty_id"], True, "hi", "now")


def test_reject_and_faculty_cancel_and_complete(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m1 = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        assert meeting_service.respond_to_meeting(m1, faculty_id, False, "busy") == "REJECTED"
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(m1, faculty_id, True, "x", "now")  # already responded

        m2 = meeting_service.request_meeting(student_id, faculty_id, "B", "")
        meeting_service.cancel_meeting(m2, fac_user, "FACULTY", "")  # faculty need not give reason
        assert queries.get_meeting_by_id(m2)["status"] == "CANCELLED"

        m3 = meeting_service.request_meeting(student_id, faculty_id, "C", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(m3, fac_user, "FACULTY")  # only accepted can complete
        meeting_service.respond_to_meeting(m3, faculty_id, True, "ok", "Mon 10am")
        meeting_service.complete_meeting(m3, fac_user, "FACULTY")
        assert queries.get_meeting_by_id(m3)["completed_by"] == "FACULTY"
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(9999, fac_user, "FACULTY")


def test_other_student_cannot_cancel_or_complete(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    intruder = create_student(app, "1AB21CS777", section_id_for(app, "AIML", "3rd Year", "A"))
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.cancel_meeting(m, intruder["user_id"], "STUDENT", "because")
        meeting_service.respond_to_meeting(m, faculty_id, True, "ok", "now")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.complete_meeting(m, intruder["user_id"], "STUDENT")


def test_faculty_cannot_respond_after_assignment_removed(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
    unassign(app, {"faculty_id": faculty_id}, section_id_for(app, "AIML", "3rd Year", "A"), 1)
    with app.app_context():
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.respond_to_meeting(m, faculty_id, True, "ok", "now")
        with pytest.raises(meeting_service.MeetingError):
            meeting_service.request_meeting(student_id, faculty_id, "New", "")


def test_send_due_reminders(app):
    student_id, faculty_id, stu_user, fac_user = _create_student_and_faculty(app)
    with app.app_context():
        m = meeting_service.request_meeting(student_id, faculty_id, "A", "")
        before = queries.get_unread_notification_count(stu_user)
    meeting_service.send_due_reminders(app)
    with app.app_context():
        assert queries.get_unread_notification_count(stu_user) == before + 1
        assert queries.get_meeting_by_id(m)["last_reminder_at"]
    meeting_service.send_due_reminders(app)  # interval not elapsed -> no duplicate reminder
    with app.app_context():
        assert queries.get_unread_notification_count(stu_user) == before + 1
