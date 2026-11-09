from baseapp_core.hashids.strategies.legacy.graphql_resolver import (
    LegacyGraphQLResolverStrategy,
)


class PkGraphQLResolverStrategy(LegacyGraphQLResolverStrategy):
    """Ids are rendered like the legacy strategy; plain pks are accepted by typed node fields."""
