"""
Which files may be uploaded, and how they are served.

Only extensions on an allowlist are accepted, so every uploadable type is a deliberate
choice. The type a file is stored and served with comes from that list, never from the
client: a declared ``text/html`` on ``photo.png`` would otherwise be served as a page and
run script on the site's domain (stored XSS), including from an S3 bucket behind a
subdomain. Stored objects that a browser would not display safely are served as downloads
(``Content-Disposition: attachment``).
"""

import mimetypes
import posixpath
from typing import Mapping

from django.conf import settings

# Extension -> the content type the file is stored and served with. No SVG, HTML, XML or
# JavaScript: browsers run those as pages.
DEFAULT_ALLOWED_FILE_TYPES: Mapping[str, str] = {
    # Images
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    # Video
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".3gp": "video/3gpp",
    # Audio
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    # Documents
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    # Archives
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
}

# Types a browser displays without running page script; anything else is a download.
INLINE_CONTENT_TYPES = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
    "image/bmp",
    "application/pdf",
)
INLINE_CONTENT_TYPE_PREFIXES = ("video/", "audio/")


def file_extension(file_name: str) -> str:
    """Lower-cased extension of the base name, ignoring trailing dots and spaces."""
    basename = posixpath.basename((file_name or "").replace("\\", "/")).rstrip(". ")
    return posixpath.splitext(basename)[1].lower()


def normalize_content_type(content_type: str) -> str:
    """``"Text/HTML; charset=utf-8"`` -> ``"text/html"``."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def allowed_file_types() -> dict[str, str]:
    """
    ``BASEAPP_FILES_ALLOWED_FILE_TYPES`` as extension -> content type. A dict is used as
    is; a list of extensions gets each type from ``mimetypes``.
    """
    configured = getattr(settings, "BASEAPP_FILES_ALLOWED_FILE_TYPES", DEFAULT_ALLOWED_FILE_TYPES)
    if isinstance(configured, Mapping):
        return {ext.lower(): content_type for ext, content_type in configured.items()}
    return {
        ext.lower(): mimetypes.guess_type(f"file{ext}")[0] or "application/octet-stream"
        for ext in configured
    }


def allowed_content_type(file_name: str) -> str | None:
    """The content type to store ``file_name`` with, or None when its extension is not allowed."""
    extension = file_extension(file_name)
    if not extension:
        return None
    return allowed_file_types().get(extension)


def is_inline_safe(content_type: str) -> bool:
    """Whether a browser may display this type inline instead of downloading it."""
    normalized = normalize_content_type(content_type)
    return normalized in INLINE_CONTENT_TYPES or normalized.startswith(INLINE_CONTENT_TYPE_PREFIXES)
