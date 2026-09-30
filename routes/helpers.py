from functools import wraps
from urllib.parse import urlsplit

from flask import session, redirect, url_for, abort, flash, request


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def flash_errors(error):
    flash(str(error), "error")


def safe_referrer_path():
    """Return the same-host path(+query) of the Referer header, or None if it is missing or points
    anywhere else. Only a local path is ever returned, never a scheme/host."""
    referrer = request.referrer
    if not referrer:
        return None
    try:
        parts = urlsplit(referrer)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    if parts.netloc.lower() != (request.host or "").lower():
        return None
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return None
    return path + (f"?{parts.query}" if parts.query else "")


def safe_redirect_back(default_endpoint="index", **values):
    """Redirect to the page the user came from, but only if the Referer is on this same host;
    otherwise go to `default_endpoint`. Prevents open redirects via a forged Referer."""
    target = safe_referrer_path()
    if target:
        return redirect(target)
    return redirect(url_for(default_endpoint, **values))
