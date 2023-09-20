from datetime import timedelta

import swapper
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..storage import get_upload_handler

File = swapper.load_model("baseapp_files", "File")


class UploadService:
    """Business logic for file uploads."""

    def __init__(self):
        self.handler = get_upload_handler()

    @transaction.atomic
    def initiate_multipart_upload(
        self,
        user,
        file_name: str,
        file_size: int,
        file_content_type: str,
        num_parts: int,
        part_size: int,
        parent_id=None,
        profile=None,
    ):
        """
        Initiate a multipart upload.

        Args:
            user: The user initiating the upload
            file_name: Original file name
            file_size: Size in bytes
            file_content_type: MIME type
            num_parts: Number of parts for multipart upload
            part_size: Size of each part in bytes
            parent_id: DocumentId primary key (optional)
            profile: Profile object (optional)

        Returns:
            (file_obj, upload_data)
        """

        # Validate inputs
        self._validate_file_params(file_size, num_parts, part_size)

        # Create File record in pending state
        file_obj = File.objects.create(
            file_name=file_name,
            file_size=file_size,
            file_content_type=file_content_type,
            upload_status=File.UploadStatus.PENDING,
            total_parts=num_parts,
            created_by=user,
            profile=profile,
            parent_id=parent_id,
            uploaded_parts={},
            upload_expires_at=timezone.now() + timedelta(hours=24),
        )

        # Get presigned URLs from storage handler
        try:
            upload_data = self.handler.initiate_upload(file_obj, num_parts, part_size)

            # Store upload_id
            file_obj.upload_id = upload_data["upload_id"]
            file_obj.upload_status = File.UploadStatus.UPLOADING
            file_obj.save(update_fields=["upload_id", "upload_status"])

            return file_obj, upload_data

        except Exception:
            # Cleanup file record if upload initiation fails
            file_obj.delete()
            raise

    @transaction.atomic
    def complete_multipart_upload(self, file_id: int, parts: list):
        """
        Complete a multipart upload.
        """
        file_obj = File.objects.select_for_update().get(id=file_id)

        # Validate state
        if file_obj.upload_status not in [File.UploadStatus.PENDING, File.UploadStatus.UPLOADING]:
            raise ValueError(f"Cannot complete upload in status: {file_obj.upload_status}")

        if not file_obj.upload_id:
            raise ValueError("No upload_id found")

        # Validate parts
        self._validate_parts(file_obj, parts)

        # Complete with storage handler
        try:
            file_path = self.handler.complete_upload(file_obj, file_obj.upload_id, parts)

            # Update file record
            file_obj.file = file_path
            file_obj.upload_status = File.UploadStatus.COMPLETED
            file_obj.uploaded_parts = {str(p["part_number"]): p["etag"] for p in parts}
            file_obj.upload_id = None
            file_obj.upload_expires_at = None
            file_obj.save()

            return file_obj

        except Exception:
            file_obj.upload_status = File.UploadStatus.FAILED
            file_obj.save(update_fields=["upload_status"])
            raise

    @transaction.atomic
    def abort_multipart_upload(self, file_id: int):
        """
        Abort a multipart upload and cleanup.
        """
        file_obj = File.objects.select_for_update().get(id=file_id)

        if file_obj.upload_id:
            try:
                self.handler.abort_upload(file_obj, file_obj.upload_id)
            except Exception:
                # Log but continue to mark as aborted
                pass

        file_obj.upload_status = File.UploadStatus.ABORTED
        file_obj.upload_id = None
        file_obj.save()

        return file_obj

    def _validate_file_params(self, file_size, num_parts, part_size):
        """Validate file upload parameters."""
        max_file_size = getattr(settings, "MAX_FILE_UPLOAD_SIZE", 5 * 1024 * 1024 * 1024)  # 5GB

        if file_size > max_file_size:
            raise ValueError(f"File size exceeds maximum {max_file_size} bytes")

        if num_parts < 1 or num_parts > 10000:
            raise ValueError("Number of parts must be between 1 and 10,000")

        if num_parts > 1 and part_size < 5 * 1024 * 1024:
            raise ValueError("Part size must be at least 5MB for multipart uploads")

        expected_size = (num_parts - 1) * part_size
        if expected_size > file_size:
            raise ValueError("Part size and count don't match file size")

    def _validate_parts(self, file_obj, parts):
        """Validate uploaded parts."""
        if len(parts) != file_obj.total_parts:
            raise ValueError(f"Expected {file_obj.total_parts} parts, received {len(parts)}")

        part_numbers = {p["part_number"] for p in parts}
        expected = set(range(1, file_obj.total_parts + 1))

        if part_numbers != expected:
            raise ValueError("Missing or duplicate part numbers")
