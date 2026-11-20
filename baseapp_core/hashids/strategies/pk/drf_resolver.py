from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy
from baseapp_core.hashids.utils import is_model_subclass


class PkDRFResolverStrategy(DRFResolverStrategy):
    def resolve_public_id_to_pk(self, public_id, expected_model=None) -> int:
        content_type, object_id = self.id_resolver.resolve_id(public_id, resolve_query=False)
        model_class = content_type.model_class()
        if expected_model and not is_model_subclass(model_class, expected_model):
            raise self.NoInstanceFound(public_id)
        return object_id
