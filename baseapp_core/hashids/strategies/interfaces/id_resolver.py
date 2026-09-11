from typing import Any


class IdResolverStrategy:
    def get_id_from_instance(self, instance) -> Any:
        raise NotImplementedError

    def resolve_id(self, id, **kwargs) -> Any:
        raise NotImplementedError
