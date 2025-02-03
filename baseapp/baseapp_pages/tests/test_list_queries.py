import pytest
import swapper

from .factories import PageFactory

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")

LIST_PAGES = """
    query {
        allPages {
            edges {
                node {
                    pk
                }
            }
        }
    }
"""


def test_anon_can_list_pages(graphql_client):
    page = PageFactory()

    response = graphql_client(
        query=LIST_PAGES,
    )

    content = response.json()

    assert content["data"]["allPages"]["edges"][0]["node"]["pk"] == page.pk


def test_owner_can_list_unpublished_pages(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user, status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query=LIST_PAGES,
    )

    content = response.json()

    assert content["data"]["allPages"]["edges"][0]["node"]["pk"] == page.pk


def test_anon_cant_list_unpublished_pages(graphql_client):
    PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_client(
        query=LIST_PAGES,
    )

    content = response.json()

    assert len(content["data"]["allPages"]["edges"]) == 0


def test_another_user_cant_list_unpublished_pages(graphql_user_client):
    PageFactory(status=Page.PageStatus.DRAFT)

    response = graphql_user_client(
        query=LIST_PAGES,
    )

    content = response.json()

    assert len(content["data"]["allPages"]["edges"]) == 0
