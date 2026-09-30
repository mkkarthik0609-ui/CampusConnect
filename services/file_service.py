import os
import uuid
from flask import current_app
from werkzeug.utils import secure_filename


class FileValidationError(Exception):
    pass


def _extension(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def sanitize_original_name(filename, ext):
    """Display/download name stored with an attachment: werkzeug-sanitised, length-capped, and
    never empty. The on-disk name is always a random uuid, independent of this value."""
    cleaned = secure_filename(filename or "")
    if not cleaned or "." not in cleaned:
        cleaned = f"attachment.{ext}"
    stem, _, suffix = cleaned.rpartition(".")
    return f"{stem[:80]}.{suffix}"


def _magic_bytes_ok(file_storage, ext):
    """Lightweight signature check so a renamed .exe can't pass as .pdf/.png/.docx."""
    header = file_storage.stream.read(8)
    file_storage.stream.seek(0)
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
    if ext not in current_app.config["ALLOWED_CHAT_EXTENSIONS"]:
        raise FileValidationError("Unsupported file type. Allowed: PDF, PNG, JPG, JPEG, DOCX.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > current_app.config["MAX_CHAT_ATTACHMENT_SIZE"]:
        raise FileValidationError("File is too large. Maximum size is 8 MB.")
    if size == 0:
        raise FileValidationError("File is empty.")
    if not _magic_bytes_ok(file_storage, ext):
        raise FileValidationError("File content does not match its extension.")

    generated_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = current_app.config["CHAT_UPLOAD_DIR"]
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, generated_name)
    file_storage.save(dest_path)

    relative_path = os.path.join("chat", generated_name).replace("\\", "/")
    return relative_path, ext, sanitize_original_name(file_storage.filename, ext)


def save_profile_picture(file_storage, role):
    if not file_storage or not file_storage.filename:
        raise FileValidationError("No file was provided.")
    ext = _extension(secure_filename(file_storage.filename))
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise FileValidationError("Unsupported image type. Allowed: PNG, JPG, JPEG.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > current_app.config["MAX_PROFILE_PICTURE_SIZE"]:
        raise FileValidationError("Image is too large. Maximum size is 3 MB.")
    if size == 0:
        raise FileValidationError("Image is empty.")
    if not _magic_bytes_ok(file_storage, ext):
        raise FileValidationError("File content does not match its extension.")

    generated_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = (
        current_app.config["PROFILE_STUDENT_DIR"]
        if role == "STUDENT"
        else current_app.config["PROFILE_FACULTY_DIR"]
    )
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, generated_name)
    file_storage.save(dest_path)

    subfolder = "students" if role == "STUDENT" else "faculty"
    relative_path = os.path.join("profile", subfolder, generated_name).replace("\\", "/")
    return relative_path
