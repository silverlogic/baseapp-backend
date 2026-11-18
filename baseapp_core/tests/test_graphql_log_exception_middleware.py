import logging
from typing import Any

import pytest
from graphql import GraphQLError

from baseapp_core.graphql.middlewares import LogExceptionMiddleware


def _resolve_returning(error: Exception) -> Any:
    return LogExceptionMiddleware().resolve(lambda root, info, **args: error, None, None)


def test_authentication_required_error_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Regression for BASEAPP-BACKEND-TEMPLATE-GE.

    `login_required` rejecting an anonymous request is an expected client condition. The error
    must still reach the client, but it must not be logged at ERROR level: every such log record
    became a Sentry error event.
    """
    error = GraphQLError("authentication required", extensions={"code": "authentication_required"})

    with caplog.at_level(logging.DEBUG), pytest.raises(GraphQLError) as exc:
        _resolve_returning(error)

    assert exc.value is error
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


@pytest.mark.parametrize(
    "error",
    [
        ValueError("boom"),
        GraphQLError("plain graphql error"),
        GraphQLError("forbidden", extensions={"code": "permission_required"}),
    ],
)
def test_other_errors_are_still_logged(caplog: pytest.LogCaptureFixture, error: Exception) -> None:
    with caplog.at_level(logging.DEBUG), pytest.raises(type(error)):
        _resolve_returning(error)

    assert [record.levelno for record in caplog.records] == [logging.ERROR]
