"""
Building the HTTP response of a protected download.

Every response carries ``nosniff``, ``no-referrer`` and a non-caching ``Cache-Control``, and
is an attachment unless the type is one browsers display without running script, or the
caller supplies a Content-Security-Policy for it. An inline response always carries a CSP.
"""

import posixpath
import unicodedata
from typing import TYPE_CHECKING, Optional, Union

from django.core.files import File as DjangoFile
from django.db import models
from django.db.models.fields.files import FieldFile
from django.http import FileResponse, HttpRequest, HttpResponse
from django.utils.http import content_disposition_header

from ..content_safety import is_inline_safe

if TYPE_CHECKING:
    from .registry import ProtectedFileSpec

DEFAULT_CACHE_CONTROL = "private, no-store"
DEFAULT_INLINE_CSP = "sandbox; default-src 'none'"
FALLBACK_FILENAME = "download"

Content = Union[FieldFile, DjangoFile, bytes]


def safe_filename(name: Optional[str], fallback: str = FALLBACK_FILENAME) -> str:
    """
    ``name`` reduced to a base name fit for ``Content-Disposition``: path components and
    control characters (CR/LF included, which would otherwise split the header) are removed.
    """
    name = posixpath.basename((name or "").replace("\\", "/"))
    name = "".join(char for char in name if unicodedata.category(char) != "Cc")
    name = name.strip().rstrip(". ")
    return name or fallback


def protected_content_response(
    content: Content,
    *,
    filename: str,
    content_type: str,
    disposition: str = "attachment",
    csp: Optional[str] = None,
    cache_control: str = DEFAULT_CACHE_CONTROL,
) -> HttpResponse:
    """
    Serve ``content`` (a stored ``FieldFile``, any Django ``File``, or bytes) with the
    protected-download headers. Usable for content that is not a registered field, such as
    an attachment kept elsewhere; access must have been checked by the caller.
    """
    if isinstance(content, (bytes, bytearray)):
        response = HttpResponse(bytes(content), content_type=content_type)
        response["Content-Length"] = str(len(content))
    else:
        if isinstance(content, FieldFile):
            # A fresh handle from the storage, independent of the FieldFile's own state.
            handle = content.storage.open(content.name, "rb")
        else:
            handle = content
            if hasattr(handle, "seek"):
                handle.seek(0)
        response = FileResponse(handle, content_type=content_type)

    inline = disposition == "inline" and bool(csp or is_inline_safe(content_type))
    response["Content-Disposition"] = content_disposition_header(
        not inline, safe_filename(filename)
    )
    if inline:
        response["Content-Security-Policy"] = csp or DEFAULT_INLINE_CSP
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = cache_control
    return response


def protected_file_response(
    spec: "ProtectedFileSpec",
    obj: models.Model,
    content: Content,
    request: Optional[HttpRequest] = None,
) -> HttpResponse:
    """
    Serve ``content`` as ``spec`` describes it for ``obj`` (name, type, disposition, CSP,
    cache control). Access must have been checked by the caller; the protected download
    views do that. ``request`` is accepted for views that pass it; it is not used.
    """
    filename = spec.get_filename(obj)
    return protected_content_response(
        content,
        filename=filename,
        content_type=spec.get_content_type(obj, filename),
        disposition=spec.disposition,
        csp=spec.csp,
        cache_control=spec.cache_control,
    )


__all__ = [
    "DEFAULT_CACHE_CONTROL",
    "DEFAULT_INLINE_CSP",
    "protected_content_response",
    "protected_file_response",
    "safe_filename",
]
