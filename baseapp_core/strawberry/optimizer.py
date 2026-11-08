"""Optimizer behaviour aligned with graphene-django-query-optimizer.

query_optimizer joins forward to-one relations with `select_related` and does not apply the
related type's `get_queryset` to them; Strawberry Django switches such a relation to a separate
`Prefetch` (one more query per relation) whenever the related type defines `get_queryset`.
Types here use `get_queryset` for root and list visibility, so keep to-one traversals joined.
"""

from typing import Any

from strawberry_django import optimizer as _optimizer
from strawberry_django.utils.inspect import is_inheritance_manager, is_polymorphic_model


def _must_use_prefetch_related(config: Any, field: Any, model_field: Any) -> bool:
    related_model = model_field.related_model
    manager = (
        related_model._default_manager
        if config.prefetch_custom_queryset
        else related_model._base_manager
    )
    return is_polymorphic_model(related_model) or is_inheritance_manager(manager)


def install() -> None:
    _optimizer._must_use_prefetch_related = _must_use_prefetch_related
