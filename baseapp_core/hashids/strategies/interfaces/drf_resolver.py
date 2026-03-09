from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class DRFResolverStrategy:
    def __init__(self, id_resolver: IdResolverStrategy):
        self.id_resolver = id_resolver

    def resolve_public_id_to_pk(self, public_id):
        raise NotImplementedError
