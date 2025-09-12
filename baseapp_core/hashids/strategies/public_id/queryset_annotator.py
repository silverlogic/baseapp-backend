from django.contrib.contenttypes.models import ContentType
from django.db.models import OuterRef, QuerySet, Subquery
from query_optimizer.typing import TModel

from baseapp_core.hashids.models import PublicIdMapping
from baseapp_core.hashids.strategies.interfaces import QuerysetAnnotatorStrategy


class PublicIdQuerysetAnnotatorStrategy(QuerysetAnnotatorStrategy):
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        content_type = ContentType.objects.get_for_model(model_cls)

        public_id_subquery = PublicIdMapping.objects.filter(
            content_type=content_type, object_id=OuterRef("pk")
        ).values("public_id")

        queryset = queryset.annotate(mapped_public_id=Subquery(public_id_subquery))
        return queryset
