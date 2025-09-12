from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy
from baseapp_core.models import PublicIdMapping, PublicIdMixin


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: PublicIdMixin):
        if hasattr(instance, "mapped_public_id"):
            return instance.mapped_public_id
        public_id, created = PublicIdMapping.get_or_create_public_id(instance)
        return public_id

    def resolve_id(self, id, model_cls):
        return PublicIdMapping.get_object_by_public_id(id, model_cls)
