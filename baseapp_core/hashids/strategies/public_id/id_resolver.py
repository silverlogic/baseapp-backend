import uuid
from typing import TYPE_CHECKING

from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy
from baseapp_core.models import DocumentId, DocumentIdMixin

if TYPE_CHECKING:
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Model


class PublicIdResolverStrategy(IdResolverStrategy):
    def get_id_from_instance(self, instance: DocumentIdMixin) -> uuid.UUID | None:
        if hasattr(instance, "mapped_public_id"):
            return instance.mapped_public_id
        return DocumentId.get_public_id_from_object(instance)

    def resolve_id(
        self, id, *, resolve_query: bool = True, **_kwargs
    ) -> "Model | tuple[ContentType, int] | None":
        """
        When resolve_query == True, return the instance of the model.
        When resolve_query == False, return (content_type, object_id).
        """
        if resolve_query:
            return DocumentId.get_object_by_public_id(id)
        else:
            return DocumentId.get_content_type_and_id_by_public_id(id)
