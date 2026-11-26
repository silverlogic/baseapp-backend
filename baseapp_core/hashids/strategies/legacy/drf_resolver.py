from typing import Any, Optional, Type

from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy


class LegacyDRFResolverStrategy(DRFResolverStrategy):
    def resolve_public_id_to_pk(  # NOSONAR
        self, id: str, expected_model: Optional[Type[Any]] = None
    ) -> Optional[int]:
        return id
