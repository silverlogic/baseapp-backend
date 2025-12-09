from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy
from baseapp_core.models import DocumentId, DocumentIdMixin


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: DocumentIdMixin):
        if hasattr(instance, "mapped_public_id"):
            return instance.mapped_public_id
        return DocumentId.get_public_id_from_object(instance)

    def resolve_id(self, id, *, resolve_query: bool = True, **_kwargs):
        """
        When resolve_query == True, return the instance of the model.
        When resolve_query == False, return (content_type, object_id).
        """
        if resolve_query:
            return DocumentId.get_object_by_public_id(id)
        else:
            return DocumentId.get_content_type_and_id_by_public_id(id)
