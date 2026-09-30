import re
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from models import queries
from models import security_queries as sq
from models import academic_queries as aq
from services import academic_service
from services.academic_service import AcademicError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USN_RE = re.compile(r"^[A-Za-z0-9]{6,15}$")
PHONE_RE = re.compile(r"^[0-9]{7,15}$")


class ValidationError(Exception):
    pass


class LockoutError(ValidationError):
    """Too many failed sign-ins; generic message, never reveals whether the account exists."""


GENERIC_LOGIN_ERROR = "Invalid email or password."
LOCKOUT_MESSAGE = "Too many unsuccessful attempts. Please wait a few minutes and try again."
PASSWORD_RULE_MESSAGE = (
    "Password must be at least 8 characters and include an uppercase letter, a lowercase letter and a digit."
)
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password, disallow=()):
    """Min 8 chars, at least one upper, one lower and one digit (symbols allowed). Also rejects a
    password that equals the account's email / username / ID (`disallow`, compared case-insensitively,
    including the part of an email before the '@')."""
    if not password or len(password) < 8:
        raise ValidationError(PASSWORD_RULE_MESSAGE)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long.")
    if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"[0-9]", password)):
        raise ValidationError(PASSWORD_RULE_MESSAGE)
    lowered = password.strip().lower()
    for value in disallow:
        if not value:
            continue
        value = str(value).strip().lower()
        candidates = {value, value.split("@", 1)[0]} if "@" in value else {value}
        if lowered in candidates:
            raise ValidationError("Password must not be the same as your email, username or ID.")
    return password


def hash_password(password, disallow=()):
    validate_password_strength(password, disallow)
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def validate_email(email, field_name="Email"):
    if not email or not EMAIL_RE.match(email):
        raise ValidationError(f"{field_name} is not a valid email address.")
    return email.strip().lower()


def validate_required(value, field_name):
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field_name} is required.")
    return str(value).strip()


def validate_usn(usn):
    usn = (usn or "").strip().upper()
    if not USN_RE.match(usn):
        raise ValidationError("USN must be 6-15 alphanumeric characters.")
    if queries.get_usn_exists(usn):
        raise ValidationError("This USN is already registered.")
    return usn


def validate_phone(phone):
    phone = (phone or "").strip()
    if not PHONE_RE.match(phone):
        raise ValidationError("Phone number must be 7-15 digits.")
    return phone


def register_student(data):
    """data: dict with full_name, usn, section_id (Admin-defined Branch/Dept/Year/Section), phone,
    personal_email, college_email, password. Returns created user id."""
    full_name = validate_required(data.get("full_name"), "Full name")
    usn = validate_usn(data.get("usn"))
    try:
        combo = academic_service.resolve_section(data.get("section_id"))
    except AcademicError as e:
        raise ValidationError(str(e))
    phone = validate_phone(data.get("phone"))
    personal_email = validate_email(data.get("personal_email"), "Personal email")
    college_email = validate_email(data.get("college_email"), "College email")
    password_hash = hash_password(data.get("password"), disallow=(college_email, usn, personal_email))

    if queries.get_user_by_email(college_email):
        raise ValidationError("An account with this college email already exists.")

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


def register_faculty(data):
    """data: dict with full_name, faculty_code, department, professional_email,
    password, subjects (list[str]). Class assignments are never chosen here - Admin assigns them."""
    full_name = validate_required(data.get("full_name"), "Full name")
    faculty_code = validate_required(data.get("faculty_code"), "Faculty ID").upper()
    department = validate_required(data.get("department"), "Department")
    known = {d.lower(): d for d in aq.list_active_department_names()}
    if department.lower() not in known:
        raise ValidationError("Please choose your department from the list.")
    department = known[department.lower()]
    professional_email = validate_email(data.get("professional_email"), "Professional email")
    password_hash = hash_password(data.get("password"), disallow=(professional_email, faculty_code))
    subjects = [s.strip() for s in data.get("subjects", []) if s and s.strip()]

    if not subjects:
        raise ValidationError("At least one subject is required.")
    if queries.get_faculty_code_exists(faculty_code):
        raise ValidationError("This Faculty ID is already registered.")
    if queries.get_user_by_email(professional_email):
        raise ValidationError("An account with this professional email already exists.")

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
    cfg = current_app.config
    window = cfg["LOGIN_WINDOW_MINUTES"]
    if sq.count_recent_failures_for_identifier(identifier, window) >= cfg["LOGIN_MAX_FAILURES_PER_IDENTIFIER"]:
        return True
    if ip and sq.count_recent_failures_for_ip(ip, window) >= cfg["LOGIN_MAX_FAILURES_PER_IP"]:
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
        raise ValidationError("Your current password is incorrect.")
    if new_password != confirm_password:
        raise ValidationError("New password and confirmation do not match.")
    if verify_password(user["password_hash"], new_password or ""):
        raise ValidationError("Your new password must be different from the current one.")
    new_hash = hash_password(new_password, disallow=(user["email"],))
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
