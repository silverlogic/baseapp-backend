from typing import TYPE_CHECKING

from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy

if TYPE_CHECKING:
    from django.db.models import Model


class GraphQLResolverStrategy:
    class NoInstanceFound(Exception):
        def __init__(self, global_id) -> None:
            super().__init__(f"No instance found for global id: {global_id}")

    def __init__(self, id_resolver: IdResolverStrategy) -> None:
        self.id_resolver = id_resolver

    def to_global_id(self, model_instance, type_, id) -> str | None:
        raise NotImplementedError

    def get_node_from_global_id(self, info, global_id, only_type=None) -> "Model | None":
        raise NotImplementedError

    def get_pk_from_global_id(self, global_id) -> int | str:
        raise NotImplementedError

    def get_instance_from_global_id(self, info, global_id, get_node=False) -> "Model":
        raise NotImplementedError
