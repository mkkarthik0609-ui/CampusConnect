import os
import re

from werkzeug.security import generate_password_hash, check_password_hash
from api.settings import get_settings
from models import queries
from models import security_queries as sq
from models import academic_queries as aq
from services import academic_service
from services.academic_service import AcademicError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USN_RE = re.compile(r"^[A-Za-z0-9]{6,15}$")
PHONE_RE = re.compile(r"^[0-9]{7,15}$")


class ValidationError(Exception):
    """A business-rule / input failure. `field` (optional) names the offending request field so the
    API can return it under error.fields."""

    def __init__(self, message="", field=None):
        super().__init__(message)
        self.field = field


class ConflictError(ValidationError):
    """The value is already taken (duplicate email / USN / Faculty ID) -> HTTP 409."""


class LockoutError(ValidationError):
    """Too many failed sign-ins; generic message, never reveals whether the account exists."""


GENERIC_LOGIN_ERROR = "Invalid email or password."
LOCKOUT_MESSAGE = "Too many unsuccessful attempts. Please wait a few minutes and try again."
PASSWORD_RULE_MESSAGE = (
    "Password must be at least 8 characters and include an uppercase letter, a lowercase letter and a digit."
)
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password, disallow=(), field="password"):
    """Min 8 chars, at least one upper, one lower and one digit (symbols allowed). Also rejects a
    password that equals the account's email / username / ID (`disallow`, compared case-insensitively,
    including the part of an email before the '@')."""
    if not password or len(password) < 8:
        raise ValidationError(PASSWORD_RULE_MESSAGE, field)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long.", field)
    if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"[0-9]", password)):
        raise ValidationError(PASSWORD_RULE_MESSAGE, field)
    lowered = password.strip().lower()
    for value in disallow:
        if not value:
            continue
        value = str(value).strip().lower()
        candidates = {value, value.split("@", 1)[0]} if "@" in value else {value}
        if lowered in candidates:
            raise ValidationError("Password must not be the same as your email, username or ID.", field)
    return password


def hash_password(password, disallow=(), field="password"):
    validate_password_strength(password, disallow, field)
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def validate_email(email, field_name="Email", field=None):
    if not email or not EMAIL_RE.match(email):
        raise ValidationError(f"{field_name} is not a valid email address.", field)
    return email.strip().lower()


def validate_required(value, field_name, field=None):
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field_name} is required.", field)
    return str(value).strip()


def validate_usn(usn):
    usn = (usn or "").strip().upper()
    if not USN_RE.match(usn):
        raise ValidationError("USN must be 6-15 alphanumeric characters.", "usn")
    if queries.get_usn_exists(usn):
        raise ConflictError("This USN is already registered.", "usn")
    return usn


def validate_phone(phone):
    phone = (phone or "").strip()
    if not PHONE_RE.match(phone):
        raise ValidationError("Phone number must be 7-15 digits.", "phone")
    return phone


def register_student(data):
    """data: dict with full_name, usn, section_id (Admin-defined Branch/Dept/Year/Section), phone,
    personal_email, college_email, password. Returns created user id."""
    full_name = validate_required(data.get("full_name"), "Full name", "full_name")
    usn = validate_usn(data.get("usn"))
    try:
        combo = academic_service.resolve_section(data.get("section_id"))
    except AcademicError as e:
        raise ValidationError(str(e), "section_id")
    phone = validate_phone(data.get("phone"))
    personal_email = validate_email(data.get("personal_email"), "Personal email", "personal_email")
    college_email = validate_email(data.get("college_email"), "College email", "college_email")
    password_hash = hash_password(data.get("password"), disallow=(college_email, usn, personal_email))

    if queries.get_user_by_email(college_email):
        raise ConflictError("An account with this college email already exists.", "college_email")

    user_id = queries.create_user("STUDENT", college_email, password_hash, full_name)
    student_id = queries.create_student(
        user_id, usn, combo["branch_name"], combo["department_name"], combo["year_name"],
        combo["section_name"], phone, personal_email, college_email,
    )
    aq.set_student_section(
        student_id, combo["section_id"], combo["branch_name"], combo["department_name"],
        combo["year_name"], combo["section_name"],
    )
    return user_id


def normalize_subjects(subjects):
    """Accept a list of names or a comma-separated string; returns a de-duplicated clean list."""
    if subjects is None:
        return []
    if isinstance(subjects, str):
        subjects = subjects.split(",")
    cleaned, seen = [], set()
    for item in subjects:
        if not isinstance(item, str):
            continue
        name = " ".join(item.split())[:100]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            cleaned.append(name)
    return cleaned


