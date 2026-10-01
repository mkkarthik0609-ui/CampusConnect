"""/api/admin/* - academic structure, faculty assignments, class requests and the class directory.

ADMIN-only (the dependency sits on the router). The business rules live in
``services.academic_service`` / ``services.assignment_service``; this module only validates the request
body, maps the services' exceptions to the conventions error shape and builds the JSON the console needs."""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import Field, StrictBool

from api.deps import ApiModel, CurrentUser, Stripped, items, ok, require_role, service_errors
from api.errors import ApiError, map_service_error
from api.routers.admin import (DecisionIn, assignment_item, assignment_request_item, combos_by_section,
                               student_item)
from api.schemas import class_object, profile_picture_url
from models import academic_queries as aq
from models import admin_queries
from services import academic_service, assignment_service
from services.academic_service import AcademicError, AcademicInUseError

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("ADMIN"))], tags=["admin-academics"])

BodyId = Annotated[int, Field(strict=True, ge=1)]
REQUEST_STATUSES = ("PENDING", "APPROVED", "REJECTED")
LEVEL_LABELS = {"branch": "Branch", "department": "Department", "year": "Academic year", "section": "Section"}


# ---------------------------------------------------------------- request models

class BranchIn(ApiModel):
    name: Stripped = Field(max_length=100)


class DepartmentIn(ApiModel):
    branch_id: BodyId
    name: Stripped = Field(max_length=100)


class YearIn(ApiModel):
    department_id: BodyId
    name: Stripped = Field(max_length=40)  # "3", "3rd", "3rd Year" -> "3rd Year"


class SectionsIn(ApiModel):
    year_id: BodyId
    names: Stripped = Field(max_length=200)  # "A" or "A, B, C" (single letters only)


class ActiveIn(ApiModel):
    active: StrictBool


class AssignIn(ApiModel):
    faculty_id: BodyId
    section_id: BodyId


# ---------------------------------------------------------------- helpers

def _structure(field, fn, *args):
    """Run an academic_service mutation; AcademicError -> ApiError (404 / 409 / 400) with the offending
    request field attached so the form can show the message inline."""
    try:
        return fn(*args)
    except AcademicInUseError as exc:
        raise ApiError(409, "in_use", str(exc)) from exc
    except AcademicError as exc:
        mapped = map_service_error(exc)
        if mapped.status in (400, 409):
            mapped.fields = {field: mapped.message}
        raise mapped from exc


def _class_row(row, faculty=None):
    """Class directory item from a row of list_combos_with_counts()/get_combo() (+ counts)."""
    item = class_object(row)
    item["is_active"] = bool(row["chain_active"])
    for key in ("student_count", "faculty_count"):
        if key in row.keys():
            item[key] = row[key]
    if faculty is not None:
        item["faculty"] = faculty
    return item


def _class_faculty(section_id):
    return [{
        "id": f["faculty_id"], "assignment_id": f["assignment_id"], "faculty_code": f["faculty_code"],
        "full_name": f["full_name"], "profile_picture_url": profile_picture_url(f["profile_picture_path"]),
    } for f in aq.list_faculty_for_section(section_id)]


def _assignment_for(faculty_id, section_id):
    row = aq.get_assignment_for(faculty_id, section_id)
    for a in aq.list_assignments_for_faculty(faculty_id, active_only=False):
        if row and a["assignment_id"] == row["id"]:
            return assignment_item(a)
    return None


# ---------------------------------------------------------------- academic structure

@router.get("/academics")
def academics():
    """The whole tree including inactive rows; every node carries usage counts and ``can_delete``."""
    return {"branches": academic_service.get_tree(active_only=False, with_usage=True)}


@router.post("/academics/branches", status_code=201)
def add_branch(body: BranchIn):
    new_id = _structure("name", academic_service.add_branch, body.name)
    return ok("Branch added.", id=new_id, name=aq.get_branch(new_id)["name"])


@router.post("/academics/departments", status_code=201)
def add_department(body: DepartmentIn):
    new_id = _structure("name", academic_service.add_department, body.branch_id, body.name)
    return ok("Department added.", id=new_id, name=aq.get_department(new_id)["name"])


@router.post("/academics/years", status_code=201)
def add_year(body: YearIn):
    new_id = _structure("name", academic_service.add_year, body.department_id, body.name)
    return ok("Academic year added.", id=new_id, name=aq.get_year(new_id)["name"])


