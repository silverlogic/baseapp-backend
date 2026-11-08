import datetime
import decimal
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Generic, Optional, get_args

import django_filters
import strawberry
import strawberry_django
from django import forms
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from graphene_django.forms import GlobalIDFormField, GlobalIDMultipleChoiceField
from graphql_relay import cursor_to_offset, offset_to_cursor
from strawberry import relay
from strawberry.annotation import StrawberryAnnotation
from strawberry.types import Info
from strawberry.types.arguments import StrawberryArgument
from strawberry.types.field import StrawberryField
from strawberry_django.fields.field import StrawberryDjangoConnectionExtension
from strawberry_django.relay import DjangoListConnection


@strawberry.type(name="Edge", description="An edge in a connection.")
class Edge(relay.Edge[relay.NodeType], Generic[relay.NodeType]):
    """Graphene's edge shape: `node` is nullable."""

    node: relay.NodeType | None = strawberry.field(description="The item at the end of the edge")


@strawberry.type(name="Connection", description="A connection to a list of items.")
class CountedConnection(DjangoListConnection[relay.NodeType]):
    """Graphene's `CountedConnection`: `totalCount` (window-optimized when selected) + `edgeCount`."""

    edges: list[Edge[relay.NodeType] | None] = strawberry.field(
        description="Contains the nodes in this connection"
    )

    @strawberry.field
    def edge_count(self) -> int | None:
        return len(self.edges)


# Mirrors graphene_django.forms.converter.convert_form_field (most specific class first).
_FORM_FIELD_TYPES: list[tuple[type, Any]] = [
    (GlobalIDMultipleChoiceField, list[Optional[strawberry.ID]]),
    (GlobalIDFormField, strawberry.ID),
    (forms.ModelMultipleChoiceField, list[Optional[strawberry.ID]]),
    (forms.ModelChoiceField, strawberry.ID),
    (forms.MultipleChoiceField, list[Optional[str]]),
    (forms.UUIDField, uuid.UUID),
    (forms.BooleanField, bool),
    (forms.NullBooleanField, bool),
    (forms.DecimalField, decimal.Decimal),  # Decimal/FloatField subclass IntegerField
    (forms.FloatField, float),
    (forms.IntegerField, int),
    (forms.DateTimeField, datetime.datetime),
    (forms.DateField, datetime.date),
    (forms.TimeField, datetime.time),
]


def _form_field_type(form_field: forms.Field) -> Any:
    for form_class, gql_type in _FORM_FIELD_TYPES:
        if isinstance(form_field, form_class):
            return gql_type
    return str


def _declared_field_type(model: type[models.Model], field_name: str) -> Any:
    """The type the model's registered GraphQL type declares for `field_name`, if explicit."""
    from .registry import type_registry

    strawberry_type = type_registry.get_type_for_model(model)
    if strawberry_type is None:
        return None
    for field in strawberry_type.__strawberry_definition__.fields:
        if field.python_name == field_name and field.type_annotation is not None:
            annotation = field.type_annotation.annotation
            if (
                isinstance(annotation, str)
                or annotation is Any
                or type(annotation).__name__ == "StrawberryAuto"
            ):
                return None
            args = [a for a in get_args(annotation) if a is not type(None)]
            return args[0] if args else annotation
    return None


def _filter_type(filterset_class: type[django_filters.FilterSet], name: str, filter_field) -> Any:
    """Argument type for one filter, following graphene_django.filter.utils."""
    if name not in filterset_class.declared_filters:
        if filter_field.lookup_expr == "isnull":
            return bool
        model = filterset_class._meta.model
        try:
            model_field = model._meta.get_field(filter_field.field_name)
        except FieldDoesNotExist:
            model_field = None
        if model_field is not None:
            if model_field.is_relation or model_field.primary_key:
                return strawberry.ID
            if declared := _declared_field_type(model, model_field.name):
                return declared
            if model_field.choices:
                from .enums import choices_enum

                return choices_enum(model, model_field.name)
            if form_field := model_field.formfield():
                return _form_field_type(form_field)
    gql_type = _form_field_type(filter_field.field)
    if isinstance(filter_field, (django_filters.BaseInFilter, django_filters.BaseRangeFilter)):
        return list[Optional[gql_type]]
    return gql_type


