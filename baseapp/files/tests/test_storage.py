import sys
from unittest.mock import MagicMock, patch

import pytest
import swapper
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.utils.functional import LazyObject
from storages.backends.s3boto3 import S3Boto3Storage

from baseapp.files.storage import get_upload_handler
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
class TestS3MultipartUploadHandler:
    """Tests for S3 multipart upload handler."""

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Mock boto3 S3 client."""
        s3 = MagicMock()

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

        return s3

    @pytest.fixture
    def mock_storage(self, mock_s3_client: MagicMock) -> MagicMock:
        """Mock django-storages S3 backend carrying the boto3 client."""
        storage = MagicMock()
        storage.connection.meta.client = mock_s3_client
        storage.bucket_name = "test-bucket"
        storage.location = "media"
        storage.default_acl = "public-read"
        storage.get_object_parameters.return_value = {}
        return storage

    @pytest.fixture
    def s3_handler(self, mock_storage: MagicMock) -> S3MultipartUploadHandler:
        """Create S3 handler backed by the mocked storage."""
        return S3MultipartUploadHandler(storage=mock_storage)

    def test_s3_handler_uses_storage_client_and_bucket(
        self, mock_storage: MagicMock, mock_s3_client: MagicMock
    ) -> None:
        """The handler reuses the storage's client so endpoint/signing config apply."""
        handler = S3MultipartUploadHandler(storage=mock_storage)

        assert handler.s3_client is mock_s3_client
        assert handler.bucket == "test-bucket"

    def test_s3_handler_defaults_to_default_storage(
        self, mock_storage: MagicMock, mock_s3_client: MagicMock
    ) -> None:
        """Without an explicit storage the handler uses Django's default_storage."""
        with patch("baseapp.files.storage.s3.default_storage", mock_storage):
            handler = S3MultipartUploadHandler()

        assert handler.s3_client is mock_s3_client

    def test_s3_key_is_stable_across_upload_lifecycle(
        self, s3_handler: S3MultipartUploadHandler, file_obj: File, mock_s3_client: MagicMock
    ) -> None:
        """Initiate, complete and abort must all address the same S3 object."""
        s3_handler.initiate_upload(file_obj, num_parts=2, part_size=5242880)
        file_name = s3_handler.complete_upload(
            file_obj, "test-upload-id", [{"part_number": 1, "etag": "abc"}]
        )
        s3_handler.abort_upload(file_obj, "test-upload-id")

        initiate_key = mock_s3_client.create_multipart_upload.call_args.kwargs["Key"]
        presigned_key = mock_s3_client.generate_presigned_url.call_args.kwargs["Params"]["Key"]
        complete_key = mock_s3_client.complete_multipart_upload.call_args.kwargs["Key"]
        abort_key = mock_s3_client.abort_multipart_upload.call_args.kwargs["Key"]

        assert initiate_key == presigned_key == complete_key == abort_key
        assert initiate_key == f"media/{file_name}"
        assert file_name.startswith("files/")
        assert file_name.endswith(".mp4")

    def test_s3_key_differs_per_file(
        self, s3_handler: S3MultipartUploadHandler, file_obj: File, user: User
    ) -> None:
        """Different files never share an S3 key."""
        other = File.objects.create(file_name="test.mp4", created_by=user)

        assert s3_handler._get_s3_key(file_obj) != s3_handler._get_s3_key(other)

    def test_s3_key_without_storage_location(self, mock_storage: MagicMock, file_obj: File) -> None:
        """With no storage location the key is the storage name itself."""
        mock_storage.location = ""
        handler = S3MultipartUploadHandler(storage=mock_storage)

        assert handler._get_s3_key(file_obj) == handler._get_file_name(file_obj)

    def test_s3_initiate_upload_applies_storage_acl(
        self, s3_handler: S3MultipartUploadHandler, file_obj: File, mock_s3_client: MagicMock
    ) -> None:
        """Uploaded objects get the storage's default ACL (e.g. public-read media)."""
        s3_handler.initiate_upload(file_obj, num_parts=1, part_size=1024)

        assert mock_s3_client.create_multipart_upload.call_args.kwargs["ACL"] == "public-read"

    def test_s3_initiate_upload_without_storage_acl(
        self, mock_storage: MagicMock, file_obj: File, mock_s3_client: MagicMock
    ) -> None:
        """No ACL is sent when the storage has none (bucket policy decides)."""
        mock_storage.default_acl = None
        S3MultipartUploadHandler(storage=mock_storage).initiate_upload(
            file_obj, num_parts=1, part_size=1024
        )

        assert "ACL" not in mock_s3_client.create_multipart_upload.call_args.kwargs

    def test_s3_initiate_upload_applies_storage_object_parameters(
        self, mock_storage: MagicMock, file_obj: File, mock_s3_client: MagicMock
    ) -> None:
        """AWS_S3_OBJECT_PARAMETERS apply to multipart uploads, and their ACL wins over default_acl."""
        mock_storage.get_object_parameters.return_value = {
            "ACL": "private",
            "CacheControl": "max-age=86400",
            "Metadata": {"source": "storage"},
        }
        handler = S3MultipartUploadHandler(storage=mock_storage)

        handler.initiate_upload(file_obj, num_parts=1, part_size=1024)

        kwargs = mock_s3_client.create_multipart_upload.call_args.kwargs
        assert kwargs["ACL"] == "private"
        assert kwargs["CacheControl"] == "max-age=86400"
        assert kwargs["ContentType"] == "video/mp4"
        assert kwargs["Metadata"]["source"] == "storage"
        assert kwargs["Metadata"]["original_filename"] == "test.mp4"
        mock_storage.get_object_parameters.assert_called_once_with(handler._get_file_name(file_obj))

    @pytest.mark.parametrize(
        "file_name, expected_ext",
        [
            ("clip.mp4", "mp4"),
            ("photo.JPG", "JPG"),
            ("dir/photo.png", "png"),
            ("dir\\photo.png", "png"),
            ("clip.mp4/../other", "bin"),
            ("clip.mp4/x", "bin"),
            ("README", "bin"),
            ("", "bin"),
            ("archive.toolongextension12345", "bin"),
        ],
    )
    def test_s3_file_name_extension_is_sanitized(
        self,
        s3_handler: S3MultipartUploadHandler,
        user: User,
        file_name: str,
        expected_ext: str,
    ) -> None:
        """The client-supplied file name never adds path segments to the S3 key."""
        file_obj = File.objects.create(file_name=file_name, created_by=user)

        name = s3_handler._get_file_name(file_obj)

        assert name.count("/") == 1
        assert name.startswith("files/")
        assert name.endswith(f".{expected_ext}")

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

        etag = local_handler.upload_part(upload_id, part_number=1, data=data)

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

    def test_factory_returns_s3_handler_for_s3_storage(self) -> None:
        """Test that factory returns S3 handler when using S3 storage."""
        with patch("baseapp.files.storage.default_storage", S3Boto3Storage(bucket_name="b")):
            with patch("baseapp.files.storage.s3.S3MultipartUploadHandler") as mock_s3:
                get_upload_handler()

                mock_s3.assert_called_once()

    def test_factory_returns_s3_handler_for_s3_storage_subclass(self) -> None:
        """Subclasses such as s3_folder_storage's DefaultStorage must select S3 too."""

        class DefaultStorage(S3Boto3Storage):
            pass

        with patch("baseapp.files.storage.default_storage", DefaultStorage(bucket_name="b")):
            with patch("baseapp.files.storage.s3.S3MultipartUploadHandler") as mock_s3:
                get_upload_handler()

                mock_s3.assert_called_once()

    def test_factory_returns_s3_handler_through_lazy_default_storage(self) -> None:
        """The real LazyObject `default_storage` proxies isinstance to the wrapped backend."""
        lazy = LazyObject()
        lazy._wrapped = S3Boto3Storage(bucket_name="b")

        with patch("baseapp.files.storage.default_storage", lazy):
            with patch("baseapp.files.storage.s3.S3MultipartUploadHandler") as mock_s3:
                get_upload_handler()

                mock_s3.assert_called_once()

    def test_factory_returns_local_handler_for_file_system_storage(self) -> None:
        """Test that factory returns local handler for non-S3 storage."""
        with patch("baseapp.files.storage.default_storage", FileSystemStorage()):
            with patch("baseapp.files.storage.local.LocalUploadHandler") as mock_local:
                get_upload_handler()

                mock_local.assert_called_once()

    def test_factory_returns_local_handler_without_django_storages(self) -> None:
        """Projects without django-storages installed fall back to local uploads."""
        with patch.dict(sys.modules, {"storages.backends.s3boto3": None}):
            with patch("baseapp.files.storage.local.LocalUploadHandler") as mock_local:
                get_upload_handler()

                mock_local.assert_called_once()
