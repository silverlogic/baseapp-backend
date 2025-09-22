from baseapp_core.hashids.models import PublicIdMapping, PublicIdMixin
from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: PublicIdMixin):
        if hasattr(instance, "mapped_public_id"):
            return instance.mapped_public_id
        return PublicIdMapping.get_public_id(instance)

    def resolve_id(self, id, *, resolve_query: bool = True, **_kwargs):
        """
        When resolve_query == True, return the instance of the model.
        When resolve_query == False, return (content_type, object_id).
        """
        if resolve_query:
            return PublicIdMapping.get_object_by_public_id(id)
        else:
            return PublicIdMapping.get_content_type_and_id(id)
