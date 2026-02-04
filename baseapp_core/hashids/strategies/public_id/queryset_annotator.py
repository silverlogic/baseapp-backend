from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import OuterRef, QuerySet, Subquery
from query_optimizer.typing import TModel

from baseapp_core.hashids.strategies.interfaces import QuerysetAnnotatorStrategy
from baseapp_core.models import DocumentId


class PublicIdQuerysetAnnotatorStrategy(QuerysetAnnotatorStrategy):
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        annotations = self.get_annotations(model_cls)
        queryset = queryset.annotate(**annotations)
        return queryset

    def get_annotations(self, model_cls: TModel) -> dict[str, Any]:
        return {
            "mapped_public_id": Subquery(
                DocumentId.objects.filter(
                    content_type=ContentType.objects.get_for_model(model_cls),
                    object_id=OuterRef("pk"),
                ).values("public_id")
            )
        }
