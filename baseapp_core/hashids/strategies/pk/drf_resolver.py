from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy
from baseapp_core.hashids.strategies.public_id.id_resolver import IdResolverStrategy


class PkDRFResolverStrategy(DRFResolverStrategy):
    def __init__(self, id_resolver: IdResolverStrategy):
        self.id_resolver = id_resolver

    def resolve_public_id_to_pk(self, public_id, expected_model=None):
        content_type, object_id = self.id_resolver.resolve_id(public_id, resolve_query=False)
        model_class = content_type.model_class()
        if expected_model and not issubclass(model_class, expected_model):
            raise self.NoInstanceFound(public_id)
        return object_id
