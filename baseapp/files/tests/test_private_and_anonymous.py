"""Private files storage (signed, expiring URLs) and anonymous uploads.

Both are opt-in per project: the defaults (``BASEAPP_FILES_STORAGE="default"``, anonymous
uploads off) must behave exactly as before, which the first tests pin down.
"""

import io
import os
import stat
from datetime import timedelta
from typing import Any, Dict, Iterator
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
import swapper
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.test import Client as DjangoClient
from django.test import override_settings
from django.utils import timezone
from easy_thumbnails.files import get_thumbnailer
from PIL import Image
from rest_framework import status
from storages.backends.s3boto3 import S3Boto3Storage

from baseapp.files.checks import check_private_files_storage, private_storage_errors
from baseapp.files.services.cleanup import (
    cleanup_unclaimed_anonymous_files,
    delete_unclaimed_anonymous_file,
)
from baseapp.files.storage import files_storage, files_storage_is_private
from baseapp.files.storage.local import LocalUploadHandler
from baseapp.files.tokens import AnonymousUploadToken, FileDownloadToken
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.graphql.testing.fixtures import GraphQLClient, graphql_query
from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory
from baseapp_core.tests.fixtures import Client

File = swapper.load_model("baseapp_files", "File")
FileObjectType = File.get_graphql_object_type()

pytestmark = pytest.mark.django_db

CONTENT = b"secret"

FILE_QUERY = """
    query File($id: ID!) {
        file(id: $id) {
            id
            url
            thumbnail(width: 10, height: 10)
        }
    }
"""

ATTACH_MUTATION = """
    mutation FileAttachToTarget($fileRelayIds: [ID]!, $targetObjectId: ID!, $uploadTokens: [String!]) {
        fileAttachToTarget(input: {
            fileRelayIds: $fileRelayIds
            targetObjectId: $targetObjectId
            uploadTokens: $uploadTokens
        }) {
            attachedFiles {
                node {
                    id
                    url
                }
            }
        }
    }
"""


@pytest.fixture(autouse=True)
def clear_throttle_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def media_root(tmp_path) -> Iterator[Any]:
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield tmp_path / "media"


@pytest.fixture
def private_storage(tmp_path, media_root) -> Iterator[Any]:
    """Point the files storage at a SignedFileSystemStorage, as a private project would."""
    location = tmp_path / "private"
    storages = {
        **settings.STORAGES,
        "files_private": {
            "BACKEND": "baseapp.files.storage.signed.SignedFileSystemStorage",
            "OPTIONS": {"location": str(location)},
        },
    }
    with override_settings(STORAGES=storages, BASEAPP_FILES_STORAGE="files_private"):
        yield location


@pytest.fixture
def anonymous_uploads() -> Iterator[None]:
    with override_settings(BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS=True):
        yield


def stored_file(**kwargs: Any) -> "File":
    """A completed file whose bytes are in the files storage."""
    name = files_storage.save("files/doc.txt", ContentFile(CONTENT))
    return File.objects.create(
        file=name,
        file_name="doc.txt",
        file_size=len(CONTENT),
        file_content_type="text/plain",
        upload_status=File.UploadStatus.COMPLETED,
        **kwargs,
    )


def stored_image(**kwargs: Any) -> "File":
    """A completed 40x40 PNG in the files storage."""
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buffer, format="PNG")
    name = files_storage.save("files/photo.png", ContentFile(buffer.getvalue()))
    return File.objects.create(
        file=name,
        file_name="photo.png",
        file_size=buffer.tell(),
        file_content_type="image/png",
        upload_status=File.UploadStatus.COMPLETED,
        **kwargs,
    )


def attached_to(comment) -> DocumentId:
    return DocumentId.get_or_create_for_object(comment)


def query_file(graphql_client: GraphQLClient, file_obj: "File") -> Dict[str, Any] | None:
    content = graphql_client(FILE_QUERY, variables={"id": file_obj.relay_id}).json()
    assert "errors" not in content, content
    return content["data"]["file"]


