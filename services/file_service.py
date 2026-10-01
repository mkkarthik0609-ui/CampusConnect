"""Upload validation + storage (framework-agnostic).

The ``upload`` arguments are Starlette/FastAPI ``UploadFile`` objects (anything with ``.filename``
and a file-like ``.file`` - or ``.stream`` - works). Files are validated by extension, size and magic
bytes and stored under a random uuid name; the original name is kept only as sanitised metadata."""
import os
import shutil
import uuid

from werkzeug.utils import secure_filename

from api.settings import get_settings


class FileValidationError(Exception):
    pass


def _extension(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _stream(upload):
    return getattr(upload, "file", None) or upload.stream


def _save(upload, dest_path):
    stream = _stream(upload)
    stream.seek(0)
    with open(dest_path, "wb") as out:
        shutil.copyfileobj(stream, out)


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


def _magic_bytes_ok(upload, ext):
    """Lightweight signature check so a renamed .exe can't pass as .pdf/.png/.docx."""
    stream = _stream(upload)
    stream.seek(0)
    header = stream.read(8)
    stream.seek(0)
    signatures = {
        "pdf": [b"%PDF-"],
        "png": [b"\x89PNG\r\n\x1a\n"],
        "jpg": [b"\xff\xd8\xff"],
        "jpeg": [b"\xff\xd8\xff"],
        "docx": [b"PK\x03\x04"],
    }
    expected = signatures.get(ext)
    if not expected:
        return False
    return any(header.startswith(sig) for sig in expected)


def save_chat_attachment(file_storage):
    if not file_storage or not file_storage.filename:
        raise FileValidationError("No file was provided.")
    ext = _extension(secure_filename(file_storage.filename))
    if ext not in get_settings().allowed_chat_extensions:
        raise FileValidationError("Unsupported file type. Allowed: PDF, PNG, JPG, JPEG, DOCX.")

    stream = _stream(file_storage)
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size > get_settings().max_chat_attachment_size:
        raise FileValidationError("File is too large. Maximum size is 8 MB.")
    if size == 0:
        raise FileValidationError("File is empty.")
    if not _magic_bytes_ok(file_storage, ext):
        raise FileValidationError("File content does not match its extension.")

    generated_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = get_settings().chat_upload_dir
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, generated_name)
    _save(file_storage, dest_path)

    relative_path = os.path.join("chat", generated_name).replace("\\", "/")
    return relative_path, ext, sanitize_original_name(file_storage.filename, ext)


def save_profile_picture(file_storage, role):
    if not file_storage or not file_storage.filename:
        raise FileValidationError("No file was provided.")
    ext = _extension(secure_filename(file_storage.filename))
    if ext not in get_settings().allowed_image_extensions:
        raise FileValidationError("Unsupported image type. Allowed: PNG, JPG, JPEG.")

    stream = _stream(file_storage)
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size > get_settings().max_profile_picture_size:
        raise FileValidationError("Image is too large. Maximum size is 3 MB.")
    if size == 0:
        raise FileValidationError("Image is empty.")
    if not _magic_bytes_ok(file_storage, ext):
        raise FileValidationError("File content does not match its extension.")

    generated_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = (
        get_settings().profile_student_dir
        if role == "STUDENT"
        else get_settings().profile_faculty_dir
    )
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, generated_name)
    _save(file_storage, dest_path)

    subfolder = "students" if role == "STUDENT" else "faculty"
    relative_path = os.path.join("profile", subfolder, generated_name).replace("\\", "/")
    return relative_path
