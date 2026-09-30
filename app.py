import logging
import os
import posixpath
import sys

from flask import (
    Flask, session, redirect, url_for, send_from_directory, abort, render_template, request, jsonify,
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, validate_config
from models.database import init_db, register_db, get_db
from models import queries
from models import security_queries

CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "script-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}


def _configure_logging(app):
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    validate_config(app.config)
    _configure_logging(app)

    if app.config.get("TRUST_PROXY"):
        # Behind Render (and possibly a Vercel rewrite proxy): trust forwarded client IP/proto/host.
        hops = max(1, int(app.config.get("TRUST_PROXY_HOPS") or 1))
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=1, x_host=1)

    CSRFProtect(app)  # per-app instance; tests turn it off with WTF_CSRF_ENABLED=False
    register_db(app)

    for path in (
        app.config["UPLOAD_ROOT"], app.config["PROFILE_STUDENT_DIR"],
        app.config["PROFILE_FACULTY_DIR"], app.config["CHAT_UPLOAD_DIR"],
    ):
        os.makedirs(path, exist_ok=True)
    db_dir = os.path.dirname(os.path.abspath(app.config["DATABASE_PATH"]))
    if app.config["DATABASE_PATH"] != ":memory:":
        os.makedirs(db_dir, exist_ok=True)

    init_db(app)  # CREATE TABLE IF NOT EXISTS is idempotent, safe to run every start
    with app.app_context():
        security_queries.ensure_schema()

    from routes.auth import auth_bp
    from routes.student import student_bp
    from routes.faculty import faculty_bp
    from routes.admin import admin_bp
    from routes.admin_academic import admin_academic_bp
    from routes.chat import chat_bp
    from routes.meetings import meetings_bp
    from routes.supporting import supporting_bp
    from routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_academic_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(supporting_bp)
    app.register_blueprint(notifications_bp)

    from services import session_service
    app.before_request(session_service.enforce_session)

    @app.route("/")
    def index():
        if "user_id" in session:
            role = session.get("role")
            if role == "STUDENT":
                return redirect(url_for("student.dashboard"))
            if role == "FACULTY":
                return redirect(url_for("faculty.dashboard"))
            if role == "ADMIN":
                return redirect(url_for("admin.dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/healthz")
    def healthz():
        """Unauthenticated liveness/readiness probe (Render health check)."""
        try:
            get_db().execute("SELECT 1").fetchone()
        except Exception:  # noqa: BLE001 - any DB failure means "not healthy"
            app.logger.exception("Health check failed")
            return jsonify({"status": "error"}), 503
        return jsonify({"status": "ok"})

    @app.route("/academic/tree.json")
    def academic_tree():
        """Read-only, active-only Branch > Department > Year > Section options for signup / request forms."""
        from services import academic_service
        return jsonify(academic_service.get_tree())

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        if "user_id" not in session:
            abort(403)
        rel = _normalise_upload_path(filename)
        if rel is None:
            abort(404)
        parts = rel.split("/")

        if len(parts) == 3 and parts[0] == "profile" and parts[1] in ("students", "faculty"):
            # Profile pictures are visible to any signed-in user (they appear in search/chat lists).
            original_name = None
            cache = "private, max-age=300"
        elif len(parts) == 2 and parts[0] == "chat":
            original_name = _authorise_chat_attachment(rel)
            cache = "private, no-store"
        else:
            abort(404)

        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        is_image = ext in _IMAGE_EXTENSIONS
        response = send_from_directory(
            app.config["UPLOAD_ROOT"], rel,
            as_attachment=not is_image,
            download_name=original_name or None,
            max_age=None,
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = cache
        return response

    @app.context_processor
    def inject_globals():
        from services import notification_service as notif
        unread_notifications = 0
        unread_messages = 0
        if "user_id" in session:
            unread_notifications = notif.get_unread_count(session["user_id"])
            unread_messages = queries.get_total_unread_for_user(session["user_id"], session.get("role"))
        return dict(
            current_user_name=session.get("full_name"),
            current_user_role=session.get("role"),
            current_theme=session.get("theme", "light"),
            unread_notifications=unread_notifications,
            unread_messages=unread_messages,
        )

    @app.after_request
    def set_security_headers(response):
        h = response.headers
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if app.config.get("IS_PRODUCTION") or request.is_secure:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if "user_id" in session and response.mimetype == "text/html":
            h["Cache-Control"] = "no-store"
            h["Pragma"] = "no-cache"
        return response

    _register_error_handlers(app)
    _bootstrap_admin_if_requested(app)
    _register_scheduler(app)

    return app


def _normalise_upload_path(filename):
    """Return a clean forward-slash relative path, or None if it tries to escape / is malformed."""
    if not filename or "\x00" in filename or "\\" in filename:
        return None
    norm = posixpath.normpath(filename)
    if norm.startswith("/") or norm == ".." or norm.startswith("../") or norm != filename:
        return None
    return norm


def _authorise_chat_attachment(rel_path):
    """Chat files are readable only by the two chat participants (subject to the normal chat access
    rules) or an ADMIN. Returns the original file name for the download header."""
    from services import chat_service
    from services.chat_service import ChatAccessError
    info = security_queries.get_chat_for_attachment(rel_path)
    if info is None:
        abort(404)
    role = session.get("role")
    if role == "ADMIN":
        return info["original_name"]
    if role not in ("STUDENT", "FACULTY") or session.get("user_id") not in (
        info["student_user_id"], info["faculty_user_id"]
    ):
        abort(403)
    try:
        chat_service.get_chat_for_participant(info["chat_id"], session["user_id"], role)
    except ChatAccessError:
        abort(403)
    return info["original_name"]


def _render_error(code, message):
    try:
        return render_template("errors.html", code=code, message=message), code
    except Exception:  # noqa: BLE001 - never let the error page itself fail
        return f"<h1>{code}</h1><p>{message}</p>", code


def _register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def csrf_error(e):
        app.logger.warning("CSRF validation failed on %s %s: %s", request.method, request.path, e.description)
        return _render_error(
            400, "Your form expired or could not be verified. Please go back, reload the page and try again."
        )

    @app.errorhandler(400)
    def bad_request(e):
        return _render_error(400, "The request could not be understood.")

    @app.errorhandler(403)
    def forbidden(e):
        return _render_error(403, "You do not have permission to view this page.")

    @app.errorhandler(404)
    def not_found(e):
        return _render_error(404, "Page not found.")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _render_error(405, "That action is not allowed on this page.")

    @app.errorhandler(413)
    def too_large(e):
        return _render_error(413, "The uploaded file is too large.")

    @app.errorhandler(429)
    def too_many(e):
        return _render_error(429, "Too many requests. Please wait a moment and try again.")

    @app.errorhandler(500)
    def server_error(e):
        return _render_error(500, "Something went wrong on our end.")

    @app.errorhandler(Exception)
    def unhandled(e):
        if isinstance(e, HTTPException):
            return _render_error(e.code or 500, "Something went wrong with that request.")
        app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
        return _render_error(500, "Something went wrong on our end.")


def _bootstrap_admin_if_requested(app):
    """BOOTSTRAP_ADMIN=1 creates the admin from ADMIN_NAME/ADMIN_EMAIL/ADMIN_PASSWORD when absent
    (idempotent; used on hosts without a shell). Secrets are never logged."""
    if not app.config.get("BOOTSTRAP_ADMIN") or app.config.get("TESTING"):
        return
    from create_admin import bootstrap_from_env
    with app.app_context():
        try:
            status = bootstrap_from_env()
            app.logger.info("Admin bootstrap: %s", status)
        except Exception as exc:  # noqa: BLE001 - misconfiguration must not stop the site
            app.logger.error("Admin bootstrap failed: %s", exc)


def _register_scheduler(app):
    if app.config.get("TESTING") or not app.config.get("ENABLE_SCHEDULER", True):
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        from services.meeting_service import send_due_reminders

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=lambda: send_due_reminders(app),
            trigger="interval",
            minutes=app.config["REMINDER_INTERVAL_MINUTES"],
            id="meeting_reminders",
            replace_existing=True,
        )
        scheduler.start()


app = create_app()

if __name__ == "__main__":
    # Debug is opt-in via FLASK_DEBUG and is never honoured in production.
    _debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    if app.config.get("IS_PRODUCTION"):
        _debug = False
    app.run(debug=_debug, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
