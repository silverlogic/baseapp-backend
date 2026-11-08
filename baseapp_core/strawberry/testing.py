"""Run one GraphQL operation against the Graphene and the Strawberry endpoints and compare them."""

import copy
from dataclasses import dataclass
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.test import Client

from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.graphql.utils import QueryData, capture_database_queries

GRAPHENE_GRAPHQL_URL = "/graphql"
STRAWBERRY_GRAPHQL_URL = "/graphql/strawberry"


@dataclass
class EndpointResult:
    content: dict[str, Any]
    queries: QueryData


@dataclass
class ParityResult:
    graphene: EndpointResult
    strawberry: EndpointResult

    def report(self, label: str) -> str:
        return (
            f"PARITY {label}: graphene={self.graphene.queries.count} queries, "
            f"strawberry={self.strawberry.queries.count} queries"
        )


def run_on_endpoint(
    client: Client,
    url: str,
    query: str,
    variables: dict | None = None,
    headers: dict | None = None,
) -> EndpointResult:
    ContentType.objects.clear_cache()
    with capture_database_queries() as queries:
        response = graphql_query(
            query,
            variables=copy.deepcopy(variables),
            client=client,
            graphql_url=url,
            headers=headers,
            extra={},
        )
    return EndpointResult(content=response.json(), queries=queries)


def run_on_both(
    client: Client, query: str, variables: dict | None = None, headers: dict | None = None
) -> ParityResult:
    """Graphene first, then Strawberry, each with a cold ContentType cache and its own query log."""
    return ParityResult(
        graphene=run_on_endpoint(client, GRAPHENE_GRAPHQL_URL, query, variables, headers),
        strawberry=run_on_endpoint(client, STRAWBERRY_GRAPHQL_URL, query, variables, headers),
    )
