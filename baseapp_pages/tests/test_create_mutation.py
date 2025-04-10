import pytest
import swapper
from django.contrib.auth.models import Permission

from .utils import make_text_into_quill

pytest.skip(
    "Page.objects.create(**kwargs) does not work with TranslatedField", allow_module_level=True
)

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")

CREATE_MUTATION_QUERY = """
    mutation PageCreate($input: PageCreateInput!) {
        pageCreate(input: $input) {
            page {
                node {
                    title
                    body
                }
            }
        }
    }
"""


def test_superuser_can_create_page(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    graphql_user_client(
        query=CREATE_MUTATION_QUERY,
        variables={
            "input": {
                "urlPath": "/about",
                "title": "About Title",
                "body": make_text_into_quill("About content"),
            }
        },
    )

    page = Page.objects.get()
    assert page.title_en == "About Title"
    assert page.body_en == make_text_into_quill("About content")
    assert page.url_paths.first().path == "/about"


def test_user_cant_create_page(graphql_user_client):
    response = graphql_user_client(
        query=CREATE_MUTATION_QUERY,
        variables={
            "input": {
                "urlPath": "/about",
                "title": "About Title",
                "body": make_text_into_quill("About content"),
            }
        },
    )

    content = response.json()
    assert content["errors"][0]["message"] == "You don't have permission to create a page"


def test_user_with_permission_can_create_page(django_user_client, graphql_user_client):
    perm = Permission.objects.get(content_type__app_label="baseapp_pages", codename="add_page")
    django_user_client.user.user_permissions.add(perm)

    graphql_user_client(
        query=CREATE_MUTATION_QUERY,
        variables={
            "input": {
                "urlPath": "/about",
                "title": "About Title",
                "body": make_text_into_quill("About content"),
            }
        },
    )

    assert Page.objects.first().title_en == "About Title"


def test_superuser_can_create_page_localized(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    graphql_user_client(
        query=CREATE_MUTATION_QUERY,
        variables={
            "input": {
                "urlPath": "/sobre",
                "title": "Titulo sobre",
                "body": make_text_into_quill("Conteudo sobre"),
            }
        },
        headers={"HTTP_ACCEPT_LANGUAGE": "pt"},
    )

    page = Page.objects.get()
    assert page.title_pt == "Titulo sobre"
    assert page.body_pt == make_text_into_quill("Conteudo sobre")

    url_path = page.url_paths.first()
    assert url_path.language == "pt"
    assert url_path.path == "/sobre"
