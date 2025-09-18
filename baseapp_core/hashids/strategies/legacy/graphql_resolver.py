from graphene.relay import Node as GrapheneRelayNode
from graphql_relay import from_global_id

from baseapp_core.hashids.strategies.interfaces import GraphQLResolverStrategy


class LegacyGraphQLResolverStrategy(GraphQLResolverStrategy):
    def to_global_id(self, model_instance, type_, id):
        return GrapheneRelayNode.to_global_id(type_, id)

    def get_node_from_global_id(self, info, global_id, only_type=None):
        """
        Needed to copy the original method from GrapheneRelayNode.get_node_from_global_id, because
        the original method uses the current class to verify if the ObjectType implements the
        'Node' interface.
        """
        from baseapp_core.graphql import Node

        _type, _id = GrapheneRelayNode.resolve_global_id(info, global_id)

        graphene_type = info.schema.get_type(_type)
        if graphene_type is None:
            raise Exception(f'Relay Node "{_type}" not found in schema')

        graphene_type = graphene_type.graphene_type

        if only_type:
            assert graphene_type == only_type, f"Must receive a {only_type._meta.name} id."

        # We make sure the ObjectType implements the "Node" interface
        if Node not in graphene_type._meta.interfaces:
            raise Exception(f'ObjectType "{_type}" does not implement the "{Node}" interface.')

        get_node = getattr(graphene_type, "get_node", None)
        if get_node:
            return get_node(info, _id)

    def get_pk_from_global_id(self, global_id):
        gid_type, gid = from_global_id(global_id)
        return gid

    def get_instance_from_global_id(self, info, global_id, get_node=False):
        gid_type, gid = from_global_id(global_id)
        object_type = info.schema.get_type(gid_type)
        if get_node:
            return object_type.graphene_type.get_node(info, gid)
        return object_type.graphene_type._meta.model.objects.get(pk=gid)
