"""Upload validation + storage (framework-agnostic).

The ``upload`` arguments are Starlette/FastAPI ``UploadFile`` objects (anything with ``.filename``
and a file-like ``.file`` - or ``.stream`` - works). Files are validated by extension, size and magic
bytes and stored under a random uuid name; the original name is kept only as sanitised metadata."""
import io
import uuid
import zipfile

from werkzeug.utils import secure_filename

from api.settings import get_settings
from api.db import get_db
from services import storage


MAX_PIXELS = 25_000_000


class FileValidationError(Exception):
    pass


def _extension(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _stream(upload):
    return getattr(upload, "file", None) or upload.stream


def upload_url(relative_path):
    """Public (auth-checked by the uploads router) URL of a stored upload, or None when there is no file."""
    if not relative_path:
        return None
    return "/uploads/" + str(relative_path).lstrip("/")


def sanitize_original_name(filename, ext):
    """Display/download name stored with an attachment: werkzeug-sanitised, length-capped, and
    never empty. The on-disk name is always a random uuid, independent of this value."""
    cleaned = secure_filename(filename or "")
    if not cleaned or "." not in cleaned:
        cleaned = f"attachment.{ext}"
    stem, _, suffix = cleaned.rpartition(".")
    return f"{stem[:80]}.{suffix}"


def _read_bounded(upload, limit):
    stream = _stream(upload)
    stream.seek(0)
    data = stream.read(limit + 1)
    stream.seek(0)
    return data


def _content_ok(data, ext):
    """Signature + structure check so a renamed .exe / polyglot cannot pass as .pdf/.png/.jpg/.docx."""
    if ext == "pdf":
        return data.startswith(b"%PDF-") and b"%%EOF" in data[-2048:]
    if ext in ("png", "jpg", "jpeg"):
        sig = b"\x89PNG\r\n\x1a\n" if ext == "png" else b"\xff\xd8\xff"
        if not data.startswith(sig):
            return False
        try:  # must actually decode as an image of the claimed kind
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > MAX_PIXELS:  # decompression-bomb guard (browsers decode these too)
                    return False
                im.verify()
                return im.format == ("PNG" if ext == "png" else "JPEG")
        except Exception:  # noqa: BLE001 - any decoder failure means "not a valid image"
            return False
    if ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                return "[Content_Types].xml" in names and any(n.startswith("word/") for n in names)
        except zipfile.BadZipFile:
            return False
    return False


def _validated_bytes(file_storage, allowed, max_size, too_large, bad_type, empty):
    if not file_storage or not file_storage.filename:
        raise FileValidationError("No file was provided.")
    ext = _extension(secure_filename(file_storage.filename))
    if ext not in allowed:
        raise FileValidationError(bad_type)
    data = _read_bounded(file_storage, max_size)
    if len(data) > max_size:
        raise FileValidationError(too_large)
    if not data:
        raise FileValidationError(empty)
    if not _content_ok(data, ext):
        raise FileValidationError("File content does not match its extension.")
    return ext, data


def save_chat_attachment(file_storage):
    cfg = get_settings()
    ext, data = _validated_bytes(
        file_storage, cfg.allowed_chat_extensions, cfg.max_chat_attachment_size,
        "File is too large. Maximum size is 8 MB.",
        "Unsupported file type. Allowed: PDF, PNG, JPG, JPEG, DOCX.", "File is empty.")
    relative_path = f"chat/{uuid.uuid4().hex}.{ext}"
    storage.put(relative_path, data)  # same transaction as the message row that will reference it
    return relative_path, ext, sanitize_original_name(file_storage.filename, ext)


def save_profile_picture(file_storage, role):
    cfg = get_settings()
    ext, data = _validated_bytes(
        file_storage, cfg.allowed_image_extensions, cfg.max_profile_picture_size,
        "Image is too large. Maximum size is 3 MB.",
        "Unsupported image type. Allowed: PNG, JPG, JPEG.", "Image is empty.")
    subfolder = "students" if role == "STUDENT" else "faculty"
    relative_path = f"profile/{subfolder}/{uuid.uuid4().hex}.{ext}"
    storage.put(relative_path, data)
    return relative_path


def delete_chat_attachment(relative_path):
    """Remove a stored chat attachment (``chat/<uuid>.<ext>``) once its message is unsent. Only keys under
    ``chat/`` are ever removed; commits with the caller's transaction."""
    if relative_path and str(relative_path).startswith("chat/"):
        storage.delete(str(relative_path))
        get_db().commit()
