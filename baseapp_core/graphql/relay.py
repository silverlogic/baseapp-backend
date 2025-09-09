from graphene.relay import Node as GrapheneRelayNode

from baseapp_core.hashids.strategies import (
    graphql_get_node_from_global_id_using_strategy,
    graphql_to_global_id_using_strategy,
)


class Node(GrapheneRelayNode):
    class Meta:
        name = "NodeV2"

    @classmethod
    def to_global_id(cls, type_, id):
        return graphql_to_global_id_using_strategy(type_, id)

    @classmethod
    def get_node_from_global_id(cls, info, global_id, only_type=None):
        return graphql_get_node_from_global_id_using_strategy(info, global_id, only_type)
