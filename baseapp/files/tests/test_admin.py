import json

import pytest
import swapper
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.test import Client, RequestFactory
from django.urls import reverse

from baseapp_core.models import DocumentId

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")
User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser() -> User:
    return User.objects.create_superuser(email="admin@example.com", password="pass1234")


@pytest.fixture
def superuser_client(superuser: User) -> Client:
    client = Client()
    client.force_login(superuser)
    return client


def document_for(obj: Model) -> DocumentId:
    return DocumentId.objects.get(
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
    )


@pytest.fixture
def owner() -> User:
    return User.objects.create_user(email="owner@example.com", password="pass1234")


@pytest.fixture
def file_obj(owner: User) -> File:
    parent_file = File.objects.create(file_name="parent.pdf", created_by=owner)
    return File.objects.create(
        file_name="a.png", name="a.png", created_by=owner, parent=document_for(parent_file)
    )


@pytest.mark.parametrize(
    "model, fields",
    [
        (File, ("parent", "created_by", "profile")),
        (FileTarget, ("target",)),
    ],
)
def test_relation_fields_use_autocomplete_widgets(
    superuser: User, model: type[Model], fields: tuple[str, ...]
) -> None:
    """Every FK/O2O on the files admins renders as an autocomplete, not a full <select>."""
    request = RequestFactory().get("/")
    request.user = superuser
    model_admin = admin.site._registry[model]
    form = model_admin.get_form(request)

    for field in fields:
        assert field in model_admin.autocomplete_fields
        assert isinstance(form.base_fields[field].widget.widget, AutocompleteSelect)


def test_file_change_view_does_not_enumerate_document_ids(
    superuser_client: Client, owner: User, file_obj: File
) -> None:
    """The change form must not render every DocumentId row as an <option>."""
    others = [File.objects.create(file_name=f"other{i}.txt", created_by=owner) for i in range(5)]
    other_ids = [document_for(other).public_id for other in others]

    response = superuser_client.get(reverse("admin:files_file_change", args=[file_obj.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "admin-autocomplete" in content
    assert str(file_obj.parent.public_id) in content
    for public_id in other_ids:
        assert str(public_id) not in content


def test_file_parent_autocomplete_endpoint(superuser_client: Client, file_obj: File) -> None:
    """DocumentIdAdmin.search_fields back the `parent` autocomplete lookups."""
    response = superuser_client.get(
        reverse("admin:autocomplete"),
        {
            "app_label": File._meta.app_label,
            "model_name": File._meta.model_name,
            "field_name": "parent",
            "term": str(file_obj.parent.public_id),
        },
    )

    assert response.status_code == 200
    results = json.loads(response.content)["results"]
    assert [r["id"] for r in results] == [str(file_obj.parent_id)]


def test_file_target_change_view_renders(superuser_client: Client, file_obj: File) -> None:
    target, _ = FileTarget.objects.get_or_create(target=file_obj.parent)

    response = superuser_client.get(reverse("admin:files_filetarget_change", args=[target.pk]))

    assert response.status_code == 200
    assert "admin-autocomplete" in response.content.decode()


def test_file_changelist_renders(superuser_client: Client, file_obj: File) -> None:
    response = superuser_client.get(reverse("admin:files_file_changelist"))

    assert response.status_code == 200
