from typing import Type

from baseapp_core.hashids.strategies.interfaces import (
    DRFResolverStrategy,
    GraphQLResolverStrategy,
    IdResolverStrategy,
    QuerysetAnnotatorStrategy,
)


class HashidsStrategyBundle:
    id_resolver: IdResolverStrategy
    graphql_resolver: GraphQLResolverStrategy
    queryset_annotator: QuerysetAnnotatorStrategy
    drf_resolver: DRFResolverStrategy

    def __init__(
        self,
        id_resolver: Type[IdResolverStrategy],
        graphql_resolver: Type[GraphQLResolverStrategy],
        queryset_annotator: Type[QuerysetAnnotatorStrategy],
        drf_resolver: Type[DRFResolverStrategy],
    ):
        self.id_resolver = id_resolver()
        self.graphql_resolver = graphql_resolver(id_resolver=self.id_resolver)
        self.drf_resolver = drf_resolver(id_resolver=self.id_resolver)
        self.queryset_annotator = queryset_annotator()
