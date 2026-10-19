import posixpath
import re
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from django.core.files.storage import Storage

if TYPE_CHECKING:
    from ..models import AbstractFile

SAFE_EXTENSION_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


def safe_extension(file_name: str) -> str:
    """
    The extension of ``file_name``'s basename when it is a short alphanumeric suffix, else
    ``bin``. Only the extension is kept: client-supplied file names can carry personal
    information and path separators.
    """
    basename = posixpath.basename((file_name or "").replace("\\", "/"))
    ext = basename.rsplit(".", 1)[-1] if "." in basename else ""
    return ext if SAFE_EXTENSION_RE.match(ext) else "bin"


def storage_name_in_folder(file_obj: "AbstractFile", file_name: str) -> str:
    """
    A random, unguessable storage name in ``file_obj``'s upload folder.

    The folder must be a plain relative path: leading and trailing slashes are dropped, and
    a ``.`` or ``..`` segment, an empty segment (``a//b``) or a backslash raises
    ``ValueError``, so an override can never address a file outside its own folder.
    """
    folder = file_obj.get_upload_folder().strip("/")
    if folder and ("\\" in folder or any(part in ("", ".", "..") for part in folder.split("/"))):
        raise ValueError(f"Invalid upload folder: {folder!r}")
    return posixpath.join(folder, f"{uuid.uuid4().hex}.{safe_extension(file_name)}")


def file_upload_to(instance: "AbstractFile", filename: str) -> str:
    """``File.file``'s ``upload_to``: files saved directly land in the same folder as uploads."""
    return storage_name_in_folder(instance, filename)


class BaseUploadHandler(ABC):
    """Abstract interface for upload handlers (S3 vs Local)."""

    # The storage the assembled file is written to (the files storage).
    storage: Storage

    @abstractmethod
    def supports_multipart(self) -> bool:
        """Whether this handler supports true multipart uploads."""
        pass

    @abstractmethod
    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """
        Initiate an upload and return presigned URLs.

        Returns:
            {
                'upload_id': str,
                'presigned_urls': [
                    {'part_number': 1, 'url': 'https://...'},
                    {'part_number': 2, 'url': 'https://...'},
                ],
                'expires_in': int (seconds)
            }
        """
        pass

    @abstractmethod
    def complete_upload(self, file_obj, upload_id: str, parts: List[Dict[str, Any]]) -> str:
        """
        Complete the upload.

        Args:
            parts: [{'part_number': 1, 'etag': 'xxx'}, ...]

        Returns:
            final_url: str (file URL)
        """
        pass

    @abstractmethod
    def abort_upload(self, file_obj, upload_id: str) -> None:
        """Abort and cleanup an upload."""
        pass

    @abstractmethod
    def get_file_url(self, file_obj) -> Optional[str]:
        """Get the URL for accessing the file, or None if not available yet."""
        pass
