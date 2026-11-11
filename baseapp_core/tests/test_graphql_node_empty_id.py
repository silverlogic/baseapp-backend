import uuid
from base64 import b64encode

import pytest

pytestmark = pytest.mark.django_db

NODE_QUERY = """
    query Node($id: ID!) {
        node(id: $id) {
            id
        }
    }
"""


def test_node_query_with_empty_id_returns_null(graphql_client) -> None:
    """Regression for BASEAPP-BACKEND-TEMPLATE-5F: an empty id 500'd into Sentry."""
    response = graphql_client(NODE_QUERY, variables={"id": ""})
    content = response.json()

    assert "errors" not in content
    assert content["data"]["node"] is None


USER_QUERY = """
    query User($id: ID!) {
        user(id: $id) {
            id
        }
    }
"""

PARSE_ERROR = (
    'Unable to parse global ID "garbage". Make sure it is a base64 encoded string in the '
    'format: "TypeName:id". Exception message: Invalid Global ID'
)


@pytest.mark.parametrize("query", [NODE_QUERY, USER_QUERY])
def test_unparseable_id_is_an_error(graphql_client, query) -> None:
    content = graphql_client(query, variables={"id": "garbage"}).json()

    assert [e["message"] for e in content["errors"]] == [PARSE_ERROR]


def test_nonexistent_public_id_is_a_parse_error(graphql_client) -> None:
    missing = str(uuid.uuid4())
    content = graphql_client(NODE_QUERY, variables={"id": missing}).json()

    assert content["errors"][0]["message"].startswith(f'Unable to parse global ID "{missing}"')


@pytest.mark.parametrize("query", [NODE_QUERY, USER_QUERY])
def test_id_of_unknown_type_is_an_error(graphql_client, query) -> None:
    global_id = b64encode(b"Nope:1").decode()
    content = graphql_client(query, variables={"id": global_id}).json()

    assert [e["message"] for e in content["errors"]] == ['Relay Node "Nope" not found in schema']


def test_id_of_non_node_type_is_an_error(graphql_client) -> None:
    global_id = b64encode(b"PageInfo:1").decode()
    content = graphql_client(NODE_QUERY, variables={"id": global_id}).json()

    assert [e["message"] for e in content["errors"]] == [
        'ObjectType "PageInfo" does not implement the "Node" interface.'
    ]


def test_typed_field_with_empty_id_returns_null(graphql_client) -> None:
    content = graphql_client(USER_QUERY, variables={"id": ""}).json()

    assert "errors" not in content
    assert content["data"]["user"] is None
