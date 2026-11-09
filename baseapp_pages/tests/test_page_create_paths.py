"""`pageCreate` paths that don't hit the TranslatedField limitation (see test_create_mutation)."""

import pytest
import swapper

from baseapp_pages.models import URLPath

from .factories import PageFactory

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")

CREATE_MUTATION_QUERY = """
    mutation PageCreate($input: PageCreateInput!) {
        pageCreate(input: $input) {
            clientMutationId
            errors { field messages }
            page { node { id } }
        }
    }
"""


def test_anonymous_cant_create_page(graphql_client) -> None:
    content = graphql_client(
        query=CREATE_MUTATION_QUERY, variables={"input": {"urlPath": "/about"}}
    ).json()

    assert content["errors"][0]["extensions"]["code"] == "authentication_required"
    assert not Page.objects.exists()


def test_taken_url_path_is_a_field_error(django_user_client, graphql_user_client) -> None:
    URLPath.objects.create(target=PageFactory(), path="/taken", language="en", is_active=True)
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    content = graphql_user_client(
        query=CREATE_MUTATION_QUERY,
        variables={"input": {"urlPath": "/taken", "clientMutationId": "c1"}},
    ).json()

    assert content["data"]["pageCreate"] == {
        "clientMutationId": "c1",
        "errors": [{"field": "url_path", "messages": ["URL Path already being used"]}],
        "page": None,
    }


def test_superuser_creates_page_with_url_path(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    content = graphql_user_client(
        query=CREATE_MUTATION_QUERY, variables={"input": {"urlPath": "/new"}}
    ).json()

    page = Page.objects.get()
    assert content["data"]["pageCreate"]["page"]["node"]["id"] == page.relay_id
    assert page.user == django_user_client.user
    assert page.url_paths.get().path == "/new"
