import pytest

pytestmark = pytest.mark.django_db

QUERY = """
    query {
        me {
            id
            isAuthenticated
            metadata {
                metaTitle
            }
        }
    }
"""


def test_anon_cant_query_me(graphql_client):
    response = graphql_client(QUERY)
    content = response.json()

    assert content["data"]["me"] is None


def test_user_cant_query_me(django_user_client, graphql_user_client):
    response = graphql_user_client(QUERY)
    content = response.json()

    assert content["data"]["me"]["id"] == django_user_client.user.relay_id
    assert content["data"]["me"]["isAuthenticated"] is True


def test_me_query_with_metadata(graphql_user_client, django_user_client):
    response = graphql_user_client(QUERY)
    content = response.json()

    assert "errors" not in content
    assert content["data"]["me"]["metadata"] is not None
    assert content["data"]["me"]["metadata"]["metaTitle"] == django_user_client.user.get_full_name()
