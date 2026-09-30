import pytest

from models import queries
from services import chat_service, supporting_service
from tests.conftest import (
    create_admin, create_faculty, create_student, section_id_for, assign, unassign, db_count,
)


@pytest.fixture
def world(app):
    """One admin, one faculty and one student (AIML 3rd A). Faculty is NOT assigned yet."""
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F3")
    stu = create_student(app, "1AB21CS002", sec)
    return {"admin": admin_id, "sec": sec, "fac": fac, "stu": stu}


def test_chat_requires_relationship(app, world):
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                              world["fac"]["user_id"])
    assert db_count(app, "chats") == 0


def test_chat_allowed_after_assignment_to_students_section(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        c1 = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        c2 = chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                               world["fac"]["user_id"])
        assert c1["id"] == c2["id"]  # one chat per student/faculty pair


def test_chat_denied_for_assignment_to_other_section(app, world):
    assign(app, world["fac"], section_id_for(app, "AIML", "3rd Year", "B"), world["admin"])
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])


def test_chat_allowed_via_accepted_supporting_relationship(app, world):
    with app.app_context():
        rel = supporting_service.student_request_faculty(world["stu"]["student_id"], world["fac"]["faculty_id"])
        # still pending: no access
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        supporting_service.respond_to_request(rel, world["fac"]["user_id"], "FACULTY", True)
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        assert chat["id"]


def test_message_edit_locked_after_seen(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    stu_user, fac_user = world["stu"]["user_id"], world["fac"]["user_id"]
    sid, fid = world["stu"]["student_id"], world["fac"]["faculty_id"]
    with app.app_context():
        chat = chat_service.open_chat(sid, fid, stu_user)
        message_id = chat_service.send_text_message(chat["id"], stu_user, "Hello")

        # editable before faculty has seen it
        chat_service.edit_message(message_id, stu_user, "Hello edited")
        message = queries.get_message_by_id(message_id)
        assert message["message_text"] == "Hello edited"
        assert message["is_edited"] == 1

        # faculty opens the chat -> marks it seen
        chat_service.open_chat(sid, fid, fac_user)
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(message_id, stu_user, "Too late")


def test_only_sender_can_edit(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        message_id = chat_service.send_text_message(chat["id"], world["stu"]["user_id"], "Hello")
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(message_id, world["fac"]["user_id"], "Hijacked")


@pytest.mark.parametrize("text,err", [("", "empty"), ("   ", "empty"), (None, "empty"), ("x" * 4001, "long")])
def test_send_text_validation(app, world, text, err):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatEditError):
            chat_service.send_text_message(chat["id"], world["stu"]["user_id"], text)
    assert db_count(app, "messages") == 0


def test_send_notifies_recipient_and_attachment_cannot_be_edited(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        chat_service.send_text_message(chat["id"], world["stu"]["user_id"], "Hi sir")
        assert queries.get_unread_notification_count(world["fac"]["user_id"]) >= 1
        att = chat_service.send_attachment_message(chat["id"], world["fac"]["user_id"], "chat/x.pdf", "pdf", "x.pdf")
        assert queries.get_unread_notification_count(world["stu"]["user_id"]) >= 1
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(att, world["fac"]["user_id"], "new")
        with pytest.raises(chat_service.ChatEditError):
            chat_service.edit_message(99999, world["fac"]["user_id"], "new")
        assert len(chat_service.list_messages(chat["id"])) == 2


def test_get_chat_for_participant_rules(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    other_stu = create_student(app, "1AB21CS003", world["sec"])
    other_fac = create_faculty(app, "F4")
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        assert chat_service.get_chat_for_participant(chat["id"], world["stu"]["user_id"], "STUDENT")
        assert chat_service.get_chat_for_participant(chat["id"], world["fac"]["user_id"], "FACULTY")
        for user, role in ((other_stu["user_id"], "STUDENT"), (other_fac["user_id"], "FACULTY"),
                           (world["admin"], "ADMIN")):
            with pytest.raises(chat_service.ChatAccessError):
                chat_service.get_chat_for_participant(chat["id"], user, role)
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.get_chat_for_participant(9999, world["stu"]["user_id"], "STUDENT")


def test_faculty_loses_chat_access_when_assignment_removed(app, world):
    assign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        chat = chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
    unassign(app, world["fac"], world["sec"], world["admin"])
    with app.app_context():
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.get_chat_for_participant(chat["id"], world["fac"]["user_id"], "FACULTY")
        with pytest.raises(chat_service.ChatAccessError):  # ...and the student side is closed as well
            chat_service.get_chat_for_participant(chat["id"], world["stu"]["user_id"], "STUDENT")
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat(world["stu"]["student_id"], world["fac"]["faculty_id"], world["stu"]["user_id"])
        with pytest.raises(chat_service.ChatAccessError):
            chat_service.open_chat_as_faculty(world["fac"]["faculty_id"], world["stu"]["student_id"],
                                              world["fac"]["user_id"])
    assert db_count(app, "chats") == 1  # history is preserved
