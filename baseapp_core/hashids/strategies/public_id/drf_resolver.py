from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class PublicIdDRFResolverStrategy:
    def __init__(self, id_resolver: IdResolverStrategy):
        self.id_resolver = id_resolver

    def resolve_public_id_to_pk(self, id, expected_model=None):
        return self.id_resolver.resolve_id(id, resolve_query=False)[1]
