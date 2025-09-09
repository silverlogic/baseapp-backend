from baseapp_core.hashids.strategies.interfaces.id_resolver import IdResolverStrategy
from baseapp_core.models import PublicIdMapping, PublicIdMixin


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: PublicIdMixin):
        return instance.public_id

    def resolve_id(self, id, model_cls):
        return PublicIdMapping.get_object_by_public_id(id, model_cls)
