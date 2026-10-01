"""/api/faculty/* - the signed-in faculty member's dashboard, profile, classes and student-request review
(role FACULTY only).

Class access is Admin-controlled: only ACTIVE assignments open a class; a class request grants nothing
until an Admin approves it.
"""
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import Field, field_validator

from api.deps import ApiModel, CurrentUser, Stripped, ok, require_role, service_errors
from api.errors import ApiError
from api.routers._people import Cards
from api.routers.meetings import meeting_item
from api.schemas import class_object, profile_picture_url
from models import academic_queries as aq
from models import connect_queries as cq
from models import queries
from services import assignment_service, file_service, permission_service

router = APIRouter(prefix="/api/faculty")
_FACULTY = require_role("FACULTY")


# ---------------------------------------------------------------- serializers

def _profile(faculty) -> dict:
    return {
        "id": faculty["id"],
        "user_id": faculty["user_id"],
        "faculty_code": faculty["faculty_code"],
        "full_name": faculty["full_name"],
        "email": faculty["email"],
        "professional_email": faculty["professional_email"],
        "department": faculty["department"],
        "theme": faculty["theme_preference"],
        "profile_picture_url": profile_picture_url(faculty["profile_picture_path"]),
    }


def _load_faculty(user: CurrentUser):
    faculty = queries.get_faculty_with_user(user["faculty_id"]) if user["faculty_id"] else None
    if faculty is None:
        raise ApiError(404, "not_found", "Faculty profile not found.")
    return faculty


def _class_item(row) -> dict:
    """Class object + assignment id / date + student_count (row of ``aq.list_assignments_for_faculty``)."""
    return dict(class_object(row), assignment_id=row["assignment_id"], assigned_at=row["assigned_at"],
                student_count=row["student_count"])


def _request_item(row) -> dict:
    """A class-assignment request of mine (row of ``aq.list_assignment_requests``)."""
    return {
        "id": row["id"], "section_id": row["section_id"], "status": row["status"], "note": row["note"],
        "created_at": row["created_at"], "reviewed_at": row["reviewed_at"], "class": class_object(row),
    }


def _changes(row) -> dict:
    try:
        value = json.loads(row["requested_changes"] or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _change_request_item(row) -> dict:
    """One of my own profile-change requests."""
    return {
        "id": row["id"], "request_type": row["request_type"], "status": row["status"],
        "requested_changes": _changes(row), "reason": row["reason"],
        "created_at": row["created_at"], "reviewed_at": row["reviewed_at"],
    }


def _permission_item(row, cards: Cards) -> dict:
    """A pending student profile-change request awaiting my review."""
    student = queries.get_student_by_user_id(row["requester_user_id"])
    requester = None
    if student is not None:
        card = cq.get_student_card(student["id"])
        requester = cards.student(id=card["id"], usn=card["usn"], full_name=card["full_name"],
                                  picture_path=card["profile_picture_path"], section_id=card["section_id"])
    return {
        "id": row["id"], "request_type": row["request_type"], "status": row["status"],
        "requested_changes": _changes(row), "reason": row["reason"], "created_at": row["created_at"],
        "requester_name": row["requester_name"], "student": requester,
    }


def _student_summary(row, cards: Cards) -> dict:
    return cards.student(id=row["id"], usn=row["usn"], full_name=row["full_name"],
                         picture_path=row["profile_picture_path"], section_id=row["section_id"])


# ---------------------------------------------------------------- request models

class ProfileChangeIn(ApiModel):
    department: Optional[Stripped] = Field(None, max_length=80)
    professional_email: Optional[Stripped] = Field(None, max_length=254)
    reason: Stripped = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value):
        if not value:
            raise ValueError("Please give a reason for the change.")
        return value


class ClassRequestIn(ApiModel):
    section_id: int
    note: Optional[Stripped] = Field(None, max_length=500)


class DecisionIn(ApiModel):
    decision: Literal["approve", "reject"]


# ---------------------------------------------------------------- dashboard / profile

@router.get("/dashboard")
def dashboard(user: CurrentUser = Depends(_FACULTY)):
    faculty = _load_faculty(user)
    fid = faculty["id"]
    cards = Cards()
    classes = [_class_item(r) for r in aq.list_assignments_for_faculty(fid)]
    class_requests = [_request_item(r) for r in aq.list_assignment_requests(status="PENDING", faculty_id=fid)]
    supporting_students = []
    for r in queries.list_accepted_supporting_students_for_faculty(fid):
        card = cq.get_student_card(r["id"])
        supporting_students.append(_student_summary(card, cards))
    pending_supporting = []
    for r in cq.list_relationships(faculty_id=fid, status="PENDING"):
        if r["requested_by"] == "STUDENT":
            pending_supporting.append({
                "id": r["id"], "created_at": r["created_at"],
                "student": cards.student(id=r["student_id"], usn=r["usn"], full_name=r["student_name"],
                                         picture_path=r["student_picture"], section_id=r["section_id"]),
            })
    recent_meetings = [meeting_item(r, user, cards) for r in cq.list_meetings(faculty_id=fid, limit=5)]
    permission_requests = [_permission_item(r, cards)
                           for r in queries.list_pending_permission_requests_for_approver(user["id"])]
    return {
        "profile": _profile(faculty),
        "subjects": [s["subject_name"] for s in queries.get_faculty_subjects(fid)],
        "classes": classes,
        "pending_class_requests": class_requests,
        "supporting_students": supporting_students,
        "pending_supporting_requests": pending_supporting,
        "recent_meetings": recent_meetings,
        "pending_permission_requests": permission_requests,
        "counts": {
            "classes": len(classes),
            "pending_class_requests": len(class_requests),
            "supporting_students": len(supporting_students),
            "pending_supporting_requests": len(pending_supporting),
            "pending_permission_requests": len(permission_requests),
            "meetings_pending": len(cq.list_meetings(faculty_id=fid, statuses=["PENDING"])),
        },
    }


