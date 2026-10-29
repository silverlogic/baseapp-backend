"""Where files are stored: the model's upload folder, fixed for an upload when it starts."""

from typing import Any, Dict
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
import swapper
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework import status

from baseapp.files.storage.base import safe_extension, storage_name_in_folder
from baseapp.files.storage.s3 import S3MultipartUploadHandler

File = swapper.load_model("baseapp_files", "File")

pytestmark = pytest.mark.django_db

PART_DATA = b"hello world"


@pytest.fixture
def media_root(tmp_path):
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield tmp_path


def initiate(client, file_name: str = "clip.mp4") -> Dict[str, Any]:
    response = client.post(
        "/v1/files/uploads",
        {
            "file_name": file_name,
            "file_size": len(PART_DATA),
            "file_content_type": "video/mp4",
            "num_parts": 1,
            "part_size": len(PART_DATA),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    return response.json()


def complete(client, user_client, initiated: Dict[str, Any]) -> None:
    parsed = urlparse(initiated["presigned_urls"][0]["url"])
    etag = client.put(
        f"{parsed.path}?{parsed.query}", data=PART_DATA, content_type="application/octet-stream"
    ).json()["etag"]
    response = user_client.post(
        f"/v1/files/uploads/{initiated['id']}/complete",
        {"parts": [{"part_number": 1, "etag": etag}]},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK, response.content


class TestUploadFolder:
    def test_uploads_are_stored_in_the_default_folder(self, client, user_client, media_root):
        initiated = initiate(user_client)
        file_obj = File.get_by_public_id(initiated["id"])

        assert file_obj.upload_storage_name.startswith("files/")
        assert file_obj.upload_storage_name.endswith(".mp4")

        complete(client, user_client, initiated)
        file_obj.refresh_from_db()
        assert file_obj.file.name == file_obj.upload_storage_name
        assert (media_root / file_obj.file.name).read_bytes() == PART_DATA

    def test_uploads_are_stored_in_the_folder_the_model_names(
        self, client, user_client, media_root
    ):
        with patch.object(File, "get_upload_folder", return_value="tenants/7/"):
            initiated = initiate(user_client)

        complete(client, user_client, initiated)

        file_obj = File.get_by_public_id(initiated["id"])
        assert file_obj.file.name.startswith("tenants/7/")
        assert (media_root / file_obj.file.name).read_bytes() == PART_DATA

    def test_an_upload_keeps_its_name_when_the_folder_changes_meanwhile(
        self, client, user_client, media_root
    ):
        with patch.object(File, "get_upload_folder", return_value="tenants/7"):
            initiated = initiate(user_client)

        with patch.object(File, "get_upload_folder", return_value="tenants/8"):
            complete(client, user_client, initiated)

        file_obj = File.get_by_public_id(initiated["id"])
        assert file_obj.file.name.startswith("tenants/7/")

    def test_the_stored_name_keeps_only_the_extension(self, user_client, media_root):
        initiated = initiate(user_client, file_name="Maria Lopez review.MP4")

        name = File.get_by_public_id(initiated["id"]).upload_storage_name

        assert "Maria" not in name
        assert name.endswith(".MP4")

    def test_an_upload_whose_folder_is_rejected_records_nothing(self, user_client, media_root):
        with patch.object(File, "get_upload_folder", return_value="../escape"):
            response = user_client.post(
                "/v1/files/uploads",
                {
                    "file_name": "clip.mp4",
                    "file_size": len(PART_DATA),
                    "file_content_type": "video/mp4",
                    "num_parts": 1,
                    "part_size": len(PART_DATA),
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not File.objects.exists()

    def test_an_upload_whose_name_would_be_too_long_never_reaches_the_storage(
        self, user_client, media_root
    ):
        with (
            patch.object(File, "get_upload_folder", return_value="t/" + "x" * 480),
            patch(
                "baseapp.files.storage.local.LocalUploadHandler.initiate_upload"
            ) as initiate_upload,
        ):
            response = user_client.post(
                "/v1/files/uploads",
                {
                    "file_name": "clip.mp4",
                    "file_size": len(PART_DATA),
                    "file_content_type": "video/mp4",
                    "num_parts": 1,
                    "part_size": len(PART_DATA),
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        initiate_upload.assert_not_called()
        assert not File.objects.exists()

    def test_a_file_saved_directly_keeps_its_name_on_the_file(self, media_root):
        file_obj = File.objects.create(file=ContentFile(PART_DATA, name="transcript.txt"))

        assert file_obj.file.name.startswith("files/")
        assert file_obj.upload_storage_name == ""

    def test_a_file_saved_directly_lands_in_the_upload_folder(self, media_root):
        with patch.object(File, "get_upload_folder", return_value="tenants/7"):
            file_obj = File.objects.create(file=ContentFile(PART_DATA, name="transcript.txt"))

        assert file_obj.file.name.startswith("tenants/7/")
        assert file_obj.file.name.endswith(".txt")


class TestS3UploadFolder:
    @pytest.fixture
    def s3_handler(self) -> S3MultipartUploadHandler:
        storage = MagicMock()
        storage.bucket_name = "bucket"
        storage.location = "media"
        storage.default_acl = None
        storage.get_object_parameters.return_value = {}
        client = storage.connection.meta.client
        client.create_multipart_upload.return_value = {"UploadId": "upload-id"}
        client.generate_presigned_url.return_value = "https://bucket/presigned"
        return S3MultipartUploadHandler(storage=storage)

    def test_the_stored_name_is_the_key_at_every_step(
        self, s3_handler: S3MultipartUploadHandler
    ) -> None:
        file_obj = File.objects.create(
            file_name="clip.mp4", upload_storage_name="tenants/7/abc.mp4"
        )
        client = s3_handler.s3_client

        s3_handler.initiate_upload(file_obj, num_parts=1, part_size=len(PART_DATA))
        name = s3_handler.complete_upload(file_obj, "upload-id", [{"part_number": 1, "etag": "e"}])
        s3_handler.abort_upload(file_obj, "upload-id")

        assert name == "tenants/7/abc.mp4"
        for call in (
            client.create_multipart_upload,
            client.complete_multipart_upload,
            client.abort_multipart_upload,
        ):
            assert call.call_args.kwargs["Key"] == "media/tenants/7/abc.mp4"

    def test_an_upload_started_before_names_were_kept_keeps_its_derived_key(
        self, s3_handler: S3MultipartUploadHandler
    ) -> None:
        file_obj = File.objects.create(file_name="clip.mp4")

        name = s3_handler._get_file_name(file_obj)

        assert name.startswith("files/")
        assert name.endswith(".mp4")
        assert s3_handler._get_file_name(file_obj) == name


@pytest.mark.parametrize(
    ("file_name", "extension"),
    [
        ("clip.mp4", "mp4"),
        ("../../etc/passwd", "bin"),
        ("folder\\clip.webm", "webm"),
        ("no-extension", "bin"),
        ("clip.averyveryverylongextension", "bin"),
        ("", "bin"),
    ],
)
def test_safe_extension(file_name: str, extension: str) -> None:
    assert safe_extension(file_name) == extension


@pytest.mark.parametrize(
    "folder", ["../escape", "tenants/../other", "tenants//7", "tenants\\7", "./tenants", "."]
)
def test_a_folder_that_is_not_a_plain_relative_path_is_rejected(folder: str) -> None:
    with patch.object(File, "get_upload_folder", return_value=folder):
        with pytest.raises(ValueError):
            storage_name_in_folder(File(file_name="clip.mp4"), "clip.mp4")


@pytest.mark.parametrize(
    ("folder", "prefix"), [("tenants/7", "tenants/7/"), ("/tenants/7/", "tenants/7/"), ("", "")]
)
def test_a_plain_relative_folder_is_accepted(folder: str, prefix: str) -> None:
    with patch.object(File, "get_upload_folder", return_value=folder):
        name = storage_name_in_folder(File(file_name="clip.mp4"), "clip.mp4")

    assert name.startswith(prefix)
    assert "/" not in name[len(prefix) :]
    assert name.endswith(".mp4")


def test_a_storage_name_longer_than_the_model_fields_is_rejected() -> None:
    with patch.object(File, "get_upload_folder", return_value="t/" + "x" * 480):
        with pytest.raises(ValueError):
            storage_name_in_folder(File(file_name="clip.mp4"), "clip.mp4")


def test_a_storage_name_that_fits_the_model_fields_is_accepted() -> None:
    # 32-character uuid + ".mp4" + "/" leaves 475 characters for the folder.
    with patch.object(File, "get_upload_folder", return_value="t/" + "x" * 473):
        name = storage_name_in_folder(File(file_name="clip.mp4"), "clip.mp4")

    assert len(name) == 512
