"""/api/auth/* - session, login/logout and self-service signup (student with OTP, faculty)."""
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictInt, field_validator

from api.deps import (ApiModel, CurrentUser, Stripped, client_ip, current_user_optional, ok, service_errors)
from api.errors import ApiError
from api.schemas import user_payload
from api.settings import get_settings
from models import academic_queries as aq
from models import queries
from services import auth_service, notification_service as notif, otp_service, session_service
from services.auth_service import ValidationError

router = APIRouter(prefix="/api/auth")


# ---------------------------------------------------------------- request models

class LoginIn(ApiModel):
    identifier: Stripped = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class StudentStartIn(ApiModel):
    college_email: Stripped = Field(min_length=1, max_length=254)


class StudentVerifyIn(ApiModel):
    college_email: Stripped = Field(min_length=1, max_length=254)
    otp: Stripped = Field(min_length=1, max_length=16)


class StudentRegisterIn(ApiModel):
    college_email: Stripped = Field(min_length=1, max_length=254)
    full_name: Stripped = Field(min_length=1, max_length=120)
    usn: Stripped = Field(min_length=1, max_length=32)
    section_id: StrictInt
    phone: Stripped = Field(min_length=1, max_length=32)
    personal_email: Stripped = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    confirm_password: str = Field(max_length=1024)


class FacultySignupIn(ApiModel):
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


@router.post("/login")
def login(body: LoginIn, request: Request):
    with service_errors():
        try:
            row = auth_service.authenticate(body.identifier, body.password, ip=client_ip(request))
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


# ---------------------------------------------------------------- student signup (3 steps)

@router.post("/signup/student/start")
def signup_student_start(body: StudentStartIn, request: Request):
    with service_errors():
        email = auth_service.validate_email(body.college_email.lower(), "College email", "college_email")
        if queries.get_user_by_email(email):
            raise auth_service.ConflictError("An account with this college email already exists.", "college_email")
        mode = otp_service.delivery_mode()
        if mode == "none":
            raise otp_service.DeliveryError(
                "Email verification is not available right now. Please contact the administrator."
            )
        otp = otp_service.generate_and_store_otp(email, ip=client_ip(request))
        emailed = otp_service.deliver_otp(email, otp)
    expiry = get_settings().otp_expiry_minutes
    if emailed:
        return ok(f"We sent a 6-digit verification code to {email}. It expires in {expiry} minutes.",
                  email=email, delivery="email", expires_in_minutes=expiry)
    # Demo mode only (no SMTP and SHOW_DEMO_OTP): the code is returned for on-screen display.
    return ok(f"Demo mode: your verification code is shown on screen for {email}.",
              email=email, delivery="demo", expires_in_minutes=expiry, demo_otp=otp)


@router.post("/signup/student/verify")
def signup_student_verify(body: StudentVerifyIn, request: Request):
    email = otp_service.normalize_email(body.college_email)
    with service_errors():
        verified, error = otp_service.verify_otp(email, body.otp)
        if not verified:
            raise ValidationError(error, "otp")
    otp_service.remember_verified_in_session(request.session, email)
    return ok("Email verified. Please complete your registration.", email=email)


@router.post("/signup/student/register", status_code=201)
def signup_student_register(body: StudentRegisterIn, request: Request):
    email = otp_service.normalize_email(body.college_email)
    # The OTP must have been verified recently AND by this browser session.
    if not (otp_service.is_email_otp_verified(email)
            and otp_service.is_verified_in_session(request.session, email)):
        raise ApiError(403, "otp_not_verified", "Please verify your college email with the OTP first.",
                       {"college_email": "Verify this email with the OTP first."})
    with service_errors():
        _require_same_passwords(body.password, body.confirm_password)
        auth_service.register_student({
            "full_name": body.full_name, "usn": body.usn, "section_id": body.section_id,
            "phone": body.phone, "personal_email": body.personal_email,
            "college_email": email, "password": body.password,
        })
    otp_service.clear_verified_in_session(request.session)
    return ok("Registration successful. Please sign in.")


# ---------------------------------------------------------------- faculty signup

@router.post("/signup/faculty", status_code=201)
def signup_faculty(body: FacultySignupIn):
    with service_errors():
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
