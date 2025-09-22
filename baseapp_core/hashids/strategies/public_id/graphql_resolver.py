from baseapp_core.hashids.strategies.interfaces import GraphQLResolverStrategy
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)


class PublicIdGraphQLResolverStrategy(GraphQLResolverStrategy):
    id_resolver: PublicIdResolverStrategy

    def to_global_id(self, model_instance, type_, id):
        if public_id := self.id_resolver.get_id_from_instance(model_instance):
            return str(public_id)
        return None

    def get_node_from_global_id(self, info, global_id, only_type=None):
        instance = self.id_resolver.resolve_id(global_id, resolve_query=False)
        if not instance:
            raise self.NoInstanceFound(global_id)

        _content_type, _id = instance
        if get_node := self._get_node(info, _content_type, _id, only_type):
            return get_node(info, _id)

    def get_instance_from_global_id(self, info, global_id, get_node=False):
        if instance := self.id_resolver.resolve_id(global_id, resolve_query=(not get_node)):
            if get_node:
                _content_type, _id = instance
                if get_node := self._get_node(info, _content_type, _id):
                    return get_node(info, _id)
                raise Exception(
                    f"No get_node method found for {_content_type.model_class().__name__}"
                )
            return instance
        raise self.NoInstanceFound(global_id)

    def get_pk_from_global_id(self, global_id):
        if node := self.id_resolver.resolve_id(global_id):
            return node.pk
        raise self.NoInstanceFound(global_id)

    def _get_node(self, info, _content_type, _id, only_type=None):
        from baseapp_core.graphql import Node

        _type = _content_type.model_class().__name__

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

        return getattr(graphene_type, "get_node", None)
