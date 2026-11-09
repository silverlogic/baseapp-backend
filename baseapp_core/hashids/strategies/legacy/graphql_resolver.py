from typing import TYPE_CHECKING

from baseapp_core.hashids.strategies.interfaces import GraphQLResolverStrategy
from baseapp_core.hashids.utils import from_global_id, to_global_id

if TYPE_CHECKING:
    from django.db.models import Model


class LegacyGraphQLResolverStrategy(GraphQLResolverStrategy):
    def to_global_id(self, model_instance, type_, id) -> str:
        return to_global_id(type_, id)

    def get_pk_from_global_id(self, global_id) -> str:
        gid_type, gid = from_global_id(global_id)
        return gid

    def get_instance_from_global_id(self, info, global_id, get_node=False) -> "Model":
        from baseapp_core.strawberry.relay import strawberry_node_type

        gid_type, gid = from_global_id(global_id)
        strawberry_type = strawberry_node_type(info, gid_type)
        if get_node:
            return strawberry_type.get_node(info, gid)
        return strawberry_type.__strawberry_django_definition__.model.objects.get(pk=gid)
