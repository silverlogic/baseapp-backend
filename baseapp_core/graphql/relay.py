from graphene.relay import BaseGlobalIDType, DefaultGlobalIDType
from graphene.relay import GlobalID as GrapheneGlobalID
from graphene.relay import Node as GrapheneRelayNode
from graphene.relay.node import AbstractNode
from graphene.types.interface import InterfaceOptions

from baseapp_core.hashids.strategies import (
    graphql_get_node_from_global_id_using_strategy,
    graphql_to_global_id_using_strategy,
)


class GlobalID(GrapheneGlobalID):
    @staticmethod
    def id_resolver(parent_resolver, node, root, info, parent_type_name=None, **args):
        type_id = parent_resolver(root, info, **args)
        parent_type_name = parent_type_name or info.parent_type.name
        return node.to_global_id_via_strategy(root, parent_type_name, type_id)  # root._meta.name


class AbstractBaseappNode(GrapheneRelayNode):
    """
    The __init_subclass_with_meta__ method must be in an intermediate class to be properly called by
    SubclassWithMeta.__init_subclass__
    """

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, global_id_type=DefaultGlobalIDType, **options):
        assert issubclass(
            global_id_type, BaseGlobalIDType
        ), "Custom ID type need to be implemented as a subclass of BaseGlobalIDType."
        _meta = InterfaceOptions(cls)
        _meta.global_id_type = global_id_type
        _meta.fields = {
            "id": GlobalID(cls, global_id_type=global_id_type, description="The ID of the object")
        }

        # Workaround so query_optimizer.GraphQLASTWalker can resolve fragment_model from Interfaces.
        if model := options.get("model"):
            _meta.model = model

        # It has to go straight to the AbstractNode parent, because we are replacing the logic
        # inside of AbstractNode.
        super(AbstractNode, cls).__init_subclass_with_meta__(_meta=_meta, **options)

    @classmethod
    def to_global_id(cls, type_, id):
        """
        Legacy to_global_id method. Still required in case __init_subclass_with_meta__ isn't properly called.
        """
        return GrapheneRelayNode.to_global_id(type_, id)

    @classmethod
    def to_global_id_via_strategy(cls, model_instance, type_, id):
        raise NotImplementedError


class Node(AbstractBaseappNode):
    @classmethod
    def to_global_id_via_strategy(cls, model_instance, type_, id):
        return graphql_to_global_id_using_strategy(model_instance, type_, id)

    @classmethod
    def get_node_from_global_id(cls, info, global_id, only_type=None):
        return graphql_get_node_from_global_id_using_strategy(info, global_id, only_type)
