from collections.abc import Callable
from typing import TYPE_CHECKING

from baseapp_core.hashids.strategies.interfaces import GraphQLResolverStrategy
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)

if TYPE_CHECKING:
    from django.db.models import Model


class PublicIdGraphQLResolverStrategy(GraphQLResolverStrategy):
    id_resolver: PublicIdResolverStrategy

    def to_global_id(self, model_instance, type_, id) -> str | None:
        if public_id := self.id_resolver.get_id_from_instance(model_instance):
            return str(public_id)
        return None

    def get_instance_from_global_id(self, info, global_id, get_node=False) -> "Model":
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

    def get_pk_from_global_id(self, global_id) -> int:
        if node := self.id_resolver.resolve_id(global_id):
            return node.pk
        raise self.NoInstanceFound(global_id)

    def _get_node(self, info, _content_type, _id, only_type=None) -> Callable | None:
        from baseapp_core.strawberry.relay import strawberry_node_type

        _type = _content_type.model_class().__name__
        return getattr(strawberry_node_type(info, _type, only_type), "get_node", None)
