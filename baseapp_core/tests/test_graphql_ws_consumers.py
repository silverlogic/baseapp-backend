from unittest.mock import patch

import channels_graphql_ws
import pytest
from rest_framework_simplejwt.exceptions import InvalidToken

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer


def test_jwt_consumer_init_sets_auth_and_exceptions():
    with patch.object(
        channels_graphql_ws.GraphqlWsConsumer, "__init__", return_value=None
    ) as mock_super_init:
        consumer = GraphqlWsJWTAuthenticatedConsumer()

    mock_super_init.assert_called_once()
    assert consumer._auth is not None
    assert isinstance(consumer._exceptions, tuple)
    assert len(consumer._exceptions) == 3


@pytest.mark.asyncio
async def test_jwt_consumer_get_jwt_user_instance_logs_on_exception():
    with patch.object(channels_graphql_ws.GraphqlWsConsumer, "__init__", return_value=None):
        consumer = GraphqlWsJWTAuthenticatedConsumer()

    with patch.object(consumer._auth, "get_validated_token", side_effect=InvalidToken("bad")):
        result = await consumer.get_jwt_user_instance("bad_token")

    assert result is None
