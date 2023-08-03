import json

from django.test import Client
from graphene_django.settings import graphene_settings

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
    return resp
