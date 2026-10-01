"""/api/auth/* - session, captcha, login/logout and self-service signup (student, faculty)."""
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field, StrictInt, field_validator

from api.deps import (ApiModel, CurrentUser, Stripped, client_ip, current_user_optional, ok, service_errors)
from api.errors import ApiError
from api.schemas import user_payload
from models import academic_queries as aq
from models import queries
from services import auth_service, captcha_service, notification_service as notif, session_service
from services.auth_service import ValidationError

router = APIRouter(prefix="/api/auth")


# ---------------------------------------------------------------- request models

class CaptchaIn(ApiModel):
    captcha_id: Stripped = Field(default="", max_length=128)
    captcha_answer: Stripped = Field(default="", max_length=32)


class LoginIn(CaptchaIn):
    identifier: Stripped = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class StudentSignupIn(CaptchaIn):
    college_email: Stripped = Field(min_length=1, max_length=254)
    full_name: Stripped = Field(min_length=1, max_length=120)
    usn: Stripped = Field(min_length=1, max_length=32)
    section_id: StrictInt
    phone: Stripped = Field(min_length=1, max_length=32)
    personal_email: Stripped = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    confirm_password: str = Field(max_length=1024)


class FacultySignupIn(CaptchaIn):
    full_name: Stripped = Field(min_length=1, max_length=120)
    faculty_code: Stripped = Field(min_length=1, max_length=32)
    department: Stripped = Field(min_length=1, max_length=80)
    professional_email: Stripped = Field(min_length=1, max_length=254)
    subjects: Union[List[str], str]
    password: str = Field(min_length=1, max_length=1024)
    confirm_password: str = Field(max_length=1024)

    @field_validator("subjects")
    @classmethod
    def _subjects(cls, value):
        names = auth_service.normalize_subjects(value)
        if not names:
            raise ValueError("At least one subject is required.")
        return names


# ---------------------------------------------------------------- helpers

def _counters(user: Optional[CurrentUser]):
    if not user:
        return 0, 0
    return notif.get_unread_count(user["id"]), queries.get_total_unread_for_user(user["id"], user["role"])


def _require_same_passwords(password, confirm, field="confirm_password"):
    if password != confirm:
        raise ValidationError("Passwords do not match.", field)


# ---------------------------------------------------------------- session

@router.get("/session")
def get_session(request: Request, user: Optional[CurrentUser] = Depends(current_user_optional)):
    """Always 200. Creates the CSRF token in the session when absent."""
    token = session_service.ensure_csrf_token(request.session)
    unread_notifications, unread_messages = _counters(user)
    return {
        "authenticated": user is not None,
        "user": user_payload(user) if user else None,
        "csrf_token": token,
        "unread_notifications": unread_notifications,
        "unread_messages": unread_messages,
    }


@router.get("/captcha")
def get_captcha(request: Request):
    """A fresh image captcha: {captcha_id, image (PNG data URL), expires_in_seconds}. Single use."""
    with service_errors():
        challenge = captcha_service.issue_challenge(ip=client_ip(request))
    return JSONResponse(challenge, headers={"Cache-Control": "no-store"})


@router.post("/login")
def login(body: LoginIn, request: Request):
    ip = client_ip(request)
    if auth_service.login_requires_captcha(body.identifier, ip):  # adaptive: only after repeated failures
        if not body.captcha_id:
            raise ApiError(400, "captcha_required", "Please solve the captcha to continue.",
                           {"captcha": "Type the characters shown in the image."})
        with service_errors():
            captcha_service.verify(body.captcha_id, body.captcha_answer)
    with service_errors():
        try:
            row = auth_service.authenticate(body.identifier, body.password, ip=ip)
        except auth_service.LockoutError:
            raise
        except ValidationError as exc:  # the one generic message for every credential failure
            raise ApiError(401, "invalid_credentials", str(exc)) from exc
    token = session_service.start_session(request.session, row)  # fixation-safe: new session + new csrf
    return ok("Welcome back!", user=user_payload(row), csrf_token=token)


@router.post("/logout")
def logout(request: Request):
    token = session_service.end_session(request.session)
    return ok("You have been signed out.", csrf_token=token)


# ---------------------------------------------------------------- signup (captcha-protected)

@router.post("/signup/student", status_code=201)
def signup_student(body: StudentSignupIn, request: Request):
    with service_errors():
        # The captcha is checked (and consumed) first, so account probing is impossible without solving one.
        captcha_service.verify(body.captcha_id, body.captcha_answer)
        _require_same_passwords(body.password, body.confirm_password)
        auth_service.register_student({
            "full_name": body.full_name, "usn": body.usn, "section_id": body.section_id,
            "phone": body.phone, "personal_email": body.personal_email,
            "college_email": body.college_email.lower(), "password": body.password,
        })
    return ok("Registration successful. Please sign in.")


@router.post("/signup/faculty", status_code=201)
def signup_faculty(body: FacultySignupIn):
    with service_errors():
        captcha_service.verify(body.captcha_id, body.captcha_answer)
        _require_same_passwords(body.password, body.confirm_password)
        auth_service.register_faculty({
            "full_name": body.full_name, "faculty_code": body.faculty_code, "department": body.department,
            "professional_email": body.professional_email, "password": body.password,
            "subjects": body.subjects,
        })
    return ok("Registration successful. Please sign in.")


@router.get("/faculty-departments")
def faculty_departments():
    return {"items": list(aq.list_active_department_names())}
