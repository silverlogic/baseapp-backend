from unittest.mock import patch

import channels_graphql_ws

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer


def test_jwt_consumer_init_sets_auth_and_exceptions():
    with patch.object(channels_graphql_ws.GraphqlWsConsumer, "__init__", return_value=None):
        consumer = GraphqlWsJWTAuthenticatedConsumer()

    assert consumer._auth is not None
    assert isinstance(consumer._exceptions, tuple)
    assert len(consumer._exceptions) == 3
