from models import queries
from models import academic_queries as aq
from services import notification_service as notif


class SupportingError(Exception):
    pass


def student_request_faculty(student_id, faculty_id):
    existing = queries.get_supporting_relationship(student_id, faculty_id)
    if existing and existing["status"] in ("PENDING", "ACCEPTED"):
        raise SupportingError("A supporting relationship request already exists with this faculty member.")
    rel_id = queries.create_supporting_request(student_id, faculty_id, "STUDENT")
    faculty = queries.get_faculty_by_id(faculty_id)
    student = queries.get_student_with_user(student_id)
    notif.notify(
        faculty["user_id"], notif.SUPPORTING_REQUESTED, "New supporting-faculty request",
        f"{student['full_name']} ({student['usn']}) requested you as a supporting faculty.",
        "supporting_relationship", rel_id,
    )
    return rel_id


def faculty_request_student(faculty_id, student_id):
    if not queries.get_student_by_id(student_id):
        raise SupportingError("Student not found.")
    if not aq.is_student_in_faculty_scope(faculty_id, student_id):
        raise SupportingError("You can only send requests to students in your assigned classes.")
    existing = queries.get_supporting_relationship(student_id, faculty_id)
    if existing and existing["status"] in ("PENDING", "ACCEPTED"):
        raise SupportingError("A supporting relationship request already exists with this student.")
    rel_id = queries.create_supporting_request(student_id, faculty_id, "FACULTY")
    student = queries.get_student_by_id(student_id)
    faculty = queries.get_faculty_with_user(faculty_id)
    notif.notify(
        student["user_id"], notif.SUPPORTING_REQUESTED, "New supporting-faculty request",
        f"{faculty['full_name']} ({faculty['faculty_code']}) requested to be your supporting faculty.",
        "supporting_relationship", rel_id,
    )
    return rel_id


def respond_to_request(rel_id, responder_user_id, responder_role, accept: bool):
    rel = queries.get_supporting_relationship_by_id(rel_id)
    if not rel:
        raise SupportingError("Request not found.")
    if rel["status"] != "PENDING":
        raise SupportingError("This request has already been responded to.")

    if responder_role == "STUDENT":
        student = queries.get_student_by_user_id(responder_user_id)
        if not student or student["id"] != rel["student_id"] or rel["requested_by"] != "FACULTY":
            raise SupportingError("You are not authorized to respond to this request.")
        notify_user_id = queries.get_faculty_by_id(rel["faculty_id"])["user_id"]
    else:
        faculty = queries.get_faculty_by_user_id(responder_user_id)
        if not faculty or faculty["id"] != rel["faculty_id"] or rel["requested_by"] != "STUDENT":
            raise SupportingError("You are not authorized to respond to this request.")
        notify_user_id = queries.get_student_by_id(rel["student_id"])["user_id"]

    new_status = "ACCEPTED" if accept else "REJECTED"
    queries.respond_supporting_relationship(rel_id, new_status)
    notif.notify(
        notify_user_id, notif.SUPPORTING_RESPONDED, "Supporting-faculty request update",
        f"Your supporting-faculty request was {new_status.lower()}.", "supporting_relationship", rel_id,
    )
    return new_status
