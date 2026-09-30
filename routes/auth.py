from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

from models import queries
from models import academic_queries as aq
from routes.helpers import login_required
from services import auth_service, otp_service, academic_service
from services import session_service
from services.auth_service import ValidationError, LockoutError

auth_bp = Blueprint("auth", __name__)


def _login_user(user_row):
    """Start a fresh session for this user (any pre-login session data is discarded)."""
    session.clear()
    session.permanent = True
    session["theme"] = user_row["theme_preference"]
    session_service.apply_identity(user_row)
    session_service.stamp_login()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            user = auth_service.authenticate(identifier, password, ip=request.remote_addr)
            _login_user(user)
            flash("Welcome back!", "success")
            return redirect(url_for("index"))
        except LockoutError as e:
            flash(str(e), "error")
            return render_template("auth/login.html"), 429
        except ValidationError as e:
            flash(str(e), "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        try:
            auth_service.change_password(
                session["user_id"],
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
                ip=request.remote_addr,
            )
            flash("Your password has been changed.", "success")
            return redirect(url_for("index"))
        except LockoutError as e:
            flash(str(e), "error")
            return render_template("auth/change_password.html"), 429
        except ValidationError as e:
            flash(str(e), "error")
    return render_template("auth/change_password.html")


# ---------- student signup ----------

@auth_bp.route("/signup/student", methods=["GET", "POST"])
def signup_student_start():
    if request.method == "POST":
        email = request.form.get("college_email", "").strip().lower()
        try:
            email = auth_service.validate_email(email, "College email")
            if queries.get_user_by_email(email):
                raise ValidationError("An account with this college email already exists.")
            if otp_service.delivery_mode() == "none":
                raise ValidationError(
                    "Email verification is not available right now. Please contact the administrator."
                )
            otp = otp_service.generate_and_store_otp(email)
            if otp_service.deliver_otp(email, otp):
                flash(f"We sent a 6-digit verification code to {email}. It expires in "
                      f"{current_app.config['OTP_EXPIRY_MINUTES']} minutes.", "info")
            else:
                flash(f"Demo OTP for {email}: {otp}  (shown on-screen only, never emailed/SMSed)", "info")
            return redirect(url_for("auth.signup_student_verify", email=email))
        except ValidationError as e:
            flash(str(e), "error")
    return render_template("auth/signup_student_start.html")


@auth_bp.route("/signup/student/verify-otp", methods=["GET", "POST"])
def signup_student_verify():
    email = (request.args.get("email") or request.form.get("email", "")).strip().lower()
    if request.method == "POST":
        otp = request.form.get("otp", "")
        ok, error = otp_service.verify_otp(email, otp)
        if ok:
            otp_service.remember_verified_in_session(email)
            flash("Email verified. Please complete your registration.", "success")
            return redirect(url_for("auth.signup_student_details", email=email))
        flash(error, "error")
    return render_template("auth/signup_student_verify.html", email=email)


@auth_bp.route("/signup/student/details", methods=["GET", "POST"])
def signup_student_details():
    email = (request.args.get("email") or request.form.get("college_email", "")).strip().lower()
    # The OTP must have been verified recently AND by this browser session.
    if not (otp_service.is_email_otp_verified(email) and otp_service.is_verified_in_session(email)):
        flash("Please verify your college email with the OTP first.", "error")
        return redirect(url_for("auth.signup_student_start"))

    if request.method == "POST":
        data = {
            "full_name": request.form.get("full_name"),
            "usn": request.form.get("usn"),
            "section_id": request.form.get("section_id"),
            "phone": request.form.get("phone"),
            "personal_email": request.form.get("personal_email"),
            "college_email": email,
            "password": request.form.get("password"),
        }
        confirm_password = request.form.get("confirm_password")
        try:
            if data["password"] != confirm_password:
                raise ValidationError("Passwords do not match.")
            auth_service.register_student(data)
            otp_service.clear_verified_in_session()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("auth.login"))
        except ValidationError as e:
            flash(str(e), "error")

    return render_template(
        "auth/signup_student_details.html", email=email,
        academic_tree=academic_service.get_tree(), form=request.form,
    )


# ---------- faculty signup ----------

@auth_bp.route("/signup/faculty", methods=["GET", "POST"])
def signup_faculty():
    if request.method == "POST":
        subjects = [s.strip() for s in request.form.get("subjects", "").split(",") if s.strip()]
        data = {
            "full_name": request.form.get("full_name"),
            "faculty_code": request.form.get("faculty_code"),
            "department": request.form.get("department"),
            "professional_email": request.form.get("professional_email"),
            "password": request.form.get("password"),
            "subjects": subjects,
        }
        confirm_password = request.form.get("confirm_password")
        try:
            if data["password"] != confirm_password:
                raise ValidationError("Passwords do not match.")
            auth_service.register_faculty(data)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("auth.login"))
        except ValidationError as e:
            flash(str(e), "error")
    return render_template(
        "auth/signup_faculty.html", departments=aq.list_active_department_names(), form=request.form,
    )