def path_of(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def initiate(client: Client, size: int = len(CONTENT)):
    return client.post(
        "/v1/files/uploads",
        {
            "file_name": "doc.txt",
            "file_size": size,
            "file_content_type": "text/plain",
            "num_parts": 1,
            "part_size": size,
        },
        format="json",
    )


def upload_part(client: Client, initiated: Dict[str, Any]) -> str:
    response = client.put(
        path_of(initiated["presigned_urls"][0]["url"]),
        data=CONTENT,
        content_type="application/octet-stream",
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["etag"]


def complete(client: Client, initiated: Dict[str, Any], etag: str, token: str | None):
    headers = {"HTTP_X_FILE_UPLOAD_TOKEN": token} if token else {}
    return client.post(
        f"/v1/files/uploads/{initiated['id']}/complete",
        {"parts": [{"part_number": 1, "etag": etag}]},
        format="json",
        **headers,
    )


class TestDefaultsUnchanged:
    def test_files_storage_is_the_default_storage_and_public(self) -> None:
        assert File._meta.get_field("file").storage is files_storage
        assert files_storage_is_private() is False

    def test_anyone_gets_the_url_of_a_public_file(
        self, graphql_client: GraphQLClient, media_root
    ) -> None:
        file_obj = stored_file(parent=attached_to(CommentFactory()))

        data = query_file(graphql_client, file_obj)

        assert data["url"].endswith(file_obj.file.url)

    def test_rest_file_api_still_hides_other_users_files(self, user_client: Client) -> None:
        file_obj = File.objects.create(
            file_name="other.txt", created_by=UserFactory(), upload_status="completed"
        )

        response = user_client.get(f"/v1/files/{file_obj.public_id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_upload_is_rejected(self, client: Client) -> None:
        response = initiate(client)

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        assert not File.objects.exists()

    def test_anonymous_attach_is_rejected(self, graphql_client: GraphQLClient) -> None:
        content = graphql_client(
            ATTACH_MUTATION,
            variables={"fileRelayIds": ["x"], "targetObjectId": CommentFactory().relay_id},
        ).json()

        assert content["errors"][0]["extensions"]["code"] == "authentication_required"

    def test_cleanup_does_nothing_while_anonymous_uploads_are_off(self, media_root) -> None:
        file_obj = stored_file(total_parts=1)
        File.objects.filter(pk=file_obj.pk).update(created=timezone.now() - timedelta(days=2))

        cleanup_unclaimed_anonymous_files()

        assert File.objects.filter(pk=file_obj.pk).exists()


class TestPrivateStorage:
    def test_url_is_a_signed_download_link_that_serves_the_file(
        self, private_storage, django_user_client: DjangoClient, graphql_user_client
    ) -> None:
        file_obj = stored_file(created_by=django_user_client.user)
        assert files_storage_is_private() is True

        url = query_file(graphql_user_client, file_obj)["url"]
        assert "/v1/files/download/" in url

        response = DjangoClient().get(path_of(url))

        assert response.status_code == status.HTTP_200_OK
        assert b"".join(response.streaming_content) == CONTENT
        assert response["Content-Disposition"] == 'attachment; filename="doc.txt"'
        assert response["X-Content-Type-Options"] == "nosniff"

    def test_download_link_rejects_a_tampered_or_expired_token(self, private_storage) -> None:
        file_obj = stored_file()
        token = FileDownloadToken.mint(file_obj.file.name)
        client = DjangoClient()

        tampered = client.get(f"/v1/files/download/{token}x")
        with patch.object(FileDownloadToken, "max_age", return_value=-1):
            expired = client.get(f"/v1/files/download/{token}")

        assert tampered.status_code == status.HTTP_403_FORBIDDEN
        assert expired.status_code == status.HTTP_403_FORBIDDEN

    def test_private_files_are_not_under_the_media_root(self, private_storage, media_root) -> None:
        file_obj = stored_file()

        assert (private_storage / file_obj.file.name).read_bytes() == CONTENT
        assert not (media_root / file_obj.file.name).exists()

    def test_stranger_gets_no_file_and_no_url(
        self, private_storage, graphql_client: GraphQLClient, graphql_user_client
    ) -> None:
        file_obj = stored_file(created_by=UserFactory())

        assert query_file(graphql_client, file_obj) is None
        assert query_file(graphql_user_client, file_obj) is None

    def test_viewers_of_the_target_get_the_url(
        self, private_storage, graphql_client: GraphQLClient
    ) -> None:
        file_obj = stored_file(created_by=UserFactory(), parent=attached_to(CommentFactory()))

        data = query_file(graphql_client, file_obj)

        assert "/v1/files/download/" in data["url"]

    def test_staff_with_the_view_permission_get_the_url(
        self, private_storage, django_client: DjangoClient
    ) -> None:
        staff = UserFactory()
        staff.user_permissions.add(
            Permission.objects.get(codename="view_file", content_type__app_label="files")
        )
        django_client.force_login(staff)
        file_obj = stored_file(created_by=UserFactory())

        content = graphql_query(
            FILE_QUERY, variables={"id": file_obj.relay_id}, client=django_client
        ).json()

        assert "/v1/files/download/" in content["data"]["file"]["url"]

    def test_thumbnail_is_private_and_signed_like_the_file(
        self, private_storage, media_root, django_user_client: DjangoClient, graphql_user_client
    ) -> None:
        file_obj = stored_image(created_by=django_user_client.user)

        url = query_file(graphql_user_client, file_obj)["thumbnail"]
        assert "/v1/files/download/" in url

        response = DjangoClient().get(path_of(url))
        assert response.status_code == status.HTTP_200_OK
        thumbnail = Image.open(io.BytesIO(b"".join(response.streaming_content)))
        assert thumbnail.size == (10, 10)

        token = path_of(url).rsplit("/", 1)[-1]
        thumbnail_name = FileDownloadToken.verify(token)
        assert (private_storage / thumbnail_name).exists()
        assert not (media_root / thumbnail_name).exists()
        with patch.object(FileDownloadToken, "max_age", return_value=-1):
            assert DjangoClient().get(path_of(url)).status_code == status.HTTP_403_FORBIDDEN

    def test_thumbnail_is_reused_and_signed_again(
        self, private_storage, django_user_client: DjangoClient, graphql_user_client
    ) -> None:
        file_obj = stored_image(created_by=django_user_client.user)

        with patch("baseapp.files.thumbnails.get_thumbnailer", wraps=get_thumbnailer) as spy:
            first = query_file(graphql_user_client, file_obj)["thumbnail"]
            second = query_file(graphql_user_client, file_obj)["thumbnail"]

        assert spy.call_count == 1
        name = FileDownloadToken.verify(path_of(first).rsplit("/", 1)[-1])
        assert FileDownloadToken.verify(path_of(second).rsplit("/", 1)[-1]) == name

    def test_no_thumbnail_for_a_file_that_is_not_an_image(
        self, private_storage, django_user_client: DjangoClient, graphql_user_client
    ) -> None:
        file_obj = stored_file(created_by=django_user_client.user)

        assert query_file(graphql_user_client, file_obj)["thumbnail"] is None

    def test_stranger_gets_no_thumbnail_of_a_visible_file(
        self, private_storage, graphql_client: GraphQLClient
    ) -> None:
        """thumbnail follows view_file even when the node itself is reached."""
        file_obj = stored_image(created_by=UserFactory())
        info = MagicMock()
        info.context.user = AnonymousUser()

        assert FileObjectType.resolve_thumbnail(file_obj, info) is None


@pytest.mark.usefixtures("private_storage", "anonymous_uploads")
class TestAnonymousUploads:
    def test_full_flow_with_the_upload_token(self, client: Client) -> None:
        initiated = initiate(client).json()
        token = initiated["upload_token"]
        file_obj = File.get_by_public_id(initiated["id"])
        assert file_obj.created_by is None

        etag = upload_part(client, initiated)
        response = complete(client, initiated, etag, token)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["upload_status"] == File.UploadStatus.COMPLETED
        assert "/v1/files/download/" in response.json()["url"]

    def test_logged_in_uploads_get_no_upload_token(self, user_client: Client) -> None:
        response = initiate(user_client)

        assert response.status_code == status.HTTP_201_CREATED
        assert "upload_token" not in response.json()

    def test_complete_and_abort_need_the_token(self, client: Client) -> None:
        initiated = initiate(client).json()
        etag = upload_part(client, initiated)
        other_token = AnonymousUploadToken.mint(File(pk=0))

        no_token = complete(client, initiated, etag, None)
        wrong_token = complete(client, initiated, etag, other_token)
        abort = client.delete(f"/v1/files/uploads/{initiated['id']}")
        abort_with_token = client.delete(
            f"/v1/files/uploads/{initiated['id']}",
            HTTP_X_FILE_UPLOAD_TOKEN=initiated["upload_token"],
        )

        assert no_token.status_code == status.HTTP_403_FORBIDDEN
        assert wrong_token.status_code == status.HTTP_403_FORBIDDEN
        assert abort.status_code == status.HTTP_403_FORBIDDEN
        assert abort_with_token.status_code == status.HTTP_204_NO_CONTENT

    def test_attach_with_the_token_and_read_back_a_signed_url(
        self, client: Client, graphql_client: GraphQLClient
    ) -> None:
        initiated = initiate(client).json()
        complete(client, initiated, upload_part(client, initiated), initiated["upload_token"])
        comment = CommentFactory()

        content = graphql_client(
            ATTACH_MUTATION,
            variables={
                "fileRelayIds": [initiated["relay_id"]],
                "targetObjectId": comment.relay_id,
                "uploadTokens": [initiated["upload_token"]],
            },
        ).json()

        assert "errors" not in content, content
        node = content["data"]["fileAttachToTarget"]["attachedFiles"][0]["node"]
        assert "/v1/files/download/" in node["url"]
        assert File.get_by_public_id(initiated["id"]).parent == attached_to(comment)

    def test_attach_without_the_token_is_rejected(
        self, client: Client, graphql_client: GraphQLClient
    ) -> None:
        initiated = initiate(client).json()
        complete(client, initiated, upload_part(client, initiated), initiated["upload_token"])

        content = graphql_client(
            ATTACH_MUTATION,
            variables={
                "fileRelayIds": [initiated["relay_id"]],
                "targetObjectId": CommentFactory().relay_id,
            },
        ).json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"

    def test_a_token_never_grants_a_logged_in_users_file(
        self, graphql_client: GraphQLClient
    ) -> None:
        file_obj = stored_file(created_by=UserFactory())

        content = graphql_client(
            ATTACH_MUTATION,
            variables={
                "fileRelayIds": [file_obj.relay_id],
                "targetObjectId": CommentFactory().relay_id,
                "uploadTokens": [AnonymousUploadToken.mint(file_obj)],
            },
        ).json()

        assert content["errors"][0]["extensions"]["code"] == "permission_required"

    @override_settings(BASEAPP_FILES_ANONYMOUS_MAX_FILE_SIZE=4)
    def test_anonymous_size_limit(self, client: Client, user_client: Client) -> None:
        response = initiate(client)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {
            "file_size": ["File is too large. The maximum size is 4\xa0bytes."]
        }
        assert initiate(user_client).status_code == status.HTTP_201_CREATED

    @override_settings(BASEAPP_FILES_ANONYMOUS_UPLOAD_RATE="1/hour")
    def test_anonymous_initiation_is_throttled(self, client: Client, user_client: Client) -> None:
        assert initiate(client).status_code == status.HTTP_201_CREATED
        assert initiate(client).status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert initiate(user_client).status_code == status.HTTP_201_CREATED


@pytest.mark.usefixtures("private_storage", "anonymous_uploads")
class TestUnclaimedAnonymousCleanup:
    def test_deletes_old_unattached_anonymous_uploads_with_their_bytes(self) -> None:
        old = timezone.now() - timedelta(days=2)
        unclaimed = stored_file(total_parts=1)
        attached = stored_file(total_parts=1, parent=attached_to(CommentFactory()))
        recent = stored_file(total_parts=1)
        owned = stored_file(total_parts=1, created_by=UserFactory())
        created_without_upload = stored_file()
        File.objects.exclude(pk=recent.pk).update(created=old)

        cleanup_unclaimed_anonymous_files()

        assert not File.objects.filter(pk=unclaimed.pk).exists()
        assert not files_storage.exists(unclaimed.file.name)
        remaining = set(File.objects.values_list("pk", flat=True))
        assert remaining == {attached.pk, recent.pk, owned.pk, created_without_upload.pk}

    def test_a_file_attached_after_the_scan_is_kept(self) -> None:
        """Cleanup re-checks each candidate under a row lock before deleting it."""
        cutoff = timezone.now() + timedelta(seconds=1)
        file_obj = stored_file(total_parts=1)
        # Attached between the scan and the deletion.
        File.objects.filter(pk=file_obj.pk).update(parent=attached_to(CommentFactory()))

        assert delete_unclaimed_anonymous_file(file_obj.pk, cutoff) is False
        assert File.objects.filter(pk=file_obj.pk).exists()
        assert files_storage.exists(file_obj.file.name)


@pytest.mark.usefixtures("private_storage", "anonymous_uploads")
class TestUploadTokenOnReads:
    """An anonymous uploader reads its file in a later request with the token header."""

    @pytest.mark.parametrize(
        "header, visible",
        [("valid", True), (None, False), ("invalid", False)],
    )
    def test_file_query_with_the_upload_token_header(
        self, django_client: DjangoClient, header: str | None, visible: bool
    ) -> None:
        file_obj = stored_file(total_parts=1)
        tokens = {"valid": AnonymousUploadToken.mint(file_obj), "invalid": "not-a-token"}
        headers = {"HTTP_X_FILE_UPLOAD_TOKEN": tokens[header]} if header else None

        content = graphql_query(
            FILE_QUERY, variables={"id": file_obj.relay_id}, client=django_client, headers=headers
        ).json()

        assert "errors" not in content, content
        if visible:
            assert "/v1/files/download/" in content["data"]["file"]["url"]
        else:
            assert content["data"]["file"] is None


class TestGetNode:
    def test_get_node_takes_id_as_keyword(self, django_user_client: DjangoClient) -> None:
        file_obj = stored_file(created_by=django_user_client.user)
        info = MagicMock()
        info.context.user = django_user_client.user

        assert FileObjectType.get_node(info=info, id=file_obj.pk) == file_obj


class TestUploadTempDir:
    def test_parts_for_a_storage_without_paths_go_to_a_private_directory(self, tmp_path) -> None:
        file_obj = File.objects.create(
            file_name="clip.mp4", created_by=UserFactory(), total_parts=1
        )
        handler = LocalUploadHandler(storage=InMemoryStorage())

        with override_settings(BASEAPP_FILES_UPLOAD_TEMP_DIR=str(tmp_path)):
            upload_id = handler.initiate_upload(file_obj, num_parts=1, part_size=4)["upload_id"]
            handler.upload_part(upload_id, part_number=1, data=b"data")
            temp_dir = tmp_path / "temp_uploads" / upload_id

            assert (temp_dir / "part_1").read_bytes() == b"data"
            assert stat.S_IMODE(os.stat(temp_dir).st_mode) == 0o700


class TestPrivateStorageChecks:
    @pytest.mark.parametrize(
        "options, error_ids",
        [
            ({"querystring_auth": True, "default_acl": "private"}, []),
            (
                {"querystring_auth": True, "default_acl": "private", "custom_domain": "cdn.x.io"},
                ["baseapp_files.E001"],
            ),
            ({"querystring_auth": True, "default_acl": "public-read"}, ["baseapp_files.E002"]),
            (
                {
                    "querystring_auth": True,
                    "default_acl": "private",
                    "object_parameters": {"ACL": "public-read"},
                },
                ["baseapp_files.E002"],
            ),
            # Public storage: nothing to check.
            (
                {"querystring_auth": False, "default_acl": "public-read", "custom_domain": "x.io"},
                [],
            ),
        ],
    )
    def test_signed_storage_that_still_serves_public_urls_is_an_error(
        self, options: Dict[str, Any], error_ids: list
    ) -> None:
        storage = S3Boto3Storage(bucket_name="b", **options)

        assert [error.id for error in private_storage_errors(storage)] == error_ids

    def test_the_check_inspects_the_files_storage(self) -> None:
        storages = {
            **settings.STORAGES,
            "files_s3": {
                "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
                "OPTIONS": {
                    "bucket_name": "b",
                    "querystring_auth": True,
                    "default_acl": "public-read",
                },
            },
        }
        with override_settings(STORAGES=storages, BASEAPP_FILES_STORAGE="files_s3"):
            assert [error.id for error in check_private_files_storage()] == ["baseapp_files.E002"]