@router.post("/academics/sections", status_code=201)
def add_sections(body: SectionsIn):
    created = _structure("names", academic_service.add_sections, body.year_id, body.names)
    return ok("Section(s) added: " + ", ".join(created) + ".", created=created)


@router.post("/academics/{level}/{row_id}/active")
def set_active(level: str, row_id: int, body: ActiveIn):
    _structure("active", academic_service.set_active, level, row_id, body.active)
    label = LEVEL_LABELS[level]
    message = (f"{label} reactivated." if body.active
               else f"{label} deactivated. It is hidden from new registrations.")
    return ok(message, level=level, id=row_id, is_active=body.active)


@router.delete("/academics/{level}/{row_id}")
def delete_item(level: str, row_id: int):
    """Only an unused item (no students, no faculty assignments - active or not) can be deleted."""
    _structure("id", academic_service.delete_unused, level, row_id)
    return ok(f"{LEVEL_LABELS[level]} deleted.", level=level, id=row_id)


# ---------------------------------------------------------------- faculty assignments

@router.get("/assignments")
def assignments():
    rows = []
    for f in admin_queries.list_faculty():
        rows.append({
            "faculty_id": f["id"],
            "faculty_code": f["faculty_code"],
            "full_name": f["full_name"],
            "department": f["department"],
            "profile_picture_url": profile_picture_url(f["profile_picture_path"]),
            "assignments": [assignment_item(a) for a in aq.list_assignments_for_faculty(f["id"], active_only=False)
                            if a["assignment_active"]],
            "pending_requests": [assignment_request_item(r) for r in
                                 aq.list_assignment_requests(status="PENDING", faculty_id=f["id"])],
        })
    return items(rows, total=len(rows), pending_count=aq.count_pending_assignment_requests())


@router.post("/assignments", status_code=201)
def assign(body: AssignIn, user: CurrentUser = Depends(require_role("ADMIN"))):
    with service_errors():
        combo = assignment_service.admin_assign(body.faculty_id, body.section_id, user["id"])
    return ok(f"Assigned to {academic_service.combo_label(combo)}.",
              assignment=_assignment_for(body.faculty_id, combo["section_id"]))


@router.delete("/assignments/{assignment_id}")
def remove_assignment(assignment_id: int, user: CurrentUser = Depends(require_role("ADMIN"))):
    """Deactivates the assignment (the row is kept; assigning again re-activates it)."""
    row = aq.get_assignment(assignment_id)
    if row is None:
        raise ApiError(404, "not_found", "Assignment not found.")
    if not row["is_active"]:
        raise ApiError(409, "already_inactive", "This assignment was already removed.")
    with service_errors():
        combo = assignment_service.admin_remove(assignment_id, user["id"])
    return ok(f"Assignment removed: {academic_service.combo_label(combo)}.", assignment_id=assignment_id)


# ---------------------------------------------------------------- faculty requests to join a class

@router.get("/assignment-requests")
def assignment_requests(status: Optional[str] = Query(None, max_length=20)):
    wanted = status.strip().upper() if status else None
    if wanted and wanted not in REQUEST_STATUSES:
        raise ApiError(400, "validation_error", "Unknown request status.",
                       {"status": "Use one of: " + ", ".join(REQUEST_STATUSES) + "."})
    rows = [assignment_request_item(r) for r in aq.list_assignment_requests(status=wanted)]
    return items(rows, total=len(rows), pending_count=aq.count_pending_assignment_requests())


@router.post("/assignment-requests/{request_id}/decide")
def decide_assignment_request(request_id: int, body: DecisionIn,
                              user: CurrentUser = Depends(require_role("ADMIN"))):
    with service_errors():
        status = assignment_service.decide_request(request_id, user["id"], body.decision == "approve")
    return ok(f"Request {status.lower()}.", status=status)


# ---------------------------------------------------------------- class directory

@router.get("/classes")
def classes():
    rows = [_class_row(c, _class_faculty(c["section_id"])) for c in aq.list_combos_with_counts()]
    return items(rows, total=len(rows))


@router.get("/classes/{section_id}")
def class_detail(section_id: int):
    combo = next((c for c in aq.list_combos_with_counts() if c["section_id"] == section_id), None)
    if combo is None:
        raise ApiError(404, "not_found", "Class not found.")
    faculty = _class_faculty(section_id)
    combos = combos_by_section()
    students = [student_item(r, combos) for r in admin_queries.list_students(section_id)]
    return {"class": _class_row(combo), "faculty": faculty, "students": students}
