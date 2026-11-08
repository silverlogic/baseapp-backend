from typing import Generic

import strawberry
from strawberry import relay
from strawberry_django.relay import DjangoListConnection


@strawberry.type(name="Edge", description="An edge in a connection.")
class Edge(relay.Edge[relay.NodeType], Generic[relay.NodeType]):
    """Graphene's edge shape: `node` is nullable."""

    node: relay.NodeType | None = strawberry.field(description="The item at the end of the edge")


@strawberry.type(name="Connection", description="A connection to a list of items.")
class CountedConnection(DjangoListConnection[relay.NodeType]):
    """Graphene's `CountedConnection`: `totalCount` (window-optimized when selected) + `edgeCount`."""

    edges: list[Edge[relay.NodeType] | None] = strawberry.field(
        description="Contains the nodes in this connection"
    )

    @strawberry.field
    def edge_count(self) -> int | None:
        return len(self.edges)
