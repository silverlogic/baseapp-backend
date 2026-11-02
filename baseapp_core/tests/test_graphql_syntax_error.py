import logging

import pytest

pytestmark = pytest.mark.django_db


def test_malformed_query_is_a_client_error_not_a_logged_exception(graphql_client, caplog) -> None:
    """Regression for BASEAPP-BACKEND-TEMPLATE-FT (also FW, FV, FX).

    A query that fails to parse is a client mistake. The view must still answer with the
    syntax error, but it must not log it at ERROR level: every such log record became a
    Sentry error event.
    """
    with caplog.at_level(logging.DEBUG):
        response = graphql_client("queryy { __typename }")

    assert response.status_code == 400
    content = response.json()
    assert "data" not in content
    assert len(content["errors"]) == 1
    assert content["errors"][0]["message"].startswith("Syntax Error: Unexpected Name 'queryy'")

    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert error_records == []


def test_well_formed_query_still_executes(graphql_client) -> None:
    response = graphql_client("query { __typename }")

    assert response.status_code == 200
    assert response.json() == {"data": {"__typename": "Query"}}
