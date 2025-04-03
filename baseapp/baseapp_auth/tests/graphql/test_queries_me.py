import pytest

pytestmark = pytest.mark.django_db

QUERY = """
    query {
        me {
            id
            isAuthenticated
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
