from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

from models import queries
from models import academic_queries as aq
from routes.helpers import role_required
from services import permission_service, file_service, academic_service, assignment_service
from services.assignment_service import AssignmentError
from services.permission_service import PermissionError_
from services.file_service import FileValidationError

faculty_bp = Blueprint("faculty", __name__, url_prefix="/faculty")


@faculty_bp.route("/dashboard")
@role_required("FACULTY")
def dashboard():
    faculty = queries.get_faculty_with_user(session["faculty_id"])
    subjects = queries.get_faculty_subjects(session["faculty_id"])
    classes = aq.list_assignments_for_faculty(session["faculty_id"])
    pending_class_requests = aq.list_assignment_requests(status="PENDING", faculty_id=session["faculty_id"])
    supporting_students = queries.list_accepted_supporting_students_for_faculty(session["faculty_id"])
    pending_supporting = queries.list_pending_supporting_requests_for_faculty(session["faculty_id"])
    recent_meetings = queries.list_meetings_for_faculty(session["faculty_id"])[:5]
    pending_permission_requests = queries.list_pending_permission_requests_for_approver(session["user_id"])
    return render_template(
        "faculty/dashboard.html", faculty=faculty, subjects=subjects, classes=classes,
        supporting_students=supporting_students, pending_supporting=pending_supporting,
        recent_meetings=recent_meetings, pending_permission_requests=pending_permission_requests,
        pending_class_requests=pending_class_requests,
    )


@faculty_bp.route("/profile")
@role_required("FACULTY")
def profile():
    faculty = queries.get_faculty_with_user(session["faculty_id"])
    subjects = queries.get_faculty_subjects(session["faculty_id"])
    classes = aq.list_assignments_for_faculty(session["faculty_id"])
    pending_requests = queries.list_permission_requests_by_requester(session["user_id"])
    return render_template(
        "faculty/profile.html", faculty=faculty, subjects=subjects, classes=classes,
        pending_requests=pending_requests, departments=aq.list_active_department_names(),
    )


@faculty_bp.route("/profile/picture", methods=["POST"])
@role_required("FACULTY")
def update_picture():
    upload = request.files.get("profile_picture")
    try:
        relative_path = file_service.save_profile_picture(upload, "FACULTY")
        queries.update_user_profile_picture(session["user_id"], relative_path)
        flash("Profile picture updated.", "success")
    except FileValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("faculty.profile"))


@faculty_bp.route("/profile/change-request", methods=["POST"])
@role_required("FACULTY")
def request_profile_change():
    changes = {
        k: request.form.get(k) for k in ("department", "professional_email") if request.form.get(k)
    }
    try:
        permission_service.faculty_request_profile_change(
            session["user_id"], changes, request.form.get("reason")
        )
        flash("Profile change request submitted for admin approval.", "success")
    except PermissionError_ as e:
        flash(str(e), "error")
    return redirect(url_for("faculty.profile"))


@faculty_bp.route("/permission-requests")
@role_required("FACULTY")
def review_permission_requests():
    requests_list = queries.list_pending_permission_requests_for_approver(session["user_id"])
    return render_template("faculty/permission_requests.html", requests_list=requests_list)


@faculty_bp.route("/permission-requests/<int:request_id>/decide", methods=["POST"])
@role_required("FACULTY")
def decide_permission_request(request_id):
    approve = request.form.get("decision") == "approve"
    try:
        permission_service.decide_permission_request(request_id, session["user_id"], approve)
        flash("Request reviewed.", "success")
    except PermissionError_ as e:
        flash(str(e), "error")
    return redirect(url_for("faculty.review_permission_requests"))


# ---------- assigned classes (Admin-controlled) ----------

@faculty_bp.route("/classes")
@role_required("FACULTY")
def classes():
    return render_template(
        "faculty/classes.html",
        assignments=aq.list_assignments_for_faculty(session["faculty_id"]),
        requests_list=aq.list_assignment_requests(faculty_id=session["faculty_id"]),
        academic_tree=academic_service.get_tree(),
    )


@faculty_bp.route("/classes/request", methods=["POST"])
@role_required("FACULTY")
def request_class():
    try:
        assignment_service.faculty_request(
            session["faculty_id"], request.form.get("section_id"), request.form.get("note")
        )
        flash("Request sent to Admin. You will get access once it is approved.", "success")
    except AssignmentError as e:
        flash(str(e), "error")
    return redirect(url_for("faculty.classes"))


@faculty_bp.route("/classes/<int:section_id>")
@role_required("FACULTY")
def class_detail(section_id):
    # Server-side gate: only ACTIVE assignments open a class context, whatever id is in the URL.
    if not aq.is_faculty_assigned_to_section(session["faculty_id"], section_id):
        abort(403)
    return render_template(
        "faculty/class_detail.html",
        combo=aq.get_combo(section_id),
        students=aq.list_students_for_section(section_id),
        co_faculty=aq.list_faculty_for_section(section_id),
    )
