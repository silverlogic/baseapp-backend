import logging
from datetime import timedelta

import swapper
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..content_safety import (
    allowed_content_type,
    file_extension,
    normalize_content_type,
)
from ..storage import get_upload_handler
from ..storage.base import storage_name_in_folder

logger = logging.getLogger(__name__)

File = swapper.load_model("baseapp_files", "File")


class UploadService:
    """Business logic for file uploads."""

    def __init__(self):
        self.handler = get_upload_handler()

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

        The storage handler's ``initiate_upload`` (a remote call for S3) runs
        outside any DB transaction: the File row is created in its own
        statement, the network call happens without holding a transaction open,
        and the row is then updated. On failure the orphan row is removed.

        Args:
            user: The user initiating the upload; an anonymous user leaves
                ``created_by`` empty
            file_name: Original file name
            file_size: Size in bytes
            file_content_type: MIME type the client declared; replaced by the type
                BASEAPP_FILES_ALLOWED_FILE_TYPES gives the extension
            num_parts: Number of parts for multipart upload
            part_size: Size of each part in bytes
            parent_id: DocumentId primary key (optional)
            profile: Profile object (optional)

        Returns:
            (file_obj, upload_data)
        """

        # Validate inputs
        self._validate_file_params(file_size, num_parts, part_size)
        stored_content_type = allowed_content_type(file_name)
        if stored_content_type is None:
            raise ValueError("File type is not allowed")
        if file_content_type and normalize_content_type(file_content_type) != stored_content_type:
            # The extension only: file names can carry personal information.
            logger.info(
                "Upload with extension %r declared %r; storing it as %r",
                file_extension(file_name),
                file_content_type,
                stored_content_type,
            )

        # Create File record in pending state
        file_obj = File.objects.create(
            file_name=file_name,
            file_size=file_size,
            file_content_type=stored_content_type,
            upload_status=File.UploadStatus.PENDING,
            total_parts=num_parts,
            created_by=user if user and user.is_authenticated else None,
            profile=profile,
            parent_id=parent_id,
            uploaded_parts={},
            upload_expires_at=timezone.now() + timedelta(hours=24),
        )

        # Fix where the upload is written now, in the file's upload folder, so complete and
        # abort reach the same object whatever happens to the file meanwhile.
        file_obj.upload_storage_name = storage_name_in_folder(file_obj, file_name)

        # Get presigned URLs from storage handler (network I/O — not in a transaction)
        try:
            upload_data = self.handler.initiate_upload(file_obj, num_parts, part_size)
        except Exception:
            # Cleanup file record if upload initiation fails
            file_obj.delete()
            raise

        # Store upload_id
        file_obj.upload_id = upload_data["upload_id"]
        file_obj.upload_status = File.UploadStatus.UPLOADING
        file_obj.save(update_fields=["upload_id", "upload_status", "upload_storage_name"])

        return file_obj, upload_data

    def complete_multipart_upload(self, file_id: int, parts: list):
        """
        Complete a multipart upload.

        The storage handler's ``complete_upload`` (a remote call for S3) runs
        outside the transaction: state is validated first, the remote assembly
        happens without holding a row lock, then a short ``select_for_update``
        transaction flips the row to COMPLETED — guarding against a concurrent
        complete/abort without pinning the lock across network I/O.
        """
        file_obj = File.objects.get(id=file_id)

        # Validate state
        if file_obj.upload_status not in [File.UploadStatus.PENDING, File.UploadStatus.UPLOADING]:
            raise ValueError(f"Cannot complete upload in status: {file_obj.upload_status}")

        if not file_obj.upload_id:
            raise ValueError("No upload_id found")

        # Validate parts
        self._validate_parts(file_obj, parts)

        # The local handler names the stored file after file_name; re-check it here in
        # case it changed since initiation, including to another allowed type.
        if allowed_content_type(file_obj.file_name) != file_obj.file_content_type:
            raise ValueError("File type is not allowed")

        # Complete with storage handler (network I/O — outside the transaction)
        try:
            file_path = self.handler.complete_upload(file_obj, file_obj.upload_id, parts)
            self._verify_stored_size(file_obj, file_path)
        except Exception:
            File.objects.filter(id=file_id).update(upload_status=File.UploadStatus.FAILED)
            raise

        # Persist the result under a short row lock. If a concurrent request
        # already finished (or aborted) this upload, don't clobber it.
        with transaction.atomic():
            locked = File.objects.select_for_update().get(id=file_id)
            if locked.upload_status in (File.UploadStatus.PENDING, File.UploadStatus.UPLOADING):
                locked.file = file_path
                locked.upload_status = File.UploadStatus.COMPLETED
                locked.uploaded_parts = {str(p["part_number"]): p["etag"] for p in parts}
                locked.upload_id = ""
                locked.upload_expires_at = None
                locked.save()
            return locked

    ABORTABLE_STATUSES = (
        File.UploadStatus.PENDING,
        File.UploadStatus.UPLOADING,
        File.UploadStatus.FAILED,
    )

    def abort_multipart_upload(self, file_id: int):
        """
        Abort an upload that has not completed, and clean up its storage parts.

        The status is checked and the row marked ABORTED under a row lock first, so a
        completed file can't be aborted (its bytes would be orphaned and later cleanup
        would drop the row) and a concurrent completion can't be overwritten. The
        storage abort (network I/O) then runs outside the transaction.

        Raises:
            ValueError: the upload is completed or already aborted.
        """
        with transaction.atomic():
            locked = File.objects.select_for_update().get(id=file_id)
            if locked.upload_status not in self.ABORTABLE_STATUSES:
                raise ValueError(f"Cannot abort upload in status: {locked.upload_status}")
            upload_id = locked.upload_id
            locked.upload_status = File.UploadStatus.ABORTED
            locked.upload_id = ""
            locked.save(update_fields=["upload_status", "upload_id"])

        if upload_id:
            try:
                self.handler.abort_upload(locked, upload_id)
            except Exception:
                # Already marked aborted; record the storage-side failure so orphaned
                # remote uploads are diagnosable.
                logger.exception(
                    "Storage abort failed for file %s (upload_id=%s)", locked.id, upload_id
                )
        return locked

    def _verify_stored_size(self, file_obj, file_path: str) -> None:
        """Reject an assembled file whose bytes differ from the declared size.

        MAX_FILE_UPLOAD_SIZE is checked against the declared ``file_size`` at
        initiation, but neither the local part endpoint nor a presigned S3 part URL
        bounds how many bytes are actually sent. Both handlers store through the
        files storage they were built with, so it can measure either. An oversized
        object is deleted rather than kept.
        """
        storage = self.handler.storage
        stored_size = storage.size(file_path)
        if stored_size == file_obj.file_size:
            return
        try:
            storage.delete(file_path)
        except Exception:
            logger.exception("Could not delete mismatched upload %s", file_path)
        raise ValueError(
            f"Stored size {stored_size} does not match declared size {file_obj.file_size}"
        )

    def _validate_file_params(self, file_size, num_parts, part_size):
        """Validate file upload parameters."""
        max_file_size = getattr(settings, "MAX_FILE_UPLOAD_SIZE", 5 * 1024 * 1024 * 1024)  # 5GB

        if file_size > max_file_size:
            raise ValueError(f"File size exceeds maximum {max_file_size} bytes")

        if num_parts < 1 or num_parts > 10000:
            raise ValueError("Number of parts must be between 1 and 10,000")

        if num_parts > 1 and part_size < 5 * 1024 * 1024:
            raise ValueError("Part size must be at least 5MB for multipart uploads")

        # file_size must fit within the declared parts: strictly greater than
        # the first (num_parts - 1) full parts, and no larger than all of them.
        # Mirrors InitiateUploadSerializer so non-REST callers are protected too.
        min_size = (num_parts - 1) * part_size
        max_size = num_parts * part_size
        if file_size < min_size or file_size > max_size:
            raise ValueError("Part size and count don't match file size")

    def _validate_parts(self, file_obj, parts):
        """Validate uploaded parts."""
        if len(parts) != file_obj.total_parts:
            raise ValueError(f"Expected {file_obj.total_parts} parts, received {len(parts)}")

        part_numbers = {p["part_number"] for p in parts}
        expected = set(range(1, file_obj.total_parts + 1))

        if part_numbers != expected:
            raise ValueError("Missing or duplicate part numbers")
