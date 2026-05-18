from typing import Any

import graphene
from graphql import GraphQLResolveInfo


class CountedConnection(graphene.Connection):
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info: GraphQLResolveInfo, **kwargs: Any) -> int:
        return self.length

    def resolve_edge_count(self, info: GraphQLResolveInfo, **kwargs: Any) -> int:
        return len(self.edges)
