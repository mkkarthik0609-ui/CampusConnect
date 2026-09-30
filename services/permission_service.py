import json
from models import queries
from models import academic_queries as aq
from services import notification_service as notif


class PermissionError_(Exception):
    pass


STUDENT_PROFILE_CHANGE = "STUDENT_PROFILE_CHANGE"
FACULTY_PROFILE_CHANGE = "FACULTY_PROFILE_CHANGE"

# Fields a student may request to change; enforced server-side, never trust client field list.
# Branch/Department/Year/Section are deliberately NOT here: only Admin can change a student's class
# (by removing the registration so the student can register again with the right combination).
STUDENT_EDITABLE_FIELDS = {"phone", "personal_email"}
FACULTY_EDITABLE_FIELDS = {"department", "professional_email"}


def student_request_profile_change(student_user_id, changes: dict, reason=None):
    changes = {k: v for k, v in changes.items() if k in STUDENT_EDITABLE_FIELDS and v}
    if not changes:
        raise PermissionError_("No valid profile fields were submitted for change.")
    student = queries.get_student_by_user_id(student_user_id)
    assigned = aq.list_assigned_faculty_for_student(student["id"]) if student else []
    if not assigned:
        raise PermissionError_("No faculty is assigned to your class yet, so the request cannot be routed.")
    # Routed to every faculty assigned to the student's class; any one of them may decide.
    primary = next((f for f in assigned if f["id"] == student["class_faculty_id"]), assigned[0])
    primary_user_id = queries.get_faculty_by_id(primary["id"])["user_id"]
    req_id = queries.create_permission_request(
        student_user_id, primary_user_id, STUDENT_PROFILE_CHANGE, json.dumps(changes), reason
    )
    for f in assigned:
        notif.notify(
            queries.get_faculty_by_id(f["id"])["user_id"], notif.PERMISSION_REQUESTED,
            "Student profile change request",
            "A student in your class has requested a profile detail change requiring your approval.",
            "permission_request", req_id,
        )
    return req_id


def faculty_request_profile_change(faculty_user_id, changes: dict, reason=None):
    changes = {k: v for k, v in changes.items() if k in FACULTY_EDITABLE_FIELDS and v}
    if not changes:
        raise PermissionError_("No valid profile fields were submitted for change.")
    if "department" in changes and changes["department"].lower() not in {
        d.lower() for d in aq.list_active_department_names()
    }:
        raise PermissionError_("Please choose a department from the list.")
    admins = queries.list_all_admins()
    if not admins:
        raise PermissionError_("No admin account exists to review this request.")
    approver_user_id = admins[0]["id"]
    req_id = queries.create_permission_request(
        faculty_user_id, approver_user_id, FACULTY_PROFILE_CHANGE, json.dumps(changes), reason
    )
    for admin in admins:
        notif.notify(
            admin["id"], notif.PERMISSION_REQUESTED, "Faculty profile change request",
            "A faculty member has requested a profile detail change requiring admin approval.",
            "permission_request", req_id,
        )
    return req_id


def decide_permission_request(request_id, approver_user_id, approve: bool):
    request_row = queries.get_permission_request_by_id(request_id)
    if not request_row:
        raise PermissionError_("Permission request not found.")
    if request_row["status"] != "PENDING":
        raise PermissionError_("This request has already been reviewed.")
    if request_row["request_type"] == STUDENT_PROFILE_CHANGE:
        faculty = queries.get_faculty_by_user_id(approver_user_id)
        student = queries.get_student_by_user_id(request_row["requester_user_id"])
        if not faculty or not student or not aq.is_student_in_faculty_scope(faculty["id"], student["id"]):
            raise PermissionError_("You are not authorized to review this request.")
    elif request_row["request_type"] == FACULTY_PROFILE_CHANGE:
        approver = queries.get_user_by_id(approver_user_id)
        if not approver or approver["role"] != "ADMIN":
            raise PermissionError_("Only an admin may review faculty change requests.")

    new_status = "APPROVED" if approve else "REJECTED"
    queries.decide_permission_request(request_id, new_status)

    if approve:
        changes = json.loads(request_row["requested_changes"])
        # Defence in depth: column names are interpolated by update_*_fields, so only ever apply
        # allow-listed fields even if the stored JSON was tampered with.
        allowed = STUDENT_EDITABLE_FIELDS if request_row["request_type"] == STUDENT_PROFILE_CHANGE else FACULTY_EDITABLE_FIELDS
        changes = {k: v for k, v in changes.items() if k in allowed}
        if request_row["request_type"] == STUDENT_PROFILE_CHANGE:
            student = queries.get_student_by_user_id(request_row["requester_user_id"])
            queries.update_student_fields(student["id"], changes)
        else:
            faculty = queries.get_faculty_by_user_id(request_row["requester_user_id"])
            queries.update_faculty_fields(faculty["id"], changes)

    notif.notify(
        request_row["requester_user_id"], notif.PERMISSION_RESPONDED,
        f"Profile change request {new_status.lower()}",
        f"Your profile change request was {new_status.lower()}.",
        "permission_request", request_id,
    )
    return new_status
