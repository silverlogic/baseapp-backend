"""Expose model relations the way graphene-django's `fields = "__all__"` does.

Types opt in with `django_type(Model, relations="__all__" | ("name", ...))`. Right before the schema
is built, each registered type gets a field for every selected relation whose related model also
has a registered type, so packages never declare fields for each other's models:

- forward FK / one-to-one -> `Related` (non-null when the column is NOT NULL)
- reverse one-to-one      -> `Related` (nullable)
- reverse FK / many-to-many -> `RelatedConnection!` with the related type's FilterSet arguments
  (a non-null `[Related!]!` list when the related type is not a `Node`)
"""

from typing import Any, Optional

import strawberry_django
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.db.models import Model

from .connections import CountedConnection, connection
from .registry import TypeEntry, type_registry


def _field_name(model_field: Any) -> str:
    if model_field.auto_created and not model_field.concrete:
        return model_field.get_accessor_name()
    return model_field.name


def _relation_field(model_field: Any, related_type: type, related: TypeEntry) -> Any:
    from .relay import Node

    if model_field.one_to_many or model_field.many_to_many:
        if issubclass(related_type, Node):
            return connection(
                CountedConnection[related_type], filterset_class=related.filterset_class
            )
        return strawberry_django.field(graphql_type=list[related_type])
    if model_field.one_to_one and model_field.auto_created:
        return strawberry_django.field(graphql_type=Optional[related_type])
    nullable = getattr(model_field, "null", True)
    return strawberry_django.field(
        graphql_type=Optional[related_type] if nullable else related_type
    )


def _selected(entry: TypeEntry, name: str) -> bool:
    if name in entry.exclude:
        return False
    return entry.relations == "__all__" or name in entry.relations


def expose_relations(model: type[Model], entry: TypeEntry) -> None:
    definition = entry.strawberry_type.__strawberry_definition__
    taken = {f.python_name for f in definition.fields} | {f.graphql_name for f in definition.fields}
    for model_field in model._meta.get_fields(include_hidden=False):
        if not model_field.is_relation or isinstance(
            model_field, (GenericForeignKey, GenericRelation)
        ):
            continue
        name = _field_name(model_field)
        if not name or name.endswith("+") or name in taken or not _selected(entry, name):
            continue
        related = type_registry.get_entry(model_field.related_model)
        if related is None:
            continue
        field = _relation_field(model_field, related.strawberry_type, related)
        field.python_name = name
        field.django_name = name
        field.origin = entry.strawberry_type
        definition.fields.append(field)
        taken.add(name)


def expose_all_relations() -> None:
    for model, entry in type_registry.entries().items():
        if entry.relations and type_registry.get_entry(model) is entry:
            expose_relations(model, entry)
