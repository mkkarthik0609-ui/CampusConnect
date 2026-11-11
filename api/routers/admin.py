"""/api/admin/* - the admin console: dashboard, people, meetings, approvals, admin accounts.

Every route here is ADMIN-only: the dependency is attached to the router itself, so a route added
later cannot forget it. Academic structure, assignments, requests and the class directory live in
``api/routers/admin_academic.py`` (same prefix)."""
import json
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from api.deps import ApiModel, CurrentUser, Stripped, items, ok, require_role, service_errors
from api.errors import ApiError
from api.settings import get_settings
from api.schemas import class_object, profile_picture_url
from models import academic_queries as aq
from models import admin_queries
from models import queries
from services import audit_service, auth_service, invitation_service, permission_service

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("ADMIN"))], tags=["admin"])

MEETING_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "COMPLETED", "CANCELLED")
_REMOVED_EMAIL_RE = re.compile(r"^removed-\d+\+")


# ---------------------------------------------------------------- shared serializers
# (also imported by api/routers/admin_academic.py)

def combos_by_section():
    """{section_id: combo row} for every class (72 rows in the default seed) - one query per request."""
    return {c["section_id"]: c for c in aq.list_combos()}


def class_for(combos, section_id):
    return class_object(combos.get(section_id)) if section_id else None


def _display_usn(usn):
    return (usn or "").split(aq.REMOVED_MARK, 1)[0]


def _display_email(email):
    return _REMOVED_EMAIL_RE.sub("", email or "")


def student_item(row, combos):
    """One student registration. A removed registration shows its original USN / e-mail (the stored
    values carry a tombstone so the person can register again) and ``is_removed: true``."""
    removed = aq.is_removed_usn(row["usn"])
    section_id = row["section_id"]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "usn": _display_usn(row["usn"]),
        "email": _display_email(row["college_email"]),
        "personal_email": row["personal_email"],
        "phone": row["phone"],
        "profile_picture_url": profile_picture_url(row["profile_picture_path"]),
        "class": class_for(combos, section_id),
        # free text typed before the academic hierarchy existed; only meaningful while unmapped
        "legacy_class": None if section_id else {
            "branch": row["branch"], "department": row["department"], "year": row["year"],
            "section": row["section"],
        },
        "is_active": bool(row["is_active"]),
        "is_removed": removed,
        "is_unmapped": section_id is None and not removed,
        "can_remove_registration": not removed,
        "registered_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def faculty_mini(faculty_id, code, name, picture, department=None):
    return {
        "id": faculty_id, "faculty_code": code, "full_name": name, "department": department,
        "profile_picture_url": profile_picture_url(picture),
    }


def assignment_item(row):
    """An assignment of a faculty member (row of academic_queries.list_assignments_for_faculty)."""
    item = class_object(row)
    item.update({
        "assignment_id": row["assignment_id"],
        "is_active": bool(row["assignment_active"]),
        "class_active": bool(row["chain_active"]),
        "student_count": row["student_count"],
        "assigned_at": row["assigned_at"],
        "can_remove": bool(row["assignment_active"]),
    })
    return item


