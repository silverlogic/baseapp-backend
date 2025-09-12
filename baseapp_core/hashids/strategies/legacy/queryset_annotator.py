from django.db.models import QuerySet
from query_optimizer.typing import TModel

from baseapp_core.hashids.strategies.interfaces import QuerysetAnnotatorStrategy


class LegacyQuerysetAnnotatorStrategy(QuerysetAnnotatorStrategy):
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        return queryset
