from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from models import queries
from models import academic_queries as aq
from routes.helpers import role_required
from services import auth_service, permission_service
from services.auth_service import ValidationError
from services.permission_service import PermissionError_

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@role_required("ADMIN")
def dashboard():
    students = queries.list_all_students_admin()
    faculty = queries.list_all_faculty_admin()
    meetings = queries.list_all_meetings_admin()
    permission_requests = queries.list_all_permission_requests_admin()
    return render_template(
        "admin/dashboard.html",
        student_count=len(students), faculty_count=len(faculty),
        meeting_count=len(meetings),
        pending_permission_count=sum(1 for p in permission_requests if p["status"] == "PENDING"),
        pending_assignment_count=aq.count_pending_assignment_requests(),
        class_count=len(aq.list_combos(active_only=True)),
        unmapped_student_count=sum(1 for s in students if s["section_id"] is None),
    )


@admin_bp.route("/students")
@role_required("ADMIN")
def students():
    return render_template("admin/students.html", students=aq.list_students_admin())


@admin_bp.route("/faculty")
@role_required("ADMIN")
def faculty():
    faculty_list = queries.list_all_faculty_admin()
    enriched = []
    for f in faculty_list:
        enriched.append({
            "row": f,
            "subjects": queries.get_faculty_subjects(f["id"]),
            "classes": aq.list_assignments_for_faculty(f["id"]),
        })
    return render_template("admin/faculty.html", faculty_list=enriched)


@admin_bp.route("/meetings")
@role_required("ADMIN")
def meetings():
    return render_template("admin/meetings.html", meetings=queries.list_all_meetings_admin())


@admin_bp.route("/chats")
@role_required("ADMIN")
def chats():
    return render_template("admin/chats.html", chats=queries.list_all_chats_admin())


@admin_bp.route("/chats/<int:chat_id>")
@role_required("ADMIN")
def chat_detail(chat_id):
    chat = queries.get_chat_by_id(chat_id)
    if not chat:
        flash("Conversation not found.", "error")
        return redirect(url_for("admin.chats"))
    messages = queries.list_messages_for_chat(chat_id)
    student = queries.get_student_with_user(chat["student_id"])
    faculty = queries.get_faculty_with_user(chat["faculty_id"])
    return render_template("admin/chat_detail.html", chat=chat, messages=messages, student=student, faculty=faculty)


@admin_bp.route("/permission-requests")
@role_required("ADMIN")
def permission_requests():
    return render_template("admin/permission_requests.html", requests_list=queries.list_all_permission_requests_admin())


@admin_bp.route("/permission-requests/<int:request_id>/decide", methods=["POST"])
@role_required("ADMIN")
def decide_permission_request(request_id):
    approve = request.form.get("decision") == "approve"
    try:
        permission_service.decide_permission_request(request_id, session["user_id"], approve)
        flash("Request reviewed.", "success")
    except PermissionError_ as e:
        flash(str(e), "error")
    return redirect(url_for("admin.permission_requests"))


@admin_bp.route("/admins")
@role_required("ADMIN")
def admins():
    return render_template("admin/admins.html", admins=queries.list_all_admins())


@admin_bp.route("/admins/add", methods=["POST"])
@role_required("ADMIN")
def add_admin():
    try:
        full_name = auth_service.validate_required(request.form.get("full_name"), "Full name")
        email = auth_service.validate_email(request.form.get("email"), "Email")
        password = request.form.get("password")
        if password != request.form.get("confirm_password"):
            raise ValidationError("Passwords do not match.")
        if queries.get_user_by_email(email):
            raise ValidationError("An account with this email already exists.")
        password_hash = auth_service.hash_password(password)
        queries.create_user("ADMIN", email, password_hash, full_name)
        flash("Admin account created.", "success")
    except ValidationError as e:
        flash(str(e), "error")
    return redirect(url_for("admin.admins"))
