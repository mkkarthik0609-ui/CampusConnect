"""Faculty <-> academic combination assignments. Admin is the only authority that can
activate an assignment; a faculty request grants nothing until Admin approves it."""
from models import queries
from models import academic_queries as aq
from services import notification_service as notif
from services.academic_service import AcademicError, resolve_section, combo_label


class AssignmentError(Exception):
    pass


def _admins():
    return queries.list_all_admins()


def admin_assign(faculty_id, section_id, admin_user_id):
    faculty = queries.get_faculty_with_user(faculty_id)
    if not faculty:
        raise AssignmentError("Faculty member not found.")
    try:
        combo = resolve_section(section_id)
    except AcademicError as e:
        raise AssignmentError(str(e))
    if aq.is_faculty_assigned_to_section(faculty_id, combo["section_id"]):
        raise AssignmentError(f"{faculty['faculty_code']} is already assigned to {combo_label(combo)}.")
    aq.upsert_assignment(faculty_id, combo["section_id"], admin_user_id)
    # An open request for the same combination is now satisfied.
    for r in aq.list_assignment_requests(status="PENDING", faculty_id=faculty_id):
        if r["section_id"] == combo["section_id"]:
            aq.decide_assignment_request(r["id"], "APPROVED", admin_user_id)
    notif.notify(
        faculty["user_id"], notif.ASSIGNMENT_CHANGED, "New class assignment",
        f"Admin assigned you to {combo_label(combo)}.", "faculty_assignment", combo["section_id"],
    )
    return combo


def admin_remove(assignment_id, admin_user_id):
    assignment = aq.get_assignment(assignment_id)
    if not assignment or not assignment["is_active"]:
        raise AssignmentError("Assignment not found or already inactive.")
    combo = aq.get_combo(assignment["section_id"])
    aq.deactivate_assignment(assignment_id)
    faculty = queries.get_faculty_by_id(assignment["faculty_id"])
    notif.notify(
        faculty["user_id"], notif.ASSIGNMENT_CHANGED, "Class assignment removed",
        f"Admin removed your assignment to {combo_label(combo)}.", "faculty_assignment", assignment["section_id"],
    )
    return combo


def faculty_request(faculty_id, section_id, note=None):
    try:
        combo = resolve_section(section_id)
    except AcademicError as e:
        raise AssignmentError(str(e))
    if aq.is_faculty_assigned_to_section(faculty_id, combo["section_id"]):
        raise AssignmentError("You are already assigned to this class.")
    if aq.has_pending_request(faculty_id, combo["section_id"]):
        raise AssignmentError("You already have a pending request for this class.")
    note = (note or "").strip()[:500] or None
    request_id = aq.create_assignment_request(faculty_id, combo["section_id"], note)
    faculty = queries.get_faculty_with_user(faculty_id)
    for admin in _admins():
        notif.notify(
            admin["id"], notif.ASSIGNMENT_REQUESTED, "Faculty class-assignment request",
            f"{faculty['full_name']} ({faculty['faculty_code']}) requested {combo_label(combo)}.",
            "faculty_assignment_request", request_id,
        )
    return request_id


def decide_request(request_id, admin_user_id, approve):
    req = aq.get_assignment_request(request_id)
    if not req:
        raise AssignmentError("Request not found.")
    if req["status"] != "PENDING":
        raise AssignmentError("This request has already been reviewed.")
    combo = aq.get_combo(req["section_id"])
    if approve and not combo["chain_active"]:
        raise AssignmentError("That class is no longer active; reactivate it before approving.")
    status = "APPROVED" if approve else "REJECTED"
    aq.decide_assignment_request(request_id, status, admin_user_id)
    if approve:
        aq.upsert_assignment(req["faculty_id"], req["section_id"], admin_user_id)
    faculty = queries.get_faculty_by_id(req["faculty_id"])
    notif.notify(
        faculty["user_id"], notif.ASSIGNMENT_RESPONDED, f"Class request {status.lower()}",
        f"Your request to join {combo_label(combo)} was {status.lower()}.",
        "faculty_assignment_request", request_id,
    )
    return status


# ---------- access rules used by chat / meetings / supporting / search ----------

def faculty_can_access_student(faculty_id, student_id):
    """Faculty reach a student through an active class assignment, or an accepted
    supporting relationship the student agreed to."""
    if aq.is_student_in_faculty_scope(faculty_id, student_id):
        return True
    rel = queries.get_supporting_relationship(student_id, faculty_id)
    return bool(rel and rel["status"] == "ACCEPTED")


def student_can_access_faculty(student_id, faculty_id):
    return faculty_can_access_student(faculty_id, student_id)
