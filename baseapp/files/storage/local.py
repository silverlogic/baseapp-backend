import os
import shutil
import uuid
from typing import Any, Dict, List

from django.conf import settings
from django.core import signing

from baseapp_core.models import random_name_in

from .base import BaseUploadHandler


class LocalUploadHandler(BaseUploadHandler):
    """
    Simplified local storage handler for dev/test.

    This doesn't implement true multipart upload - instead it provides
    "presigned URLs" that are actually backend endpoints with signed tokens
    that accept the file parts and store them locally.
    """

    def supports_multipart(self) -> bool:
        return False  # Simplified multipart

    def initiate_upload(self, file_obj, num_parts: int, part_size: int) -> Dict[str, Any]:
        """
        Generate presigned URLs with signed tokens for secure uploads.
        """

        # Generate a simple upload token
        upload_id = str(uuid.uuid4())

        # Create temp directory for parts if needed
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        # Get the base URL from settings or use default
        base_url = getattr(settings, "BASE_URL", "http://localhost:8000")

        # Generate presigned URLs with signed tokens
        presigned_urls = []
        for part_num in range(1, num_parts + 1):
            # Create a signed token for this specific file and part
            token_data = {
                "file_id": file_obj.id,
                "part_number": part_num,
                "upload_id": upload_id,
            }
            token = signing.dumps(token_data)

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
