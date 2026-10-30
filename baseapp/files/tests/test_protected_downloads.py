"""Protected downloads (``baseapp.files.downloads``): registry, endpoints, links, GraphQL, DRF, admin."""

import uuid
from types import SimpleNamespace
from typing import Any, Callable, Iterator
from unittest import mock
from urllib.parse import urlparse

import graphene
import pytest
import swapper
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, InMemoryStorage
from django.db import models
from django.http import Http404
from django.test import RequestFactory, override_settings
from graphql_relay import to_global_id
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied

from baseapp.files.downloads import (
    Gone,
    protected_content_response,
    protected_file_downloaded,
    protected_files,
)
from baseapp.files.downloads.admin import ProtectedFileAdminMixin
from baseapp.files.downloads.checks import (
    check_protected_file_storage,
    check_protected_files,
)
from baseapp.files.downloads.graphql import ProtectedFileField
from baseapp.files.downloads.responses import safe_filename
from baseapp.files.downloads.rest_framework import ProtectedFileSerializerField
from baseapp.files.downloads.services import describe_protected_file
from baseapp.files.downloads.tickets import ProtectedDownloadTicket
from baseapp.files.storage import (
    AliasStorage,
    files_storage,
    files_storage_is_private,
    get_wrapped_files_storage,
)
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_core.tests.fixtures import Client, DjangoClient
from baseapp_profiles.tests.factories import ProfileFactory

File = swapper.load_model("baseapp_files", "File")

pytestmark = pytest.mark.django_db

CONTENT = b"secret report"
KEY = "files.file.file"
OWNER_PERM = f"{File._meta.app_label}.change_{File._meta.model_name}"

LINK_MUTATION = """
    mutation ProtectedFileLink($input: ProtectedFileLinkInput!) {
        protectedFileLink(input: $input) {
            url
            expiresAt
            file {
                key
                objectId
                fileName
                contentType
                size
            }
        }
    }
"""


@pytest.fixture(autouse=True)
def media_root(tmp_path) -> Iterator[Any]:
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield tmp_path / "media"


@pytest.fixture(autouse=True)
def clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def register() -> Iterator[Callable[..., Any]]:
    """Register specs for one test; they are removed afterwards."""
    keys = []

    def _register(*args: Any, **kwargs: Any) -> Any:
        if not args:
            args = (File, "file")
        kwargs.setdefault("permission", OWNER_PERM)
        spec = protected_files.register(*args, **kwargs)
        keys.append(spec.key)
        return spec

    yield _register
    for key in keys:
        protected_files.unregister(key)


def allow_all(user: Any, request: Any) -> bool:
    return True


def stored_file(owner: Any = None, name: str = "report.pdf", content: bytes = CONTENT) -> Any:
    stored = files_storage.save(f"files/{name}", ContentFile(content))
    return File.objects.create(
        file=stored,
        file_name=name,
        file_size=len(content),
        file_content_type="application/pdf",
        upload_status=File.UploadStatus.COMPLETED,
        created_by=owner,
    )


def body(response: Any) -> bytes:
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return response.content


def jwt_client(user: Any) -> Client:
    client = Client()
    client.force_authenticate(user)
    return client


def session_client(user: Any) -> DjangoClient:
    client = DjangoClient()
    client.force_login(user)
    return client


def mint(user: Any, input_data: dict[str, Any], client: Any = None) -> dict[str, Any]:
    client = client or (session_client(user) if user else DjangoClient())
    return graphql_query(LINK_MUTATION, input_data=input_data, client=client).json()


def ticket_url_path(content: dict[str, Any]) -> str:
    assert "errors" not in content, content
    return urlparse(content["data"]["protectedFileLink"]["url"]).path


def error_code(content: dict[str, Any]) -> str:
    return content["errors"][0]["extensions"]["code"]