def register_faculty(data):
    """data: dict with full_name, faculty_code, department, professional_email,
    password, subjects (list[str]). Class assignments are never chosen here - Admin assigns them."""
    full_name = validate_required(data.get("full_name"), "Full name", "full_name")
    faculty_code = validate_required(data.get("faculty_code"), "Faculty ID", "faculty_code").upper()
    department = validate_required(data.get("department"), "Department", "department")
    known = {d.lower(): d for d in aq.list_active_department_names()}
    if department.lower() not in known:
        raise ValidationError("Please choose your department from the list.", "department")
    department = known[department.lower()]
    professional_email = validate_email(data.get("professional_email"), "Professional email", "professional_email")
    password_hash = hash_password(data.get("password"), disallow=(professional_email, faculty_code))
    subjects = normalize_subjects(data.get("subjects"))

    if not subjects:
        raise ValidationError("At least one subject is required.", "subjects")
    if queries.get_faculty_code_exists(faculty_code):
        raise ConflictError("This Faculty ID is already registered.", "faculty_code")
    if queries.get_user_by_email(professional_email):
        raise ConflictError("An account with this professional email already exists.", "professional_email")

    user_id = queries.create_user("FACULTY", professional_email, password_hash, full_name)
    faculty_id = queries.create_faculty(user_id, faculty_code, department, professional_email)
    for subject in subjects:
        queries.add_faculty_subject(faculty_id, subject)
    return user_id


_DUMMY_HASH = None


def _dummy_hash():
    """A real password hash (same algorithm/cost as real ones) checked when the account does not
    exist, so response time does not reveal which identifiers are registered."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = generate_password_hash("dummy-password-for-timing-equalisation")
    return _DUMMY_HASH


def normalize_identifier(identifier):
    # Control characters are stripped so a login identifier can never collide with the internal
    # throttle keys (prefixed with a control character) used by other flows, e.g. password change.
    return re.sub(r"[\x00-\x1f]", "", (identifier or "")).strip().lower()[:254]


def _is_locked_out(identifier, ip):
    cfg = get_settings()
    window = cfg.login_window_minutes
    if sq.count_recent_failures_for_identifier(identifier, window) >= cfg.login_max_failures_per_identifier:
        return True
    if ip and sq.count_recent_failures_for_ip(ip, window) >= cfg.login_max_failures_per_ip:
        return True
    return False


def authenticate(identifier, password, ip=None):
    """Verify credentials for an email / Faculty ID / USN. Raises ValidationError with one identical
    message for unknown user, wrong password and inactive account; raises LockoutError when throttled.
    Failures are recorded per identifier and per IP; a success clears the identifier's counter."""
    ident = normalize_identifier(identifier)
    if _is_locked_out(ident, ip):
        raise LockoutError(LOCKOUT_MESSAGE)

    user = queries.get_user_by_identifier(identifier)
    password_ok = verify_password(user["password_hash"] if user else _dummy_hash(), password or "")
    if not user or not password_ok or not user["is_active"]:
        sq.record_login_attempt(ident, ip, False)
        raise ValidationError(GENERIC_LOGIN_ERROR)

    sq.clear_failures_for_identifier(ident)
    sq.record_login_attempt(ident, ip, True)
    sq.touch_last_login(user["id"])
    return user


def change_password(user_id, current_password, new_password, confirm_password, ip=None):
    """Change a logged-in user's password. Current-password guesses are throttled like logins."""
    throttle_key = f"\x01pwchange:{user_id}"
    if _is_locked_out(throttle_key, None):
        raise LockoutError(LOCKOUT_MESSAGE)
    user = queries.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise ValidationError("Your account is not available.")
    if not verify_password(user["password_hash"], current_password or ""):
        sq.record_login_attempt(throttle_key, ip, False)
        raise ValidationError("Your current password is incorrect.", "current_password")
    if new_password != confirm_password:
        raise ValidationError("New password and confirmation do not match.", "confirm_password")
    if verify_password(user["password_hash"], new_password or ""):
        raise ValidationError("Your new password must be different from the current one.", "new_password")
    new_hash = hash_password(new_password, disallow=(user["email"],), field="new_password")
    queries.update_user_password(user_id, new_hash)
    sq.clear_failures_for_identifier(throttle_key)


def ensure_admin(full_name, email, password):
    """Idempotent admin creation used by `create_admin.py --from-env` and BOOTSTRAP_ADMIN.
    Returns True if a new admin was created, False if a user with that email already exists
    (an existing account and its password are never modified)."""
    email = validate_email((email or "").strip().lower(), "Email")
    if queries.get_user_by_email(email):
        return False
    full_name = validate_required(full_name, "Full name")
    password_hash = hash_password(password, disallow=(email,))
    queries.create_user("ADMIN", email, password_hash, full_name)
    return True


def bootstrap_admin_from_env():
    """Create the admin described by ADMIN_NAME / ADMIN_EMAIL / ADMIN_PASSWORD when it does not exist
    yet (BOOTSTRAP_ADMIN=1 at start, or ``create_admin.py --from-env``). Needs a db_session/request.
    Returns 'created', 'exists' or 'skipped' (variables missing). Raises ValidationError if the
    supplied values are invalid. An existing account and its password are never modified; the
    password is never logged."""
    name = os.environ.get("ADMIN_NAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not (name and email and password):
        return "skipped"
    return "created" if ensure_admin(name, email, password) else "exists"
