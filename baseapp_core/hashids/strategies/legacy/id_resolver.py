from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy


class LegacyIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance):
        return instance.pk

    def resolve_id(self, id, *, model_cls=None, **kwargs):
        if not model_cls:
            raise ValueError("model_cls is required")
        return model_cls.objects.get(pk=id)
