from django.utils.translation import gettext_lazy as _
from graphql import (
    FieldNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLSchema,
    InlineFragmentNode,
    SelectionSetNode,
    get_named_type,
    is_abstract_type,
)
from strawberry.relay import Connection, Edge
from strawberry.types import Info
from strawberry_django.utils.typing import get_django_definition


def _is_model_type(schema, type_name: str) -> bool | None:
    """True for model types, False for connection/edge wrappers, None for anything else."""
    definition = schema.get_type_by_name(type_name)
    origin = getattr(definition, "origin", None)
    if origin is None:
        return None
    if isinstance(origin, type) and issubclass(origin, (Connection, Edge)):
        return False
    return True if get_django_definition(origin) else None


def _complexity(
    info: Info, gql_schema: GraphQLSchema, parent, selection_set: SelectionSetNode | None
) -> int:
    if selection_set is None:
        return 0
    total = 0
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            field = parent.fields.get(selection.name.value) if hasattr(parent, "fields") else None
            if field is None:
                continue
            named = get_named_type(field.type)
            kind = _is_model_type(info.schema, named.name)
            if kind is None and not is_abstract_type(named):
                continue
            total += 1 if kind else 0
            total += _complexity(info, gql_schema, named, selection.selection_set)
        elif isinstance(selection, InlineFragmentNode):
            target = (
                gql_schema.get_type(selection.type_condition.name.value)
                if selection.type_condition
                else parent
            )
            total += _complexity(info, gql_schema, target, selection.selection_set)
        elif isinstance(selection, FragmentSpreadNode):
            fragment = info._raw_info.fragments[selection.name.value]
            target = gql_schema.get_type(fragment.type_condition.name.value)
            total += _complexity(info, gql_schema, target, fragment.selection_set)
    return total


def check_max_complexity(info: Info, max_complexity: int) -> None:
    """query_optimizer's `max_complexity`: count related fields selected below the current field.

    Raises before any SQL runs.
    """
    raw = info._raw_info
    gql_schema = raw.schema
    named = get_named_type(raw.return_type)
    complexity = sum(
        _complexity(info, gql_schema, named, node.selection_set) for node in raw.field_nodes
    )
    if complexity > max_complexity:
        raise GraphQLError(
            _("Query complexity exceeds the maximum allowed of %(max)s") % {"max": max_complexity}
        )
