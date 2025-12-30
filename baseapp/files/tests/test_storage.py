from unittest.mock import MagicMock, patch

import pytest
import swapper
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth import get_user_model

from baseapp.files.storage.base import BaseUploadHandler
from baseapp.files.storage.local import LocalUploadHandler
from baseapp.files.storage.s3 import S3MultipartUploadHandler

File = swapper.load_model("baseapp_files", "File")
User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def file_obj(user):
    """Create a file object for testing."""
    return File.objects.create(
        file_name="test.mp4",
        file_size=10485760,
        file_content_type="video/mp4",
        upload_status=File.UploadStatus.PENDING,
        total_parts=2,
        created_by=user,
    )


@pytest.mark.django_db
class TestBaseUploadHandler:
    """Tests for the base upload handler interface."""

    def test_base_handler_is_abstract(self):
        """Test that base handler cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseUploadHandler()


@pytest.mark.django_db
@pytest.mark.skipif(
    not hasattr(settings, "AWS_ACCESS_KEY_ID"),
    reason="AWS settings not configured - skipping S3 tests",
)
class TestS3MultipartUploadHandler:
    """Tests for S3 multipart upload handler."""

    @pytest.fixture
    def mock_s3_client(self):
        """Mock boto3 S3 client."""
        with patch("baseapp.files.storage.s3.boto3.client") as mock_client:
            s3 = MagicMock()
            mock_client.return_value = s3

            # Mock create_multipart_upload
            s3.create_multipart_upload.return_value = {"UploadId": "test-upload-id-123"}

            # Mock generate_presigned_url
            s3.generate_presigned_url.return_value = (
                "https://bucket.s3.amazonaws.com/test?signature=abc"
            )

            # Mock complete_multipart_upload
            s3.complete_multipart_upload.return_value = {
                "Location": "https://bucket.s3.amazonaws.com/files/test.mp4"
            }

            yield s3

    @pytest.fixture
    def s3_handler(self, mock_s3_client):
        """Create S3 handler with mocked client."""
        handler = S3MultipartUploadHandler()
        handler.s3_client = mock_s3_client
        yield handler

    def test_s3_handler_supports_multipart(self, s3_handler):
        """Test that S3 handler supports multipart."""
        assert s3_handler.supports_multipart() is True

    def test_s3_initiate_upload(self, s3_handler, file_obj, mock_s3_client):
        """Test S3 multipart upload initiation."""
        result = s3_handler.initiate_upload(file_obj, num_parts=2, part_size=5242880)

        assert result["upload_id"] == "test-upload-id-123"
        assert len(result["presigned_urls"]) == 2
        assert result["presigned_urls"][0]["part_number"] == 1
        assert result["presigned_urls"][1]["part_number"] == 2
        assert result["expires_in"] == 3600

        # Verify S3 calls
        mock_s3_client.create_multipart_upload.assert_called_once()
        assert mock_s3_client.generate_presigned_url.call_count == 2

    def test_s3_initiate_upload_validates_part_count(self, s3_handler, file_obj):
        """Test that S3 handler validates max part count."""
        with pytest.raises(ValueError, match="maximum 10,000 parts"):
            s3_handler.initiate_upload(file_obj, num_parts=10001, part_size=5242880)

    def test_s3_initiate_upload_validates_part_size(self, s3_handler, file_obj):
        """Test that S3 handler validates minimum part size."""
        with pytest.raises(ValueError, match="minimum 5MB"):
            s3_handler.initiate_upload(file_obj, num_parts=2, part_size=1048576)

    def test_s3_complete_upload(self, s3_handler, file_obj, mock_s3_client):
        """Test S3 multipart upload completion."""
        parts = [
            {"part_number": 1, "etag": "abc123"},
            {"part_number": 2, "etag": "def456"},
        ]

        result = s3_handler.complete_upload(file_obj, "test-upload-id", parts)

        assert result  # Returns the S3 key

        # Verify S3 call
        mock_s3_client.complete_multipart_upload.assert_called_once()
        call_args = mock_s3_client.complete_multipart_upload.call_args
        assert call_args.kwargs["UploadId"] == "test-upload-id"
        assert len(call_args.kwargs["MultipartUpload"]["Parts"]) == 2

    def test_s3_abort_upload(self, s3_handler, file_obj, mock_s3_client):
        """Test S3 multipart upload abort."""
        s3_handler.abort_upload(file_obj, "test-upload-id")

        mock_s3_client.abort_multipart_upload.assert_called_once()

    def test_s3_abort_upload_handles_no_such_upload(self, s3_handler, file_obj, mock_s3_client):
        """Test that abort handles NoSuchUpload error gracefully."""
        mock_s3_client.abort_multipart_upload.side_effect = ClientError(
            {"Error": {"Code": "NoSuchUpload"}}, "abort_multipart_upload"
        )

        # Should not raise exception
        s3_handler.abort_upload(file_obj, "test-upload-id")

    def test_s3_abort_upload_raises_other_errors(self, s3_handler, file_obj, mock_s3_client):
        """Test that abort raises other errors."""
        mock_s3_client.abort_multipart_upload.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "abort_multipart_upload"
        )

        with pytest.raises(ClientError):
            s3_handler.abort_upload(file_obj, "test-upload-id")


@pytest.mark.django_db
class TestLocalUploadHandler:
    """Tests for local upload handler."""

    @pytest.fixture
    def local_handler(self):
        """Create local handler."""
        return LocalUploadHandler()

    @pytest.fixture
    def temp_media_root(self, tmp_path):
        """Use temporary directory for media root."""
        with patch.object(settings, "MEDIA_ROOT", str(tmp_path)):
            yield tmp_path

    def test_local_handler_does_not_support_true_multipart(self, local_handler):
        """Test that local handler doesn't support true multipart."""
        assert local_handler.supports_multipart() is False

    def test_local_initiate_upload(self, local_handler, file_obj, temp_media_root):
        """Test local upload initiation."""
        result = local_handler.initiate_upload(file_obj, num_parts=2, part_size=5242880)

        assert "upload_id" in result
        assert len(result["presigned_urls"]) == 2
        assert result["presigned_urls"][0]["part_number"] == 1
        assert "url" in result["presigned_urls"][0]

        # Check temp directory was created
        temp_dir = temp_media_root / "temp_uploads" / result["upload_id"]
        assert temp_dir.exists()

    def test_local_upload_part(self, local_handler, file_obj, temp_media_root):
        """Test uploading a part to local storage."""
        upload_id = "test-upload-123"
        data = b"test file content"

        etag = local_handler.upload_part(file_obj, upload_id, part_number=1, data=data)

        assert etag  # Should return MD5 hash
        assert len(etag) == 32  # MD5 hash length

        # Check part file was created
        part_file = temp_media_root / "temp_uploads" / upload_id / "part_1"
        assert part_file.exists()
        assert part_file.read_bytes() == data

    def test_local_complete_upload(self, local_handler, file_obj, temp_media_root):
        """Test completing local upload."""
        upload_id = "test-upload-123"

        # Create temp parts
        temp_dir = temp_media_root / "temp_uploads" / upload_id
        temp_dir.mkdir(parents=True)

        (temp_dir / "part_1").write_bytes(b"part 1 content")
        (temp_dir / "part_2").write_bytes(b"part 2 content")

        parts = [
            {"part_number": 1, "etag": "abc"},
            {"part_number": 2, "etag": "def"},
        ]

        result = local_handler.complete_upload(file_obj, upload_id, parts)

        assert result  # Returns file path

        # Check final file exists
        final_file = temp_media_root / result
        assert final_file.exists()
        assert final_file.read_bytes() == b"part 1 contentpart 2 content"

        # Check temp directory was cleaned up
        assert not temp_dir.exists()

    def test_local_abort_upload(self, local_handler, file_obj, temp_media_root):
        """Test aborting local upload."""
        upload_id = "test-upload-123"

        # Create temp directory
        temp_dir = temp_media_root / "temp_uploads" / upload_id
        temp_dir.mkdir(parents=True)
        (temp_dir / "part_1").write_bytes(b"test")

        # Abort
        local_handler.abort_upload(file_obj, upload_id)

        # Check temp directory was cleaned up
        assert not temp_dir.exists()