def filterset_arguments(
    filterset_class: type[django_filters.FilterSet], overrides: Mapping[str, Any] | None = None
) -> list[StrawberryArgument]:
    overrides = overrides or {}
    arguments = []
    for name, filter_field in filterset_class.base_filters.items():
        gql_type = overrides.get(name) or _filter_type(filterset_class, name, filter_field)
        arguments.append(
            StrawberryArgument(
                python_name=name,
                graphql_name=None,
                type_annotation=StrawberryAnnotation(Optional[gql_type]),
                description=str(filter_field.label) if filter_field.label else None,
                default=None,
            )
        )
    return arguments


def apply_filterset(
    filterset_class: type[django_filters.FilterSet],
    queryset: models.QuerySet,
    data: Mapping[str, Any],
    info: Info,
) -> models.QuerySet:
    """Filter like DjangoFilterConnectionField: enums become their values, invalid input raises."""
    data = {k: getattr(v, "value", v) for k, v in data.items() if v is not None}
    filterset = filterset_class(data=data, queryset=queryset, request=info.context)
    if not filterset.is_valid():
        # Same exception and payload as DjangoFilterConnectionField.
        raise ValidationError(filterset.form.errors.as_json())
    return filterset.qs


class BaseAppConnectionExtension(StrawberryDjangoConnectionExtension):
    """Strawberry Django connection + Graphene's `offset` argument and FilterSet arguments."""

    def __init__(
        self,
        filterset_class: type[django_filters.FilterSet] | None = None,
        filter_overrides: Mapping[str, Any] | None = None,
        default_first: int | None = None,
        max_results: int | None = None,
    ) -> None:
        super().__init__(max_results=max_results)
        self.filterset_class = filterset_class
        self.filter_overrides = filter_overrides
        self.default_first = default_first
        self.filter_names: set[str] = set()

    def apply(self, field: StrawberryField) -> None:
        super().apply(field)
        extra = [
            StrawberryArgument(
                python_name="offset",
                graphql_name=None,
                type_annotation=StrawberryAnnotation(Optional[int]),
                default=None,
            )
        ]
        if self.filterset_class is not None:
            filter_args = filterset_arguments(self.filterset_class, self.filter_overrides)
            self.filter_names = {a.python_name for a in filter_args}
            extra.extend(filter_args)
        existing = {a.python_name for a in field.arguments}
        field.arguments = [*field.arguments, *(a for a in extra if a.python_name not in existing)]
        if self.default_first is not None:
            for argument in field.arguments:
                if argument.python_name == "first":
                    argument.default = self.default_first

    def resolve(
        self,
        next_: Callable,
        source: Any,
        info: Info,
        *,
        offset: int | None = None,
        **kwargs: Any,
    ) -> Any:
        filters = {k: kwargs.pop(k) for k in list(kwargs) if k in self.filter_names}
        if offset:
            if kwargs.get("before") is not None:
                # Same exception and text as graphene-django.
                raise ValueError(
                    f"You can't provide a `before` value at the same time as an `offset` value "
                    f"to properly paginate the `{info.field_name}` connection."
                )
            if after := kwargs.get("after"):
                offset += cursor_to_offset(after) + 1
            kwargs["after"] = offset_to_cursor(offset - 1)

        if self.filterset_class is None or not any(v is not None for v in filters.values()):
            return super().resolve(next_, source, info, **kwargs)

        def filtered_next(source: Any, info: Info, **resolver_kwargs: Any) -> Any:
            nodes = next_(source, info, **resolver_kwargs)
            if isinstance(nodes, models.Manager):
                nodes = nodes.all()
            return apply_filterset(self.filterset_class, nodes, filters, info)

        return super().resolve(filtered_next, source, info, **kwargs)


def connection(
    graphql_type: Any = None,
    *,
    filterset_class: type[django_filters.FilterSet] | None = None,
    filter_overrides: Mapping[str, Any] | None = None,
    default_first: int | None = None,
    max_results: int | None = None,
    resolver: Callable | None = None,
    **kwargs: Any,
) -> Any:
    """`strawberry_django.connection` with Graphene's connection arguments.

    Use `CountedConnection[T] | None` for Graphene's explicit connection fields and
    `CountedConnection[T]` for connections Graphene derived from model relations.
    """
    field = strawberry_django.connection(graphql_type, **kwargs)
    field.extensions = [
        e for e in field.extensions if not isinstance(e, StrawberryDjangoConnectionExtension)
    ] + [
        BaseAppConnectionExtension(
            filterset_class=filterset_class,
            filter_overrides=filter_overrides,
            default_first=default_first,
            max_results=max_results,
        )
    ]
    return field(resolver) if resolver else field
