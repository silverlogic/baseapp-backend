from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import swapper
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import status

from baseapp_core.models import DocumentId

File = swapper.load_model("baseapp_files", "File")
User = get_user_model()


@pytest.fixture
def mock_s3_handler():
    """Mock S3 upload handler to avoid actual S3 calls."""
    with patch("baseapp.files.services.upload_service.get_upload_handler") as mock_get_handler:
        mock_handler = MagicMock()
        mock_handler.supports_multipart.return_value = True
        mock_handler.initiate_upload.return_value = {
            "upload_id": "test-upload-id-123",
            "presigned_urls": [
                {"part_number": 1, "url": "https://s3.amazonaws.com/bucket/part1?signature=abc"},
                {"part_number": 2, "url": "https://s3.amazonaws.com/bucket/part2?signature=def"},
            ],
            "expires_in": 3600,
        }
        mock_handler.complete_upload.return_value = "files/test-file.mp4"
        mock_handler.abort_upload.return_value = None
        mock_get_handler.return_value = mock_handler
        yield mock_handler


@pytest.mark.django_db
class TestFileUploadInitiation:
    """Tests for POST /v1/files/uploads/ (initiate upload)."""

    def test_initiate_upload_success(self, user_client, mock_s3_handler):
        """Test successful upload initiation."""
        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "test-video.mp4",
                "file_size": 10485760,  # 10MB
                "file_content_type": "video/mp4",
                "num_parts": 2,
                "part_size": 5242880,  # 5MB
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Check response structure
        assert "id" in data
        assert data["upload_id"] == "test-upload-id-123"
        assert len(data["presigned_urls"]) == 2
        assert data["presigned_urls"][0]["part_number"] == 1
        assert data["expires_in"] == 3600
        assert data["upload_status"] == File.UploadStatus.UPLOADING

        # Check file was created in database (id is now public_id UUID)
        file_obj = File.get_by_public_id(data["id"])
        assert file_obj.file_name == "test-video.mp4"
        assert file_obj.file_size == 10485760
        assert file_obj.upload_status == File.UploadStatus.UPLOADING
        assert file_obj.total_parts == 2
        assert file_obj.created_by == user_client.user

        # Verify S3 handler was called
        mock_s3_handler.initiate_upload.assert_called_once()

    def test_initiate_upload_with_parent(self, user_client, mock_s3_handler):
        """Test upload initiation with parent object."""
        # Get or create DocumentId for the user
        user_ct = ContentType.objects.get_for_model(User)
        document_id, _ = DocumentId.objects.get_or_create(
            content_type=user_ct,
            object_id=user_client.user.id,
        )

        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "avatar.jpg",
                "file_size": 1048576,  # 1MB
                "file_content_type": "image/jpeg",
                "num_parts": 1,
                "part_size": 1048576,
                "parent_id": str(document_id.public_id),
            },
            format="json",
        )

        # Print response for debugging if it fails
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Response status: {response.status_code}")
            print(f"Response data: {response.json()}")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        file_obj = File.get_by_public_id(data["id"])
        # Parent is now a ForeignKey to DocumentId
        assert file_obj.parent is not None
        assert file_obj.parent.content_type_id == user_ct.id
        assert file_obj.parent.object_id == user_client.user.id

    def test_initiate_upload_requires_authentication(self, client):
        """Test that upload initiation requires authentication."""
        response = client.post(
            "/v1/files/uploads",
            {
                "file_name": "test.mp4",
                "file_size": 1048576,
                "file_content_type": "video/mp4",
                "num_parts": 1,
                "part_size": 1048576,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_initiate_upload_invalid_part_size(self, user_client, mock_s3_handler):
        """Test validation for part size (must be at least 5MB for multipart)."""
        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "test.mp4",
                "file_size": 10485760,
                "file_content_type": "video/mp4",
                "num_parts": 3,
                "part_size": 1048576,  # Too small (1MB)
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initiate_upload_file_size_mismatch(self, user_client, mock_s3_handler):
        """Test validation for file size matching parts."""
        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "test.mp4",
                "file_size": 100000,  # 100KB - doesn't match parts
                "file_content_type": "video/mp4",
                "num_parts": 2,
                "part_size": 5242880,  # 5MB
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        # DRF returns validation errors as dict with field names or non_field_errors
        error_message = str(response_data)
        assert "doesn't match" in error_message

    def test_initiate_upload_too_many_parts(self, user_client, mock_s3_handler):
        """Test validation for maximum parts (10,000)."""
        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "test.mp4",
                "file_size": 52428800000,  # 50GB
                "file_content_type": "video/mp4",
                "num_parts": 10001,  # Too many
                "part_size": 5242880,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initiate_upload_invalid_parent_id(self, user_client, mock_s3_handler):
        """Test that invalid parent_id returns error."""
        import uuid

        response = user_client.post(
            "/v1/files/uploads",
            {
                "file_name": "test.mp4",
                "file_size": 1048576,
                "file_content_type": "video/mp4",
                "num_parts": 1,
                "part_size": 1048576,
                "parent_id": str(uuid.uuid4()),  # Non-existent DocumentId
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestFileUploadCompletion:
    """Tests for POST /v1/files/uploads/{id}/complete."""

    @pytest.fixture
    def pending_upload(self, user_client):
        """Create a pending upload for testing."""
        return File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.UPLOADING,
            upload_id="test-upload-id",
            total_parts=2,
            created_by=user_client.user,
            upload_expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_complete_upload_success(self, user_client, pending_upload, mock_s3_handler):
        """Test successful upload completion."""
        response = user_client.post(
            f"/v1/files/uploads/{pending_upload.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1, "etag": "abc123"},
                    {"part_number": 2, "etag": "def456"},
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["upload_status"] == File.UploadStatus.COMPLETED
        assert "url" in data

        # Check file was updated in database
        pending_upload.refresh_from_db()
        assert pending_upload.upload_status == File.UploadStatus.COMPLETED
        assert pending_upload.upload_id is None
        assert pending_upload.uploaded_parts == {"1": "abc123", "2": "def456"}

        # Verify S3 handler was called
        mock_s3_handler.complete_upload.assert_called_once()

    def test_complete_upload_wrong_number_of_parts(
        self, user_client, pending_upload, mock_s3_handler
    ):
        """Test validation for incorrect number of parts."""
        response = user_client.post(
            f"/v1/files/uploads/{pending_upload.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1, "etag": "abc123"},
                    # Missing part 2
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Expected 2 parts" in str(response.json())

    def test_complete_upload_missing_part_number(
        self, user_client, pending_upload, mock_s3_handler
    ):
        """Test validation for missing part numbers."""
        response = user_client.post(
            f"/v1/files/uploads/{pending_upload.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1, "etag": "abc123"},
                    {"part_number": 3, "etag": "ghi789"},  # Skipped part 2
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing or duplicate" in str(response.json())

    def test_complete_upload_requires_ownership(self, client, pending_upload, mock_s3_handler):
        """Test that only the file owner can complete upload."""
        other_user = User.objects.create_user(email="other@example.com", password="pass123")
        client.force_authenticate(user=other_user)

        response = client.post(
            f"/v1/files/uploads/{pending_upload.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1, "etag": "abc123"},
                    {"part_number": 2, "etag": "def456"},
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_complete_upload_invalid_status(self, user_client, mock_s3_handler):
        """Test that completed uploads cannot be completed again."""
        completed_file = File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.COMPLETED,
            created_by=user_client.user,
        )

        response = user_client.post(
            f"/v1/files/uploads/{completed_file.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1, "etag": "abc123"},
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_complete_upload_invalid_part_structure(
        self, user_client, pending_upload, mock_s3_handler
    ):
        """Test validation for part structure."""
        response = user_client.post(
            f"/v1/files/uploads/{pending_upload.public_id}/complete",
            {
                "parts": [
                    {"part_number": 1},  # Missing etag
                    {"etag": "def456"},  # Missing part_number
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestFileUploadAbort:
    """Tests for DELETE /v1/files/uploads/{id}."""

    @pytest.fixture
    def uploading_file(self, user_client):
        """Create an uploading file for testing."""
        return File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.UPLOADING,
            upload_id="test-upload-id",
            total_parts=2,
            created_by=user_client.user,
        )

    def test_abort_upload_success(self, user_client, uploading_file, mock_s3_handler):
        """Test successful upload abort."""
        response = user_client.delete(f"/v1/files/uploads/{uploading_file.public_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Check file was updated
        uploading_file.refresh_from_db()
        assert uploading_file.upload_status == File.UploadStatus.ABORTED
        assert uploading_file.upload_id is None

        # Verify S3 handler was called
        mock_s3_handler.abort_upload.assert_called_once_with(uploading_file, "test-upload-id")

    def test_abort_upload_requires_ownership(self, client, uploading_file, mock_s3_handler):
        """Test that only file owner can abort upload."""
        other_user = User.objects.create_user(email="other@example.com", password="pass123")
        client.force_authenticate(user=other_user)

        response = client.delete(f"/v1/files/uploads/{uploading_file.public_id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_abort_upload_without_upload_id(self, user_client, mock_s3_handler):
        """Test aborting upload without upload_id still marks as aborted."""
        file_obj = File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.PENDING,
            upload_id=None,  # No upload_id
            total_parts=2,
            created_by=user_client.user,
        )

        response = user_client.delete(f"/v1/files/uploads/{file_obj.public_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        file_obj.refresh_from_db()
        assert file_obj.upload_status == File.UploadStatus.ABORTED


@pytest.mark.django_db
class TestFileCRUD:
    """Tests for file CRUD endpoints."""

    @pytest.fixture
    def completed_file(self, user_client):
        """Create a completed file for testing."""
        return File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.COMPLETED,
            created_by=user_client.user,
        )

    def test_list_files(self, user_client, completed_file):
        """Test listing files."""
        response = user_client.get("/v1/files")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 1
        assert str(data["results"][0]["id"]) == str(completed_file.public_id)

    def test_list_files_filter_by_status(self, user_client):
        """Test filtering files by status."""
        File.objects.create(
            file_name="completed.mp4",
            file_size=100,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.COMPLETED,
            created_by=user_client.user,
        )
        File.objects.create(
            file_name="uploading.mp4",
            file_size=100,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.UPLOADING,
            created_by=user_client.user,
        )

        # Default: only completed
        response = user_client.get("/v1/files")
        assert len(response.json()["results"]) == 1

        # Filter by uploading
        response = user_client.get(f"/v1/files?status={File.UploadStatus.UPLOADING}")
        assert len(response.json()["results"]) == 1
        assert response.json()["results"][0]["upload_status"] == File.UploadStatus.UPLOADING

    def test_list_files_only_own_files(self, user_client):
        """Test that users only see their own files."""
        other_user = User.objects.create_user(email="other@example.com", password="pass123")

        # Create file for other user
        File.objects.create(
            file_name="other.mp4",
            file_size=100,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.COMPLETED,
            created_by=other_user,
        )

        response = user_client.get("/v1/files")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["results"]) == 0

    def test_retrieve_file(self, user_client, completed_file):
        """Test retrieving a single file."""
        response = user_client.get(f"/v1/files/{completed_file.public_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert str(data["id"]) == str(completed_file.public_id)
        assert data["file_name"] == "test.mp4"
        assert data["upload_status"] == File.UploadStatus.COMPLETED

    def test_update_file_metadata(self, user_client, completed_file):
        """Test updating file metadata."""
        response = user_client.patch(
            f"/v1/files/{completed_file.public_id}",
            {"name": "My Video", "description": "Test description"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        completed_file.refresh_from_db()
        assert completed_file.name == "My Video"
        assert completed_file.description == "Test description"

    def test_delete_file(self, user_client, completed_file):
        """Test deleting a file."""
        response = user_client.delete(f"/v1/files/{completed_file.public_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not File.objects.filter(id=completed_file.id).exists()


@pytest.mark.django_db
class TestSetParent:
    """Tests for POST /v1/files/{id}/set-parent."""

    @pytest.fixture
    def standalone_file(self, user_client):
        """Create a standalone file without parent."""
        return File.objects.create(
            file_name="test.mp4",
            file_size=10485760,
            file_content_type="video/mp4",
            upload_status=File.UploadStatus.COMPLETED,
            created_by=user_client.user,
        )

    def test_set_parent_success(self, user_client, standalone_file):
        """Test setting parent on standalone file."""
        user_ct = ContentType.objects.get_for_model(User)
        document_id, _ = DocumentId.objects.get_or_create(
            content_type=user_ct,
            object_id=user_client.user.id,
        )

        response = user_client.post(
            f"/v1/files/{standalone_file.public_id}/set-parent",
            {
                "parent_id": str(document_id.public_id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        standalone_file.refresh_from_db()
        # Parent is now a ForeignKey to DocumentId
        assert standalone_file.parent is not None
        assert standalone_file.parent.content_type_id == user_ct.id
        assert standalone_file.parent.object_id == user_client.user.id

    def test_set_parent_invalid_parent_id(self, user_client, standalone_file):
        """Test setting invalid parent_id."""
        import uuid

        response = user_client.post(
            f"/v1/files/{standalone_file.public_id}/set-parent",
            {
                "parent_id": str(uuid.uuid4()),  # Non-existent DocumentId
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_set_parent_requires_ownership(self, client, standalone_file):
        """Test that only file owner can set parent."""
        other_user = User.objects.create_user(email="other@example.com", password="pass123")
        client.force_authenticate(user=other_user)

        user_ct = ContentType.objects.get_for_model(User)
        document_id, _ = DocumentId.objects.get_or_create(
            content_type=user_ct,
            object_id=other_user.id,
        )

        response = client.post(
            f"/v1/files/{standalone_file.public_id}/set-parent",
            {
                "parent_id": str(document_id.public_id),
            },
            format="json",
        )

        # Returns 403 because permission check fails (user doesn't own the file)
        assert response.status_code == status.HTTP_403_FORBIDDEN
