import pytest
import swapper
from django.contrib.auth.models import Permission

from .factories import PageFactory
from .utils import make_text_into_quill

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label


EDIT_MUTATION_QUERY = """
    mutation PageChange($input: PageEditInput!) {
        pageEdit(input: $input) {
            page {
                title
                body
            }
        }
    }
"""


def test_user_cant_edit_page(graphql_user_client):
    page = PageFactory()

    response = graphql_user_client(
        query=EDIT_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
                "urlPath": "/about",
                "title": "About Title",
                "body": "About content",
            }
        },
    )

    content = response.json()
    assert content["errors"][0]["message"] == "You don't have permission to edit this page"


def test_superuser_can_edit_page_localized(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    page = PageFactory(
        title_en="Title",
        body_en=make_text_into_quill("Body"),
    )

    graphql_user_client(
        query=EDIT_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
                "urlPath": "/sobre",
                "title": "Titulo sobre",
                "body": make_text_into_quill("Conteudo sobre"),
            }
        },
        headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
    )

    page.refresh_from_db()
    assert page.title_pt == "Titulo sobre"
    assert page.body_pt == make_text_into_quill("Conteudo sobre")
    assert page.title_en == "Title"
    assert page.body_en == make_text_into_quill("Body")

    url_path = page.url_paths.first()
    assert url_path.language == "pt"
    assert url_path.path == "/sobre"


def test_owner_can_edit_page(django_user_client, graphql_user_client):
    page = PageFactory(
        user=django_user_client.user,
        title_en="Title",
        body_en=make_text_into_quill("Body"),
    )

    graphql_user_client(
        query=EDIT_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
                "title": "Edited title",
                "body": make_text_into_quill("Edited body"),
            }
        },
    )

    page.refresh_from_db()
    assert page.title_en == "Edited title"
    assert page.body_en == make_text_into_quill("Edited body")


def test_user_with_permission_can_edit_page(django_user_client, graphql_user_client):
    perm = Permission.objects.get(content_type__app_label=page_app_label, codename="change_page")
    django_user_client.user.user_permissions.add(perm)

    page = PageFactory(
        title_en="Title",
        body_en=make_text_into_quill("Body"),
    )

    graphql_user_client(
        query=EDIT_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
                "title": "Edited title",
                "body": make_text_into_quill("Edited body"),
            }
        },
    )

    page.refresh_from_db()
    assert page.title_en == "Edited title"
    assert page.body_en == make_text_into_quill("Edited body")
