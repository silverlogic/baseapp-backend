import os
import shutil
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files import File as DjangoFile
from django.core.files.storage import FileSystemStorage, Storage, default_storage

from baseapp_core.models import random_name_in

from ..tokens import PresignedUploadToken
from .base import BaseUploadHandler


class LocalUploadHandler(BaseUploadHandler):
    """
    Simplified local storage handler for dev/test.

    This doesn't implement true multipart upload - instead it provides
    "presigned URLs" that are actually backend endpoints with signed tokens
    that accept the file parts and store them locally.

    Parts are kept under the storage's own directory (so a private storage keeps them
    out of the public media root) and the assembled file is written into that storage.
    """

    def __init__(self, storage: Optional[Storage] = None) -> None:
        self.storage = storage or default_storage

    def _local_path(self, name: str) -> Optional[str]:
        """Where ``name`` lives on disk, for filesystem storages; None otherwise."""
        if isinstance(self.storage, FileSystemStorage):
            return self.storage.path(name)
        return None

    def _temp_dir(self, upload_id: str) -> str:
        """
        Where an upload's parts wait for completion: under the storage's own directory,
        or, for a storage without one, ``BASEAPP_FILES_UPLOAD_TEMP_DIR`` (default: a
        directory in the system temp dir). Point that setting at a shared volume when
        workers run on several hosts, since parts and completion may land on different ones.
        """
        root = self._local_path("") or getattr(settings, "BASEAPP_FILES_UPLOAD_TEMP_DIR", None)
        if not root:
            root = os.path.join(tempfile.gettempdir(), "baseapp_files")
        return os.path.join(root, "temp_uploads", upload_id)

    def _make_temp_dir(self, upload_id: str) -> str:
        """Create the parts directory, readable only by this process's user."""
        temp_dir = self._temp_dir(upload_id)
        os.makedirs(temp_dir, mode=0o700, exist_ok=True)
        return temp_dir

    def supports_multipart(self) -> bool:
        return False  # Simplified multipart

    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """
        Generate presigned URLs with signed tokens for secure uploads.
        """

        # Generate a simple upload token
        upload_id = str(uuid.uuid4())

        # Create temp directory for parts if needed
        self._make_temp_dir(upload_id)

        # Get the base URL from settings or use default
        base_url = settings.URL

        # Generate presigned URLs with signed tokens
        presigned_urls = []
        for part_num in range(1, num_parts + 1):
            token = PresignedUploadToken.mint(
                file_id=file_obj.id,
                part_number=part_num,
                upload_id=upload_id,
            )

            presigned_urls.append(
                {
                    "part_number": part_num,
                    "url": f"{base_url}/v1/files/presigned-uploads/{file_obj.id}/upload-part/{part_num}?token={token}",
                    "method": "PUT",
                }
            )

        return {
            "upload_id": upload_id,
            "presigned_urls": presigned_urls,
            "expires_in": PresignedUploadToken.max_age(),
        }

    def upload_part(self, upload_id: str, part_number: int, data: bytes) -> str:
        """
        Upload a part to local storage.
        This method is called by the backend when handling local uploads.

        Returns:
            etag: str (hash of the data)
        """
        import hashlib

        temp_dir = self._make_temp_dir(upload_id)

        part_file = os.path.join(temp_dir, f"part_{part_number}")

        # Write the part
        with open(part_file, "wb") as f:
            f.write(data)

        # Generate ETag (MD5 hash like S3). Content checksum, not a security
        # primitive — usedforsecurity=False documents intent and satisfies linters.
        etag = hashlib.md5(data, usedforsecurity=False).hexdigest()
        return etag

    def complete_upload(self, file_obj, upload_id: str, parts: List[Dict]) -> str:
        """
        Combine uploaded parts into final file.
        """
        temp_dir = self._temp_dir(upload_id)

        # The name fixed when the upload started; uploads started before it was kept get
        # a fresh one in the default folder, as they always did.
        final_path = file_obj.upload_storage_name or random_name_in("files")(
            file_obj, file_obj.file_name or "file"
        )
        # Not a filesystem storage: assemble beside the parts, then save through it.
        full_path = self._local_path(final_path)
        assembled_path = full_path or os.path.join(temp_dir, "assembled")

        # Ensure directory exists
        os.makedirs(os.path.dirname(assembled_path), exist_ok=True)

        # Combine parts in order. A missing part would silently truncate the
        # assembled file, so fail loudly instead.
        with open(assembled_path, "wb") as outfile:
            for part in sorted(parts, key=lambda x: x["part_number"]):
                part_file = os.path.join(temp_dir, f"part_{part['part_number']}")
                if not os.path.exists(part_file):
                    raise ValueError(f"Missing uploaded part {part['part_number']}")
                with open(part_file, "rb") as infile:
                    outfile.write(infile.read())

        if full_path is None:
            with open(assembled_path, "rb") as assembled:
                final_path = self.storage.save(final_path, DjangoFile(assembled))

        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Return the relative path (FileField will handle this)
        return final_path

    def abort_upload(self, file_obj, upload_id: str):
        """Cleanup temp files."""
        shutil.rmtree(self._temp_dir(upload_id), ignore_errors=True)

    def get_file_url(self, file_obj) -> Optional[str]:
        """Get the local file URL, or None if the file isn't stored yet."""
        if file_obj.file:
            return file_obj.file.url
        return None
