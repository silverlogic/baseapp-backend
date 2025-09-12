from baseapp_core.hashids.strategies.interfaces import GraphQLResolverStrategy
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)


class PublicIdGraphQLResolverStrategy(GraphQLResolverStrategy):
    id_resolver: PublicIdResolverStrategy

    def to_global_id(self, model_instance, type_, id):
        return str(self.id_resolver.get_id_from_instance(model_instance))

    def get_node_from_global_id(self, info, global_id, only_type=None):
        from baseapp_core.graphql import Node

        instance = self.id_resolver.resolve_id(global_id, None)
        _id = instance.pk
        _type = instance.__class__.__name__

        graphene_type = info.schema.get_type(_type)
        if graphene_type is None:
            raise Exception(f'Relay Node "{_type}" not found in schema')
        graphene_type = graphene_type.graphene_type

        if only_type:
            assert graphene_type == only_type, f"Must receive a {only_type._meta.name} id."

        # We make sure the ObjectType implements the "Node" interface
        if Node not in graphene_type._meta.interfaces:
            raise Exception(
                f'ObjectType "{graphene_type._meta.name}" does not implement the "{Node}" interface.'
            )

        get_node = getattr(graphene_type, "get_node", None)
        if get_node:
            return get_node(info, _id)

    def get_pk_from_global_id(self, global_id):
        if node := self.id_resolver.resolve_id(global_id, None):
            return node.pk
