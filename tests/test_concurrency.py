"""Regression tests for races and atomicity that SQLite's single writer used to hide (PostgreSQL runs
requests truly in parallel): registrations, chat creation, meeting status changes, reminders, approvals."""
import threading

import pytest
from fastapi.testclient import TestClient

from api import db as dbmod
from models import queries
from services import auth_service, meeting_service
from tests.conftest import (
    assign, create_admin, create_faculty, create_student, db_count, db_one, find_section, http_student_signup,
    section_id_for,
)


def run_parallel(fn, n):
    results, errors = [], []
    barrier = threading.Barrier(n)

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results.append(fn(i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results, errors


def _world(app):
    admin_id = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "F1")
    stu = create_student(app, "1AB21CS001", sec)
    assign(app, fac, sec, admin_id)
    return stu, fac, admin_id


def test_parallel_signups_with_the_same_email_create_exactly_one_account(app):
    sec = find_section(app=app)
    codes = []

    def signup(i):
        c = TestClient(app)
        r = http_student_signup(c, None, "same@college.edu", f"1AB21CS{100 + i}", sec)
        codes.append(r.status_code)

    run_parallel(signup, 6)
    assert sorted(codes).count(201) == 1 and all(c in (201, 409) for c in codes), codes
    assert db_count(app, "users", "email = 'same@college.edu'") == 1
    assert db_count(app, "students") == 1  # no orphaned user / student halves


def test_registration_is_all_or_nothing(app, monkeypatch):
    sec = find_section(app=app)
    from models import academic_queries as aq

    def boom(*a, **k):
        raise RuntimeError("class link failed")

    monkeypatch.setattr(aq, "set_student_section", boom)
    with dbmod.db_session(app.state.settings):
        with pytest.raises(RuntimeError):
            auth_service.register_student({
                "full_name": "Half Done", "usn": "1AB21CS777", "section_id": sec, "phone": "9999999999",
                "personal_email": "p@example.com", "college_email": "half@college.edu", "password": "Passw0rd!x"})
    assert db_count(app, "users", "email = 'half@college.edu'") == 0
    assert db_count(app, "students", "usn = '1AB21CS777'") == 0


def test_parallel_first_messages_use_a_single_chat(app):
    stu, fac, _ = _world(app)

    def open_chat(i):
        with dbmod.db_session(app.state.settings):
            return queries.get_or_create_chat(stu["student_id"], fac["faculty_id"])["id"]

    results, errors = run_parallel(open_chat, 8)
    assert not errors, errors
    assert len(set(results)) == 1
    assert db_count(app, "chats") == 1


def test_parallel_meeting_responses_have_one_winner_and_one_notification(app):
    stu, fac, _ = _world(app)
    with dbmod.db_session(app.state.settings):
        meeting_id = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Doubt", "")

    def respond(i):
        with dbmod.db_session(app.state.settings):
            try:
                meeting_service.respond_to_meeting(meeting_id, fac["faculty_id"], i % 2 == 0, "ok", f"Slot {i}")
                return "won"
            except meeting_service.MeetingError:
                return "lost"

    results, errors = run_parallel(respond, 6)
    assert not errors, errors
    assert results.count("won") == 1
    notes = db_count(app, "notifications", "related_entity_type = 'meeting' AND related_entity_id = ? "
                                           "AND notification_type IN ('MEETING_ACCEPTED', 'MEETING_REJECTED')",
                     (meeting_id,))
    assert notes == 1


def test_cancel_and_complete_race_ends_in_exactly_one_terminal_state(app):
    stu, fac, _ = _world(app)
    with dbmod.db_session(app.state.settings):
        mid = meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Doubt", "")
        meeting_service.respond_to_meeting(mid, fac["faculty_id"], True, "ok", "Tomorrow")

    def act(i):
        with dbmod.db_session(app.state.settings):
            try:
                if i % 2:
                    meeting_service.complete_meeting(mid, fac["user_id"], "FACULTY")
                else:
                    meeting_service.cancel_meeting(mid, stu["user_id"], "STUDENT", "changed my mind")
                return "ok"
            except meeting_service.MeetingError:
                return "refused"

    results, errors = run_parallel(act, 6)
    assert not errors, errors
    assert results.count("ok") == 1
    assert db_one(app, "SELECT status FROM meeting_requests WHERE id = ?", (mid,))["status"] in ("COMPLETED", "CANCELLED")


def test_reminders_are_sent_once_even_when_runs_overlap(app):
    stu, fac, _ = _world(app)
    with dbmod.db_session(app.state.settings):
        meeting_service.request_meeting(stu["student_id"], fac["faculty_id"], "Doubt", "")
    before = db_count(app, "notifications", "notification_type = 'MEETING_REMINDER'")

    def remind(i):
        meeting_service.send_due_reminders(app.state.settings)

    _, errors = run_parallel(remind, 5)
    assert not errors, errors
    assert db_count(app, "notifications", "notification_type = 'MEETING_REMINDER'") == before + 2  # student + faculty, once
    meeting_service.send_due_reminders(app.state.settings)  # inside the interval: still nothing new
    assert db_count(app, "notifications", "notification_type = 'MEETING_REMINDER'") == before + 2


def _faculty_email_request(app, fac, new_email):
    from services import permission_service
    with dbmod.db_session(app.state.settings):
        return permission_service.faculty_request_profile_change(fac["user_id"], {"professional_email": new_email}, "new mailbox")


def test_double_approval_applies_once_and_keeps_both_email_columns_in_sync(app):
    from services import permission_service
    stu, fac, admin_id = _world(app)
    rid = _faculty_email_request(app, fac, "renamed@college.edu")

    def approve(i):
        with dbmod.db_session(app.state.settings):
            try:
                permission_service.decide_permission_request(rid, admin_id, True)
                return "won"
            except permission_service.PermissionError_:
                return "lost"

    results, errors = run_parallel(approve, 5)
    assert not errors, errors
    assert results.count("won") == 1
    assert db_one(app, "SELECT status FROM permission_requests WHERE id = ?", (rid,))["status"] == "APPROVED"
    assert db_one(app, "SELECT professional_email FROM faculty WHERE id = ?", (fac["faculty_id"],))["professional_email"] == "renamed@college.edu"
    assert db_one(app, "SELECT email FROM users WHERE id = ?", (fac["user_id"],))["email"] == "renamed@college.edu"
    assert db_count(app, "notifications", "notification_type = 'PERMISSION_RESPONDED'") == 1
    from tests.conftest import api_login
    assert api_login(TestClient(app), "renamed@college.edu")["user"]["email"] == "renamed@college.edu"


def test_email_change_to_an_address_already_in_use_is_refused_and_changes_nothing(app):
    from services import permission_service
    stu, fac, admin_id = _world(app)
    rid = _faculty_email_request(app, fac, stu["email"])  # a student already owns it
    with dbmod.db_session(app.state.settings):
        with pytest.raises(permission_service.PermissionError_):
            permission_service.decide_permission_request(rid, admin_id, True)
    assert db_one(app, "SELECT status FROM permission_requests WHERE id = ?", (rid,))["status"] == "PENDING"
    assert db_one(app, "SELECT email FROM users WHERE id = ?", (fac["user_id"],))["email"] == fac["email"]


def test_many_more_requests_than_pooled_connections_never_deadlock(tmp_path):
    """Regression (found by load test): with 40 worker threads and a small pool, requests holding connections and
    requests waiting for connections starved each other until timeouts. Admission control keeps in-flight
    requests <= pool size, so 40 simultaneous requests against a pool of 2 must all complete."""
    import time
    from api.main import create_app
    from tests.conftest import make_settings, new_test_db_url
    url = new_test_db_url() + "?application_name=pooltest"  # distinct URL => its own tiny pool
    app = create_app(make_settings(tmp_path, database_url=url, database_url_direct=url, db_pool_max=2,
                                   db_pool_timeout=20.0))
    statuses = []

    def hit(i):
        statuses.append(TestClient(app).get("/api/auth/session").status_code)

    started = time.time()
    _, errors = run_parallel(hit, 40)
    assert not errors, errors
    assert statuses.count(200) == 40, statuses
    assert time.time() - started < 15


def test_faculty_cannot_move_onto_an_admin_reserved_address(app):
    from services import permission_service
    stu, fac, admin_id = _world(app)
    with dbmod.db_session(app.state.settings):
        for reserved in ("mkkarthik0609@gmail.com",):
            with pytest.raises(permission_service.PermissionError_):
                permission_service.faculty_request_profile_change(fac["user_id"], {"professional_email": reserved}, "x")
