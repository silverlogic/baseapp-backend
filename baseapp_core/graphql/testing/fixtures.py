import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from django.http import HttpResponse
from django.test import Client

from baseapp_core.graphql.utils import QueryData, capture_database_queries

DEFAULT_GRAPHQL_URL = "/graphql"

# Callable returned by the `graphql_client` / `graphql_user_client` fixtures, so tests can
# annotate the fixture parameter without restating the signature.
GraphQLClient = Callable[..., HttpResponse | tuple[HttpResponse, QueryData]]


def graphql_query(
    query,
    operation_name=None,
    input_data=None,
    variables=None,
    headers=None,
    client=None,
    graphql_url=None,
    content_type="application/json",
    extra=None,
    queries=None,
) -> HttpResponse | tuple[HttpResponse, QueryData]:
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
        graphql_url = DEFAULT_GRAPHQL_URL

    body = dict(extra or {})
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


@pytest.fixture(scope="session", autouse=True)
def build_graphql_schemas() -> None:
    """Import the URL conf (which builds the schemas) while every app is installed.

    Otherwise a test that disables apps can be the first to load it and leave a schema
    without those apps for the rest of the session.
    """
    from importlib import import_module

    from django.conf import settings

    import_module(settings.ROOT_URLCONF)


@pytest.fixture
def graphql_client(django_client) -> GraphQLClient:
    def func(*args, **kwargs) -> HttpResponse | tuple[HttpResponse, QueryData]:
        return graphql_query(*args, **kwargs, client=django_client)

    return func


@pytest.fixture
def graphql_client_with_queries(django_client) -> Callable[..., tuple[HttpResponse, QueryData]]:
    def func(*args, **kwargs) -> tuple[HttpResponse, QueryData]:
        with capture_database_queries() as queries:
            return graphql_query(*args, **kwargs, client=django_client, queries=queries)

    return func


@pytest.fixture
def graphql_user_client(django_user_client) -> GraphQLClient:
    def func(*args, **kwargs) -> HttpResponse | tuple[HttpResponse, QueryData]:
        return graphql_query(*args, **kwargs, client=django_user_client)

    return func


@pytest.fixture
def graphql_ws_user_client(django_user_client) -> Callable[..., Awaitable[Any]]:
    """Factory of graphql-transport-ws communicators authenticated as `django_user_client.user`.

    ```
    async with await graphql_ws_user_client() as ws:
        async for result in ws.subscribe(SUBSCRIPTION, variables): ...
    ```
    """
    from baseapp_core.strawberry.testing import ws_communicator

    async def connect(**connection_params: Any) -> Any:
        return await ws_communicator(django_user_client.user, **connection_params)

    return connect
