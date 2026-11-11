"""GET /uploads/{path} - authorised file serving.

* ``profile/students|faculty/<file>``: any signed-in user (pictures show up in search / chat lists).
* ``chat/<file>``: only the two chat participants (subject to the normal chat access rules). Admins get 403.
* anything else: 404. Always ``nosniff``; non-images are sent as attachments.
"""
import os
import posixpath
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.deps import CurrentUser, get_current_user
from api.errors import ApiError
from models import security_queries
from services import chat_service, storage
from services.chat_service import ChatAccessError

router = APIRouter()

_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}


def normalise_upload_path(filename):
    """Clean forward-slash relative path, or None if it tries to escape / is malformed."""
    if not filename or "\x00" in filename or "\\" in filename:
        return None
    norm = posixpath.normpath(filename)
    if norm.startswith("/") or norm == ".." or norm.startswith("../") or norm != filename:
        return None
    return norm


def _authorise_chat_attachment(rel_path, user):
    """Returns the original file name for the download header."""
    info = security_queries.get_chat_for_attachment(rel_path)
    if info is None:
        raise ApiError(404, "not_found", "File not found.")
    role = user["role"]
    if role not in ("STUDENT", "FACULTY") or user["id"] not in (
        info["student_user_id"], info["faculty_user_id"]
    ):
        raise ApiError(403, "forbidden", "You do not have access to this file.")
    try:
        chat_service.get_chat_for_participant(info["chat_id"], user["id"], role)
    except ChatAccessError:
        raise ApiError(403, "forbidden", "You do not have access to this file.")
    return info["original_name"]


@router.get("/uploads/{filename:path}", include_in_schema=False)
def uploaded_file(filename: str, user: CurrentUser = Depends(get_current_user)):
    rel = normalise_upload_path(filename)
    if rel is None:
        raise ApiError(404, "not_found", "File not found.")
    parts = rel.split("/")

    original_name = None
    if len(parts) == 3 and parts[0] == "profile" and parts[1] in ("students", "faculty"):
        cache = "private, max-age=300"
    elif len(parts) == 2 and parts[0] == "chat":
        original_name = _authorise_chat_attachment(rel, user)
        cache = "private, no-store"
    else:
        raise ApiError(404, "not_found", "File not found.")

    blob = storage.get(rel)
    if blob is None:
        raise ApiError(404, "not_found", "File not found.")
    data, content_type = blob
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": cache}
    if ext in _IMAGE_EXTENSIONS:
        headers["Content-Disposition"] = "inline"
    else:
        name = (original_name or os.path.basename(rel)).replace('"', "").replace("\r", "").replace("\n", "")
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name)}"
    return Response(content=data, media_type=content_type, headers=headers)
