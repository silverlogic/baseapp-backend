from typing import Type

from baseapp_core.hashids.strategies.interfaces.graphql_resolver import (
    GraphQLResolverStrategy,
)
from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class HashidsStrategyBundle:
    id_resolver: IdResolverStrategy
    graphql_resolver: GraphQLResolverStrategy

    def __init__(
        self, id_resolver: Type[IdResolverStrategy], graphql_resolver: Type[GraphQLResolverStrategy]
    ):
        self.id_resolver = id_resolver()
        self.graphql_resolver = graphql_resolver(id_resolver=self.id_resolver)