def assignment_request_item(row):
    item = {
        "id": row["id"],
        "status": row["status"],
        "note": row["note"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "reviewed_by": row["reviewed_by"],
        "faculty": {
            "id": row["faculty_id"], "faculty_code": row["faculty_code"], "full_name": row["faculty_name"],
            "department": row["faculty_department"],
            "profile_picture_url": profile_picture_url(row["faculty_picture"]),
        },
        "class": class_object(row),
        "class_active": bool(row["chain_active"]),
        "can_decide": row["status"] == "PENDING",
    }
    return item


# ---------------------------------------------------------------- request models

class DecisionIn(ApiModel):
    decision: Literal["approve", "reject"]


class AdminInviteIn(ApiModel):
    email: Stripped = Field(min_length=1, max_length=254)
    full_name: Optional[Stripped] = Field(default=None, max_length=120)


class ActiveIn(ApiModel):
    active: bool


# ---------------------------------------------------------------- dashboard

@router.get("/dashboard")
def dashboard():
    stats = admin_queries.dashboard_counts()
    stats["class_count"] = len(aq.list_combos(active_only=True))
    stats["pending_assignment_count"] = aq.count_pending_assignment_requests()
    return {"stats": stats}


# ---------------------------------------------------------------- students

@router.get("/students")
def list_students(section_id: Optional[int] = Query(None, ge=1)):
    combos = combos_by_section()
    rows = [student_item(r, combos) for r in admin_queries.list_students(section_id)]
    return items(rows, total=len(rows))


@router.post("/students/{student_id}/remove-registration")
def remove_student_registration(student_id: int):
    """Idempotent: the first call tombstones the registration, every later call is a 409 no-op."""
    row = admin_queries.get_student(student_id)
    if row is None:
        raise ApiError(404, "not_found", "Student not found.")
    if aq.is_removed_usn(row["usn"]) or not aq.archive_student_registration(student_id):
        raise ApiError(409, "already_removed", "This registration was already removed.")
    message = (f"Registration for {row['full_name']} ({_display_usn(row['usn'])}) removed. "
               "They can now register again with the correct class.")
    return ok(message, student=student_item(admin_queries.get_student(student_id), combos_by_section()))


# ---------------------------------------------------------------- faculty

@router.get("/faculty")
def list_faculty():
    out = []
    for row in admin_queries.list_faculty():
        assignments = [assignment_item(a) for a in aq.list_assignments_for_faculty(row["id"], active_only=False)
                       if a["assignment_active"]]
        out.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "faculty_code": row["faculty_code"],
            "full_name": row["full_name"],
            "email": row["email"],
            "professional_email": row["professional_email"],
            "department": row["department"],
            "profile_picture_url": profile_picture_url(row["profile_picture_path"]),
            "is_active": bool(row["is_active"]),
            "subjects": [s["subject_name"] for s in queries.get_faculty_subjects(row["id"])],
            "assignments": assignments,
            "pending_request_count": len(aq.list_assignment_requests(status="PENDING", faculty_id=row["id"])),
            "registered_at": row["created_at"],
            "last_login_at": row["last_login_at"],
        })
    return items(out, total=len(out))


# ---------------------------------------------------------------- meetings

@router.get("/meetings")
def list_meetings(status: Optional[str] = Query(None, max_length=20)):
    wanted = status.strip().upper() if status else None
    if wanted and wanted not in MEETING_STATUSES:
        raise ApiError(400, "validation_error", "Unknown meeting status.",
                       {"status": "Use one of: " + ", ".join(MEETING_STATUSES) + "."})
    combos = combos_by_section()
    out = []
    for m in admin_queries.list_meetings(wanted):
        out.append({
            "id": m["id"],
            "status": m["status"],
            "reason": m["reason"],
            "student_message": m["student_message"],
            "faculty_response": m["faculty_response"],
            "meeting_time_text": m["meeting_time_text"],
            "requested_at": m["requested_at"],
            "responded_at": m["responded_at"],
            "completed_at": m["completed_at"],
            "completed_by": m["completed_by"],
            "cancelled_at": m["cancelled_at"],
            "cancelled_by": m["cancelled_by"],
            "cancellation_reason": m["cancellation_reason"],
            "student": {
                "id": m["student_id"], "full_name": m["student_name"], "usn": _display_usn(m["usn"]),
                "profile_picture_url": profile_picture_url(m["student_picture"]),
                "class": class_for(combos, m["student_section_id"]),
            },
            "faculty": faculty_mini(m["faculty_id"], m["faculty_code"], m["faculty_name"], m["faculty_picture"],
                                    m["faculty_department"]),
        })
    return items(out, total=len(out))


# ---------------------------------------------------------------- permission (profile change) requests