@router.get("/profile")
def profile(user: CurrentUser = Depends(_FACULTY)):
    faculty = _load_faculty(user)
    mine = [r for r in queries.list_permission_requests_by_requester(user["id"])
            if r["request_type"] == permission_service.FACULTY_PROFILE_CHANGE]
    return {
        "profile": _profile(faculty),
        "subjects": [s["subject_name"] for s in queries.get_faculty_subjects(faculty["id"])],
        "classes": [_class_item(r) for r in aq.list_assignments_for_faculty(faculty["id"])],
        "change_requests": [_change_request_item(r) for r in mine],
        "departments": aq.list_active_department_names(),
    }


@router.post("/profile/picture")
def update_picture(profile_picture: UploadFile = File(...), user: CurrentUser = Depends(_FACULTY)):
    with service_errors():
        relative_path = file_service.save_profile_picture(profile_picture, "FACULTY")
    queries.update_user_profile_picture(user["id"], relative_path)
    return ok("Profile picture updated.", profile_picture_url=profile_picture_url(relative_path))


@router.post("/profile/change-request", status_code=201)
def request_profile_change(body: ProfileChangeIn, user: CurrentUser = Depends(_FACULTY)):
    changes = {k: v for k, v in (("department", body.department), ("professional_email", body.professional_email)) if v}
    with service_errors():
        request_id = permission_service.faculty_request_profile_change(user["id"], changes, body.reason)
    return ok("Profile change request submitted for admin approval.", id=request_id)


# ---------------------------------------------------------------- classes

@router.get("/classes")
def classes(user: CurrentUser = Depends(_FACULTY)):
    """My ACTIVE assignments and every class request I made (pending first)."""
    fid = user["faculty_id"]
    return {
        "assignments": [_class_item(r) for r in aq.list_assignments_for_faculty(fid)],
        "requests": [_request_item(r) for r in aq.list_assignment_requests(faculty_id=fid)],
    }


@router.post("/classes/request", status_code=201)
def request_class(body: ClassRequestIn, user: CurrentUser = Depends(_FACULTY)):
    with service_errors():
        request_id = assignment_service.faculty_request(user["faculty_id"], body.section_id, body.note)
    return ok("Request sent to Admin. You will get access once it is approved.", id=request_id)


@router.get("/classes/{section_id}")
def class_detail(section_id: int, user: CurrentUser = Depends(_FACULTY)):
    # Server-side gate: only ACTIVE assignments open a class, whatever id is in the URL (no 404 oracle).
    if not aq.is_faculty_assigned_to_section(user["faculty_id"], section_id):
        raise ApiError(403, "forbidden", "You are not assigned to this class.")
    combo = aq.get_combo(section_id)
    assignment = next((r for r in aq.list_assignments_for_faculty(user["faculty_id"])
                       if r["section_id"] == section_id), None)
    students = aq.list_students_for_section(section_id)
    class_obj = dict(class_object(combo), student_count=len(students),
                     assignment_id=assignment["assignment_id"] if assignment else None)
    return {
        "class": class_obj,
        "students": [{
            "id": s["id"], "usn": s["usn"], "full_name": s["full_name"], "phone": s["phone"],
            "college_email": s["college_email"], "profile_picture_url": profile_picture_url(s["profile_picture_path"]),
        } for s in students],
        "co_faculty": [{
            "id": f["faculty_id"], "faculty_code": f["faculty_code"], "full_name": f["full_name"],
            "profile_picture_url": profile_picture_url(f["profile_picture_path"]),
            "is_me": f["faculty_id"] == user["faculty_id"],
        } for f in aq.list_faculty_for_section(section_id)],
    }


# ---------------------------------------------------------------- student profile-change requests

@router.get("/permission-requests")
def permission_requests(user: CurrentUser = Depends(_FACULTY)):
    """Pending student profile-change requests from the classes I am ACTIVELY assigned to."""
    cards = Cards()
    rows = queries.list_pending_permission_requests_for_approver(user["id"])
    return {"items": [_permission_item(r, cards) for r in rows], "total": len(rows)}


@router.post("/permission-requests/{request_id}/decide")
def decide_permission_request(request_id: int, body: DecisionIn, user: CurrentUser = Depends(_FACULTY)):
    approve = body.decision == "approve"
    with service_errors():
        new_status = permission_service.decide_permission_request(request_id, user["id"], approve)
    return ok("Request approved." if approve else "Request rejected.", status=new_status)
