"""
Keep uploaded files from running script on a site's own domain.

Any file type may be uploaded, but a browser renders some of them as documents that run
script (HTML, SVG, XML, JavaScript). Served from the app's origin, a custom media domain,
or an S3 bucket behind a subdomain, that is stored XSS. Those types are rejected at
upload, and stored objects that a browser would not display safely are served as
downloads (``Content-Disposition: attachment``).
"""

import posixpath

from django.conf import settings

DEFAULT_BLOCKED_EXTENSIONS = (
    ".html",
    ".htm",
    ".xhtml",
    ".xht",
    ".shtml",
    ".svg",
    ".svgz",
    ".xml",
    ".xsl",
    ".xslt",
    ".js",
    ".mjs",
)

# A leading "*" matches a suffix: "*+xml" covers every XML-based type (atom, rss, ...).
DEFAULT_BLOCKED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/xml",
    "application/xml",
    "text/xsl",
    "text/javascript",
    "application/javascript",
    "application/ecmascript",
    "text/ecmascript",
    "*+xml",
)

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


def is_blocked_extension(file_name: str) -> bool:
    blocked = getattr(settings, "BASEAPP_FILES_BLOCKED_EXTENSIONS", DEFAULT_BLOCKED_EXTENSIONS)
    return file_extension(file_name) in {ext.lower() for ext in blocked}


def is_blocked_content_type(content_type: str) -> bool:
    blocked = getattr(
        settings, "BASEAPP_FILES_BLOCKED_CONTENT_TYPES", DEFAULT_BLOCKED_CONTENT_TYPES
    )
    normalized = normalize_content_type(content_type)
    for entry in blocked:
        entry = entry.lower()
        if entry.startswith("*") and normalized.endswith(entry[1:]):
            return True
        if normalized == entry:
            return True
    return False


def is_inline_safe(content_type: str) -> bool:
    """Whether a browser may display this type inline instead of downloading it."""
    normalized = normalize_content_type(content_type)
    return normalized in INLINE_CONTENT_TYPES or normalized.startswith(INLINE_CONTENT_TYPE_PREFIXES)
