"""Tests for the presigned upload-part endpoint backed by local storage.

Exercises the full local upload flow: the initiate REST endpoint (which uses
LocalUploadHandler in tests since default storage is FileSystemStorage)
returns presigned URLs containing signed tokens, and the token-authenticated
PUT endpoint stores the part data.
"""

from datetime import timedelta
from typing import Any, Dict
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
import swapper
from django.conf import settings
from django.core import signing
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status

File = swapper.load_model("baseapp_files", "File")

pytestmark = pytest.mark.django_db

PART_DATA = b"hello world"


@pytest.fixture
def temp_media_root(tmp_path):
    """Use a temporary directory for media root."""
    with patch.object(settings, "MEDIA_ROOT", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def initiated_upload(user_client, temp_media_root) -> Dict[str, Any]:
    """Initiate a single-part upload through the REST endpoint with local storage."""
    response = user_client.post(
        "/v1/files/uploads",
        {
            "file_name": "doc.txt",
            "file_size": len(PART_DATA),
            "file_content_type": "text/plain",
            "num_parts": 1,
            "part_size": len(PART_DATA),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def presigned_path(presigned_url: Dict[str, Any]) -> str:
    """Extract the relative path (with token query string) from a presigned URL."""
    parsed = urlparse(presigned_url["url"])
    return f"{parsed.path}?{parsed.query}"


def put_part(client, path: str, data: bytes = PART_DATA):
    """PUT raw binary data to a presigned upload-part path."""
    return client.put(path, data=data, content_type="application/octet-stream")


class TestPresignedUploadPart:
    """Tests for PUT /v1/files/presigned-uploads/{id}/upload-part/{part}?token=..."""

    def test_upload_part_success(self, client, temp_media_root, initiated_upload):
        """A valid token uploads the part and returns the etag in body and header."""
        path = presigned_path(initiated_upload["presigned_urls"][0])

        response = put_part(client, path)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["part_number"] == 1
        assert len(data["etag"]) == 32  # MD5 hex digest
        assert response["ETag"] == data["etag"]

        part_file = temp_media_root / "temp_uploads" / initiated_upload["upload_id"] / "part_1"
        assert part_file.read_bytes() == PART_DATA

    def test_full_upload_flow(self, client, user_client, temp_media_root, initiated_upload):
        """Upload a part via presigned URL, then complete the upload."""
        path = presigned_path(initiated_upload["presigned_urls"][0])
        etag = put_part(client, path).json()["etag"]

        response = user_client.post(
            f"/v1/files/uploads/{initiated_upload['id']}/complete",
            {"parts": [{"part_number": 1, "etag": etag}]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["upload_status"] == File.UploadStatus.COMPLETED

        file_obj = File.get_by_public_id(initiated_upload["id"])
        assert file_obj.upload_status == File.UploadStatus.COMPLETED
        assert (temp_media_root / file_obj.file.name).read_bytes() == PART_DATA

    def test_missing_token(self, client, initiated_upload):
        """A request without a token is rejected."""
        path = presigned_path(initiated_upload["presigned_urls"][0]).split("?")[0]

        response = put_part(client, path)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing token" in response.json()["error"]

    def test_tampered_token(self, client, initiated_upload):
        """A token with an invalid signature is rejected."""
        path = presigned_path(initiated_upload["presigned_urls"][0])

        response = put_part(client, path + "tampered")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token signature" in response.json()["error"]

    def test_token_for_wrong_part(self, client, initiated_upload):
        """A valid token cannot be reused for a different part number."""
        parsed = urlparse(initiated_upload["presigned_urls"][0]["url"])
        wrong_part_path = parsed.path.replace("/upload-part/1", "/upload-part/2")

        response = put_part(client, f"{wrong_part_path}?{parsed.query}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token for this file/part" in response.json()["error"]

    def test_expired_token(self, client, initiated_upload):
        """A token older than 1 hour is rejected."""
        file_obj = File.get_by_public_id(initiated_upload["id"])

        with freeze_time(timezone.now() - timedelta(hours=2)):
            token = signing.dumps(
                {
                    "file_id": file_obj.id,
                    "part_number": 1,
                    "upload_id": file_obj.upload_id,
                }
            )

        response = put_part(
            client, f"/v1/files/presigned-uploads/{file_obj.id}/upload-part/1?token={token}"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token has expired" in response.json()["error"]

    def test_upload_part_invalid_status(self, client, initiated_upload):
        """Parts cannot be uploaded once the file is no longer pending/uploading."""
        file_obj = File.get_by_public_id(initiated_upload["id"])
        file_obj.upload_status = File.UploadStatus.COMPLETED
        file_obj.save(update_fields=["upload_status"])

        path = presigned_path(initiated_upload["presigned_urls"][0])
        response = put_part(client, path)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot upload parts" in response.json()["error"]

    def test_upload_part_number_out_of_range(self, client, initiated_upload):
        """A part number above total_parts is rejected even with a valid token."""
        file_obj = File.get_by_public_id(initiated_upload["id"])
        token = signing.dumps(
            {
                "file_id": file_obj.id,
                "part_number": 5,
                "upload_id": file_obj.upload_id,
            }
        )

        response = put_part(
            client, f"/v1/files/presigned-uploads/{file_obj.id}/upload-part/5?token={token}"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid part number" in response.json()["error"]

    def test_token_for_other_file(self, client, user_client, temp_media_root, initiated_upload):
        """A token signed for one file cannot be used on another file's URL."""
        other_file = File.objects.create(
            file_name="other.txt",
            file_size=len(PART_DATA),
            file_content_type="text/plain",
            upload_status=File.UploadStatus.UPLOADING,
            upload_id="other-upload-id",
            total_parts=1,
            created_by=user_client.user,
        )

        parsed = urlparse(initiated_upload["presigned_urls"][0]["url"])
        response = put_part(
            client,
            f"/v1/files/presigned-uploads/{other_file.id}/upload-part/1?{parsed.query}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token for this file/part" in response.json()["error"]
