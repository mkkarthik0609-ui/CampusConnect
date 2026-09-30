"""Admin-only management of the academic hierarchy, faculty assignments and class requests."""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from models import academic_queries as aq
from models import queries
from routes.helpers import role_required
from services import academic_service, assignment_service
from services.academic_service import AcademicError
from services.assignment_service import AssignmentError

admin_academic_bp = Blueprint("admin_academic", __name__, url_prefix="/admin")


def _back(endpoint="admin_academic.academics", **values):
    return redirect(url_for(endpoint, **values))


# ---------- academic structure ----------

@admin_academic_bp.route("/academics")
@role_required("ADMIN")
def academics():
    return render_template("admin/academics.html", tree=academic_service.get_tree(active_only=False))


def _structure_action(fn, success):
    try:
        fn()
        flash(success, "success")
    except AcademicError as e:
        flash(str(e), "error")
    return _back()


@admin_academic_bp.route("/academics/branch", methods=["POST"])
@role_required("ADMIN")
def add_branch():
    return _structure_action(lambda: academic_service.add_branch(request.form.get("name")), "Branch added.")


@admin_academic_bp.route("/academics/department", methods=["POST"])
@role_required("ADMIN")
def add_department():
    return _structure_action(
        lambda: academic_service.add_department(request.form.get("branch_id", type=int), request.form.get("name")),
        "Department added.",
    )


@admin_academic_bp.route("/academics/year", methods=["POST"])
@role_required("ADMIN")
def add_year():
    return _structure_action(
        lambda: academic_service.add_year(request.form.get("department_id", type=int), request.form.get("name")),
        "Academic year added.",
    )


@admin_academic_bp.route("/academics/sections", methods=["POST"])
@role_required("ADMIN")
def add_sections():
    return _structure_action(
        lambda: academic_service.add_sections(request.form.get("year_id", type=int), request.form.get("names")),
        "Section(s) added.",
    )


@admin_academic_bp.route("/academics/<level>/<int:row_id>/active", methods=["POST"])
@role_required("ADMIN")
def set_active(level, row_id):
    active = request.form.get("active") == "1"
    return _structure_action(
        lambda: academic_service.set_active(level, row_id, active),
        "Item reactivated." if active else "Item deactivated. It is hidden from new registrations.",
    )


@admin_academic_bp.route("/academics/<level>/<int:row_id>/delete", methods=["POST"])
@role_required("ADMIN")
def delete_item(level, row_id):
    return _structure_action(lambda: academic_service.delete_unused(level, row_id), "Item deleted.")


# ---------- faculty assignments ----------

@admin_academic_bp.route("/assignments")
@role_required("ADMIN")
def assignments():
    faculty_rows = []
    for f in queries.list_all_faculty_admin():
        faculty_rows.append({
            "row": f,
            "assignments": aq.list_assignments_for_faculty(f["id"]),
            "pending": aq.list_assignment_requests(status="PENDING", faculty_id=f["id"]),
        })
    return render_template(
        "admin/assignments.html", faculty_rows=faculty_rows,
        academic_tree=academic_service.get_tree(),
        pending_count=aq.count_pending_assignment_requests(),
    )


@admin_academic_bp.route("/assignments/assign", methods=["POST"])
@role_required("ADMIN")
def assign():
    try:
        combo = assignment_service.admin_assign(
            request.form.get("faculty_id", type=int), request.form.get("section_id"), session["user_id"]
        )
        flash(f"Assigned to {academic_service.combo_label(combo)}.", "success")
    except AssignmentError as e:
        flash(str(e), "error")
    return _back("admin_academic.assignments")


@admin_academic_bp.route("/assignments/<int:assignment_id>/remove", methods=["POST"])
@role_required("ADMIN")
def remove_assignment(assignment_id):
    try:
        combo = assignment_service.admin_remove(assignment_id, session["user_id"])
        flash(f"Assignment removed: {academic_service.combo_label(combo)}.", "info")
    except AssignmentError as e:
        flash(str(e), "error")
    return _back("admin_academic.assignments")


# ---------- faculty requests to join a class ----------

@admin_academic_bp.route("/assignment-requests")
@role_required("ADMIN")
def assignment_requests():
    return render_template("admin/assignment_requests.html", requests_list=aq.list_assignment_requests())


@admin_academic_bp.route("/assignment-requests/<int:request_id>/decide", methods=["POST"])
@role_required("ADMIN")
def decide_assignment_request(request_id):
    approve = request.form.get("decision") == "approve"
    try:
        status = assignment_service.decide_request(request_id, session["user_id"], approve)
        flash(f"Request {status.lower()}.", "success")
    except AssignmentError as e:
        flash(str(e), "error")
    return _back("admin_academic.assignment_requests")


# ---------- class directory: who is assigned to each combination ----------

@admin_academic_bp.route("/classes")
@role_required("ADMIN")
def classes():
    directory = []
    for combo in aq.list_combos_with_counts():
        directory.append({
            "combo": combo,
            "faculty": aq.list_faculty_for_section(combo["section_id"]),
        })
    return render_template("admin/classes.html", directory=directory)


@admin_academic_bp.route("/classes/<int:section_id>")
@role_required("ADMIN")
def class_detail(section_id):
    combo = aq.get_combo(section_id)
    if not combo:
        flash("Class not found.", "error")
        return _back("admin_academic.classes")
    return render_template(
        "admin/class_detail.html", combo=combo,
        faculty=aq.list_faculty_for_section(section_id),
        students=aq.list_students_admin(section_id),
    )


# ---------- student registrations ----------

@admin_academic_bp.route("/students/<int:student_id>/remove-registration", methods=["POST"])
@role_required("ADMIN")
def remove_student_registration(student_id):
    student = queries.get_student_with_user(student_id)
    if not student:
        flash("Student not found.", "error")
    elif aq.archive_student_registration(student_id):
        flash(
            f"Registration for {student['full_name']} ({student['usn']}) removed. "
            "They can now register again with the correct class.", "success",
        )
    else:
        flash("This registration was already removed.", "info")
    return redirect(url_for("admin.students"))