class TestRegistry:
    def test_defaults(self, register) -> None:
        spec = protected_files.register(File, "file")
        try:
            assert spec.key == KEY
            assert spec.permission == f"{File._meta.app_label}.view_{File._meta.model_name}"
            assert spec.disposition == "attachment"
            assert spec.cache_control == "private, no-store"
            assert protected_files.get(KEY) is spec
            assert KEY in protected_files and len(protected_files) >= 1
            assert protected_files.get_for(File, "file") is spec
            assert protected_files.get_for(File(), "file") is spec
            assert protected_files.get_for(File, "name") is None
        finally:
            protected_files.unregister(KEY)
        assert protected_files.get(KEY) is None

    def test_model_label(self, register) -> None:
        spec = register(File._meta.label, "file", key="by-label")
        assert spec.model is File

    @pytest.mark.parametrize(
        "kwargs",
        [{"key": "t"}, {"key": "bad/key"}, {"key": "a b"}, {"disposition": "download"}],
    )
    def test_invalid_registrations(self, register, kwargs) -> None:
        with pytest.raises(ImproperlyConfigured):
            register(**kwargs)

    def test_duplicate_key(self, register) -> None:
        register()
        with pytest.raises(ImproperlyConfigured):
            register()

    def test_system_check(self, register) -> None:
        assert check_protected_files() == []
        register(File, "missing", key="missing")
        register(File, "name", key="not-a-file")
        register(File, "file", key="bad-lookup", lookup_field="nope")
        register(File, "file", key="public-id", lookup_field="public_id")
        assert sorted(error.id for error in check_protected_files()) == [
            "baseapp_files.E010",
            "baseapp_files.E011",
            "baseapp_files.E012",
        ]

    def test_storage_warning(self, register, settings, tmp_path) -> None:
        settings.STORAGES = {
            **settings.STORAGES,
            "signed": {
                "BACKEND": "baseapp.files.storage.signed.SignedFileSystemStorage",
                "OPTIONS": {"location": str(tmp_path / "signed")},
            },
        }
        assert check_protected_file_storage() == []
        register(File, "missing", key="missing")  # E010 only
        assert check_protected_file_storage() == []

        register()  # File.file on the public default storage of the tests
        warnings = check_protected_file_storage()
        assert [warning.id for warning in warnings] == ["baseapp_files.W010"]
        assert f"{KEY!r}" in warnings[0].msg
        assert get_wrapped_files_storage().__class__.__name__ in warnings[0].msg

        field = File._meta.get_field("file")
        original = field.storage
        try:
            field.storage = AliasStorage("signed")
            assert files_storage_is_private(field.storage) is True
            assert check_protected_file_storage() == []
            field.storage = AliasStorage("unknown")
            warnings = check_protected_file_storage()
            assert [warning.id for warning in warnings] == ["baseapp_files.W010"]
            assert "AliasStorage('unknown')" in warnings[0].msg
        finally:
            field.storage = original


