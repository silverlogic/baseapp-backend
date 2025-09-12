from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy


class LegacyIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance):
        return instance.pk

    def resolve_id(self, id, model_cls):
        return model_cls.objects.get(pk=id)
