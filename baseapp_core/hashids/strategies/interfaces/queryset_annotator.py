from typing import Any

from django.db.models import QuerySet
from query_optimizer.typing import TModel


class QuerysetAnnotatorStrategy:
    def annotate(self, model_cls: TModel, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        raise NotImplementedError

    def get_annotations(
        self, model_cls: TModel, field: str = "pk", alias: str = "mapped_public_id"
    ) -> dict[str, Any]:
        """Annotations that load the public id of `model_cls` rows.

        `field` is the path, on the annotated queryset, to the `model_cls` pk: "pk" for the
        queryset's own rows, or a foreign key path such as "author" or "post__author" for related
        rows. `alias` is the name of the annotation.
        """
        raise NotImplementedError