class TestAuthenticatedDownload:
    def url(self, file_obj: Any, key: str = KEY) -> str:
        return f"/v1/files/protected/{key}/{file_obj.pk}"

    def test_owner_with_jwt(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)

        response = jwt_client(owner).get(self.url(file_obj))

        assert response.status_code == status.HTTP_200_OK
        assert body(response) == CONTENT
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == 'attachment; filename="report.pdf"'
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"
        assert response["Referrer-Policy"] == "no-referrer"
        assert "Content-Security-Policy" not in response

    def test_owner_with_session(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)

        response = session_client(owner).get(self.url(file_obj))

        assert response.status_code == status.HTTP_200_OK
        assert body(response) == CONTENT

    def test_anonymous_is_401(self, register) -> None:
        register()
        file_obj = stored_file(UserFactory())
        assert Client().get(self.url(file_obj)).status_code == status.HTTP_401_UNAUTHORIZED

    def test_without_permission_is_403(self, register) -> None:
        register()
        file_obj = stored_file(UserFactory())
        response = jwt_client(UserFactory()).get(self.url(file_obj))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_allowed_when_the_spec_allows_it(self, register) -> None:
        register(permission=False)
        file_obj = stored_file(UserFactory())
        assert Client().get(self.url(file_obj)).status_code == status.HTTP_200_OK

    def test_outside_queryset_is_404(self, register) -> None:
        register(queryset=lambda user: File.objects.filter(created_by_id=user.pk))
        file_obj = stored_file(UserFactory())
        response = jwt_client(UserFactory()).get(self.url(file_obj))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize("object_id", ["999999", "not-a-number"])
    def test_unknown_object_is_404(self, register, object_id) -> None:
        register()
        response = jwt_client(UserFactory()).get(f"/v1/files/protected/{KEY}/{object_id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_key_is_404(self) -> None:
        response = jwt_client(UserFactory()).get("/v1/files/protected/nope.nope.file/1")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_id_lookup(self, register) -> None:
        register(lookup_field="public_id")
        owner = UserFactory()
        file_obj = stored_file(owner)
        client = jwt_client(owner)

        assert client.get(f"/v1/files/protected/{KEY}/{file_obj.public_id}").status_code == 200
        response = client.get(f"/v1/files/protected/{KEY}/{uuid.uuid4()}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_coded_errors_from_check_pass_through(self, register) -> None:
        def check(user: Any, obj: Any) -> None:
            raise PermissionDenied("Members only.", code="no_membership")

        register(check=check)
        owner = UserFactory()
        response = jwt_client(owner).get(self.url(stored_file(owner)))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "Members only."

    def test_gone(self, register) -> None:
        def check(user: Any, obj: Any) -> None:
            raise Gone()

        register(check=check)
        owner = UserFactory()
        response = jwt_client(owner).get(self.url(stored_file(owner)))
        assert response.status_code == status.HTTP_410_GONE

    def test_check_runs_as_the_current_profile(self, register) -> None:
        seen = []
        register(check=lambda user, obj: seen.append(user.current_profile))
        owner = UserFactory()
        profile = ProfileFactory(owner=owner)

        response = jwt_client(owner).get(
            self.url(stored_file(owner)), HTTP_CURRENT_PROFILE=profile.relay_id
        )

        assert response.status_code == status.HTTP_200_OK
        assert seen == [profile]

    def test_missing_file_without_ensure_is_404(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        files_storage.delete(file_obj.file.name)
        assert jwt_client(owner).get(self.url(file_obj)).status_code == 404

    def test_ensure_regenerates_a_missing_file(self, register) -> None:
        def ensure(obj: Any) -> Any:
            obj.file.save("regenerated.pdf", ContentFile(b"fresh"), save=True)
            return obj.file

        register(ensure=ensure)
        owner = UserFactory()
        file_obj = stored_file(owner)
        files_storage.delete(file_obj.file.name)

        response = jwt_client(owner).get(self.url(file_obj))

        assert response.status_code == status.HTTP_200_OK
        assert body(response) == b"fresh"

    def test_ensure_derives_bytes(self, register) -> None:
        register(ensure=lambda obj: b"derived", filename=lambda obj: "draft.pdf")
        owner = UserFactory()
        file_obj = File.objects.create(file_name="draft.pdf", created_by=owner)

        response = jwt_client(owner).get(self.url(file_obj))

        assert response.status_code == status.HTTP_200_OK
        assert response.content == b"derived"
        assert response["Content-Length"] == "7"
        assert response["Content-Disposition"] == 'attachment; filename="draft.pdf"'

    def test_ensure_returning_nothing_is_404(self, register) -> None:
        register(ensure=lambda obj: None)
        owner = UserFactory()
        file_obj = File.objects.create(file_name="draft.pdf", created_by=owner)
        assert jwt_client(owner).get(self.url(file_obj)).status_code == 404

    def test_ensure_returning_a_file(self, register) -> None:
        register(ensure=lambda obj: ContentFile(b"made", name="made.pdf"))
        owner = UserFactory()
        file_obj = File.objects.create(file_name="draft.pdf", created_by=owner)
        response = jwt_client(owner).get(self.url(file_obj))
        assert body(response) == b"made"

    def test_signal(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        received = []

        def receiver(**kwargs: Any) -> None:
            received.append(kwargs)

        protected_file_downloaded.connect(receiver)
        try:
            jwt_client(owner).get(self.url(file_obj))
        finally:
            protected_file_downloaded.disconnect(receiver)

        assert len(received) == 1
        assert received[0]["sender"] is File
        assert received[0]["instance"] == file_obj
        assert received[0]["field"] == "file"
        assert received[0]["key"] == KEY
        assert received[0]["user"] == owner
        assert received[0]["via"] == "session"


class TestResponseHeaders:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("../../etc/report.pdf", "report.pdf"),
            ("C:\\Users\\me\\report.pdf", "report.pdf"),
            ("evil\r\nSet-Cookie: x.pdf", "evilSet-Cookie: x.pdf"),
            ("trailing. ", "trailing"),
            ("", "download"),
            (None, "download"),
        ],
    )
    def test_safe_filename(self, name, expected) -> None:
        assert safe_filename(name) == expected

    def test_unicode_and_quotes_in_filename(self) -> None:
        response = protected_content_response(
            b"x", filename='Relatório "final".pdf', content_type="application/pdf"
        )
        assert response["Content-Disposition"] == (
            "attachment; filename*=utf-8''Relat%C3%B3rio%20%22final%22.pdf"
        )
        quoted = protected_content_response(
            b"x", filename='say "hi".pdf', content_type="application/pdf"
        )
        assert quoted["Content-Disposition"] == 'attachment; filename="say \\"hi\\".pdf"'

    def test_crlf_filename_cannot_split_headers(self) -> None:
        response = protected_content_response(
            b"x", filename="a\r\nX-Injected: 1.pdf", content_type="application/pdf"
        )
        assert "X-Injected" not in response.headers
        assert "\n" not in response["Content-Disposition"]

    def test_inline_safe_type_gets_the_default_csp(self) -> None:
        response = protected_content_response(
            b"x", filename="a.png", content_type="image/png", disposition="inline"
        )
        assert response["Content-Disposition"] == 'inline; filename="a.png"'
        assert response["Content-Security-Policy"] == "sandbox; default-src 'none'"

    def test_unsafe_inline_type_is_forced_to_attachment(self) -> None:
        response = protected_content_response(
            b"<script>", filename="a.html", content_type="text/html", disposition="inline"
        )
        assert response["Content-Disposition"].startswith("attachment;")
        assert "Content-Security-Policy" not in response

    def test_inline_with_csp(self) -> None:
        response = protected_content_response(
            b"<p>",
            filename="a.html",
            content_type="text/html",
            disposition="inline",
            csp="sandbox; default-src 'none'; style-src 'unsafe-inline'",
        )
        assert response["Content-Disposition"] == 'inline; filename="a.html"'
        assert response["Content-Security-Policy"] == (
            "sandbox; default-src 'none'; style-src 'unsafe-inline'"
        )
        assert response["X-Content-Type-Options"] == "nosniff"

    def test_spec_content_type_and_filename(self, register) -> None:
        register(
            filename=lambda obj: f"invoice-{obj.pk}.pdf",
            content_type="application/pdf",
            disposition="inline",
            cache_control="no-store",
        )
        owner = UserFactory()
        file_obj = stored_file(owner, name="raw.bin")

        response = jwt_client(owner).get(f"/v1/files/protected/{KEY}/{file_obj.pk}")

        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == f'inline; filename="invoice-{file_obj.pk}.pdf"'
        assert response["Cache-Control"] == "no-store"

    def test_unknown_type_falls_back_to_octet_stream(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner, name="payload.exe")
        response = jwt_client(owner).get(f"/v1/files/protected/{KEY}/{file_obj.pk}")
        assert response["Content-Type"] == "application/octet-stream"


class TestLinks:
    def test_mint_and_open(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)

        content = mint(owner, {"key": KEY, "objectId": str(file_obj.pk)})

        link = content["data"]["protectedFileLink"]
        assert link["url"].startswith("http://testserver/v1/files/protected/t/")
        assert link["expiresAt"]
        assert link["file"] == {
            "key": KEY,
            "objectId": str(file_obj.pk),
            "fileName": "report.pdf",
            "contentType": "application/pdf",
            "size": len(CONTENT),
        }
        response = Client().get(ticket_url_path(content))  # no credentials at all
        assert response.status_code == status.HTTP_200_OK
        assert body(response) == CONTENT
        assert response["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.parametrize("lookup_field", ["pk", "public_id"])
    def test_object_id_may_be_a_relay_or_public_id(self, register, lookup_field) -> None:
        register(lookup_field=lookup_field)
        owner = UserFactory()
        file_obj = stored_file(owner)
        type_name = File.get_graphql_object_type()._meta.name

        for object_id in (
            file_obj.relay_id,
            to_global_id(type_name, file_obj.pk),
            str(file_obj.public_id),
        ):
            content = mint(owner, {"key": KEY, "objectId": object_id})
            assert Client().get(ticket_url_path(content)).status_code == status.HTTP_200_OK
        unknown = mint(owner, {"key": KEY, "objectId": to_global_id(type_name, 999999)})
        assert error_code(unknown) == "not_found"

    def test_mint_errors(self, register) -> None:
        def check(user: Any, obj: Any) -> None:
            if obj.file_name == "revoked.pdf":
                raise Gone()

        register(check=check)
        owner = UserFactory()
        file_obj = stored_file(owner)
        revoked = stored_file(owner, name="revoked.pdf")
        empty = File.objects.create(file_name="empty.pdf", created_by=owner)

        assert error_code(mint(owner, {"key": "nope", "objectId": "1"})) == "not_found"
        assert error_code(mint(owner, {"key": KEY, "objectId": "999999"})) == "not_found"
        assert error_code(mint(owner, {"key": KEY, "objectId": str(empty.pk)})) == "not_found"
        assert error_code(mint(owner, {"key": KEY, "objectId": str(revoked.pk)})) == "gone"
        other = mint(UserFactory(), {"key": KEY, "objectId": str(file_obj.pk)})
        assert error_code(other) == "permission_denied"
        anonymous = mint(None, {"key": KEY, "objectId": str(file_obj.pk)})
        assert error_code(anonymous) == "not_authenticated"

    def test_anonymous_link_when_the_spec_allows_it(self, register) -> None:
        register(permission=False)
        file_obj = stored_file(UserFactory())
        content = mint(None, {"key": KEY, "objectId": str(file_obj.pk)})
        assert Client().get(ticket_url_path(content)).status_code == status.HTTP_200_OK

    def test_signal_via_ticket(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        path = ticket_url_path(mint(owner, {"key": KEY, "objectId": str(file_obj.pk)}))
        received = []

        def receiver(**kwargs: Any) -> None:
            received.append(kwargs)

        protected_file_downloaded.connect(receiver)
        try:
            Client().get(path)
        finally:
            protected_file_downloaded.disconnect(receiver)
        assert [(item["user"], item["via"]) for item in received] == [(owner, "ticket")]

    def ticket_for(self, spec: Any, file_obj: Any, user: Any) -> str:
        return f"/v1/files/protected/t/{ProtectedDownloadTicket.mint(spec, file_obj, user)}"

    def test_expired(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        with override_settings(BASEAPP_FILES_DOWNLOAD_TICKET_MAX_AGE=-1):
            response = Client().get(path)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "This download link has expired."

    def test_tampered(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        assert Client().get(path[:-2] + "xx").status_code == status.HTTP_403_FORBIDDEN
        assert Client().get("/v1/files/protected/t/garbage").status_code == 403

    def test_unregistered_key(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        protected_files.unregister(KEY)
        assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN

    def test_deactivated_user(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        owner.is_active = False
        owner.save()
        assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN

    def test_password_change(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        owner.set_password("another-password-1")
        owner.save()
        assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN

    def test_access_revoked_after_minting(self, register) -> None:
        spec = register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        path = self.ticket_for(spec, file_obj, owner)
        File.objects.filter(pk=file_obj.pk).update(created_by=UserFactory())
        assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN

    def test_replaced_file(self, register) -> None:
        spec = register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        path = self.ticket_for(spec, file_obj, owner)
        file_obj.file.save("other.pdf", ContentFile(b"new"), save=True)
        assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN

    def test_profile_is_rebound_while_usable(self, register) -> None:
        seen = []
        spec = register(check=lambda user, obj: seen.append(user.current_profile))
        owner = UserFactory()
        file_obj = stored_file(owner)
        own = ProfileFactory(owner=owner)
        foreign = ProfileFactory()

        owner.current_profile = own
        assert Client().get(self.ticket_for(spec, file_obj, owner)).status_code == 200
        owner.current_profile = foreign  # not (or no longer) usable by the owner
        assert Client().get(self.ticket_for(spec, file_obj, owner)).status_code == 200
        assert seen == [own, None]

    def test_user_check_hook(self, register) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        calls = []

        def deny(user: Any, request: Any) -> bool:
            calls.append(user)
            return False

        with override_settings(BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK=deny):
            assert Client().get(path).status_code == status.HTTP_403_FORBIDDEN
        assert calls == [owner]
        with override_settings(
            BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK=f"{__name__}.allow_all",
        ):
            assert Client().get(path).status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("stored", [False, True])
    def test_link_to_a_regenerated_file_survives_its_first_use(self, register, stored) -> None:
        def ensure(obj: Any) -> Any:
            obj.file.save("regenerated.pdf", ContentFile(b"fresh"), save=True)
            return obj.file

        spec = register(ensure=ensure)
        owner = UserFactory()
        if stored:  # a name is stored but the file is gone
            file_obj = stored_file(owner)
            files_storage.delete(file_obj.file.name)
        else:
            file_obj = File.objects.create(file_name="draft.pdf", created_by=owner)
        path = self.ticket_for(spec, file_obj, owner)

        first = Client().get(path)
        assert first.status_code == status.HTTP_200_OK
        assert body(first) == b"fresh"
        second = Client().get(path)  # a retried or double-clicked link
        assert second.status_code == status.HTTP_200_OK
        assert body(second) == b"fresh"

    def test_head_is_not_served(self, register) -> None:
        spec = register(ensure=lambda obj: pytest.fail("HEAD ran ensure"))
        owner = UserFactory()
        file_obj = stored_file(owner)
        received = []

        def receiver(**kwargs: Any) -> None:
            received.append(kwargs)

        protected_file_downloaded.connect(receiver)
        try:
            response = Client().head(self.ticket_for(spec, file_obj, owner))
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
            response = jwt_client(owner).head(f"/v1/files/protected/{KEY}/{file_obj.pk}")
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        finally:
            protected_file_downloaded.disconnect(receiver)
        assert received == []

    def test_logout_does_not_revoke_a_link(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        client = session_client(owner)
        path = ticket_url_path(mint(owner, {"key": KEY, "objectId": str(file_obj.pk)}, client))
        client.logout()
        assert Client().get(path).status_code == status.HTTP_200_OK  # documented

    def test_throttle(self, register, settings) -> None:
        spec = register()
        owner = UserFactory()
        path = self.ticket_for(spec, stored_file(owner), owner)
        assert Client().get(path).status_code == 200  # no rate configured: no limit
        assert Client().get(path).status_code == 200

        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"protected_download": "1/hour"},
        }
        cache.clear()
        assert Client().get(path).status_code == 200
        assert Client().get(path).status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestFields:
    def test_graphql_field(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        field = ProtectedFileField("file")

        def resolve(user: Any, obj: Any = file_obj) -> Any:
            info = SimpleNamespace(context=SimpleNamespace(user=user))
            return field.resolve_protected_file(obj, info)

        described = resolve(owner)
        assert (described.key, described.object_id, described.file_name) == (
            KEY,
            str(file_obj.pk),
            "report.pdf",
        )
        assert resolve(UserFactory()) is None
        assert resolve(AnonymousUser()) is None
        assert resolve(owner, File.objects.create(created_by=owner)) is None  # empty
        assert ProtectedFileField("file", key=KEY).get_spec(file_obj) is protected_files.get(KEY)

    def test_graphql_field_in_a_schema(self, register) -> None:
        def check(user: Any, obj: Any) -> None:
            if obj.file_name == "blocked.pdf":
                raise DjangoPermissionDenied()

        register(check=check)
        owner = UserFactory()
        own = stored_file(owner)
        foreign = stored_file(UserFactory(), name="foreign.pdf")
        blocked = stored_file(owner, name="blocked.pdf")
        empty = File.objects.create(file_name="empty.pdf", created_by=owner)

        class ProtectedFileHolder(DjangoObjectType):
            file = ProtectedFileField("file")

            class Meta:
                model = File
                fields = ("id", "file")
                skip_registry = True

        class Query(graphene.ObjectType):
            files = graphene.List(ProtectedFileHolder)

            def resolve_files(root: Any, info: Any) -> Any:
                return File.objects.filter(pk__in=[own.pk, foreign.pk, blocked.pk, empty.pk])

        request = RequestFactory().get("/")
        request.user = owner
        result = graphene.Schema(query=Query).execute(
            "{ files { id file { key objectId fileName contentType size } } }",
            context_value=request,
        )

        assert result.errors is None
        files = {int(item["id"]): item["file"] for item in result.data["files"]}
        assert files == {
            own.pk: {
                "key": KEY,
                "objectId": str(own.pk),
                "fileName": "report.pdf",
                "contentType": "application/pdf",
                "size": len(CONTENT),
            },
            foreign.pk: None,  # no permission
            blocked.pk: None,  # check raised Django's PermissionDenied
            empty.pk: None,
        }

    @pytest.mark.parametrize("error", [DjangoPermissionDenied, Http404])
    def test_django_errors_from_check_render_null(self, register, error) -> None:
        def check(user: Any, obj: Any) -> None:
            raise error()

        spec = register(check=check)
        owner = UserFactory()
        file_obj = stored_file(owner)

        class FileSerializer(serializers.ModelSerializer):
            file = ProtectedFileSerializerField()

            class Meta:
                model = File
                fields = ["id", "file"]

        context = {"request": SimpleNamespace(user=owner)}
        assert FileSerializer([file_obj], many=True, context=context).data[0]["file"] is None
        assert describe_protected_file(spec, file_obj, owner) is None
        expected = 403 if error is DjangoPermissionDenied else 404
        response = jwt_client(owner).get(f"/v1/files/protected/{KEY}/{file_obj.pk}")
        assert response.status_code == expected

    def test_unregistered_field_is_null(self) -> None:
        assert describe_protected_file(protected_files.get_for(File, "file"), None, None) is None

    def test_size_is_null_when_the_file_is_missing(self, register) -> None:
        spec = register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        files_storage.delete(file_obj.file.name)
        assert describe_protected_file(spec, file_obj, owner).size is None

    def test_size_is_null_when_the_s3_object_is_missing(self, register) -> None:
        exceptions = pytest.importorskip("botocore.exceptions")
        spec = register()
        owner = UserFactory()
        file_obj = stored_file(owner)
        missing = exceptions.ClientError({"Error": {"Code": "404"}}, "HeadObject")
        with mock.patch.object(type(get_wrapped_files_storage()), "size", side_effect=missing):
            assert describe_protected_file(spec, file_obj, owner).size is None

    def test_drf_field(self, register) -> None:
        register()
        owner = UserFactory()
        file_obj = stored_file(owner)

        class FileSerializer(serializers.ModelSerializer):
            file = ProtectedFileSerializerField()
            same = ProtectedFileSerializerField("file", key=KEY)

            class Meta:
                model = File
                fields = ["id", "file", "same"]

        def serialize(user: Any) -> dict[str, Any]:
            request = SimpleNamespace(user=user)
            return FileSerializer(file_obj, context={"request": request}).data

        expected = {
            "key": KEY,
            "object_id": str(file_obj.pk),
            "file_name": "report.pdf",
            "content_type": "application/pdf",
            "size": len(CONTENT),
        }
        data = serialize(owner)
        assert data["file"] == expected
        assert data["same"] == expected
        assert serialize(UserFactory())["file"] is None
        assert FileSerializer(file_obj).data["file"] is None  # no request: anonymous


class TestAdminMixin:
    def request(self) -> Any:
        request = RequestFactory().get("/")
        request.user = UserFactory(is_superuser=True, is_staff=True)
        return request

    def model_admin(self, **attrs: Any) -> Any:
        admin_class = type("FileLinkAdmin", (ProtectedFileAdminMixin, admin.ModelAdmin), attrs)
        return admin_class(File, admin.site)

    def test_registered_field_links_to_the_download(self, register) -> None:
        register()
        model_admin = self.model_admin()
        request = self.request()
        file_obj = stored_file(UserFactory())

        assert "file_link" in model_admin.get_readonly_fields(request, file_obj)
        assert "file" not in model_admin.get_fields(request, file_obj)
        assert "file" in model_admin.get_exclude(request, file_obj)
        html = model_admin.file_link(file_obj)
        assert f'href="/v1/files/protected/{KEY}/{file_obj.pk}"' in html
        assert 'rel="noopener noreferrer"' in html
        assert model_admin.file_link(File(file_name="empty")) == "-"
        assert model_admin.file_link.short_description == "file"
        with pytest.raises(AttributeError):
            model_admin.something_else  # noqa: B018

    def test_change_and_add_views_render(self, register) -> None:
        register()
        model_admin = self.model_admin()
        file_obj = stored_file(UserFactory())

        response = model_admin.change_view(self.request(), str(file_obj.pk))
        response.render()
        assert response.status_code == status.HTTP_200_OK
        html = response.content.decode()
        assert f'href="/v1/files/protected/{KEY}/{file_obj.pk}"' in html
        assert 'type="file"' not in html

        response = model_admin.add_view(self.request())
        response.render()
        assert response.status_code == status.HTTP_200_OK

    def test_public_unregistered_field_keeps_its_widget(self) -> None:
        model_admin = self.model_admin()
        request = self.request()
        assert model_admin.get_protected_file_fields() == []
        assert "file" in model_admin.get_fields(request)

    def test_private_unregistered_field_shows_its_name(self) -> None:
        field = File._meta.get_field("file")
        model_admin = self.model_admin(private_storage_aliases=("private",))
        file_obj = stored_file(UserFactory())
        original = field.storage
        field.storage = AliasStorage("private")
        try:
            assert model_admin.get_protected_file_fields() == ["file"]
            assert model_admin.file_link(file_obj) == file_obj.file.name
        finally:
            field.storage = original
        assert model_admin.is_private_storage(AliasStorage("default")) is False


class TestAliasStorage:
    def test_deconstructs_to_its_alias(self) -> None:
        storage = AliasStorage("private")
        path, args, kwargs = storage.deconstruct()
        assert (path, args, kwargs) == (
            "baseapp.files.storage.alias.AliasStorage",
            ("private",),
            {},
        )
        assert storage == AliasStorage("private")
        assert storage != AliasStorage("default")
        assert hash(storage) == hash(AliasStorage("private"))
        assert repr(storage) == "AliasStorage('private')"

    def test_resolves_the_alias_on_every_operation(self, settings, tmp_path) -> None:
        storage = AliasStorage("private")
        settings.STORAGES = {
            **settings.STORAGES,
            "private": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        }
        assert isinstance(storage.backend, InMemoryStorage)
        name = storage.save("docs/a.txt", ContentFile(b"abc"))
        assert storage.exists(name)
        assert storage.size(name) == 3
        assert storage.open(name).read() == b"abc"
        assert storage.listdir("docs") == ([], ["a.txt"])
        assert storage.get_valid_name("a b.txt") == "a_b.txt"
        assert storage.generate_filename("x/y.txt") == "x/y.txt"
        assert storage.get_available_name(name) != name
        assert storage.get_alternative_name("a", ".txt").startswith("a_")
        assert storage.url(name)
        for getter in (
            storage.get_accessed_time,
            storage.get_created_time,
            storage.get_modified_time,
        ):
            assert getter(name)
        storage.delete(name)
        assert not storage.exists(name)

        settings.STORAGES = {
            **settings.STORAGES,
            "private": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": str(tmp_path / "private")},
            },
        }
        assert isinstance(storage.backend, FileSystemStorage)
        name = storage.save("b.txt", ContentFile(b"b"))
        assert storage.path(name) == str(tmp_path / "private" / "b.txt")

    def test_on_a_model_field(self) -> None:
        field = models.FileField(storage=AliasStorage("private"))
        assert field.deconstruct()[3]["storage"] == AliasStorage("private")
