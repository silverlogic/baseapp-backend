"""
The files attached to an object, listed on its admin change page.

A file reaches its object through a `DocumentId` rather than a foreign key, which Django's
inlines are built on, so `FilesInline` finds the files itself. It only lists them: files arrive
through the upload API.
"""

from collections.abc import Iterator

import pytest
import swapper
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models import Model
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.urls import reverse

from baseapp.files.admin import FilesInline, file_link
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.admin_helpers import ModelAdmin
from baseapp_core.models import DocumentId

File = swapper.load_model("baseapp_files", "File")
Comment = swapper.load_model("baseapp_comments", "Comment")
User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(tmp_path) -> Iterator[None]:
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield


@pytest.fixture
def superuser() -> User:
    return User.objects.create_superuser(email="admin@example.com", password="pass1234")


@pytest.fixture
def admin_request(superuser: User) -> HttpRequest:
    request = RequestFactory().get("/")
    request.user = superuser
    return request


def attach(obj: Model, name: str = "a.png", **fields: object) -> "File":
    """A file attached to `obj` the way the upload API attaches one, with its bytes stored."""
    file_obj = File.objects.create(
        **{
            "parent": DocumentId.get_or_create_for_object(obj),
            "file_name": name,
            "file_size": 5,
            "file_content_type": "image/png",
            "upload_status": File.UploadStatus.COMPLETED,
            **fields,
        }
    )
    if file_obj.upload_status == File.UploadStatus.COMPLETED:
        file_obj.file.save(name, ContentFile(b"bytes"))
    return file_obj


def listed(obj: Model | None, request: HttpRequest) -> list["File"]:
    inline = FilesInline(Comment, admin.site)
    formset = inline.get_formset(request, obj)(instance=obj, queryset=inline.get_queryset(request))
    return [form.instance for form in formset.forms]


class TestFilesInline:
    def test_lists_only_the_objects_own_files_newest_first(
        self, admin_request: HttpRequest
    ) -> None:
        comment = CommentFactory()
        first = attach(comment, "first.png")
        second = attach(comment, "second.png")
        attach(CommentFactory(), "elsewhere.png")

        assert listed(comment, admin_request) == [second, first]

    def test_an_upload_still_in_progress_is_listed_too(self, admin_request: HttpRequest) -> None:
        comment = CommentFactory()
        pending = attach(comment, upload_status=File.UploadStatus.UPLOADING)

        assert listed(comment, admin_request) == [pending]

    def test_an_object_not_yet_saved_has_none(self, admin_request: HttpRequest) -> None:
        attach(CommentFactory())

        assert listed(None, admin_request) == []

    def test_it_lists_and_changes_nothing(self, admin_request: HttpRequest) -> None:
        comment = CommentFactory()
        attach(comment)
        inline = FilesInline(Comment, admin.site)
        formset = inline.get_formset(admin_request, comment)(instance=comment)

        assert not inline.has_add_permission(admin_request, comment)
        assert not inline.has_change_permission(admin_request, comment)
        assert not formset.can_delete
        assert formset.extra == 0
        # Only the hidden id a model formset always carries to tell its rows apart.
        assert all(set(form.fields) == {"id"} for form in formset.forms)

    def test_a_forged_post_saves_nothing(self, admin_request: HttpRequest) -> None:
        comment = CommentFactory()
        file_obj = attach(comment)
        inline = FilesInline(Comment, admin.site)
        prefix = "attached-files"
        # The page shows no extra forms, but a POST can claim one, naming an existing file.
        data = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-id": str(file_obj.pk),
        }
        formset = inline.get_formset(admin_request, comment)(data=data, instance=comment)
        files_before = File.objects.count()

        if formset.is_valid():
            formset.save()

        assert File.objects.count() == files_before

    def test_passes_the_admins_checks_without_a_foreign_key(self) -> None:
        class CommentAdmin(ModelAdmin):
            inlines = (FilesInline,)

        assert FilesInline(Comment, admin.site).check() == []
        assert CommentAdmin(Comment, admin.site).check() == []


class TestOnTheChangePage:
    def test_each_file_is_shown_with_a_link_to_it_and_to_its_admin(
        self, admin_request: HttpRequest
    ) -> None:
        class CommentAdmin(ModelAdmin):
            inlines = (FilesInline,)

        comment = CommentFactory()
        file_obj = attach(comment, "photo.png")
        attach(comment, "pending.png", upload_status=File.UploadStatus.UPLOADING)

        response = CommentAdmin(Comment, admin.site).change_view(admin_request, str(comment.pk))
        content = response.render().content.decode()

        assert response.status_code == 200
        assert 'id="attached-files-group"' in content
        assert file_obj.file.url in content
        assert reverse("admin:files_file_change", args=[file_obj.pk]) in content
        assert "pending.png" in content


class TestFileLink:
    def test_links_a_stored_file_by_its_name(self) -> None:
        file_obj = attach(CommentFactory(), "photo.png")

        link = file_link(file_obj)

        assert f'href="{file_obj.file.url}"' in link
        assert ">photo.png</a>" in link

    def test_takes_a_label(self) -> None:
        assert ">Open</a>" in file_link(attach(CommentFactory()), "Open")

    def test_a_file_with_nothing_stored_has_no_link(self) -> None:
        assert file_link(File(file_name="pending.png")) == "-"


class TestFileName:
    def test_a_file_is_named_by_its_display_name_first(self) -> None:
        assert str(File(name="Holiday photo", file_name="IMG_0001.png")) == "Holiday photo"

    def test_then_by_its_file_name(self) -> None:
        assert str(File(file_name="IMG_0001.png")) == "IMG_0001.png"

    def test_and_otherwise_as_django_names_it(self) -> None:
        file_obj = File.objects.create()

        assert str(file_obj) == f"{File._meta.object_name} object ({file_obj.pk})"
