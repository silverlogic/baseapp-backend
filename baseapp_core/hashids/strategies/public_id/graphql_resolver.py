from baseapp_core.graphql.utils import get_model_from_graphql_object_type
from baseapp_core.hashids.strategies.interfaces.graphql_resolver import (
    GraphQLResolverStrategy,
)
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)


class PublicIdGraphQLResolverStrategy(GraphQLResolverStrategy):
    id_resolver: PublicIdResolverStrategy

    def to_global_id(self, type_, id):
        model = get_model_from_graphql_object_type(type_)
        instance = model.objects.get(pk=id)
        return self.id_resolver.get_id_from_instance(instance)

    def get_node_from_global_id(self, info, global_id, only_type=None):
        return self.id_resolver.resolve_id(global_id, None)

    def get_pk_from_global_id(self, global_id):
        if node := self.id_resolver.resolve_id(global_id, None):
            return node.pk
