import json

import channels
import channels_graphql_ws
import channels_graphql_ws.testing
import django
import pytest
from django.test import Client
from graphene_django.settings import graphene_settings
from rest_framework.authtoken.models import Token

from baseapp_core.graphql.utils import capture_database_queries

from ..consumers import GraphqlWsAuthenticatedConsumer

DEFAULT_GRAPHQL_URL = "/graphql"


def graphql_query(
    query,
    operation_name=None,
    input_data=None,
    variables=None,
    headers=None,
    client=None,
    graphql_url=None,
    content_type="application/json",
    extra={},
    queries=None,
):
    """
    Args:
        query (string)              - GraphQL query to run
        operation_name (string)     - If the query is a mutation or named query, you must
                                      supply the operation_name.  For annon queries ("{ ... }"),
                                      should be None (default).
        input_data (dict)           - If provided, the $input variable in GraphQL will be set
                                      to this value. If both ``input_data`` and ``variables``,
                                      are provided, the ``input`` field in the ``variables``
                                      dict will be overwritten with this value.
        variables (dict)            - If provided, the "variables" field in GraphQL will be
                                      set to this value.
        headers (dict)              - If provided, the headers in POST request to GRAPHQL_URL
                                      will be set to this value. Keys should be prepended with
                                      "HTTP_" (e.g. to specify the "Authorization" HTTP header,
                                      use "HTTP_AUTHORIZATION" as the key).
        client (django.test.Client) - Test client. Defaults to django.test.Client.
        graphql_url (string)        - URL to graphql endpoint. Defaults to "/graphql".
    Returns:
        Response object from client
    """
    if client is None:
        client = Client()
    if not graphql_url:
        graphql_url = graphene_settings.TESTING_ENDPOINT

    body = extra
    body["query"] = query
    if operation_name:
        body["operationName"] = operation_name
    if variables:
        body["variables"] = variables
    if input_data:
        if "variables" in body:
            body["variables"]["input"] = input_data
        else:
            body["variables"] = {"input": input_data}

    if content_type == "application/json":
        encoded_body = json.dumps(body)
    else:
        # to send multipart
        encoded_body = {}
        for key, value in body.items():
            if isinstance(value, dict):
                encoded_body[key] = json.dumps(value)
            else:
                encoded_body[key] = value

    if headers:
        resp = client.post(graphql_url, encoded_body, content_type=content_type, **headers)
    else:
        resp = client.post(graphql_url, encoded_body, content_type=content_type)
    if queries:
        return resp, queries
    return resp


@pytest.fixture
def graphql_client(django_client):
    def func(*args, **kwargs):
        return graphql_query(*args, **kwargs, client=django_client)

    return func


@pytest.fixture
def graphql_client_with_queries(django_client):
    def func(*args, **kwargs):
        with capture_database_queries() as queries:
            return graphql_query(*args, **kwargs, client=django_client, queries=queries)

    return func


@pytest.fixture
def graphql_user_client(django_user_client):
    def func(*args, **kwargs):
        return graphql_query(*args, **kwargs, client=django_user_client)

    return func


@pytest.fixture
def graphql_websocket(request):
    """PyTest fixture for testing GraphQL WebSocket backends.

    The fixture provides a method to setup GraphQL testing backend for
    the given GraphQL schema (query, mutation, and subscription). In
    particular: it sets up an instance of `GraphqlWsConsumer` and an
    instance of `GraphqlWsClient`. The former one is returned
    from the function.

    Syntax:
        graphql_websocket(
            *,
            consumer_attrs=None,
            communicator_kwds=None
        ):

    Args:
        consumer_attrs: `GraphqlWsConsumer` attributes dict. Optional.
        communicator_kwds: Extra keyword arguments for the Channels
            `channels.testing.WebsocketCommunicator`. Optional.

    Returns:
        An instance of the `GraphqlWsClient` class which has many
        useful GraphQL-related methods, see the `GraphqlWsClient`
        class docstrings for details.

    Use like this:
    ```
    def test_something(graphql_websocket):
        client = graphql_websocket(
            # `GraphqlWsConsumer` settings.
            consumer_attrs={"strict_ordering": True},
            # `channels.testing.WebsocketCommunicator` settings.
            communicator_kwds={"headers": [...]}
        )
        ...
    ```

    """

    # NOTE: We need Django DB to be initialized each time we work with
    # `GraphqlWsConsumer`, because it uses threads and sometimes calls
    # `django.db.close_old_connections()`.
    # del db

    issued_clients = []

    def client_constructor(
        *,
        consumer_attrs=None,
        communicator_kwds=None,
    ):
        """Setup GraphQL consumer and the communicator for tests."""

        ChannelsConsumer = GraphqlWsAuthenticatedConsumer

        # Set additional attributes to the `ChannelsConsumer`.
        if consumer_attrs is not None:
            for attr, val in consumer_attrs.items():
                setattr(ChannelsConsumer, attr, val)

        application = channels.routing.ProtocolTypeRouter(
            {
                "websocket": channels.routing.URLRouter(
                    [django.urls.path("graphql/", ChannelsConsumer.as_asgi())]
                )
            }
        )

        transport = channels_graphql_ws.testing.GraphqlWsTransport(
            application=application,
            path="graphql/",
            communicator_kwds=communicator_kwds,
        )

        client = channels_graphql_ws.testing.GraphqlWsClient(transport)
        issued_clients.append(client)
        return client

    yield client_constructor

    # Assert all issued client are properly finalized.
    for client in reversed(issued_clients):
        assert not client.connected, f"Test has left connected client: {request.node.nodeid}!"


@pytest.fixture
def graphql_ws_client(graphql_websocket):
    async def internal_client(django_user_client, consumer_attrs=None, communicator_kwds=None):
        client = graphql_websocket(
            consumer_attrs=consumer_attrs, communicator_kwds=communicator_kwds
        )

        token, _ = await Token.objects.aget_or_create(user=django_user_client.user)

        await client.connect_and_init(payload={"Authorization": token.key})

        return client

    return internal_client


@pytest.fixture
def graphql_ws_user_client(graphql_ws_client, django_user_client):
    async def internal_client(consumer_attrs=None, communicator_kwds=None):
        client = await graphql_ws_client(django_user_client, consumer_attrs, communicator_kwds)
        return client

    return internal_client
