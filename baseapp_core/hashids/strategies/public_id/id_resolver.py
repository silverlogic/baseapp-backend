from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy
from baseapp_core.models import PublicIdMapping, PublicIdMixin


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: PublicIdMixin):
        if hasattr(instance, "mapped_public_id"):
            return instance.mapped_public_id
        return PublicIdMapping.get_public_id(instance)

    def resolve_id(self, id, resolve_query=True, **kwargs):
        """
        When resolve_type == True, it will return the instance of the model.
        When resolve_type == False, it will return the content_type and object_id.
        """
        if resolve_query:
            return PublicIdMapping.get_object_by_public_id(id)
        else:
            return PublicIdMapping.get_content_type_and_id(id)
