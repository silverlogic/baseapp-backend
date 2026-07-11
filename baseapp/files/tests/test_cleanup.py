from datetime import timedelta
from typing import Optional
from unittest.mock import MagicMock

import pytest
import swapper
from django.contrib.auth import get_user_model
from django.utils import timezone

from baseapp.files.services.cleanup import (
    cleanup_expired_uploads,
    cleanup_failed_uploads,
)

File = swapper.load_model("baseapp_files", "File")
User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> "User":
    return User.objects.create_user(email="cleanup@example.com", password="testpass123")


@pytest.fixture
def mock_handler(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the storage handler used by the cleanup task."""
    handler = MagicMock()
    monkeypatch.setattr("baseapp.files.services.cleanup.get_upload_handler", lambda: handler)
    return handler


def create_file(
    user: "User",
    upload_status: str,
    expires_delta: Optional[timedelta] = None,
    upload_id: Optional[str] = "upload-id-123",
) -> "File":
    """Create a File in the given upload status with an optional expiration offset."""
    upload_expires_at = timezone.now() + expires_delta if expires_delta is not None else None
    return File.objects.create(
        file_name="test.mp4",
        file_size=1024,
        file_content_type="video/mp4",
        upload_status=upload_status,
        upload_id=upload_id,
        total_parts=1,
        created_by=user,
        upload_expires_at=upload_expires_at,
    )


class TestCleanupExpiredUploads:
    """Tests for the cleanup_expired_uploads celery task."""

    def test_aborts_expired_pending_and_uploading(self, user, mock_handler):
        """Expired PENDING and UPLOADING uploads are aborted on storage and in the DB."""
        pending = create_file(user, File.UploadStatus.PENDING, expires_delta=timedelta(hours=-1))
        uploading = create_file(
            user, File.UploadStatus.UPLOADING, expires_delta=timedelta(hours=-1)
        )

        result = cleanup_expired_uploads()

        assert result == "Cleaned up 2 expired uploads"
        assert mock_handler.abort_upload.call_count == 2

        for file_obj in (pending, uploading):
            file_obj.refresh_from_db()
            assert file_obj.upload_status == File.UploadStatus.ABORTED
            assert file_obj.upload_id is None

    def test_leaves_non_expired_uploads_alone(self, user, mock_handler):
        """Uploads that have not expired yet are untouched."""
        file_obj = create_file(user, File.UploadStatus.UPLOADING, expires_delta=timedelta(hours=1))

        result = cleanup_expired_uploads()

        assert result == "Cleaned up 0 expired uploads"
        mock_handler.abort_upload.assert_not_called()

        file_obj.refresh_from_db()
        assert file_obj.upload_status == File.UploadStatus.UPLOADING
        assert file_obj.upload_id == "upload-id-123"

    def test_leaves_completed_files_alone(self, user, mock_handler):
        """COMPLETED files are never aborted, even with a past expiration date."""
        file_obj = create_file(
            user, File.UploadStatus.COMPLETED, expires_delta=timedelta(hours=-1), upload_id=None
        )

        result = cleanup_expired_uploads()

        assert result == "Cleaned up 0 expired uploads"
        mock_handler.abort_upload.assert_not_called()

        file_obj.refresh_from_db()
        assert file_obj.upload_status == File.UploadStatus.COMPLETED

    def test_skips_storage_abort_without_upload_id(self, user, mock_handler):
        """Expired uploads without an upload_id are aborted in the DB only."""
        file_obj = create_file(
            user, File.UploadStatus.PENDING, expires_delta=timedelta(hours=-1), upload_id=None
        )

        result = cleanup_expired_uploads()

        assert result == "Cleaned up 1 expired uploads"
        mock_handler.abort_upload.assert_not_called()

        file_obj.refresh_from_db()
        assert file_obj.upload_status == File.UploadStatus.ABORTED

    def test_continues_past_handler_exception(self, user, mock_handler):
        """A storage failure on one file doesn't stop cleanup of the others."""
        failing = create_file(user, File.UploadStatus.UPLOADING, expires_delta=timedelta(hours=-1))
        succeeding = create_file(
            user, File.UploadStatus.UPLOADING, expires_delta=timedelta(hours=-1)
        )

        def abort_upload(file_obj, upload_id):
            if file_obj.pk == failing.pk:
                raise Exception("S3 is down")

        mock_handler.abort_upload.side_effect = abort_upload

        result = cleanup_expired_uploads()

        assert result == "Cleaned up 1 expired uploads"
        assert mock_handler.abort_upload.call_count == 2

        failing.refresh_from_db()
        assert failing.upload_status == File.UploadStatus.UPLOADING

        succeeding.refresh_from_db()
        assert succeeding.upload_status == File.UploadStatus.ABORTED


class TestCleanupFailedUploads:
    """Tests for the cleanup_failed_uploads helper."""

    def _age_file(self, file_obj: "File", days: int) -> None:
        """Backdate the modified timestamp bypassing auto_now."""
        File.objects.filter(pk=file_obj.pk).update(modified=timezone.now() - timedelta(days=days))

    def test_deletes_old_failed_and_aborted(self, user):
        """FAILED/ABORTED files older than the cutoff are deleted."""
        failed = create_file(user, File.UploadStatus.FAILED, upload_id=None)
        aborted = create_file(user, File.UploadStatus.ABORTED, upload_id=None)
        self._age_file(failed, days=8)
        self._age_file(aborted, days=8)

        result = cleanup_failed_uploads(days_old=7)

        assert result == "Deleted 2 old failed/aborted uploads"
        assert not File.objects.filter(pk__in=[failed.pk, aborted.pk]).exists()

    def test_keeps_recent_failed_uploads(self, user):
        """FAILED/ABORTED files newer than the cutoff are kept."""
        failed = create_file(user, File.UploadStatus.FAILED, upload_id=None)
        aborted = create_file(user, File.UploadStatus.ABORTED, upload_id=None)
        self._age_file(failed, days=3)

        result = cleanup_failed_uploads(days_old=7)

        assert result == "Deleted 0 old failed/aborted uploads"
        assert File.objects.filter(pk__in=[failed.pk, aborted.pk]).count() == 2

    def test_keeps_old_files_in_other_statuses(self, user):
        """Old COMPLETED/PENDING/UPLOADING files are never deleted."""
        completed = create_file(user, File.UploadStatus.COMPLETED, upload_id=None)
        pending = create_file(user, File.UploadStatus.PENDING)
        uploading = create_file(user, File.UploadStatus.UPLOADING)
        for file_obj in (completed, pending, uploading):
            self._age_file(file_obj, days=30)

        result = cleanup_failed_uploads(days_old=7)

        assert result == "Deleted 0 old failed/aborted uploads"
        assert File.objects.count() == 3

    def test_respects_custom_cutoff(self, user):
        """The days_old argument moves the deletion cutoff."""
        failed = create_file(user, File.UploadStatus.FAILED, upload_id=None)
        self._age_file(failed, days=2)

        assert cleanup_failed_uploads(days_old=7) == "Deleted 0 old failed/aborted uploads"
        assert cleanup_failed_uploads(days_old=1) == "Deleted 1 old failed/aborted uploads"
        assert not File.objects.filter(pk=failed.pk).exists()
