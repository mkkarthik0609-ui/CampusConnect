from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify

from models import queries
from routes.helpers import role_required
from services import chat_service, file_service
from services.chat_service import ChatAccessError, ChatEditError
from services.file_service import FileValidationError

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


@chat_bp.route("/")
@role_required("STUDENT", "FACULTY")
def list_chats():
    if session["role"] == "STUDENT":
        chats = queries.list_chats_for_student(session["student_id"])
        template = "student/chat_list.html"
    else:
        chats = queries.list_chats_for_faculty(session["faculty_id"])
        template = "faculty/chat_list.html"
    return render_template(template, chats=chats)


@chat_bp.route("/open/<int:faculty_id>")
@role_required("STUDENT")
def open_with_faculty(faculty_id):
    try:
        chat = chat_service.open_chat(session["student_id"], faculty_id, session["user_id"])
    except ChatAccessError as e:
        flash(str(e), "error")
        return redirect(url_for("student.dashboard"))
    return redirect(url_for("chat.view_chat", chat_id=chat["id"]))


@chat_bp.route("/open-student/<int:student_id>")
@role_required("FACULTY")
def open_with_student(student_id):
    try:
        chat = chat_service.open_chat_as_faculty(session["faculty_id"], student_id, session["user_id"])
    except ChatAccessError as e:
        flash(str(e), "error")
        return redirect(url_for("faculty.dashboard"))
    return redirect(url_for("chat.view_chat", chat_id=chat["id"]))


@chat_bp.route("/<int:chat_id>")
@role_required("STUDENT", "FACULTY")
def view_chat(chat_id):
    try:
        chat = chat_service.get_chat_for_participant(chat_id, session["user_id"], session["role"])
    except ChatAccessError as e:
        flash(str(e), "error")
        return redirect(url_for("chat.list_chats"))
    queries.mark_messages_seen(chat_id, session["user_id"])
    messages = chat_service.list_messages(chat_id)

    if session["role"] == "STUDENT":
        other = queries.get_faculty_with_user(chat["faculty_id"])
        template = "student/chat_view.html"
    else:
        other = queries.get_student_with_user(chat["student_id"])
        template = "faculty/chat_view.html"
    return render_template(template, chat=chat, messages=messages, other=other)


@chat_bp.route("/<int:chat_id>/message", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def send_message(chat_id):
    try:
        chat_service.get_chat_for_participant(chat_id, session["user_id"], session["role"])
        text = request.form.get("message_text", "")
        upload = request.files.get("attachment")

        if upload and upload.filename:
            relative_path, ext, original_name = file_service.save_chat_attachment(upload)
            chat_service.send_attachment_message(chat_id, session["user_id"], relative_path, ext, original_name)
        elif text.strip():
            chat_service.send_text_message(chat_id, session["user_id"], text)
        else:
            flash("Please enter a message or attach a file.", "error")
    except (ChatAccessError, ChatEditError, FileValidationError) as e:
        flash(str(e), "error")
    return redirect(url_for("chat.view_chat", chat_id=chat_id))


@chat_bp.route("/message/<int:message_id>/edit", methods=["POST"])
@role_required("STUDENT", "FACULTY")
def edit_message(message_id):
    message = queries.get_message_by_id(message_id)
    if not message:
        flash("Message not found.", "error")
        return redirect(url_for("chat.list_chats"))
    new_text = request.form.get("message_text", "")
    try:
        chat_service.edit_message(message_id, session["user_id"], new_text)
    except ChatEditError as e:
        flash(str(e), "error")
    return redirect(url_for("chat.view_chat", chat_id=message["chat_id"]))
