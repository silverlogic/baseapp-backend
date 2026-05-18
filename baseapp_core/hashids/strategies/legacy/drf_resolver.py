from typing import Any, Optional, Type

from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class LegacyDRFResolverStrategy:
    def __init__(self, id_resolver: IdResolverStrategy):
        self.id_resolver = id_resolver

    def resolve_public_id_to_pk(  # NOSONAR
        self, id: str, expected_model: Optional[Type[Any]] = None
    ) -> Optional[int]:
        return id
