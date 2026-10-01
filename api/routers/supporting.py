"""/api/supporting/* - supporting-faculty relationships and the searches that feed them.

A supporting relationship is the way a student and a faculty member who are NOT linked through an
Admin class assignment can still talk / meet: one side requests, the OTHER side accepts. Faculty can only
search (and invite) students of the classes they are actively assigned to.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from api.deps import CurrentUser, items, ok, require_role, service_errors
from api.routers._people import Cards
from models import academic_queries as aq
from models import connect_queries as cq
from services import supporting_service

router = APIRouter(prefix="/api/supporting")
_PARTICIPANT = require_role("STUDENT", "FACULTY")


def _relationship_brief(rel_id, status, requested_by):
    if rel_id is None:
        return None
    return {"id": rel_id, "status": status, "requested_by": requested_by}


def _can_request(rel_status) -> bool:
    return rel_status is None or rel_status == "REJECTED"


def relationship_item(row, user: CurrentUser, cards: Optional[Cards] = None) -> dict:
    """A supporting relationship from the viewer's side (``connect_queries.list_relationships`` row)."""
    cards = cards or Cards()
    is_student = user["role"] == "STUDENT"
    student = cards.student(id=row["student_id"], usn=row["usn"], full_name=row["student_name"],
                            picture_path=row["student_picture"], section_id=row["section_id"])
    faculty = cards.faculty(id=row["faculty_id"], faculty_code=row["faculty_code"],
                            department=row["faculty_department"], full_name=row["faculty_name"],
                            picture_path=row["faculty_picture"])
    mine = (row["requested_by"] == "STUDENT") == is_student
    return {
        "id": row["id"],
        "status": row["status"],
        "requested_by": row["requested_by"],
        "direction": "outgoing" if mine else "incoming",
        "can_respond": row["status"] == "PENDING" and not mine,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "student": student,
        "faculty": faculty,
        "counterpart": dict(faculty, role="FACULTY") if is_student else dict(student, role="STUDENT"),
    }


def _relationship_response(rel_id, user):
    row = cq.get_relationship_full(rel_id)
    return relationship_item(row, user) if row else None


# ---------------------------------------------------------------- searches

@router.get("/faculty/search")
def search_faculty(q: str = Query("", max_length=100), user: CurrentUser = Depends(require_role("STUDENT"))):
    """Student: find any faculty member by name or Faculty ID (blank query -> empty list)."""
    q = q.strip()
    rows = cq.search_faculty(q, user["student_id"]) if q else []
    cards = Cards()
    results = []
    for row in rows:
        in_class = aq.is_student_in_faculty_scope(row["id"], user["student_id"])
        accepted = row["rel_status"] == "ACCEPTED"
        results.append(dict(
            cards.faculty(id=row["id"], faculty_code=row["faculty_code"], department=row["department"],
                          full_name=row["full_name"], picture_path=row["profile_picture_path"]),
            relationship=_relationship_brief(row["rel_id"], row["rel_status"], row["rel_requested_by"]),
            has_access=in_class or accepted,
            access_via="class" if in_class else ("supporting" if accepted else None),
            can_request=_can_request(row["rel_status"]),
        ))
    return items(results, total=len(results), query=q)


@router.get("/students/search")
def search_students(q: str = Query("", max_length=100), user: CurrentUser = Depends(require_role("FACULTY"))):
    """Faculty: find students by USN or name, SCOPED to the classes the faculty member is actively assigned to."""
    q = q.strip()
    rows = aq.search_students_in_faculty_scope(user["faculty_id"], q) if q else []
    relations = cq.relationships_for_faculty_students(user["faculty_id"], [r["id"] for r in rows])
    cards = Cards()
    results = []
    for row in rows:
        card = cq.get_student_card(row["id"])
        rel = relations.get(row["id"])
        results.append(dict(
            cards.student(id=card["id"], usn=card["usn"], full_name=card["full_name"],
                          picture_path=card["profile_picture_path"], section_id=card["section_id"]),
            relationship=_relationship_brief(rel["id"], rel["status"], rel["requested_by"]) if rel else None,
            can_request=_can_request(rel["status"] if rel else None),
        ))
    return items(results, total=len(results), query=q)


# ---------------------------------------------------------------- requests

@router.post("/faculty/{faculty_id}/request", status_code=201)
def request_faculty(faculty_id: int, user: CurrentUser = Depends(require_role("STUDENT"))):
    with service_errors():
        rel_id = supporting_service.student_request_faculty(user["student_id"], faculty_id)
    return ok("Supporting-faculty request sent.", id=rel_id, relationship=_relationship_response(rel_id, user))


@router.post("/students/{student_id}/request", status_code=201)
def request_student(student_id: int, user: CurrentUser = Depends(require_role("FACULTY"))):
    with service_errors():
        rel_id = supporting_service.faculty_request_student(user["faculty_id"], student_id)
    return ok("Supporting-student request sent.", id=rel_id, relationship=_relationship_response(rel_id, user))


def _respond(rel_id: int, accept: bool, user: CurrentUser):
    with service_errors():
        new_status = supporting_service.respond_to_request(rel_id, user["id"], user["role"], accept)
    return ok("Request accepted." if accept else "Request rejected.", status=new_status,
              relationship=_relationship_response(rel_id, user))


@router.post("/{rel_id}/accept")
def accept(rel_id: int, user: CurrentUser = Depends(_PARTICIPANT)):
    return _respond(rel_id, True, user)


@router.post("/{rel_id}/reject")
def reject(rel_id: int, user: CurrentUser = Depends(_PARTICIPANT)):
    return _respond(rel_id, False, user)


@router.get("")
def my_relationships(status: Optional[Literal["PENDING", "ACCEPTED", "REJECTED"]] = Query(None),
                     user: CurrentUser = Depends(_PARTICIPANT)):
    """All my supporting relationships (pending ones first). ``direction`` says who has to answer."""
    if user["role"] == "STUDENT":
        rows = cq.list_relationships(student_id=user["student_id"], status=status)
    else:
        rows = cq.list_relationships(faculty_id=user["faculty_id"], status=status)
    cards = Cards()
    rels = [relationship_item(r, user, cards) for r in rows]
    return items(rels, total=len(rels))
