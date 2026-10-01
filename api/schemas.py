"""Shared response shapes from docs/api/CONVENTIONS.md (user object, class object, faculty card).

Plain-dict serializers (same names as the old ``routes/helpers``) plus the matching pydantic models
for OpenAPI documentation. Routers may use the dict helpers directly in their JSON responses.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from services import file_service


class UserOut(BaseModel):
    id: int
    role: str
    full_name: str
    email: str
    theme: str
    profile_picture_url: Optional[str] = None
    student_id: Optional[int] = None
    faculty_id: Optional[int] = None


class ClassOut(BaseModel):
    section_id: int
    branch: str
    department: str
    year: str
    section: str
    label: str


def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def profile_picture_url(path):
    return file_service.upload_url(path)


def class_object(combo):
    """Class object from a row of academic_queries.get_combo()/list_combos(), or None."""
    if not combo:
        return None
    branch, department = combo["branch_name"], combo["department_name"]
    year, section = combo["year_name"], combo["section_name"]
    return {
        "section_id": combo["section_id"], "branch": branch, "department": department,
        "year": year, "section": section,
        "label": f"{branch} → {department} → {year} → {section}",
    }


def class_object_for_section(section_id):
    """Class object for a section id (None when the id is missing / unknown)."""
    if not section_id:
        return None
    from models import academic_queries as aq
    return class_object(aq.get_combo(section_id))


def user_payload(user):
    """The ``user`` object of CONVENTIONS.md from a ``users`` row *or* a ``CurrentUser``."""
    from models import queries
    role = user["role"]
    student_id = faculty_id = None
    if role == "STUDENT":
        student = queries.get_student_by_user_id(user["id"])
        student_id = student["id"] if student else None
    elif role == "FACULTY":
        faculty = queries.get_faculty_by_user_id(user["id"])
        faculty_id = faculty["id"] if faculty else None
    return {
        "id": user["id"],
        "role": role,
        "full_name": user["full_name"],
        "email": user["email"],
        "theme": user["theme_preference"],
        "profile_picture_url": profile_picture_url(_get(user, "profile_picture_path")),
        "student_id": student_id,
        "faculty_id": faculty_id,
    }


def faculty_brief(row):
    """Compact faculty card from rows with id/faculty_code/department/full_name/profile_picture_path."""
    return {
        "id": row["id"],
        "faculty_code": row["faculty_code"],
        "department": row["department"],
        "full_name": row["full_name"],
        "profile_picture_url": profile_picture_url(_get(row, "profile_picture_path")),
    }
