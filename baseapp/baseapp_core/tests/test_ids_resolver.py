from base64 import b64encode

import pytest

from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

QUERY = """
    query GetUser($id: ID!) {
        user(id: $id) {
            id
            pk
        }
    }
"""


def test_get_node_from_global_id_works_properly_with_django_raw_ids(graphql_client):
    # The global_id is created by a Base64-encoding string in the format "TypeName:ID".
    # For certain IDs (like 1586), the resulting Base64 string will mislead how Graphene resolves the global_id to _type and _id. e.g. "1586" will be resolved as _type="ן" and _id="".
    # This test ensures that our custom Node handles these edge cases properly.
    user = UserFactory(id=1586)
    response = graphql_client(QUERY, variables={"id": user.pk})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["pk"] == user.pk


def test_get_node_from_global_id_works_properly(graphql_client):
    # this test ensures our custom Node can properly resolve global ids
    global_id = b64encode("User:1586".encode()).decode()
    user = UserFactory(id=1586)
    response = graphql_client(QUERY, variables={"id": global_id})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["pk"] == user.pk
