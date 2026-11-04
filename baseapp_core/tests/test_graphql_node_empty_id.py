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