@pytest.mark.django_db
class TestStorageFactory:
    """Tests for storage handler factory."""

    @pytest.mark.skipif(
        not hasattr(settings, "AWS_ACCESS_KEY_ID"),
        reason="AWS settings not configured - skipping S3 factory test",
    )
    def test_factory_returns_s3_handler_for_s3_storage(self):
        """Test that factory returns S3 handler when using S3 storage."""
        with patch("baseapp.files.storage.default_storage") as mock_storage:
            # Mock S3 storage
            mock_storage.__class__.__name__ = "S3Boto3Storage"

            with patch("baseapp.files.storage.s3.S3MultipartUploadHandler") as mock_s3:
                from baseapp.files.storage import get_upload_handler

                get_upload_handler()

                # Should instantiate S3 handler
                mock_s3.assert_called_once()

    def test_factory_returns_local_handler_for_file_system_storage(self):
        """Test that factory returns local handler for non-S3 storage."""
        with patch("baseapp.files.storage.default_storage") as mock_storage:
            # Mock file system storage
            mock_storage.__class__.__name__ = "FileSystemStorage"

            with patch("baseapp.files.storage.local.LocalUploadHandler") as mock_local:
                from baseapp.files.storage import get_upload_handler

                get_upload_handler()

                # Should instantiate local handler
                mock_local.assert_called_once()
