from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from models import queries
from models import academic_queries as aq
from routes.helpers import role_required, safe_redirect_back
from services import supporting_service
from services.supporting_service import SupportingError

supporting_bp = Blueprint("supporting", __name__, url_prefix="/supporting")


@supporting_bp.route("/faculty/search")
@role_required("STUDENT")
def search_faculty():
    query = request.args.get("q", "").strip()
    results = queries.search_faculty(query) if query else []
    return render_template("student/faculty_search.html", results=results, query=query)


@supporting_bp.route("/faculty/<int:faculty_id>/request", methods=["POST"])
@role_required("STUDENT")
def request_faculty(faculty_id):
    try:
        supporting_service.student_request_faculty(session["student_id"], faculty_id)
        flash("Supporting-faculty request sent.", "success")
    except SupportingError as e:
        flash(str(e), "error")
    return safe_redirect_back("student.dashboard")


@supporting_bp.route("/student/search")
@role_required("FACULTY")
def search_student():
    query = request.args.get("q", "").strip()
    results = aq.search_students_in_faculty_scope(session["faculty_id"], query) if query else []
    return render_template("faculty/student_search.html", results=results, query=query)


@supporting_bp.route("/student/<int:student_id>/request", methods=["POST"])
@role_required("FACULTY")
def request_student(student_id):
    try:
        supporting_service.faculty_request_student(session["faculty_id"], student_id)
        flash("Supporting-student request sent.", "success")
    except SupportingError as e:
        flash(str(e), "error")
    return safe_redirect_back("faculty.dashboard")


@supporting_bp.route("/<int:rel_id>/accept", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def accept(rel_id):
    try:
        supporting_service.respond_to_request(rel_id, session["user_id"], session["role"], True)
        flash("Request accepted.", "success")
    except SupportingError as e:
        flash(str(e), "error")
    return safe_redirect_back("index")


@supporting_bp.route("/<int:rel_id>/reject", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def reject(rel_id):
    try:
        supporting_service.respond_to_request(rel_id, session["user_id"], session["role"], False)
        flash("Request rejected.", "info")
    except SupportingError as e:
        flash(str(e), "error")
    return safe_redirect_back("index")
