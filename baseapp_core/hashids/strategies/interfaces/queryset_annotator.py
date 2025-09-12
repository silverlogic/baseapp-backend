from django.db.models import QuerySet
from query_optimizer.typing import TModel


class QuerysetAnnotatorStrategy:
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        raise NotImplementedError
