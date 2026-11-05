from typing import Any, Optional, Type

from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy
from baseapp_core.hashids.utils import is_model_subclass


class PublicIdDRFResolverStrategy(DRFResolverStrategy):
    def resolve_public_id_to_pk(
        self, id: str, expected_model: Optional[Type[Any]] = None
    ) -> Optional[int]:
        resolved = self.id_resolver.resolve_id(id, resolve_query=False)
        if resolved is None:
            return None

        content_type, object_id = resolved
        if expected_model is not None and not is_model_subclass(
            content_type.model_class(), expected_model
        ):
            raise self.NoInstanceFound(id)
        return object_id
