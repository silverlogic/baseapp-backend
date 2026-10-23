import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from baseapp_core.hashids.strategies.interfaces import IdResolverStrategy
from baseapp_core.hashids.utils import is_model_subclass
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
        self, id, *, resolve_query: bool = True, model_cls=None, **_kwargs
    ) -> "Model | tuple[ContentType, int] | None":
        """
        When resolve_query == True, return the instance of the model, or None when the id is
        unknown or, if `model_cls` is given, belongs to another model.
        When resolve_query == False, return (content_type, object_id).
        """
        if not resolve_query:
            return DocumentId.get_content_type_and_id_by_public_id(id)
        if model_cls is None:
            return DocumentId.get_object_by_public_id(id)

        resolved = DocumentId.get_content_type_and_id_by_public_id(id)
        if resolved is None:
            return None
        content_type, object_id = resolved
        if not is_model_subclass(content_type.model_class(), model_cls):
            return None
        try:
            return content_type.get_object_for_this_type(pk=object_id)
        except ObjectDoesNotExist:
            return None
