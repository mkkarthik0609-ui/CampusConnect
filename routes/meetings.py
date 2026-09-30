from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from models import queries
from routes.helpers import role_required
from services import meeting_service
from services.meeting_service import MeetingError

meetings_bp = Blueprint("meetings", __name__, url_prefix="/meetings")


@meetings_bp.route("/request/<int:faculty_id>", methods=["GET", "POST"])
@role_required("STUDENT")
def request_meeting(faculty_id):
    faculty = queries.get_faculty_with_user(faculty_id)
    if not faculty:
        flash("Faculty not found.", "error")
        return redirect(url_for("student.dashboard"))
    if request.method == "POST":
        try:
            meeting_service.request_meeting(
                session["student_id"], faculty_id,
                request.form.get("reason"), request.form.get("details"),
            )
            flash("Meeting request sent.", "success")
            return redirect(url_for("meetings.list_meetings"))
        except MeetingError as e:
            flash(str(e), "error")
    return render_template("student/meeting_request.html", faculty=faculty)


@meetings_bp.route("/")
@role_required("STUDENT", "FACULTY")
def list_meetings():
    status_filter = request.args.get("status")
    statuses = [status_filter] if status_filter else None
    if session["role"] == "STUDENT":
        meetings = queries.list_meetings_for_student(session["student_id"], statuses)
        template = "student/meetings.html"
    else:
        meetings = queries.list_meetings_for_faculty(session["faculty_id"], statuses)
        template = "faculty/meetings.html"
    return render_template(template, meetings=meetings, status_filter=status_filter)


@meetings_bp.route("/<int:meeting_id>/respond", methods=["POST"])
@role_required("FACULTY")
def respond(meeting_id):
    accept = request.form.get("decision") == "accept"
    try:
        meeting_service.respond_to_meeting(
            meeting_id, session["faculty_id"], accept,
            request.form.get("faculty_response"), request.form.get("meeting_time_text"),
        )
        flash("Response recorded.", "success")
    except MeetingError as e:
        flash(str(e), "error")
    return redirect(url_for("meetings.list_meetings"))


@meetings_bp.route("/<int:meeting_id>/cancel", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def cancel(meeting_id):
    try:
        meeting_service.cancel_meeting(
            meeting_id, session["user_id"], session["role"], request.form.get("reason")
        )
        flash("Meeting cancelled.", "info")
    except MeetingError as e:
        flash(str(e), "error")
    return redirect(url_for("meetings.list_meetings"))


@meetings_bp.route("/<int:meeting_id>/complete", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def complete(meeting_id):
    try:
        meeting_service.complete_meeting(meeting_id, session["user_id"], session["role"])
        flash("Meeting marked completed.", "success")
    except MeetingError as e:
        flash(str(e), "error")
    return redirect(url_for("meetings.list_meetings"))
