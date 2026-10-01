"""/api/meetings/* - meeting requests between a student and a faculty member (STUDENT or FACULTY).

Authorization is enforced server-side on every call: a student only sees / acts on their own meetings, a
faculty member only on meetings addressed to them; requesting and responding additionally require that the
student is currently reachable (active class assignment or accepted supporting relationship).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator

from api.deps import ApiModel, CurrentUser, Stripped, items, ok, require_role, service_errors
from api.errors import ApiError
from api.routers._people import Cards
from models import connect_queries as cq
from models import queries
from services import meeting_service

router = APIRouter(prefix="/api/meetings")

STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "COMPLETED", "CANCELLED")
_OPEN = ("PENDING", "ACCEPTED")


# ---------------------------------------------------------------- serializers

def meeting_item(row, user, cards: Optional[Cards] = None) -> dict:
    """One meeting as the SPA needs it. ``row`` comes from ``connect_queries.list_meetings/get_meeting_full``."""
    cards = cards or Cards()
    is_student = user["role"] == "STUDENT"
    status = row["status"]
    student = cards.student(id=row["student_id"], usn=row["usn"], full_name=row["student_name"],
                            picture_path=row["student_picture"], section_id=row["student_section_id"])
    faculty = cards.faculty(id=row["faculty_id"], faculty_code=row["faculty_code"],
                            department=row["faculty_department"], full_name=row["faculty_name"],
                            picture_path=row["faculty_picture"])
    can_respond = False
    if not is_student and status == "PENDING" and row["faculty_id"] == user["faculty_id"]:
        can_respond = queries.is_student_accessible_to_faculty(row["faculty_id"], row["student_id"])
    return {
        "id": row["id"],
        "status": status,
        "reason": row["reason"],
        "student_message": row["student_message"],
        "faculty_response": row["faculty_response"],
        "meeting_time_text": row["meeting_time_text"],
        "requested_at": row["requested_at"],
        "responded_at": row["responded_at"],
        "completed_at": row["completed_at"],
        "completed_by": row["completed_by"],
        "cancelled_at": row["cancelled_at"],
        "cancelled_by": row["cancelled_by"],
        "cancellation_reason": row["cancellation_reason"],
        "student": student,
        "faculty": faculty,
        # the other party, from the viewer's point of view
        "counterpart": dict(faculty, role="FACULTY") if is_student else dict(student, role="STUDENT"),
        "counterpart_name": faculty["full_name"] if is_student else student["full_name"],
        "counterpart_code": faculty["faculty_code"] if is_student else student["usn"],
        "can_respond": can_respond,
        "can_cancel": status in _OPEN,
        "can_complete": status == "ACCEPTED",
    }


def _load_for(user: CurrentUser, meeting_id: int):
    """The meeting row if the viewer is one of its two parties (404 unknown, 403 somebody else's)."""
    row = cq.get_meeting_full(meeting_id)
    if row is None:
        raise ApiError(404, "not_found", "Meeting request not found.")
    own = row["student_id"] == user["student_id"] if user["role"] == "STUDENT" else row["faculty_id"] == user["faculty_id"]
    if not own:
        raise ApiError(403, "forbidden", "You do not have access to this meeting.")
    return row


def _statuses(raw: Optional[str]):
    if not raw:
        return None
    wanted = [part.strip().upper() for part in raw.split(",") if part.strip()]
    bad = [s for s in wanted if s not in STATUSES]
    if bad:
        raise ApiError(400, "validation_error", "Unknown status filter.",
                       {"status": "Use one of: " + ", ".join(STATUSES) + "."})
    return wanted or None


# ---------------------------------------------------------------- request models

class RequestMeetingIn(ApiModel):
    faculty_id: int
    reason: Stripped = Field(max_length=200)
    details: Optional[Stripped] = Field(None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value):
        if not value:
            raise ValueError("Please provide a reason/topic for the meeting.")
        return value


class RespondIn(ApiModel):
    decision: Literal["accept", "reject"]
    faculty_response: Optional[Stripped] = Field(None, max_length=1000)
    meeting_time_text: Optional[Stripped] = Field(None, max_length=200)


class CancelIn(ApiModel):
    reason: Optional[Stripped] = Field(None, max_length=1000)


# ---------------------------------------------------------------- endpoints

@router.get("")
def list_meetings(status: Optional[str] = Query(None, description="One status or a comma separated list"),
                  user: CurrentUser = Depends(require_role("STUDENT", "FACULTY"))):
    statuses = _statuses(status)
    if user["role"] == "STUDENT":
        rows = cq.list_meetings(student_id=user["student_id"], statuses=statuses)
    else:
        rows = cq.list_meetings(faculty_id=user["faculty_id"], statuses=statuses)
    cards = Cards()
    return items([meeting_item(r, user, cards) for r in rows], total=len(rows))


@router.post("", status_code=201)
def request_meeting(body: RequestMeetingIn, user: CurrentUser = Depends(require_role("STUDENT"))):
    with service_errors():
        meeting_id = meeting_service.request_meeting(user["student_id"], body.faculty_id, body.reason, body.details)
    return ok("Meeting request sent.", id=meeting_id,
              meeting=meeting_item(cq.get_meeting_full(meeting_id), user))


@router.get("/{meeting_id}")
def get_meeting(meeting_id: int, user: CurrentUser = Depends(require_role("STUDENT", "FACULTY"))):
    return {"meeting": meeting_item(_load_for(user, meeting_id), user)}


@router.post("/{meeting_id}/respond")
def respond(meeting_id: int, body: RespondIn, user: CurrentUser = Depends(require_role("FACULTY"))):
    _load_for(user, meeting_id)  # 404 unknown / 403 not addressed to this faculty member
    accept = body.decision == "accept"
    if accept and not body.meeting_time_text:
        message = "Please provide the meeting timing when accepting a request."
        raise ApiError(400, "validation_error", message, {"meeting_time_text": message})
    with service_errors():
        new_status = meeting_service.respond_to_meeting(
            meeting_id, user["faculty_id"], accept, body.faculty_response, body.meeting_time_text)
    return ok("Meeting request accepted." if accept else "Meeting request rejected.", status=new_status,
              meeting=meeting_item(cq.get_meeting_full(meeting_id), user))


@router.post("/{meeting_id}/cancel")
def cancel(meeting_id: int, body: Optional[CancelIn] = None,
           user: CurrentUser = Depends(require_role("STUDENT", "FACULTY"))):
    _load_for(user, meeting_id)  # 404 unknown / 403 not one of the two parties
    reason = body.reason if body else None
    if user["role"] == "STUDENT" and not reason:
        message = "Please provide a reason for cancelling this meeting."
        raise ApiError(400, "validation_error", message, {"reason": message})
    with service_errors():
        meeting_service.cancel_meeting(meeting_id, user["id"], user["role"], reason)
    return ok("Meeting cancelled.", status="CANCELLED", meeting=meeting_item(cq.get_meeting_full(meeting_id), user))


@router.post("/{meeting_id}/complete")
def complete(meeting_id: int, user: CurrentUser = Depends(require_role("STUDENT", "FACULTY"))):
    with service_errors():
        meeting_service.complete_meeting(meeting_id, user["id"], user["role"])
    return ok("Meeting marked completed.", status="COMPLETED",
              meeting=meeting_item(cq.get_meeting_full(meeting_id), user))
