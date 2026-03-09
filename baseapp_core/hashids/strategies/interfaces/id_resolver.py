class IdResolverStrategy:
    def get_id_from_instance(self, instance):
        raise NotImplementedError

    def resolve_id(self, id, **kwargs):
        raise NotImplementedError
