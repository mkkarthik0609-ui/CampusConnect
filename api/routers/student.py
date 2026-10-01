"""/api/student/* - the signed-in student's dashboard and own profile (role STUDENT only)."""
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, UploadFile

from api.deps import ApiModel, CurrentUser, Stripped, ok, require_role, service_errors
from api.errors import ApiError
from api.routers._people import Cards
from api.routers.meetings import meeting_item
from api.routers.supporting import relationship_item
from api.schemas import class_object_for_section, faculty_brief, profile_picture_url
from models import academic_queries as aq
from models import connect_queries as cq
from models import queries
from services import auth_service, file_service, permission_service

router = APIRouter(prefix="/api/student")

# Class membership is Admin-controlled: a student can never edit these (no endpoint exists for it).
_ADMIN_ONLY_FIELDS = ("branch", "department", "year", "section", "section_id", "usn", "college_email")
_ADMIN_ONLY_MESSAGE = (
    "Branch, department, year, section, USN and college email can only be changed by an administrator."
)


# ---------------------------------------------------------------- serializers

def _student_payload(student) -> dict:
    class_obj = class_object_for_section(student["section_id"])
    return {
        "id": student["id"],
        "user_id": student["user_id"],
        "usn": student["usn"],
        "full_name": student["full_name"],
        "email": student["email"],
        "college_email": student["college_email"],
        "personal_email": student["personal_email"],
        "phone": student["phone"],
        "branch": student["branch"],
        "department": student["department"],
        "year": student["year"],
        "section": student["section"],
        "class": class_obj,
        "theme": student["theme_preference"],
        "profile_picture_url": profile_picture_url(student["profile_picture_path"]),
    }


def _faculty_cards(rows) -> list:
    return [faculty_brief(r) for r in rows]


def _request_item(row) -> dict:
    try:
        changes = json.loads(row["requested_changes"] or "{}")
    except ValueError:
        changes = {}
    return {
        "id": row["id"],
        "request_type": row["request_type"],
        "requested_changes": changes,
        "reason": row["reason"],
        "status": row["status"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
    }


def _load_student(user: CurrentUser):
    student = queries.get_student_with_user(user["student_id"]) if user["student_id"] else None
    if student is None:
        raise ApiError(404, "not_found", "Student profile not found.")
    return student


# ---------------------------------------------------------------- request models

class ChangeRequestIn(ApiModel):
    phone: Optional[Stripped] = None
    personal_email: Optional[Stripped] = None
    reason: Stripped
    # Declared only so that an attempt to change the class gets a clear message instead of a generic one.
    branch: Optional[Any] = None
    department: Optional[Any] = None
    year: Optional[Any] = None
    section: Optional[Any] = None
    section_id: Optional[Any] = None
    usn: Optional[Any] = None
    college_email: Optional[Any] = None


# ---------------------------------------------------------------- endpoints

@router.get("/dashboard")
def dashboard(user: CurrentUser = Depends(require_role("STUDENT"))):
    student = _load_student(user)
    sid = student["id"]
    assigned = _faculty_cards(aq.list_assigned_faculty_for_student(sid))
    supporting = _faculty_cards(queries.list_accepted_supporting_faculty_for_student(sid))
    cards = Cards()
    pending = [relationship_item(r, user, cards)
               for r in cq.list_relationships(student_id=sid, status="PENDING") if r["requested_by"] == "FACULTY"]
    recent = [meeting_item(r, user, cards) for r in cq.list_meetings(student_id=sid, limit=5)]
    by_status = {}
    for row in cq.list_meetings(student_id=sid):
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {
        "student": _student_payload(student),
        "assigned_faculty": assigned,
        "supporting_faculty": supporting,
        "pending_supporting_requests": pending,
        "recent_meetings": recent,
        "counts": {
            "assigned_faculty": len(assigned),
            "supporting_faculty": len(supporting),
            "pending_supporting_requests": len(pending),
            "meetings_total": sum(by_status.values()),
            "meetings_pending": by_status.get("PENDING", 0),
            "meetings_accepted": by_status.get("ACCEPTED", 0),
        },
    }


@router.get("/profile")
def profile(user: CurrentUser = Depends(require_role("STUDENT"))):
    student = _load_student(user)
    return {
        "student": _student_payload(student),
        "assigned_faculty": _faculty_cards(aq.list_assigned_faculty_for_student(student["id"])),
        "permission_requests": [
            _request_item(r) for r in sorted(queries.list_permission_requests_by_requester(user["id"]),
                                             key=lambda r: (r["created_at"], r["id"]), reverse=True)
        ],
    }


@router.post("/profile/picture")
def update_picture(profile_picture: UploadFile = File(...),
                   user: CurrentUser = Depends(require_role("STUDENT"))):
    with service_errors():
        relative_path = file_service.save_profile_picture(profile_picture, "STUDENT")
    queries.update_user_profile_picture(user["id"], relative_path)
    return ok("Profile picture updated.", profile_picture_url=profile_picture_url(relative_path))


@router.post("/profile/change-request", status_code=201)
def request_profile_change(body: ChangeRequestIn, user: CurrentUser = Depends(require_role("STUDENT"))):
    blocked = {name: _ADMIN_ONLY_MESSAGE for name in _ADMIN_ONLY_FIELDS if name in body.model_fields_set}
    if blocked:
        raise ApiError(400, "validation_error", _ADMIN_ONLY_MESSAGE, blocked)
    if not body.reason:
        raise ApiError(400, "validation_error", "Please give a reason for the change.",
                       {"reason": "Please give a reason for the change."})
    changes = {}
    with service_errors():
        if body.phone:
            changes["phone"] = auth_service.validate_phone(body.phone)
        if body.personal_email:
            changes["personal_email"] = auth_service.validate_email(
                body.personal_email.lower(), "Personal email", "personal_email")
        request_id = permission_service.student_request_profile_change(user["id"], changes, body.reason)
    return ok("Profile change request submitted for faculty approval.", id=request_id)
