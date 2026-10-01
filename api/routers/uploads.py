"""GET /uploads/{path} - authorised file serving.

* ``profile/students|faculty/<file>``: any signed-in user (pictures show up in search / chat lists).
* ``chat/<file>``: only the two chat participants (subject to the normal chat access rules) or an ADMIN.
* anything else: 404. Always ``nosniff``; non-images are sent as attachments.
"""
import os
import posixpath

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import CurrentUser, get_current_user
from api.errors import ApiError
from api.settings import get_settings
from models import security_queries
from services import chat_service
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
    if role == "ADMIN":
        return info["original_name"]
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

    root = os.path.realpath(get_settings().upload_root)
    full = os.path.realpath(os.path.join(root, *parts))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        raise ApiError(404, "not_found", "File not found.")

    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    is_image = ext in _IMAGE_EXTENSIONS
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": cache}
    if is_image:
        return FileResponse(full, content_disposition_type="inline", headers=headers)
    return FileResponse(full, filename=original_name or os.path.basename(full),
                        content_disposition_type="attachment", headers=headers)
