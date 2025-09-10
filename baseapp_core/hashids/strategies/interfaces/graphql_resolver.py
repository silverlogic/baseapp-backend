from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy


class GraphQLResolverStrategy:
    def __init__(self, id_resolver: IdResolverStrategy):
        self.id_resolver = id_resolver

    def to_global_id(self, type_, id):
        raise NotImplementedError

    def get_node_from_global_id(self, info, global_id, only_type=None):
        raise NotImplementedError

    def get_pk_from_global_id(self, global_id):
        raise NotImplementedError
