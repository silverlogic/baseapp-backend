"""
Protected downloads: model file fields served only through the app, with the viewer's
access checked on every request. See "Protected downloads" in ``baseapp/files/README.md``.
"""

from .exceptions import Gone
from .registry import ProtectedFileSpec, protected_files
from .responses import protected_content_response, protected_file_response
from .signals import protected_file_downloaded

__all__ = [
    "Gone",
    "ProtectedFileSpec",
    "protected_content_response",
    "protected_file_downloaded",
    "protected_file_response",
    "protected_files",
]
