from flask import Blueprint, render_template, redirect, url_for, session, request

from routes.helpers import login_required, safe_redirect_back
from services import notification_service as notif

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    items = notif.list_notifications(session["user_id"])
    return render_template("notifications.html", notifications=items)


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    notif.mark_read(notification_id, session["user_id"])
    return safe_redirect_back("notifications.list_notifications")


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    notif.mark_all_read(session["user_id"])
    return safe_redirect_back("notifications.list_notifications")
