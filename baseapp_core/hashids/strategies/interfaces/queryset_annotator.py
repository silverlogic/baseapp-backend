from typing import Any, TypeVar

from django.db.models import Model, QuerySet

TModel = TypeVar("TModel", bound=Model)


class QuerysetAnnotatorStrategy:
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        raise NotImplementedError

    def get_annotations(self, model_cls: TModel) -> dict[str, Any]:
        raise NotImplementedError
