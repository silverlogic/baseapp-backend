from typing import Any

from django.db.models import QuerySet

from baseapp_core.hashids.strategies.interfaces import QuerysetAnnotatorStrategy
from baseapp_core.hashids.strategies.interfaces.queryset_annotator import TModel


class LegacyQuerysetAnnotatorStrategy(QuerysetAnnotatorStrategy):
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        return queryset

    def get_annotations(self, model_cls: TModel) -> dict[str, Any]:
        return {}
