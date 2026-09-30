from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from models import queries
from models import academic_queries as aq
from routes.helpers import role_required, safe_redirect_back
from services import permission_service, file_service
from services.permission_service import PermissionError_
from services.file_service import FileValidationError

student_bp = Blueprint("student", __name__, url_prefix="/student")


@student_bp.route("/dashboard")
@role_required("STUDENT")
def dashboard():
    student = queries.get_student_with_user(session["student_id"])
    assigned_faculty = aq.list_assigned_faculty_for_student(session["student_id"])
    supporting_faculty = queries.list_accepted_supporting_faculty_for_student(session["student_id"])
    pending_supporting = queries.list_pending_supporting_requests_for_student(session["student_id"])
    recent_meetings = queries.list_meetings_for_student(session["student_id"])[:5]
    return render_template(
        "student/dashboard.html", student=student, assigned_faculty=assigned_faculty,
        supporting_faculty=supporting_faculty, pending_supporting=pending_supporting,
        recent_meetings=recent_meetings,
    )


@student_bp.route("/profile")
@role_required("STUDENT")
def profile():
    student = queries.get_student_with_user(session["student_id"])
    assigned_faculty = aq.list_assigned_faculty_for_student(session["student_id"])
    pending_requests = queries.list_permission_requests_by_requester(session["user_id"])
    return render_template(
        "student/profile.html", student=student, assigned_faculty=assigned_faculty,
        pending_requests=pending_requests,
    )


@student_bp.route("/profile/picture", methods=["POST"])
@role_required("STUDENT")
def update_picture():
    upload = request.files.get("profile_picture")
    try:
        relative_path = file_service.save_profile_picture(upload, "STUDENT")
        queries.update_user_profile_picture(session["user_id"], relative_path)
        flash("Profile picture updated.", "success")
    except FileValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("student.profile"))


@student_bp.route("/profile/change-request", methods=["POST"])
@role_required("STUDENT")
def request_profile_change():
    changes = {
        k: request.form.get(k) for k in
        ("phone", "personal_email")
        if request.form.get(k)
    }
    try:
        permission_service.student_request_profile_change(
            session["user_id"], changes, request.form.get("reason")
        )
        flash("Profile change request submitted for faculty approval.", "success")
    except PermissionError_ as e:
        flash(str(e), "error")
    return redirect(url_for("student.profile"))


@student_bp.route("/theme/<theme>", methods=["POST"])
@role_required("STUDENT", "FACULTY", "ADMIN")
def set_theme(theme):
    if theme not in ("light", "dark"):
        theme = "light"
    queries.update_user_theme(session["user_id"], theme)
    session["theme"] = theme
    return safe_redirect_back("index")