def _changes(raw):
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def permission_request_item(r):
    # An admin can only review faculty profile changes; student requests are routed to the class faculty.
    can_decide = (r["status"] == "PENDING"
                  and r["request_type"] == permission_service.FACULTY_PROFILE_CHANGE)
    return {
        "id": r["id"],
        "request_type": r["request_type"],
        "status": r["status"],
        "requester": {
            "user_id": r["requester_user_id"], "full_name": r["requester_name"], "role": r["requester_role"],
            "usn": _display_usn(r["requester_usn"]) if r["requester_usn"] else None,
            "faculty_code": r["requester_faculty_code"],
            "profile_picture_url": profile_picture_url(r["requester_picture"]),
        },
        "approver": {"user_id": r["target_approver_user_id"], "full_name": r["approver_name"]},
        "requested_changes": _changes(r["requested_changes"]),
        "reason": r["reason"],
        "created_at": r["created_at"],
        "reviewed_at": r["reviewed_at"],
        "can_decide": can_decide,
    }


@router.get("/permission-requests")
def list_permission_requests():
    out = [permission_request_item(r) for r in admin_queries.list_permission_requests()]
    return items(out, total=len(out), pending=sum(1 for r in out if r["status"] == "PENDING"))


@router.post("/permission-requests/{request_id}/decide")
def decide_permission_request(request_id: int, body: DecisionIn, user: CurrentUser = Depends(require_role("ADMIN"))):
    approve = body.decision == "approve"
    with service_errors():
        status = permission_service.decide_permission_request(request_id, user["id"], approve)
    return ok(f"Request {status.lower()}.", status=status)


# ---------------------------------------------------------------- admin accounts

def admin_item(row, current_user_id):
    return {
        "id": row["id"], "full_name": row["full_name"], "email": row["email"],
        "profile_picture_url": profile_picture_url(row["profile_picture_path"]),
        "is_active": bool(row["is_active"]), "is_you": row["id"] == current_user_id,
        "is_primary": get_settings().is_primary_admin(row["email"]),
        "created_at": row["created_at"], "last_login_at": row["last_login_at"],
    }


def primary_admin(user: CurrentUser = Depends(require_role("ADMIN"))) -> CurrentUser:
    """Appointing, deactivating and resetting admins is reserved for the primary administrator."""
    if not get_settings().is_primary_admin(user["email"]):
        raise ApiError(403, "forbidden", "Only the primary administrator can manage admin accounts.")
    return user


@router.get("/admins")
def list_admins(user: CurrentUser = Depends(require_role("ADMIN"))):
    out = [admin_item(r, user["id"]) for r in admin_queries.list_admins()]
    return items(out, total=len(out))


def _invite_response(message, invitation):
    """Nothing is e-mailed: the primary admin tells the person to sign in at Admin Login with their e-mail + the admin ID."""
    return ok(f"{message} Tell them to sign in at Admin Login with this e-mail and the admin ID.", invitation=invitation)


@router.get("/admin-invitations")
def list_admin_invitations(user: CurrentUser = Depends(primary_admin)):
    out = invitation_service.list_invitations()
    return items(out, total=len(out))


@router.post("/admin-invitations", status_code=201)
def invite_admin(body: AdminInviteIn, request: Request, user: CurrentUser = Depends(primary_admin)):
    """Primary admin only: register a future administrator by e-mail address."""
    with service_errors():
        invitation = invitation_service.create_invitation(user, body.email, body.full_name)
    return _invite_response("Admin added.", invitation)


@router.post("/admin-invitations/{invitation_id}/resend")
def resend_admin_invitation(invitation_id: int, user: CurrentUser = Depends(primary_admin)):
    with service_errors():
        invitation = invitation_service.resend_invitation(user, invitation_id)
    return _invite_response("Registration renewed.", invitation)


@router.delete("/admin-invitations/{invitation_id}")
def revoke_admin_invitation(invitation_id: int, user: CurrentUser = Depends(primary_admin)):
    with service_errors():
        invitation_service.revoke_invitation(user, invitation_id)
    return ok("Invitation revoked.")


@router.post("/admins/{admin_id}/active")
def set_admin_active(admin_id: int, body: ActiveIn, user: CurrentUser = Depends(primary_admin)):
    with service_errors():
        auth_service.set_admin_active(user["id"], admin_id, body.active)
    audit_service.record(user, "admin.activate" if body.active else "admin.deactivate", admin_id)
    return ok("Admin reactivated." if body.active else "Admin deactivated.",
              admin=admin_item(admin_queries.get_admin(admin_id), user["id"]))


