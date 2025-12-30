import os
import shutil
import uuid
from typing import Any, Dict, List

from django.conf import settings

from baseapp_core.models import random_name_in

from .base import BaseUploadHandler


class LocalUploadHandler(BaseUploadHandler):
    """
    Simplified local storage handler for dev/test.

    This doesn't implement true multipart upload - instead it provides
    "presigned URLs" that are actually backend endpoints that accept
    the file parts and store them locally.
    """

    def supports_multipart(self) -> bool:
        return False  # Simplified multipart

    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """
        Generate pseudo-presigned URLs pointing to backend endpoints.
        """

        # Generate a simple upload token
        upload_id = str(uuid.uuid4())

        # Create temp directory for parts if needed
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        # For local storage, we'll provide URLs that are actually simple identifiers
        # The client will need to upload via the backend endpoint
        presigned_urls = []
        for part_num in range(1, num_parts + 1):
            # In local mode, we provide a simple part identifier
            # The actual upload will go through a backend endpoint
            presigned_urls.append(
                {
                    "part_number": part_num,
                    "url": f"/api/v1/files/uploads/{file_obj.id}/upload-part/{part_num}",
                    "method": "PUT",
                }
            )

        return {
            "upload_id": upload_id,
            "presigned_urls": presigned_urls,
            "expires_in": 3600,
        }

    def upload_part(self, file_obj, upload_id: str, part_number: int, data: bytes) -> str:
        """
        Upload a part to local storage.
        This method is called by the backend when handling local uploads.

        Returns:
            etag: str (hash of the data)
        """
        import hashlib

        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        part_file = os.path.join(temp_dir, f"part_{part_number}")

        # Write the part
        with open(part_file, "wb") as f:
            f.write(data)

        # Generate ETag (MD5 hash like S3)
        etag = hashlib.md5(data).hexdigest()
        return etag

    def complete_upload(self, file_obj, upload_id: str, parts: List[Dict]) -> str:
        """
        Combine uploaded parts into final file.
        """
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", upload_id)

        # Generate final file path
        final_path = random_name_in("files")(file_obj, file_obj.file_name or "file")
        full_path = os.path.join(settings.MEDIA_ROOT, final_path)

        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Combine parts in order
        with open(full_path, "wb") as outfile:
            for part in sorted(parts, key=lambda x: x["part_number"]):
                part_file = os.path.join(temp_dir, f"part_{part['part_number']}")
                if os.path.exists(part_file):
                    with open(part_file, "rb") as infile:
                        outfile.write(infile.read())

        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Return the relative path (FileField will handle this)
        return final_path

    def abort_upload(self, file_obj, upload_id: str):
        """Cleanup temp files."""
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", upload_id)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def get_file_url(self, file_obj) -> str:
        """Get the local file URL."""
        if file_obj.file:
            return file_obj.file.url
        return None
