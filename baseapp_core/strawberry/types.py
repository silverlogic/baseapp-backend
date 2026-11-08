import dataclasses
import datetime
from collections.abc import Callable
from typing import Any, TypeVar

import strawberry_django
from django.db.models import Model
from model_utils.fields import AutoCreatedField, AutoLastModifiedField
from strawberry.types import Info
from strawberry_django.fields.types import field_type_map
from strawberry_django.optimizer import OptimizerStore

from .registry import type_registry

_T = TypeVar("_T")

# graphene-django converts by `isinstance`, strawberry-django by exact class: register subclasses.
field_type_map.update(
    {AutoCreatedField: datetime.datetime, AutoLastModifiedField: datetime.datetime}
)


@dataclasses.dataclass
class PublicIdOptimizerStore(OptimizerStore):
    """Optimizer hint on `Node.id`: annotates `mapped_public_id` only when `id` is selected.

    Strawberry equivalent of `baseapp_core.graphql.DjangoObjectType.pre_optimization_hook`, applied
    at every nesting level. The model is read from the type owning the field at query time, because
    the `id` field object is shared by every type implementing `Node`.
    """

    def __bool__(self) -> bool:
        return True

    def with_resolved_callables(self, info: Info) -> OptimizerStore:
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        from .relay import model_from_info

        model = model_from_info(info)
        if model is None:
            return OptimizerStore()
        strategy = get_hashids_strategy_from_instance_or_cls(model)
        return OptimizerStore(annotate=strategy.queryset_annotator.get_annotations(model))

    def with_prefix(self, prefix: str, *, info: Info) -> OptimizerStore:
        return self.with_resolved_callables(info).with_prefix(prefix, info=info)


def django_type(
    model: type[Model],
    *,
    filterset_class: Any = None,
    relations: str | tuple[str, ...] | list[str] = (),
    exclude_relations: tuple[str, ...] | list[str] = (),
    **kwargs: Any,
) -> Callable[[_T], _T]:
    """`strawberry_django.type` with BaseApp defaults.

    - The GraphQL name is the model name (as Graphene's `DjangoObjectType` did).
    - The type is registered for `type_for_model(model)` lookups; later registrations override.
    - `filterset_class` gives relation-derived connections to this type their filter arguments.
    - `relations="__all__"` (or a tuple of names) exposes model relations to other registered
      types when the schema is built, like graphene-django's `fields = "__all__"`.
    """

    def wrapper(cls: _T) -> _T:
        kwargs.setdefault("name", model.__name__)
        processed = strawberry_django.type(model, **kwargs)(cls)
        type_registry.register(
            model,
            processed,
            filterset_class=filterset_class,
            relations=relations if relations == "__all__" else tuple(relations),
            exclude=tuple(exclude_relations),
        )
        return processed

    return wrapper
